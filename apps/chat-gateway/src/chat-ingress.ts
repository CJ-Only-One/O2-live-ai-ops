/** Accepted chat의 Valkey 팬아웃과 SQS 분석 분기를 조정한다. */

import { digest, type ChatSendPayload, type EmitContext } from './events.js';
import type { ChatSignalInput } from './chat-signal.js';

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
    if (message.length > deps.maxMessageLength) {
      deps.emitChatSend({ ...base, rejected_code: 'TOO_LONG' }, ctx);
      return;
    }
    if (await deps.overRateLimit(conn)) {
      deps.emitChatSend({ ...base, rejected_code: 'RATE_LIMITED' }, ctx);
      return;
    }
    // 개인 한도 통과분만 채널 총량과 비교한다 — 총량 제한은 "다들 개인
    // 한도 안에 있는데 인원이 많아서 넘친다"는 S1 전제를 재현하는 조치다.
    if (await deps.overChannelLimit(conn)) {
      deps.emitChatSend({ ...base, rejected_code: 'CHANNEL_LIMITED' }, ctx);
      return;
    }

    deps.emitChatSend(base, ctx);

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

    await deps.publishFanout(conn, message);
  };
}
