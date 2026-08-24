import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  createChatIngressHandler,
  type ChatIngressConnection,
} from './chat-ingress.js';
import type { ChatSendPayload, EmitContext } from './events.js';
import type { ChatSignalInput } from './chat-signal.js';

function fixture(overrides: {
  rateLimited?: boolean;
  channelLimited?: boolean;
  emitChatSignal?: (input: ChatSignalInput) => Promise<unknown>;
}) {
  const telemetry: Array<{ payload: ChatSendPayload; ctx: EmitContext }> = [];
  const signals: ChatSignalInput[] = [];
  const fanout: string[] = [];
  const conn: ChatIngressConnection = {
    broadcastId: 'bc_1042',
    userKey: 'u_0123456789abcdef',
    lastHash: null,
  };
  const emitSignal =
    overrides.emitChatSignal ??
    (async () => undefined);
  const handle = createChatIngressHandler({
    maxMessageLength: 200,
    overRateLimit: async () => overrides.rateLimited ?? false,
    overChannelLimit: async () => overrides.channelLimited ?? false,
    emitChatSend: (payload, ctx) => telemetry.push({ payload, ctx }),
    emitChatSignal: async (input) => {
      signals.push(input);
      return emitSignal(input);
    },
    publishFanout: async (_conn, message) => {
      fanout.push(message);
    },
  });

  return { conn, fanout, handle, signals, telemetry };
}

test('accepted chat: SQS와 Valkey로 각각 한 번 분기한다', async () => {
  const state = fixture({});
  await state.handle(state.conn, '느려요');

  assert.equal(state.signals.length, 1);
  assert.deepEqual(state.signals[0], {
    broadcastId: 'bc_1042',
    userKey: 'u_0123456789abcdef',
    message: '느려요',
    traceId: null,
  });
  assert.deepEqual(state.fanout, ['느려요']);
  assert.equal(state.telemetry.length, 1);
  assert.equal(state.telemetry[0].payload.result, 'SUCCESS');
  assert.equal(state.telemetry[0].payload.failure_code, undefined);
});

test('길이 초과: 원문 SQS와 Valkey 모두 보내지 않는다', async () => {
  const state = fixture({});
  await state.handle(state.conn, '가'.repeat(201));

  assert.equal(state.signals.length, 0);
  assert.equal(state.fanout.length, 0);
  assert.equal(state.telemetry[0].payload.result, 'FAILED');
  assert.equal(state.telemetry[0].payload.failure_code, 'TOO_LONG');
});

test('rate limited: 원문 SQS와 Valkey 모두 보내지 않는다', async () => {
  const state = fixture({ rateLimited: true });
  await state.handle(state.conn, '느려요');

  assert.equal(state.signals.length, 0);
  assert.equal(state.fanout.length, 0);
  assert.equal(state.telemetry[0].payload.result, 'FAILED');
  assert.equal(state.telemetry[0].payload.failure_code, 'RATE_LIMITED');
});

test('channel limited: 개인 한도는 통과했지만 총량 제한에 걸린다', async () => {
  const state = fixture({ channelLimited: true });
  await state.handle(state.conn, '느려요');

  assert.equal(state.signals.length, 0);
  assert.equal(state.fanout.length, 0);
  assert.equal(state.telemetry[0].payload.result, 'FAILED');
  assert.equal(state.telemetry[0].payload.failure_code, 'CHANNEL_LIMITED');
});

test('AC-008: SQS Promise가 거부돼도 Valkey 팬아웃은 성공한다', async () => {
  const state = fixture({
    emitChatSignal: async () => {
      throw new Error('SQS unavailable');
    },
  });

  await state.handle(state.conn, '느리네');
  assert.deepEqual(state.fanout, ['느리네']);
});

test('SQS 호출이 동기 예외를 던져도 Valkey 팬아웃은 성공한다', async () => {
  const state = fixture({
    emitChatSignal: (() => {
      throw new Error('publisher regression');
    }) as (input: ChatSignalInput) => Promise<unknown>,
  });

  await state.handle(state.conn, '나만 느림?');
  assert.deepEqual(state.fanout, ['나만 느림?']);
});

test('SQS가 끝나지 않아도 Valkey 팬아웃을 기다리게 하지 않는다', async () => {
  const state = fixture({
    emitChatSignal: async () => new Promise(() => undefined),
  });

  await state.handle(state.conn, '계속 로딩돼요');
  assert.deepEqual(state.fanout, ['계속 로딩돼요']);
});
