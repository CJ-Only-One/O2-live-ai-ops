#!/usr/bin/env node

import { setTimeout as sleep } from 'node:timers/promises';

import { WebSocket } from 'ws';

const WINDOW_SECONDS = 15;
const allowLive = process.env.ALLOW_LIVE_SHADOW_TEST;
const wsBase = process.env.CHAT_TEST_WS_BASE;
const idBase = Number.parseInt(process.env.CHAT_TEST_ID_BASE ?? '', 10);

if (allowLive !== '1') {
  throw new Error('ALLOW_LIVE_SHADOW_TEST=1 is required');
}
if (!wsBase || !/^wss?:\/\//.test(wsBase)) {
  throw new Error('CHAT_TEST_WS_BASE must be an explicit ws:// or wss:// URL');
}
if (!Number.isSafeInteger(idBase) || idBase < 1000) {
  throw new Error('CHAT_TEST_ID_BASE must be an integer greater than or equal to 1000');
}

const broadcast = (offset) => `bc_${idBase + offset}`;
const offsetSeconds = () => (Date.now() / 1000) % WINDOW_SECONDS;

async function waitForOffset(target) {
  const current = offsetSeconds();
  let seconds = (target - current + WINDOW_SECONDS) % WINDOW_SECONDS;
  if (seconds < 0.15) seconds += WINDOW_SECONDS;
  await sleep(seconds * 1000);
  return offsetSeconds();
}

function openSocket(broadcastId, token) {
  const url = new URL('/ws', wsBase);
  url.searchParams.set('broadcast_id', broadcastId);
  const socket = new WebSocket(url, token);
  let chatItems = 0;

  socket.on('message', (raw) => {
    try {
      const frame = JSON.parse(raw.toString());
      if (frame.t === 'chat' && Array.isArray(frame.items)) chatItems += frame.items.length;
    } catch {
      // Malformed output is reflected by a missing item count, not by logging its content.
    }
  });

  const opened = new Promise((resolve, reject) => {
    socket.once('open', resolve);
    socket.once('error', reject);
  });

  return { socket, opened, count: () => chatItems };
}

async function closeSockets(clients) {
  for (const { socket } of clients) socket.close();
  await sleep(100);
}

async function sendMessages(clients, messages) {
  for (let index = 0; index < messages.length; index += 1) {
    clients[index % clients.length].socket.send(JSON.stringify({ t: 'chat', msg: messages[index] }));
    await sleep(30);
  }
}

async function runWave({ name, broadcastId, users, messages, targetOffset = 2 }) {
  const clients = Array.from({ length: users }, (_unused, index) =>
    openSocket(broadcastId, `shadow-${broadcastId}-${name}-${index + 1}`),
  );
  await Promise.all(clients.map((client) => client.opened));
  await sleep(500);
  const sentAtOffset = await waitForOffset(targetOffset);
  await sendMessages(clients, messages);
  await sleep(1000);

  const result = {
    name,
    broadcast_id: broadcastId,
    connections: clients.length,
    sent_messages: messages.length,
    received_chat_items: clients.reduce((total, client) => total + client.count(), 0),
    sent_at_window_offset_seconds: Number(sentAtOffset.toFixed(3)),
  };
  await closeSockets(clients);
  return result;
}

async function runBoundaryCase(broadcastId) {
  const name = 'boundary_3_plus_1';
  const clients = Array.from({ length: 4 }, (_unused, index) =>
    openSocket(broadcastId, `shadow-${broadcastId}-${name}-${index + 1}`),
  );
  await Promise.all(clients.map((client) => client.opened));
  await sleep(500);

  const beforeBoundaryOffset = await waitForOffset(13.2);
  await sendMessages(clients, ['나만 느림?', '느리네', '느려요']);
  const afterBoundaryOffset = await waitForOffset(0.4);
  await sendMessages([clients[3]], ['렉 걸린 것 같은데']);
  await sleep(1000);

  const result = {
    name,
    broadcast_id: broadcastId,
    connections: clients.length,
    sent_messages: 4,
    received_chat_items: clients.reduce((total, client) => total + client.count(), 0),
    before_boundary_offset_seconds: Number(beforeBoundaryOffset.toFixed(3)),
    after_boundary_offset_seconds: Number(afterBoundaryOffset.toFixed(3)),
  };
  await closeSockets(clients);
  return result;
}

const weakMessages = ['나만 느림?', '느리네', '느려요', '렉 걸린 것 같은데'];

const firstWaves = await Promise.all([
  runWave({
    name: 'unrelated',
    broadcastId: broadcast(1),
    users: 4,
    messages: ['오늘 할인 좋네요', '상품 예쁘네요', '사이즈가 궁금해요', '방송 잘 보고 있어요'],
  }),
  runWave({
    name: 'same_user_repeat',
    broadcastId: broadcast(2),
    users: 1,
    messages: weakMessages,
  }),
  runWave({
    name: 'strong_threshold',
    broadcastId: broadcast(3),
    users: 4,
    messages: ['상품 정보가 늦게 떠요', '새로고침해도 계속 로딩돼요', '결제 버튼 반응이 없어요', '느리네'],
  }),
  runWave({
    name: 'cooldown_wave_1',
    broadcastId: broadcast(5),
    users: 4,
    messages: weakMessages,
  }),
]);

const boundaryResult = await runBoundaryCase(broadcast(4));
const cooldownWave2 = await runWave({
  name: 'cooldown_wave_2',
  broadcastId: broadcast(5),
  users: 4,
  messages: weakMessages,
  targetOffset: 2,
});

console.log(
  JSON.stringify(
    {
      schema_version: '1.0',
      suite: 'chat-signal-shadow-observation',
      results: [...firstWaves, boundaryResult, cooldownWave2],
    },
    null,
    2,
  ),
);
