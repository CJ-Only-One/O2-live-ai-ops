/**
 * 이름은 계약이다. 클러스터에서는 api 와 같은 ConfigMap o2-data 가 envFrom 으로
 * 들어오므로 키 이름이 거기와 같아야 한다. 새 이름을 만들면 주입값이 조용히
 * 무시되고 기본값이 쓰인다.
 */

function num(name: string, fallback: number): number {
  const raw = process.env[name];
  const parsed = raw ? Number(raw) : NaN;
  return Number.isFinite(parsed) ? parsed : fallback;
}

function positiveNum(name: string, fallback: number): number {
  const value = num(name, fallback);
  return value > 0 ? Math.floor(value) : fallback;
}

export type ChatSignalMode = 'off' | 'shadow';

const rawChatSignalMode = process.env.CHAT_SIGNAL_MODE ?? 'off';
export function parseChatSignalMode(raw: string | undefined): ChatSignalMode {
  return raw === 'shadow' ? 'shadow' : 'off';
}

const chatSignalMode = parseChatSignalMode(rawChatSignalMode);

export const config = {
  port: num('PORT', 8080),

  valkeyHost: process.env.VALKEY_HOST ?? 'localhost',
  valkeyPort: num('VALKEY_PORT', 6379),
  // 클러스터의 Valkey 는 transit 암호화가 켜져 있다. 평문으로 붙으면 연결이
  // 그 자리에서 끊긴다.
  valkeyTls: (process.env.VALKEY_TLS ?? 'false') === 'true',

  /**
   * 200ms 창에 쌓인 것을 한 프레임으로 보낸다 (contracts.md 3.2).
   * 메시지당 1프레임이면 Peak 에서 write 가 초당 800,000 회가 된다.
   */
  tickMs: num('CHAT_TICK_MS', 200),

  /**
   * 창당 최대 전송 건수. 초과분은 버린다.
   *
   * 상시 최적화가 아니라 발화율 스파이크 방어다 — 평시에는 창당 평균 4건이라
   * 상한에 닿지 않는다. 실제 값은 Phase 4 측정으로 정한다. 지금 값은 자리를
   * 잡아두기 위한 것이지 근거가 있는 숫자가 아니다.
   */
  maxPerTick: num('CHAT_MAX_PER_TICK', 50),

  // 메시지 길이 상한과 분당 발화 상한 (contracts.md 3.4 · 4).
  maxMessageLength: num('CHAT_MAX_LENGTH', 200),
  rateLimitPerMinute: num('CHAT_RATE_PER_MIN', 20),

  // 스케일다운 시 close frame 을 보내고 기다리는 시간 (architecture.md 9.4-2).
  drainMs: num('CHAT_DRAIN_MS', 15000),

  /**
   * chat.send 발행 스위치.
   *
   * 기본값이 꺼짐인 이유였던 "모르는 event_name이 들어갔을 때 수집단이 어떻게
   * 처리하는지"(contracts.md 5.5)는 확인됐다 — Warm(sketch.py `add()`)과
   * Cold(Glue ETL `get_json_object`) 양쪽 다 event_name을 고정 목록과 대조하지
   * 않고 그대로 받아들인다. 기본값은 여전히 꺼짐으로 둔다 — 배포 매니페스트에서
   * EMIT_CHAT_EVENTS=true로 명시적으로 켜는 것이 안전하다.
   */
  emitChatEvents: (process.env.EMIT_CHAT_EVENTS ?? 'false') === 'true',

  /**
   * Incident Candidate 입력용 SQS 분기. 기본값과 알 수 없는 값은 fail-safe로 off다.
   * shadow는 큐에 쓰기만 하며 사용자 응답이나 Valkey 팬아웃 결과를 기다리지 않는다.
   */
  chatSignalMode,
  chatSignalQueueUrl: process.env.SQS_CHAT_SIGNAL_QUEUE_URL ?? '',

  /**
   * 백그라운드 SQS 요청이 무한히 쌓이지 않게 하는 초기 가드다. 500ms는 실측 SLO가
   * 아니며 Shadow Mode에서 성공률·지연을 측정한 뒤 조정한다.
   */
  chatSignalSendTimeoutMs: positiveNum('CHAT_SIGNAL_SEND_TIMEOUT_MS', 500),

  /**
   * chat.send 전송 목적지. Python SDK 의 O2_EVENTS_SINK 와 같은 이름·같은 값
   * (stdout|kinesis) 을 쓴다 — 두 서비스가 같은 스위치로 배선을 맞춘다.
   */
  eventsSink: process.env.O2_EVENTS_SINK ?? 'stdout',

  // SDK 기본값과 같다 (O2_STREAM_BUSINESS, AWS_REGION). 04-platform 이 이미
  // 이 기본값 그대로 IAM 권한을 주고 있어(app_events.tf) 따로 안 바꾼다.
  // chat.send 는 client.*/live.* 접두어가 아니라 항상 business 로 간다
  // (SDK sinks.py 의 `_stream_for()` 와 동일 규칙).
  streamBusiness: process.env.O2_STREAM_BUSINESS ?? 'stream-business',
  awsRegion: process.env.AWS_REGION ?? 'ap-northeast-2',

  service: process.env.O2_SERVICE ?? 'chat-gateway',
  serviceVersion: process.env.O2_SERVICE_VERSION ?? 'unknown',
  // Python SDK의 hash_key와 같은 salt를 써야 API·채팅 이벤트의 user_key를
  // 같은 사용자 기준으로 조인할 수 있다.
  eventsSalt: process.env.O2_EVENTS_SALT ?? '',
};
