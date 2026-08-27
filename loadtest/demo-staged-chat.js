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
import exec from 'k6/execution';
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
const NORMAL_RPS = Number(__ENV.NORMAL_RPS || 1.6);
const SALE_RPS = Number(__ENV.SALE_RPS || 3.2);
const COMPLAINT_PEAK_RPS = Number(__ENV.COMPLAINT_PEAK_RPS || 5);

// 불만이 오르는 시간과 잦아드는 시간. 나머지가 도배 고원이다.
const COMPLAINT_RAMP_UP_SECONDS = Number(__ENV.COMPLAINT_RAMP_UP_SECONDS || 20);
const COMPLAINT_DECAY_SECONDS = Number(__ENV.COMPLAINT_DECAY_SECONDS || 120);

// 발화 직전 대기의 평균. k6 의 도착률은 일정한 간격으로 발화를 시작시키므로
// 이 값이 없으면 채팅이 메트로놈처럼 규칙적으로 올라온다. 지수분포로 흔들어
// 사람들이 제각각 치는 것처럼 만든다 — 가끔 두 줄이 겹치고 가끔 잠깐 조용하다.
const JITTER_MEAN_SECONDS = Number(__ENV.JITTER_MEAN_SECONDS || 0.6);

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

// 고원 구간을 한 발화율로 두면 채팅이 메트로놈처럼 규칙적으로 올라온다. 발화
// 직전 지연을 흔들어도 소용이 없다 — VU 가 여럿이라 합쳐지면 다시 고르게 편다.
// 눈에 보이는 불규칙은 **발화율 자체가 시간에 따라 오르내려야** 생긴다. 실제
// 방송에서도 불만은 물결로 온다(누가 쓰면 따라 쓰고, 잠깐 잦아든다).
//
// 배수와 길이는 고정값이다. 무작위로 만들면 VU 마다 다른 options 를 계산할 수
// 있어 위험하고, 고정이어도 주기가 서로 어긋나 화면에서는 불규칙해 보인다.
const WAVE_MULTIPLIERS = [1.3, 0.6, 1.1, 0.45, 1.4, 0.75, 1.0, 0.55];
const WAVE_SECONDS = [7, 5, 9, 6, 8, 5, 10, 6];

function holdWaves() {
  const stages = [];
  let remaining = COMPLAINT_HOLD_SECONDS;
  for (let i = 0; remaining > 0; i += 1) {
    const seconds = Math.min(WAVE_SECONDS[i % WAVE_SECONDS.length], remaining);
    stages.push({
      target: perTenSeconds(COMPLAINT_PEAK_RPS * WAVE_MULTIPLIERS[i % WAVE_MULTIPLIERS.length]),
      duration: `${seconds}s`,
    });
    remaining -= seconds;
  }
  return stages;
}

const generalSent = new Counter('demo_general_chats_sent');
const complaintsSent = new Counter('demo_complaints_sent');
const recoveredSent = new Counter('demo_recovered_chats_sent');
const chatFailed = new Counter('demo_chat_failed');

// k6 의 도착률은 정수만 받는다. 초당 1.6 건 같은 값을 쓰려면 단위를 10초로
// 늘려 정수로 표현한다(초당 1.6 = 10초당 16).
function perTenSeconds(rps) {
  return Math.max(1, Math.round(rps * 10));
}

const normal = (rps, startSeconds, durationSeconds, exec) => ({
  executor: 'constant-arrival-rate',
  rate: perTenSeconds(rps),
  timeUnit: '10s',
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
    // 3. 불만 — 오르고, 물결치고, 잦아든다
    p3_complaints: {
      executor: 'ramping-arrival-rate',
      startTime: `${INCIDENT_AT}s`,
      startRate: 0,
      timeUnit: '10s',
      preAllocatedVUs: PRE_ALLOCATED_VUS,
      maxVUs: MAX_VUS,
      exec: 'sendComplaint',
      stages: [
        { target: perTenSeconds(COMPLAINT_PEAK_RPS), duration: `${COMPLAINT_RAMP_UP_SECONDS}s` },
        ...holdWaves(),
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

// 문구를 무작위로 고르면 같은 줄이 연달아 뜬다 — 리허설 로그에서 세 번 연속
// 나오는 것을 봤다. VU별로 직전 값을 피하는 것으로는 안 된다(연속으로 보이는
// 두 줄은 대개 다른 VU 가 쓴 것이다). 시나리오 전체 이터레이션 번호로 풀을
// 순서대로 훑으면 같은 문구 사이에 풀 크기만큼 간격이 보장된다.
//
// 보폭을 두는 방법도 써봤는데 보폭과 풀 크기가 서로소가 아니면 조용히 몇 개만
// 돌고 만다(7과 28이면 넷만 쓴다). 풀 크기가 바뀌면 깨지는 조건이라 안 쓴다.
// 발화 직전 무작위 지연이 있어 화면에 뜨는 순서는 어차피 조금씩 섞인다.
function pick(pool) {
  return pool[exec.scenario.iterationInTest % pool.length];
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
  // 지수분포 대기. 균등분포(0~0.5초)로는 도착 간격이 여전히 고르게 남아
  // 화면에서 주기성이 보인다. 지수분포는 간격이 제각각이라 사람이 치는 것처럼
  // 보인다 — 다만 꼬리가 길어 구간 경계를 넘길 수 있으므로 평균의 3배에서 자른다.
  const wait = -Math.log(1 - Math.random()) * JITTER_MEAN_SECONDS;
  sleep(Math.min(wait, JITTER_MEAN_SECONDS * 3));

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
