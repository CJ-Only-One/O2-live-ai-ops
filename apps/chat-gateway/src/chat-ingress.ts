import { performance } from 'node:perf_hooks';

import { digest, type ChatSendPayload, type EmitContext } from './events.js';
import type { ChatSignalInput } from './chat-signal.js';
import { businessEvent, duration, failure, messageSize } from './telemetry.js';

export type ChatIngressConnection = {
  broadcastId: string;
  userKey: string;
  // 직전 발화 해시만 저장한다. 원문은 연결 상태에 남기지 않는다.
  lastHash: string | null;
};

type Dependencies = {
  maxMessageLength: number;
  overRateLimit: (conn: ChatIngressConnection) => Promise<boolean>;
  // S1(scenario-experiment.md 0.5) 조치인 채널 총량 제한. 평시엔 노브가 꺼져
  // 있어 개인별 overRateLimit 만 적용되고, 이건 인시던트 중에만 걸린다.
  overChannelLimit: (conn: ChatIngressConnection) => Promise<boolean>;
  emitChatSend: (payload: ChatSendPayload, ctx: EmitContext) => void;
  emitChatSignal: (input: ChatSignalInput) => Promise<unknown>;
  publishFanout: (conn: ChatIngressConnection, message: string) => Promise<unknown>;
};

export function createChatIngressHandler(deps: Dependencies) {
  return async (conn: ChatIngressConnection, message: string): Promise<void> => {
    const started = performance.now();
    messageSize(Buffer.byteLength(message, 'utf8'));
    const hash = digest(message);
    const isDuplicate = conn.lastHash === hash;
    conn.lastHash = hash;

    const base = {
      msg_length: message.length,
      msg_hash: hash,
      is_duplicate: isDuplicate,
    };
    const ctx = { broadcastId: conn.broadcastId, userKey: conn.userKey };

    // 거부된 발화는 chat.send 관측 이벤트에만 남고 원문 SQS로는 보내지 않는다.
    // result 는 성공에도 싣는다(contracts.md 5.3) — 실패율의 분모가 되어야
    // failure_rate 가 항상 1.0 으로 나오는 사고를 피한다.
    if (message.length > deps.maxMessageLength) {
      deps.emitChatSend({ ...base, result: 'FAILED', failure_code: 'TOO_LONG' }, ctx);
      businessEvent('chat.send', 'failed');
      failure('chat.send', 'TOO_LONG');
      duration('chat.message', performance.now() - started);
      return;
    }
    if (await deps.overRateLimit(conn)) {
      deps.emitChatSend({ ...base, result: 'FAILED', failure_code: 'RATE_LIMITED' }, ctx);
      businessEvent('chat.send', 'failed');
      failure('chat.send', 'RATE_LIMITED');
      duration('chat.message', performance.now() - started);
      return;
    }
    // 개인 한도 통과분만 채널 총량과 비교한다 — 총량 제한은 "다들 개인
    // 한도 안에 있는데 인원이 많아서 넘친다"는 S1 전제를 재현하는 조치다.
    if (await deps.overChannelLimit(conn)) {
      deps.emitChatSend({ ...base, result: 'FAILED', failure_code: 'CHANNEL_LIMITED' }, ctx);
      businessEvent('chat.send', 'failed');
      failure('chat.send', 'CHANNEL_LIMITED');
      duration('chat.message', performance.now() - started);
      return;
    }

    deps.emitChatSend({ ...base, result: 'SUCCESS' }, ctx);
    businessEvent('chat.send', 'success');

    // SQS 분기는 await하지 않는다. 내부 Promise 거부와 동기 예외를 모두 흡수해
    // Publisher 구현이 퇴행해도 Valkey 팬아웃이 계속되게 한다.
    try {
      void deps
        .emitChatSignal({
          broadcastId: conn.broadcastId,
          userKey: conn.userKey,
          message,
          traceId: null,
        })
        .catch(() => undefined);
    } catch {
      // fail-open: 분석 신호보다 사용자 채팅 전달이 우선이다.
    }

    const fanoutStarted = performance.now();
    await deps.publishFanout(conn, message);
    duration('chat.fanout', performance.now() - fanoutStarted);
    duration('chat.message', performance.now() - started);
  };
}
