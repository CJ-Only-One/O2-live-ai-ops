import assert from 'node:assert/strict';
import { test } from 'node:test';

import { packet } from './telemetry.js';

test('counter packet은 계약된 이름과 저카디널리티 태그만 허용한다', () => {
  assert.equal(
    packet('o2.app.business_event', 1, 'c', {
      service: 'chat-gateway',
      event: 'chat.send',
      result: 'success',
      env: 'dev',
    }),
    'o2.app.business_event:1|c|#service:chat-gateway,event:chat.send,result:success,env:dev',
  );
  assert.equal(
    packet('o2.app.business_event', 1, 'c', { user_id: 'u_1234' }),
    null,
  );
  assert.equal(packet('o2.app.unapproved', 1, 'c', { service: 'chat-gateway' }), null);
  assert.equal(packet('o2.app.failure', 1, 'c', { failure_code: 'free text' }), null);
});

test('duration packet은 distribution 타입을 유지한다', () => {
  assert.equal(
    packet('o2.app.operation.duration', 12.5, 'd', {
      service: 'chat-gateway',
      operation: 'chat.fanout',
      env: 'dev',
      pod_name: 'chat-gateway-abc-123',
    }),
    'o2.app.operation.duration:12.5|d|#service:chat-gateway,operation:chat.fanout,env:dev,pod_name:chat-gateway-abc-123',
  );
});

test('활성 연결만 gauge이고 메시지 크기는 distribution이다', () => {
  assert.equal(
    packet('o2.app.websocket.connections', 3, 'g', { service: 'chat-gateway' }),
    'o2.app.websocket.connections:3|g|#service:chat-gateway',
  );
  assert.equal(
    packet('o2.app.fanout.items', 12, 'c', { result: 'delivered' }),
    'o2.app.fanout.items:12|c|#result:delivered',
  );
  assert.equal(
    packet('o2.chat.propagation', 275, 'd', { service: 'chat-gateway' }),
    'o2.chat.propagation:275|d|#service:chat-gateway',
  );
  assert.equal(
    packet('o2.app.message.size', 128, 'd', { service: 'chat-gateway', operation: 'chat.receive' }),
    'o2.app.message.size:128|d|#service:chat-gateway,operation:chat.receive',
  );
});
