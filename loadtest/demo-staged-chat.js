// 발표 녹화 전용 — 대본대로 채팅만 흘린다. 장애도, 주문도, Agent도 없다.
//
// 이 파일은 **연출이다.** 측정에 쓰지 않는다. 여기서 나오는 불만 채팅은 실제
// 결제 실패의 결과가 아니라 시각에 맞춰 쏘는 것이다. 실제 장애 주입과 Agent
// 해결을 찍는 것은 `s3-payment.js` + `s3-coldopen.sh` 다.
//
// 대본 (기본값 기준, 총 10분 35초):
//
//   1. 0:00–0:20   상품 판매      — 정상 채팅
//   2. 0:20–0:30   타임세일 시작  — 정상 채팅(세일 문구 섞임)
//   3. 0:30–10:30  장애·해결 중   — 정상 + 불만. 불만은 20초에 걸쳐 오르고,
//                                    마지막 2분에 걸쳐 0으로 잦아든다
//   4. 10:30–10:35 해결 완료      — 정상 + "이제 되네요" 문구
//
//   BROADCAST_ID=bc_1042 WS_URL=wss://<ALB> k6 run loadtest/demo-staged-chat.js
//
// ★ **채팅 Source Adapter 실행 게이트를 끄고 돌려라.** 켜져 있으면 여기서 쏘는
//   불만 채팅이 진짜 Candidate 를 만들고 Agent 가 깨어난다 — 연출 녹화 도중에
//   실제 조치가 나갈 수 있다. `infra/08-chat-signal/terraform.tfvars` 의
//   `chat_source_adapter_execution_enabled = false` 로 두고 apply 한 상태에서 찍는다.
//
// 발화율·VU 는 화면에 보기 좋은 값이지 실측이 아니다. 채팅이 너무 빨리 흐르면
// 읽히지 않고 너무 느리면 방송 같지 않다 — 리허설에서 눈으로 보고 맞춘다.

import { sleep } from 'k6';
import { WebSocket } from 'k6/websockets';
import { setTimeout } from 'k6/timers';
import { Counter } from 'k6/metrics';

import { generalChats, saleChats, complaints, recoveredChats } from './chat-messages.js';

const WS_URL = __ENV.WS_URL || 'ws://localhost:8080';
const BROADCAST_ID = __ENV.BROADCAST_ID || 'bc_1042';

// 구간 길이 (초). 발표 대본이 바뀌면 여기만 바꾼다.
const P1_SECONDS = Number(__ENV.P1_SECONDS || 20);
const P2_SECONDS = Number(__ENV.P2_SECONDS || 10);
const P3_SECONDS = Number(__ENV.P3_SECONDS || 600);
const P4_SECONDS = Number(__ENV.P4_SECONDS || 5);

// 발화율 (초당). 정상 채팅은 구간 내내 흐르고, 불만만 오르내린다.
const NORMAL_RPS = Number(__ENV.NORMAL_RPS || 2);
const SALE_RPS = Number(__ENV.SALE_RPS || 4);
const COMPLAINT_PEAK_RPS = Number(__ENV.COMPLAINT_PEAK_RPS || 6);

// 불만이 오르는 시간과 잦아드는 시간. 나머지가 도배 고원이다.
const COMPLAINT_RAMP_UP_SECONDS = Number(__ENV.COMPLAINT_RAMP_UP_SECONDS || 20);
const COMPLAINT_DECAY_SECONDS = Number(__ENV.COMPLAINT_DECAY_SECONDS || 120);

const PRE_ALLOCATED_VUS = Number(__ENV.PRE_ALLOCATED_VUS || 30);
const MAX_VUS = Number(__ENV.MAX_VUS || 80);

for (const [name, value] of [
  ['P1_SECONDS', P1_SECONDS],
  ['P2_SECONDS', P2_SECONDS],
  ['P3_SECONDS', P3_SECONDS],
  ['P4_SECONDS', P4_SECONDS],
]) {
  if (!Number.isInteger(value) || value <= 0) throw new Error(`${name}는 양의 정수여야 합니다`);
}
for (const [name, value] of [
  ['NORMAL_RPS', NORMAL_RPS],
  ['SALE_RPS', SALE_RPS],
  ['COMPLAINT_PEAK_RPS', COMPLAINT_PEAK_RPS],
]) {
  if (!Number.isFinite(value) || value <= 0) throw new Error(`${name}는 양수여야 합니다`);
}

const COMPLAINT_HOLD_SECONDS = P3_SECONDS - COMPLAINT_RAMP_UP_SECONDS - COMPLAINT_DECAY_SECONDS;
if (COMPLAINT_HOLD_SECONDS <= 0) {
  throw new Error(
    'P3_SECONDS가 COMPLAINT_RAMP_UP_SECONDS + COMPLAINT_DECAY_SECONDS보다 길어야 합니다',
  );
}

const SALE_AT = P1_SECONDS;
const INCIDENT_AT = P1_SECONDS + P2_SECONDS;
const RESOLVED_AT = P1_SECONDS + P2_SECONDS + P3_SECONDS;

const generalSent = new Counter('demo_general_chats_sent');
const complaintsSent = new Counter('demo_complaints_sent');
const recoveredSent = new Counter('demo_recovered_chats_sent');
const chatFailed = new Counter('demo_chat_failed');

const normal = (rate, startSeconds, durationSeconds, exec) => ({
  executor: 'constant-arrival-rate',
  rate,
  timeUnit: '1s',
  duration: `${durationSeconds}s`,
  startTime: `${startSeconds}s`,
  preAllocatedVUs: PRE_ALLOCATED_VUS,
  maxVUs: MAX_VUS,
  exec,
});

export const options = {
  scenarios: {
    // 1. 상품 판매
    p1_selling: normal(NORMAL_RPS, 0, P1_SECONDS, 'sendGeneral'),
    // 2. 타임세일 안내·시작
    p2_sale_open: normal(SALE_RPS, SALE_AT, P2_SECONDS, 'sendSale'),
    // 3. 장애 구간의 정상 채팅 — 불만만 나오면 방송이 아니라 장애 화면이 된다
    p3_normal: normal(SALE_RPS, INCIDENT_AT, P3_SECONDS, 'sendSale'),
    // 3. 불만 — 오르고, 버티고, 잦아든다
    p3_complaints: {
      executor: 'ramping-arrival-rate',
      startTime: `${INCIDENT_AT}s`,
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: PRE_ALLOCATED_VUS,
      maxVUs: MAX_VUS,
      exec: 'sendComplaint',
      stages: [
        { target: COMPLAINT_PEAK_RPS, duration: `${COMPLAINT_RAMP_UP_SECONDS}s` },
        { target: COMPLAINT_PEAK_RPS, duration: `${COMPLAINT_HOLD_SECONDS}s` },
        { target: 0, duration: `${COMPLAINT_DECAY_SECONDS}s` },
      ],
    },
    // 4. 해결 완료
    p4_resolved: normal(SALE_RPS, RESOLVED_AT, P4_SECONDS, 'sendRecovered'),
  },
  thresholds: {
    // 연출이라 성능 임계는 없다. 채팅이 안 나가는 것만 실패로 본다.
    demo_chat_failed: ['count==0'],
  },
};

function uuidV4() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.floor(Math.random() * 16);
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function pick(pool) {
  return pool[Math.floor(Math.random() * pool.length)];
}

export function sendGeneral() {
  send(pick(generalChats), 'demo-general', generalSent);
}

export function sendSale() {
  send(pick(saleChats), 'demo-sale', generalSent);
}

export function sendComplaint() {
  send(pick(complaints), 'demo-complaint', complaintsSent);
}

export function sendRecovered() {
  // 마지막 5초는 회복 문구만 나오게 둔다 — 여기서 일반 문의가 섞이면
  // "고쳐졌다"가 화면에서 안 읽힌다.
  send(pick(recoveredChats), 'demo-recovered', recoveredSent);
}

function send(message, prefix, counter) {
  // 사람마다 타이핑 속도가 다르다. 같은 초에 발화가 몰리면 줄이 계단처럼 붙어
  // 생성기 티가 난다.
  sleep(Math.random() * 0.5);

  const ws = new WebSocket(
    `${WS_URL}/ws?broadcast_id=${encodeURIComponent(BROADCAST_ID)}`,
    [`${prefix}-${uuidV4()}`],
  );
  let sent = false;

  ws.onopen = () => {
    ws.send(JSON.stringify({ t: 'chat', msg: message }));
    sent = true;
    counter.add(1);
    setTimeout(() => ws.close(), 500);
  };
  ws.onerror = () => chatFailed.add(1);
  ws.onclose = () => {
    if (!sent) chatFailed.add(1);
  };
}
