/**
 * Accepted chat을 Incident Candidate 분석용 SQS로 분기한다.
 *
 * 이 모듈은 분류·집계·Datadog 조회·Agent 호출을 하지 않는다. 원문은 SQS
 * MessageBody에만 넣고 오류 메시지나 관측 이벤트에는 절대 넣지 않는다.
 */

import { performance } from 'node:perf_hooks';

import { SendMessageCommand, SQSClient } from '@aws-sdk/client-sqs';

import { config, type ChatSignalMode } from './config.js';
import { ulid } from './events.js';

export type ChatSignalInput = {
  broadcastId: string;
  userKey: string;
  message: string;
  traceId: string | null;
};

export type ChatSignalObservation = {
  outcome: 'success' | 'failure';
  durationMs: number;
  errorCode?: string;
};

export type ChatSignalPublishResult =
  | { status: 'off' }
  | { status: 'sent' }
  | { status: 'failed'; errorCode: string };

type Send = (command: SendMessageCommand, signal: AbortSignal) => Promise<unknown>;
type Observe = (observation: ChatSignalObservation) => void;

type PublisherOptions = {
  mode: ChatSignalMode;
  queueUrl: string;
  region: string;
  timeoutMs: number;
  send?: Send;
  observe?: Observe;
  eventId?: () => string;
  now?: () => Date;
};

class ChatSignalTimeoutError extends Error {
  override name = 'CHAT_SIGNAL_TIMEOUT';
}

function sanitizeErrorCode(error: unknown): string {
  if (!(error instanceof Error)) return 'UNKNOWN';
  const name = error.name;
  return /^[A-Za-z0-9_.-]{1,64}$/.test(name) ? name : 'UNKNOWN';
}

function defaultObserve(observation: ChatSignalObservation): void {
  if (observation.outcome !== 'failure') return;
  // error.message는 AWS SDK나 테스트 입력을 통해 원문을 포함할 수 있으므로 쓰지 않는다.
  console.error(
    `[chat-signal] SQS send failed code=${observation.errorCode ?? 'UNKNOWN'} ` +
      `duration_ms=${observation.durationMs.toFixed(1)}`,
  );
}

function safeObserve(observe: Observe, observation: ChatSignalObservation): void {
  try {
    observe(observation);
  } catch {
    // 관측 실패가 채팅과 SQS 전송 결과를 바꾸지 않는다.
  }
}

function normalizedTimeout(value: number): number {
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : 500;
}

export function createChatSignalPublisher(options: PublisherOptions) {
  let client: SQSClient | null = null;
  const send: Send =
    options.send ??
    ((command, signal) => {
      client ??= new SQSClient({ region: options.region });
      return client.send(command, { abortSignal: signal });
    });
  const observe = options.observe ?? defaultObserve;
  const eventId = options.eventId ?? ulid;
  const now = options.now ?? (() => new Date());
  const timeoutMs = normalizedTimeout(options.timeoutMs);

  return async (input: ChatSignalInput): Promise<ChatSignalPublishResult> => {
    if (options.mode !== 'shadow') return { status: 'off' };

    const started = performance.now();
    if (!options.queueUrl) {
      const durationMs = performance.now() - started;
      safeObserve(observe, { outcome: 'failure', durationMs, errorCode: 'QUEUE_URL_MISSING' });
      return { status: 'failed', errorCode: 'QUEUE_URL_MISSING' };
    }
    if (input.message.length > 200) {
      const durationMs = performance.now() - started;
      safeObserve(observe, { outcome: 'failure', durationMs, errorCode: 'MESSAGE_TOO_LONG' });
      return { status: 'failed', errorCode: 'MESSAGE_TOO_LONG' };
    }

    const body = JSON.stringify({
      schema_version: '1.0',
      event_id: eventId(),
      event_ts: now().toISOString(),
      broadcast_id: input.broadcastId,
      user_key: input.userKey,
      message: input.message,
      trace_id: input.traceId,
    });
    const command = new SendMessageCommand({ QueueUrl: options.queueUrl, MessageBody: body });
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    const timeout = new Promise<never>((_resolve, reject) => {
      timer = setTimeout(() => {
        controller.abort();
        reject(new ChatSignalTimeoutError());
      }, timeoutMs);
    });

    try {
      await Promise.race([send(command, controller.signal), timeout]);
      safeObserve(observe, { outcome: 'success', durationMs: performance.now() - started });
      return { status: 'sent' };
    } catch (error: unknown) {
      const errorCode = controller.signal.aborted ? 'CHAT_SIGNAL_TIMEOUT' : sanitizeErrorCode(error);
      safeObserve(observe, {
        outcome: 'failure',
        durationMs: performance.now() - started,
        errorCode,
      });
      return { status: 'failed', errorCode };
    } finally {
      if (timer) clearTimeout(timer);
    }
  };
}

export const emitChatSignal = createChatSignalPublisher({
  mode: config.chatSignalMode,
  queueUrl: config.chatSignalQueueUrl,
  region: config.awsRegion,
  timeoutMs: config.chatSignalSendTimeoutMs,
});
