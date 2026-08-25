/** 저카디널리티 DogStatsD 계측. 전송 실패는 항상 업무 경로와 분리한다. */

import { createSocket, type Socket } from 'node:dgram';

const METRICS = new Set([
  'o2.app.business_event',
  'o2.app.failure',
  'o2.app.operation.duration',
  'o2.app.websocket.connections',
  'o2.app.message.size',
  'o2.app.fanout.items',
  'o2.chat.propagation',
]);

const TAG_KEYS = new Set([
  'env',
  'service',
  'version',
  'event',
  'result',
  'failure_code',
  'pod_name',
  'operation',
]);

export type MetricType = 'c' | 'd' | 'g';
export type MetricTags = Record<string, string>;
type Send = (packet: string) => void;

function safeValue(value: string): boolean {
  return /^[A-Za-z0-9_.:/-]{1,80}$/.test(value);
}

export function packet(
  metric: string,
  value: number,
  type: MetricType,
  tags: MetricTags,
): string | null {
  if (!METRICS.has(metric) || !Number.isFinite(value) || value < 0) return null;
  const entries = Object.entries(tags);
  if (entries.some(([key, tagValue]) => !TAG_KEYS.has(key) || !safeValue(tagValue))) return null;
  const suffix = entries.length
    ? `|#${entries.map(([key, tagValue]) => `${key}:${tagValue}`).join(',')}`
    : '';
  return `${metric}:${value}|${type}${suffix}`;
}

function udpSender(): Send {
  const host = process.env.DD_AGENT_HOST;
  const port = Number(process.env.DD_DOGSTATSD_PORT ?? '8125');
  let socket: Socket | null = null;

  return (payload: string): void => {
    if (!host || !Number.isInteger(port) || port <= 0 || port > 65535) return;
    try {
      if (!socket) {
        socket = createSocket('udp4');
        socket.on('error', () => {
          socket?.close();
          socket = null;
        });
      }
      socket.send(Buffer.from(payload), port, host, () => undefined);
    } catch {
      // fail-open: 관측 실패는 채팅 처리 결과를 바꾸지 않는다.
    }
  };
}

const send = udpSender();
const commonTags = {
  env: process.env.DD_ENV ?? 'dev',
  service: process.env.DD_SERVICE ?? 'chat-gateway',
  version: process.env.DD_VERSION ?? 'unknown',
  pod_name: process.env.O2_POD_NAME ?? process.env.HOSTNAME ?? 'unknown',
};

function emit(metric: string, value: number, type: MetricType, tags: MetricTags): void {
  const payload = packet(metric, value, type, { ...commonTags, ...tags });
  if (payload) send(payload);
}

export function businessEvent(event: string, result: 'success' | 'failed'): void {
  emit('o2.app.business_event', 1, 'c', { event, result });
}

export function failure(event: string, failureCode: string): void {
  emit('o2.app.failure', 1, 'c', { event, failure_code: failureCode });
}

export function duration(operation: string, durationMs: number): void {
  emit('o2.app.operation.duration', durationMs, 'd', { operation });
}

export function activeConnections(value: number): void {
  emit('o2.app.websocket.connections', value, 'g', {});
}

export function messageSize(value: number): void {
  emit('o2.app.message.size', value, 'd', { operation: 'chat.receive' });
}

export function fanoutItems(result: 'delivered' | 'dropped', value: number): void {
  emit('o2.app.fanout.items', value, 'c', { result });
}

// M-010의 40,000 items/s에서 모든 전달을 UDP로 보내면 계측이 장애를 만듭니다.
// 우선 무작위 0.1%로 상한을 두고, 표본 충실도와 비용은 재실측해 조정합니다.
export const PROPAGATION_SAMPLE_RATE = 0.001;

export function chatPropagation(durationMs: number, randomValue = Math.random()): void {
  if (randomValue >= PROPAGATION_SAMPLE_RATE) return;
  emit('o2.chat.propagation', durationMs, 'd', {});
}
