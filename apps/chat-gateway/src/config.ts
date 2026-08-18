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
   * 기본값이 꺼짐인 이유는, 모르는 event_name 이 들어갔을 때 수집단이 어떻게
   * 처리하는지 아직 확인되지 않았기 때문이다 (contracts.md 5.5). 우리가 남의
   * 파이프라인을 깨뜨릴 수 있으므로 답이 온 뒤에 켠다.
   */
  emitChatEvents: (process.env.EMIT_CHAT_EVENTS ?? 'false') === 'true',

  service: process.env.O2_SERVICE ?? 'chat-gateway',
  serviceVersion: process.env.O2_SERVICE_VERSION ?? 'unknown',
  // Python SDK의 hash_key와 같은 salt를 써야 API·채팅 이벤트의 user_key를
  // 같은 사용자 기준으로 조인할 수 있다.
  eventsSalt: process.env.O2_EVENTS_SALT ?? '',
};
