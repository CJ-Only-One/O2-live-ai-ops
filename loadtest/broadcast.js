// 방송 부하 — 시청자 N명 동시 접속 + 채팅 고정 발화율.
//
//   ALB=k8s-o2dev-frontend-0af27d967f-1008618203.ap-northeast-2.elb.amazonaws.com
//   k6 run -e WS_URL=ws://$ALB loadtest/broadcast.js
//
// 계단을 밟아 올린다. 4,000 을 처음부터 던지면 어디서 꺾였는지 모른다.
//   WS_URL=ws://$ALB loadtest/run.sh broadcast.js VIEWERS 500 1000 2000 4000
//
// ── 두 축을 따로 재라 ────────────────────────────────────────────────────
// 프레임 수는 **시청자 수**에만 비례하고(틱마다 연결당 한 프레임),
// 바이트 수는 **발화율**에도 비례한다. 확대 비율이 달라서 한 축만 늘려
// 재고 곱셈으로 외삽하면 틀린다. 두 번 돌려라.
//
//   시청자 축   VIEWERS 500/1000/2000/4000,  CHAT_RPS 고정
//   발화율 축   VIEWERS 4000 고정,           CHAT_RPS 2/10/20/250
//
// 마지막 250 이 `CHAT_MAX_PER_TICK`(기본 50) 방어를 건드리는 유일한 값이다.
// 10 msg/s 면 틱당 2 건이라 상한 근처도 못 간다.
//
// ── 이 수치가 만드는 부하 (VIEWERS=4000, CHAT_RPS=10) ────────────────────
// 인입 10 msg/s 는 아무것도 아니다. **팬아웃이 인입의 수천 배다.**
//   틱 200ms = 초당 5회 (config.ts `tickMs`)
//   4,000 연결 × 5틱 = 초당 약 20,000 회 send + 20,000 회 JSON.stringify
//
// main.ts 의 틱 루프는 연결마다 `JSON.stringify` 를 새로 부른다. 같은 방송의
// 모든 연결은 배치 내용이 **동일한데도** 그렇다. 여기가 먼저 꺾일 것으로
// 본다 — 예측이지 측정이 아니다. 맞으면 방송당 한 번만 만들어 재사용한다.
//
// ── Peak 대비 몇 분의 일인가 ─────────────────────────────────────────────
// 설계 Peak 는 40,000명 × 20 msg/s = 초당 800,000 전달이다 (architecture 9.4).
// VIEWERS=4000 · CHAT_RPS=10 은 초당 40,000 전달이라 **1/10 이 아니라 1/20**
// 이다. 시청자만 1/10 이고 발화율이 1/2 이기 때문이다. 깔끔한 1/10 을
// 원하면 CHAT_RPS=20 으로 둔다. 어느 쪽이든 표에 조건을 같이 적어라.
//
// ── 돌리기 전에 ──────────────────────────────────────────────────────────
// 1. Datadog 모니터를 Downtime 으로 재운다. `@webhook-dify` 가 붙은 모니터가
//    6개고 이 테스트가 그중 넷을 때린다 — 특히 "채팅 인입 급증"은 이
//    스크립트의 목적 그 자체다. 안 재우면 에이전트가 깨어나서 측정 중에
//    뭔가 바꾼다.
// 2. idle 영점 기록 — run.sh 가 자동으로 한다.
// 3. **k6 프로세스 자신의 CPU 를 같이 봐라.** 부하 생성기가 먼저 포화하면
//    측정이 통째로 무효다. run.sh 가 같이 샘플링한다.
//
// ── 레이트 리밋 ──────────────────────────────────────────────────────────
// `CHAT_RATE_PER_MIN = 20` 이라 한 사람이 10 msg/s 를 쏘면 2 초 만에 차단되고
// 그 뒤로는 팬아웃이 0 이 된다. 발화자당 분당 10 건(상한의 절반)으로 잡고
// 필요한 인원을 역산한다 — CHAT_RPS × 6 명.

import { WebSocket } from 'k6/websockets';
import { setTimeout } from 'k6/timers';
import exec from 'k6/execution';
import { Counter, Trend } from 'k6/metrics';

const WS_URL = __ENV.WS_URL || 'ws://localhost:8080';
const BROADCAST_ID = __ENV.BROADCAST_ID || 'bc_1042';

const VIEWERS = Number(__ENV.VIEWERS || 4000);
// VU 하나가 소켓 여러 개를 든다. 레거시 k6/ws 면 소켓당 VU 하나가 묶여
// 4,000 VU 가 필요하고 노트북이 먼저 죽는다.
//
// 그렇다고 많이 들려도 안 된다. **k6 VU 는 자바스크립트 이벤트 루프가
// 하나**라서, 소켓 100개가 초당 430 프레임을 한 루프에 밀어넣으면 거기서
// 밀린 시간이 서버 지연으로 잘못 기록된다. 50 이면 4,000명에 79 VU 이고
// VU 하나가 초당 215 프레임을 받는다.
const SOCKETS_PER_VU = Number(__ENV.SOCKETS_PER_VU || 50);

// 임계 허용치. 인원의 0.5%, 최소 2건.
const TOLERANCE = Math.max(2, Math.ceil(VIEWERS * 0.005));

const CHAT_RPS = Number(__ENV.CHAT_RPS || 10);
// 발화자당 분당 10 건 = 상한 20 의 절반. 그래서 필요한 발화자 수는 CHAT_RPS×6.
const SENDERS = Number(__ENV.SENDERS || CHAT_RPS * 6);
const SEND_PERIOD_MS = Math.round((SENDERS / CHAT_RPS) * 1000);

const RAMP_S = Number(__ENV.RAMP_S || 30); // 방송 시작 30초 내 만재 (12.1)
const HOLD_S = Number(__ENV.HOLD_S || 300);

// 프레임을 전부 JSON.parse 하면 초당 20,000 파싱이라 k6 쪽이 먼저 포화한다.
// 개수는 전 소켓에서 세고, 파싱이 필요한 지연·전달률은 N 개마다 하나만 본다.
const SAMPLE_EVERY = Number(__ENV.SAMPLE_EVERY || 20);

// **발화자도 시청자다.** 별도로 더 열면 총 연결이 목표를 넘는다 — 500 계단에서
// 560 이 되어 12% 가 어긋난다. 목표 인원 안에서 나눈다.
const VIEWER_SOCKETS = Math.max(1, VIEWERS - SENDERS);
const VIEWER_VUS = Math.max(1, Math.ceil(VIEWER_SOCKETS / SOCKETS_PER_VU));
// VU 마다 균등하게 나누고 나머지는 앞쪽 VU 가 하나씩 더 가진다. 합이 정확히
// VIEWER_SOCKETS 가 되어야 "몇 명을 넣었나"가 표와 어긋나지 않는다.
const PER_VU = Math.floor(VIEWER_SOCKETS / VIEWER_VUS);
const EXTRA = VIEWER_SOCKETS - PER_VU * VIEWER_VUS;

const wsOpened = new Counter('ws_opened');
const wsFailed = new Counter('ws_failed');
const wsClosedEarly = new Counter('ws_closed_early');
// 전달률의 분모를 만든다. 샘플 소켓 하나는 발화 전부를 받아야 정상이다.
const wsSampled = new Counter('ws_sampled');
const framesRecv = new Counter('chat_frames_received');
const itemsRecv = new Counter('chat_items_received');
const badFrames = new Counter('chat_bad_frames');
const chatSent = new Counter('chat_sent');
// 발화 시각을 메시지 본문에 박아 두고 수신 시각과 뺀다. 보내는 쪽과 받는 쪽이
// 같은 노트북이라 시계가 같다.
const chatLatency = new Trend('chat_latency_ms', true);

export const options = {
  scenarios: {
    viewers: {
      executor: 'per-vu-iterations',
      vus: VIEWER_VUS,
      iterations: 1,
      maxDuration: `${RAMP_S + HOLD_S + 60}s`,
      exec: 'viewer',
    },
    senders: {
      executor: 'per-vu-iterations',
      vus: SENDERS,
      iterations: 1,
      maxDuration: `${RAMP_S + HOLD_S + 60}s`,
      // 시청자가 다 붙은 뒤에 발화한다. 램프 중에 쏘면 늦게 붙은 연결이
      // 앞부분을 못 받아 전달률이 이유 없이 떨어진다.
      startTime: `${RAMP_S}s`,
      exec: 'sender',
    },
  },
  thresholds: {
    // 허용치를 인원에 비례해 잡는다(0.5%). `count<1` 로 두면 4,000 연결 중
    // 딱 하나가 어긋나도 계단이 멈춘다 — 읽기 경로에서 실패 0.04% 를
    // 불합격으로 읽었던 것과 같은 실수다. 진짜 상한이면 수십~수백 건 나온다.
    ws_failed: [`count<${TOLERANCE}`],
    // 붙었다가 끊기는 것은 더 나쁘다 — 파드 OOM 이나 ALB idle timeout 이다.
    ws_closed_early: [`count<${TOLERANCE}`],
    // 목표 인원이 실제로 다 붙었는지. 안 붙었으면 아래 숫자들이 전부 무의미하다.
    ws_opened: [`count>=${VIEWERS - TOLERANCE}`],
    // 깨진 프레임은 조용히 넘기면 안 된다. 배치 포맷이 깨진 신호다.
    chat_bad_frames: [`count<${TOLERANCE}`],
    chat_latency_ms: ['p(95)<1000'],
  },
};

function url() {
  return `${WS_URL}/ws?broadcast_id=${BROADCAST_ID}`;
}

function open(holdMs, onFrame) {
  let ready = false;
  const ws = new WebSocket(url());

  ws.onopen = () => {
    ready = true;
    wsOpened.add(1);
    setTimeout(() => {
      ready = false; // 우리가 닫는 것이므로 close 를 조기 종료로 세지 않는다
      ws.close();
    }, holdMs);
  };
  ws.onerror = () => wsFailed.add(1);
  ws.onclose = () => {
    if (ready) wsClosedEarly.add(1);
  };
  if (onFrame) ws.onmessage = onFrame;
  return ws;
}

export function viewer() {
  // 시나리오 안에서 0 부터 매겨진다. vu.idInTest 는 시나리오끼리 섞여서 못 쓴다.
  const vuIndex = exec.scenario.iterationInTest;
  const count = PER_VU + (vuIndex < EXTRA ? 1 : 0);
  const gapMs = (RAMP_S * 1000) / Math.max(1, count);

  for (let i = 0; i < count; i++) {
    const delay = Math.round(i * gapMs);
    // 늦게 연 소켓도 같은 시각에 닫는다. 안 그러면 뒤쪽 연결이 더 오래 살아
    // 마지막 구간의 동시 접속 수가 목표보다 낮아진다.
    const holdMs = RAMP_S * 1000 - delay + HOLD_S * 1000;
    const sampled = (vuIndex * PER_VU + i) % SAMPLE_EVERY === 0;
    if (sampled) wsSampled.add(1);

    setTimeout(() => {
      open(holdMs, (e) => {
        framesRecv.add(1);
        if (!sampled) return; // 파싱 비용을 N 분의 1 로 줄인다

        let frame;
        try {
          frame = JSON.parse(String(e.data));
        } catch {
          badFrames.add(1);
          return;
        }
        // 계약상 프레임 페이로드는 항상 배열이다 (contracts.md 3.2).
        // 단건으로 오면 배치 포맷이 깨진 것이므로 세어야 한다.
        if (frame.t !== 'chat' || !Array.isArray(frame.items)) {
          badFrames.add(1);
          return;
        }

        itemsRecv.add(frame.items.length);
        const now = Date.now();
        for (const item of frame.items) {
          const sentAt = Number(String(item.msg).split('|')[0]);
          if (Number.isFinite(sentAt)) chatLatency.add(now - sentAt);
          else badFrames.add(1);
        }
      });
    }, delay);
  }
}

export function sender() {
  const holdMs = HOLD_S * 1000;
  const ws = open(holdMs, null);
  // 발화자끼리 시각을 흩는다. 다 같이 쏘면 한 틱에 몰려 평시가 아니라
  // 스파이크를 재게 된다.
  const offset = Math.round(Math.random() * SEND_PERIOD_MS);

  function fire() {
    if (ws.readyState !== 1) return;
    // 앞자리가 발화 시각. 수신 쪽이 이걸로 전파 지연을 계산한다.
    ws.send(JSON.stringify({ t: 'chat', msg: `${Date.now()}|부하테스트 발화` }));
    chatSent.add(1);
    setTimeout(fire, SEND_PERIOD_MS);
  }
  setTimeout(fire, offset);
}
