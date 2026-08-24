/**
 * 채팅 게이트웨이.
 *
 * WebSocket 연결을 받고, 인입 메시지를 Valkey Pub/Sub 으로 흘려 모든 파드가
 * 자기 로컬 커넥션에만 브로드캐스트한다. 이것이 팬아웃 구조의 전부다
 * (contracts.md 3.7).
 *
 * 파드 간 트래픽은 인입량 × 파드 수라 Peak 에서도 초당 수백 건이다. Kafka 나
 * Streams 가 낄 자리가 없다.
 *
 * 무상태다. 커넥션 목록만 프로세스 메모리에 있고, 그것은 그 파드의 소유물이지
 * 공유 상태가 아니다. 채팅 이력은 저장하지 않는다 — 재연결하면 스냅샷을 다시
 * 받고 흘러간 채팅은 흘러간 것으로 본다 (3.6).
 */

import { timingSafeEqual } from 'node:crypto';
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';

import Redis from 'ioredis';
import { WebSocket, WebSocketServer } from 'ws';

import { config } from './config.js';
import { createChatIngressHandler, type ChatIngressConnection } from './chat-ingress.js';
import { emitChatSend, hashUserKey } from './events.js';
import { emitChatSignal } from './chat-signal.js';

// ── Valkey ────────────────────────────────────────────────────
// 구독 전용 연결과 명령용 연결을 나눈다. 구독 모드에 들어간 연결은 다른
// 명령을 받지 못한다.
const redisOptions = {
  host: config.valkeyHost,
  port: config.valkeyPort,
  ...(config.valkeyTls ? { tls: {} } : {}),
};

const pub = new Redis(redisOptions);
const sub = new Redis(redisOptions);

// ── 연결 관리 ─────────────────────────────────────────────────

type Outgoing = { t: string; item: unknown };

type Conn = ChatIngressConnection & {
  socket: WebSocket;
  // 200ms 창에 쌓이는 것들. 창이 비면 프레임을 보내지 않는다.
  pending: Outgoing[];
};

const conns = new Set<Conn>();

/** 이 파드가 구독 중인 방송. 방마다 한 번만 subscribe 한다. */
const subscribed = new Set<string>();

function channel(broadcastId: string): string {
  return `chat:${broadcastId}`;
}

// ── 브로드캐스트 ──────────────────────────────────────────────
// 다른 파드가 발행한 것을 받아 자기 로컬 커넥션의 큐에만 넣는다.
// 여기서 이벤트를 발행하면 안 된다 — 전달 횟수만큼 발행되어 파드가 죽는다.
sub.on('message', (ch, raw) => {
  const broadcastId = ch.slice('chat:'.length);
  let item: unknown;
  try {
    item = JSON.parse(raw);
  } catch {
    return;
  }
  for (const conn of conns) {
    if (conn.broadcastId === broadcastId) conn.pending.push({ t: 'chat', item });
  }
});

/**
 * 200ms 틱. 창에 쌓인 것을 종류별로 묶어 한 프레임으로 보낸다.
 *
 * 프레임 페이로드는 단건이어도 항상 배열이다. 단건 포맷으로 출발하면 배치를
 * 도입할 때 서버·클라이언트·테스트를 전부 고쳐야 한다 (contracts.md 3.2).
 */
setInterval(() => {
  for (const conn of conns) {
    if (conn.pending.length === 0) continue;

    // 초과분은 버린다. 스파이크 방어이지 상시 최적화가 아니다.
    const batch = conn.pending.splice(0, config.maxPerTick);
    conn.pending.length = 0;

    const byType = new Map<string, unknown[]>();
    for (const { t, item } of batch) {
      const list = byType.get(t) ?? [];
      list.push(item);
      byType.set(t, list);
    }

    if (conn.socket.readyState !== WebSocket.OPEN) continue;
    for (const [t, items] of byType) {
      conn.socket.send(JSON.stringify({ t, items }));
    }
  }
}, config.tickMs);

// ── 인입 처리 ─────────────────────────────────────────────────

async function overRateLimit(conn: ChatIngressConnection): Promise<boolean> {
  const key = `chat:rate:${conn.broadcastId}:${conn.userKey}`;
  const count = await pub.incr(key);
  // 첫 증가에만 만료를 건다. 매번 걸면 창이 계속 밀려 제한이 무의미해진다.
  if (count === 1) await pub.expire(key, 60);
  return count > config.rateLimitPerMinute;
}

/**
 * S1(docs/scenario-experiment.md 0.5) 조치 — 채널 총량 제한.
 *
 * `cfg:channel_limit:{broadcastId}` 가 그 방송의 노브다. 키가 없으면(평시)
 * 총량 제한을 아예 안 건다 — Agent 가 인시던트 중에만 이 키를 SET 한다.
 * 카운터는 overRateLimit 과 같은 Valkey INCR+EXPIRE 패턴이고, 파드 로컬로
 * 만들지 않는다 — chat-gateway 가 여러 replicas 라 로컬 카운터면 실제
 * 상한이 파드 수만큼 배가된다(4.1).
 */
async function overChannelLimit(conn: ChatIngressConnection): Promise<boolean> {
  const limit = await pub.get(`cfg:channel_limit:${conn.broadcastId}`);
  if (limit === null) return false;

  const key = `chat:total:${conn.broadcastId}`;
  const count = await pub.incr(key);
  if (count === 1) await pub.expire(key, 60);
  return count > Number(limit);
}

const handleChat = createChatIngressHandler({
  maxMessageLength: config.maxMessageLength,
  overRateLimit,
  overChannelLimit,
  emitChatSend,
  emitChatSignal,
  publishFanout: (conn, msg) =>
    pub.publish(
      channel(conn.broadcastId),
      JSON.stringify({ user: conn.userKey, nick: conn.userKey.slice(0, 8), msg, ts: Date.now() }),
    ),
});

// ── 조치 실행 — S1 채널 총량 노브 ────────────────────────────────
//
// S1(docs/scenario-experiment.md 0.5) 조치와 원복이 둘 다 이 라우트다 —
// `action: "set"`(조치) / `"clear"`(원복)로만 갈린다. `cfg:channel_limit:
// {broadcast_id}` 를 chat-gateway 가 이미 들고 있는 `pub` 커넥션으로 직접
// SET/DEL 한다 — 별도 Lambda 를 두지 않는다. chat-gateway 는 이미 Valkey에
// TLS 로 붙어 있고 이미 일반 HTTP 서버를 갖고 있어서(이 아래 healthz),
// 새 인프라 없이 라우트 하나만 추가하면 된다. ALB 인그레스가 `/ws` 를
// prefix 로 이 서비스에 이미 매핑해 뒀으므로(frontend-ingress.yaml)
// `/ws/admin/*` 도 별도 설정 없이 바로 도달한다.

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', (chunk: Buffer) => {
      data += chunk;
    });
    req.on('end', () => resolve(data));
    req.on('error', reject);
  });
}

function authorized(req: IncomingMessage): boolean {
  const provided = req.headers['x-admin-key'];
  const expected = config.channelLimitAdminKey;
  if (typeof provided !== 'string' || expected.length === 0) return false;
  // 길이가 다르면 timingSafeEqual 이 예외를 던진다 — 길이부터 맞춰야 한다.
  if (provided.length !== expected.length) return false;
  return timingSafeEqual(Buffer.from(provided), Buffer.from(expected));
}

async function handleChannelLimitAdmin(req: IncomingMessage, res: ServerResponse): Promise<void> {
  if (!authorized(req)) {
    res.writeHead(403);
    res.end();
    return;
  }

  let body: { broadcast_id?: unknown; action?: unknown; limit?: unknown };
  try {
    body = JSON.parse(await readBody(req));
  } catch {
    res.writeHead(400);
    res.end();
    return;
  }

  const broadcastId = body.broadcast_id;
  const action = body.action;
  const limit = body.limit;

  if (typeof broadcastId !== 'string' || !broadcastId || (action !== 'set' && action !== 'clear')) {
    res.writeHead(400);
    res.end();
    return;
  }
  if (action === 'set' && (!Number.isInteger(limit) || (limit as number) <= 0)) {
    res.writeHead(400);
    res.end();
    return;
  }

  const key = `cfg:channel_limit:${broadcastId}`;
  // Precheck 재확인 — 지금 값을 다시 읽어 응답에 같이 실어 보낸다.
  const previous = await pub.get(key);

  if (action === 'set') {
    await pub.set(key, String(limit));
  } else {
    await pub.del(key);
  }

  res.writeHead(200, { 'content-type': 'application/json' });
  res.end(
    JSON.stringify({
      broadcast_id: broadcastId,
      action,
      previous_limit: previous !== null ? Number(previous) : null,
      limit: action === 'set' ? limit : null,
    }),
  );
}

// ── 서버 ──────────────────────────────────────────────────────

const server = createServer((req, res) => {
  // ALB 헬스체크용. WebSocket 이 아니라 일반 HTTP 로 답한다.
  if (req.url === '/healthz') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end('{"status":"ok"}');
    return;
  }
  if (req.url === '/ws/admin/channel-limit' && req.method === 'POST') {
    void handleChannelLimitAdmin(req, res);
    return;
  }
  res.writeHead(404);
  res.end();
});

const wss = new WebSocketServer({ noServer: true });

server.on('upgrade', (req, socket, head) => {
  const url = new URL(req.url ?? '', 'http://localhost');
  if (url.pathname !== '/ws') {
    socket.destroy();
    return;
  }
  const broadcastId = url.searchParams.get('broadcast_id');
  if (!broadcastId) {
    socket.destroy();
    return;
  }

  // 인증 토큰은 쿼리스트링이 아니라 서브프로토콜로 받는다.
  // 쿼리스트링은 ALB 접근 로그에 남는다 (contracts.md 3.1).
  const token = (req.headers['sec-websocket-protocol'] as string | undefined)?.split(',')[0]?.trim();

  wss.handleUpgrade(req, socket, head, (ws) => {
    void open(ws, broadcastId, token ?? '');
  });
});

async function open(socket: WebSocket, broadcastId: string, token: string): Promise<void> {
  // 원본 세션 키를 채팅 프레임·Valkey 키·이벤트에 남기지 않는다. API의 이벤트
  // SDK와 같은 HMAC 규칙을 써야 서비스 사이에서 같은 사용자를 조인할 수 있다.
  const rawUserKey = token || `anon-${Math.random().toString(36).slice(2, 10)}`;
  const userKey = hashUserKey(rawUserKey);
  const conn: Conn = { socket, broadcastId, userKey, pending: [], lastHash: null };
  conns.add(conn);

  if (!subscribed.has(broadcastId)) {
    subscribed.add(broadcastId);
    await sub.subscribe(channel(broadcastId));
  }

  socket.on('message', (raw) => {
    let msg: { t?: string; msg?: string };
    try {
      msg = JSON.parse(raw.toString());
    } catch {
      return;
    }
    // 클라이언트 → 서버는 배열이 아니다. 한 번에 하나만 보낸다 (3.4).
    if (msg.t === 'ping') return;
    if (msg.t === 'chat' && typeof msg.msg === 'string') void handleChat(conn, msg.msg);
  });

  socket.on('close', () => conns.delete(conn));
  socket.on('error', () => conns.delete(conn));
}

server.listen(config.port, () => {
  console.log(`chat-gateway listening on ${config.port}`);
});

// ── 종료 ──────────────────────────────────────────────────────
// close frame 을 먼저 보내고 기다린다. 그냥 끊으면 클라이언트가 비정상 종료로
// 보고 즉시 재연결하는데, 스케일다운이면 그 순간 남은 파드가 폭풍을 맞는다.
// 클라이언트 쪽 지터 백오프와 짝을 이룬다 (architecture.md 9.4-2, R-01).
let shuttingDown = false;

function shutdown(signal: string): void {
  if (shuttingDown) return;
  shuttingDown = true;
  console.log(`${signal} 수신. close frame 을 보내고 ${config.drainMs}ms 기다린다.`);

  for (const conn of conns) {
    if (conn.socket.readyState === WebSocket.OPEN) conn.socket.close(1001, 'going away');
  }
  server.close();

  setTimeout(() => {
    void pub.quit();
    void sub.quit();
    process.exit(0);
  }, config.drainMs);
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
