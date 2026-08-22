import assert from 'node:assert/strict';
import { test } from 'node:test';

import { SendMessageCommand } from '@aws-sdk/client-sqs';

import { parseChatSignalMode } from './config.js';
import {
  createChatSignalPublisher,
  type ChatSignalInput,
  type ChatSignalObservation,
} from './chat-signal.js';

const INPUT: ChatSignalInput = {
  broadcastId: 'bc_1042',
  userKey: 'u_0123456789abcdef',
  message: '상품 정보가 너무 느리게 떠요',
  traceId: null,
};

function baseOptions() {
  return {
    mode: 'shadow' as const,
    queueUrl: 'https://sqs.ap-northeast-2.amazonaws.com/123/chat-signal',
    region: 'ap-northeast-2',
    timeoutMs: 50,
    eventId: () => '01K00000000000000000000000',
    now: () => new Date('2026-08-22T00:00:00.000Z'),
  };
}

test('mode parser: shadow만 활성화하고 나머지는 off로 닫는다', () => {
  assert.equal(parseChatSignalMode('shadow'), 'shadow');
  assert.equal(parseChatSignalMode('off'), 'off');
  assert.equal(parseChatSignalMode('unexpected'), 'off');
  assert.equal(parseChatSignalMode(undefined), 'off');
});

test('off: AWS client를 만들거나 호출하지 않는다', async () => {
  let calls = 0;
  const publish = createChatSignalPublisher({
    ...baseOptions(),
    mode: 'off',
    send: async () => {
      calls += 1;
    },
  });

  assert.deepEqual(await publish(INPUT), { status: 'off' });
  assert.equal(calls, 0);
});

test('shadow: chat.signal.v1 계약 그대로 한 번 전송한다', async () => {
  const commands: SendMessageCommand[] = [];
  const observations: ChatSignalObservation[] = [];
  const publish = createChatSignalPublisher({
    ...baseOptions(),
    send: async (command, signal) => {
      assert.equal(signal.aborted, false);
      commands.push(command);
    },
    observe: (observation) => observations.push(observation),
  });

  assert.deepEqual(await publish(INPUT), { status: 'sent' });
  assert.equal(commands.length, 1);
  assert.equal(commands[0].input.QueueUrl, baseOptions().queueUrl);
  assert.deepEqual(JSON.parse(commands[0].input.MessageBody ?? ''), {
    schema_version: '1.0',
    event_id: '01K00000000000000000000000',
    event_ts: '2026-08-22T00:00:00.000Z',
    broadcast_id: 'bc_1042',
    user_key: 'u_0123456789abcdef',
    message: INPUT.message,
    trace_id: null,
  });
  assert.equal(observations.length, 1);
  assert.equal(observations[0].outcome, 'success');
  assert.ok(observations[0].durationMs >= 0);
});

test('SQS 실패: 예외를 밖으로 던지지 않고 원문을 로그에 남기지 않는다', async () => {
  const logged: string[] = [];
  const original = console.error;
  console.error = (...args: unknown[]) => logged.push(args.map(String).join(' '));

  try {
    const publish = createChatSignalPublisher({
      ...baseOptions(),
      send: async () => {
        throw new Error(`upstream rejected: ${INPUT.message}`);
      },
    });

    assert.deepEqual(await publish(INPUT), { status: 'failed', errorCode: 'Error' });
    assert.equal(logged.length, 1);
    assert.doesNotMatch(logged[0], new RegExp(INPUT.message));
    assert.match(logged[0], /code=Error/);
  } finally {
    console.error = original;
  }
});

test('timeout: 요청을 abort하고 CHAT_SIGNAL_TIMEOUT으로 흡수한다', async () => {
  let aborted = false;
  const observations: ChatSignalObservation[] = [];
  const publish = createChatSignalPublisher({
    ...baseOptions(),
    timeoutMs: 5,
    send: async (_command, signal) =>
      new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => {
          aborted = true;
          reject(new Error(`timeout body leak: ${INPUT.message}`));
        });
      }),
    observe: (observation) => observations.push(observation),
  });

  assert.deepEqual(await publish(INPUT), {
    status: 'failed',
    errorCode: 'CHAT_SIGNAL_TIMEOUT',
  });
  assert.equal(aborted, true);
  assert.equal(observations[0].errorCode, 'CHAT_SIGNAL_TIMEOUT');
  assert.doesNotMatch(JSON.stringify(observations), new RegExp(INPUT.message));
});

test('shadow + queue URL 누락: AWS 호출 없이 안전하게 실패한다', async () => {
  let calls = 0;
  const publish = createChatSignalPublisher({
    ...baseOptions(),
    queueUrl: '',
    send: async () => {
      calls += 1;
    },
    observe: () => undefined,
  });

  assert.deepEqual(await publish(INPUT), {
    status: 'failed',
    errorCode: 'QUEUE_URL_MISSING',
  });
  assert.equal(calls, 0);
});

test('200자 초과: 계약 위반 원문을 SQS에 보내지 않는다', async () => {
  let calls = 0;
  const publish = createChatSignalPublisher({
    ...baseOptions(),
    send: async () => {
      calls += 1;
    },
    observe: () => undefined,
  });

  assert.deepEqual(await publish({ ...INPUT, message: '가'.repeat(201) }), {
    status: 'failed',
    errorCode: 'MESSAGE_TOO_LONG',
  });
  assert.equal(calls, 0);
});

test('관측 콜백 실패도 SQS 전송 결과를 바꾸지 않는다', async () => {
  const publish = createChatSignalPublisher({
    ...baseOptions(),
    send: async () => undefined,
    observe: () => {
      throw new Error('observer unavailable');
    },
  });

  assert.deepEqual(await publish(INPUT), { status: 'sent' });
});
