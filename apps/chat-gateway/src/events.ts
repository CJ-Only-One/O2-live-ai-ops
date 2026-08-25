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
import { performance } from 'node:perf_hooks';

import { KinesisClient, PutRecordCommand } from '@aws-sdk/client-kinesis';

import { config } from './config.js';
import { businessEvent, duration, failure } from './telemetry.js';

export type ChatSendPayload = {
  msg_length: number;
  msg_hash: string;
  is_duplicate: boolean;
  // contracts.md 5.3 — warm 은 payload 에서 result·failure_code 라는 이름을
  // 찾는다(o2warm/contract.py F_RESULT·F_FAILURE_CODE). result 는 성공에도
  // 싣는다 — 실패율 = 실패 / result 를 실은 전체 로 계산하기 때문이다.
  result: 'SUCCESS' | 'FAILED';
  failure_code?: string;
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
    // SDK config.py 와 같은 규칙 — O2_POD_NAME 이 없으면 HOSTNAME 으로 대체한다.
    // K8s 가 파드 이름을 HOSTNAME 에 기본으로 채워준다.
    pod_name: process.env.O2_POD_NAME || process.env.HOSTNAME || null,
    payload,
  };
}

type Envelope = ReturnType<typeof envelope>;

/**
 * 스트림별 파티션 키 규칙. SDK sinks.py 의 `_partition_key()` 와 동일하다.
 *
 * stream-business 는 order_id 로 같은 주문의 이벤트 순서를 보장하는데,
 * chat.send 는 order_id 도 session_id 도 없어 항상 event_id 로 떨어진다 —
 * 메시지마다 파티션이 갈리지만, 채팅은 순서를 보장할 필요가 없어 상관없다.
 */
function partitionKey(env: Envelope): string {
  const orderId = (env.payload as { order_id?: string }).order_id;
  return orderId || env.session_id || env.event_id;
}

let kinesis: KinesisClient | null = null;

function kinesisClient(): KinesisClient {
  if (!kinesis) kinesis = new KinesisClient({ region: config.awsRegion });
  return kinesis;
}

/**
 * 전송은 절대 예외를 밖으로 던지지 않는다 — SDK sinks.py 의 `_send()` 와
 * 같은 원칙이다. 이벤트 발행 실패가 채팅 자체를 막으면 안 된다.
 */
function send(env: Envelope): void {
  if (config.eventsSink === 'kinesis') {
    const started = performance.now();
    kinesisClient()
      .send(
        new PutRecordCommand({
          StreamName: config.streamBusiness,
          PartitionKey: partitionKey(env),
          Data: new TextEncoder().encode(JSON.stringify(env) + '\n'),
        }),
      )
      .then(() => {
        businessEvent('chat.kinesis', 'success');
        duration('chat.kinesis.publish', performance.now() - started);
      })
      .catch(() => {
        businessEvent('chat.kinesis', 'failed');
        failure('chat.kinesis', 'PUBLISH_FAILED');
        duration('chat.kinesis.publish', performance.now() - started);
        // SDK 오류 문자열에 요청 본문이 섞일 수 있어 고정 코드만 남긴다.
        console.error('[events] chat.send Kinesis 전송 실패 code=PUBLISH_FAILED');
      });
    return;
  }

  // 기본값 — 로컬 개발·확인용.
  process.stdout.write(JSON.stringify(env) + '\n');
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

  // **인입 지점에서만 부른다.** 팬아웃 루프 안에서 부르면 초당 80만 건이 되어
  // 파드가 죽는다 — 인입 20/s 와 전달 800,000/s 는 40,000 배 차이다.
  send(envelope('chat.send', payload, ctx));
}
