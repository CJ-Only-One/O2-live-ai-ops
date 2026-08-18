/**
 * chat.send 발행.
 *
 * 이벤트 SDK 는 Python 이라 여기서는 같은 봉투를 내는 얇은 클라이언트를 직접
 * 만든다 (contracts.md 5.3). 게이트웨이가 낼 이벤트는 chat.send 하나뿐이라
 * 사이드카로 Python SDK 를 띄우는 것은 이벤트 하나 때문에 할 일이 아니다.
 *
 * **본문을 싣지 않는다.** 채팅은 이 시스템에서 유일하게 외부인이 자유롭게 쓰는
 * 입력이고, 그것이 에이전트가 읽는 저장소로 흘러간다. 본문을 저장하면 시청자
 * 아무나가 운영 에이전트에게 지시를 넣는 경로가 생긴다 (architecture.md 8.5).
 * 길이·해시·중복 여부만으로 부하 분석 목적은 전부 달성된다.
 */

import { createHash, createHmac, randomBytes } from 'node:crypto';

import { config } from './config.js';

export type ChatSendPayload = {
  msg_length: number;
  msg_hash: string;
  is_duplicate: boolean;
  rejected_code?: string;
};

/**
 * SDK core.py 의 ulid() 와 같은 값을 만든다.
 *
 * randomUUID 를 쓰면 안 된다. 앞 10자가 밀리초 타임스탬프라 문자열 정렬이 곧
 * 시간순 정렬이고, 수집단이 중복 제거 키로 쓴다. UUID 로 내면 chat.send 만
 * 정렬이 깨지는데, 깨져도 아무도 에러를 내지 않아 늦게 발견된다.
 */
const CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

function b32(value: bigint, length: number): string {
  const out: string[] = [];
  for (let i = 0; i < length; i += 1) {
    out.push(CROCKFORD[Number(value & 31n)]);
    value >>= 5n;
  }
  return out.reverse().join('');
}

export function ulid(): string {
  // 10자 = 50비트(밀리초), 16자 = 80비트(난수). SDK 와 같은 분할이다.
  return b32(BigInt(Date.now()), 10) + b32(BigInt('0x' + randomBytes(10).toString('hex')), 16);
}

function envelope(eventName: string, payload: ChatSendPayload, ctx: EmitContext) {
  const now = new Date().toISOString();
  return {
    event_id: ulid(),
    event_name: eventName,
    // SDK config.py 의 schema_version 상수와 같아야 한다. 그쪽이 올라가면
    // 여기도 같이 올려야 하는데, 어긋나도 아무 에러가 안 난다.
    schema_version: '1.0',
    event_ts: now,
    received_ts: now,
    service: config.service,
    service_version: config.serviceVersion,
    trace_id: null,
    broadcast_id: ctx.broadcastId,
    user_key: ctx.userKey,
    session_id: null,
    client_ip_key: null,
    payload,
  };
}

export type EmitContext = {
  broadcastId: string;
  userKey: string | null;
};

/** Python SDK의 hash_key("u", raw)와 같은 사용자 키를 만든다. */
export function hashUserKey(raw: string): string {
  const digest = createHmac('sha256', config.eventsSalt).update(raw).digest('hex').slice(0, 16);
  return `u_${digest}`;
}

/** 본문 대신 남기는 파생값. 같은 문구 도배는 해시로 탐지된다. */
export function digest(message: string): string {
  return createHash('sha256').update(message).digest('hex').slice(0, 16);
}

export function emitChatSend(payload: ChatSendPayload, ctx: EmitContext): void {
  if (!config.emitChatEvents) return;

  // 지금은 stdout 싱크다. Kinesis 전환은 이 함수 안쪽만 바꾸면 된다.
  //
  // **인입 지점에서만 부른다.** 팬아웃 루프 안에서 부르면 초당 80만 건이 되어
  // 파드가 죽는다 — 인입 20/s 와 전달 800,000/s 는 40,000 배 차이다.
  process.stdout.write(JSON.stringify(envelope('chat.send', payload, ctx)) + '\n');
}
