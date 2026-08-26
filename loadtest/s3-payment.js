// S3: 결제 불만 채팅 선감지 후 PG 장애 주문 부하.
// PG 장애 주입/해제는 관리자 API로 별도 수행한다. 이 파일은 사용자 트래픽만 만든다.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { WebSocket } from 'k6/websockets';
import { setTimeout } from 'k6/timers';
import exec from 'k6/execution';
import { Counter } from 'k6/metrics';

const CHAT_ONLY = __ENV.CHAT_ONLY === 'true';

for (const name of [
  'DURATION',
  'CHAT_BASE_RPS',
  'CHAT_SALE_RPS',
  'CHAT_INCIDENT_RPS',
  'CHAT_PRE_ALLOCATED_VUS',
  'CHAT_MAX_VUS',
]) {
  if (!__ENV[name]) throw new Error(`S3 부하에는 -e ${name}=... 입력이 필요합니다`);
}
if (!CHAT_ONLY) {
  for (const name of ['RATE', 'PRE_ALLOCATED_VUS', 'MAX_VUS']) {
    if (!__ENV[name]) throw new Error(`S3 주문 부하에는 -e ${name}=... 입력이 필요합니다`);
  }
}

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const WS_URL = __ENV.WS_URL || 'ws://localhost:8080';
const BROADCAST_ID = __ENV.BROADCAST_ID || 'bc_1042';
const SKU_ID = __ENV.SKU_ID || '88213';
const QTY = Number(__ENV.QTY || 1);
const RATE = Number(__ENV.RATE);
const DURATION = __ENV.DURATION;
const PRE_ALLOCATED_VUS = Number(__ENV.PRE_ALLOCATED_VUS);
const MAX_VUS = Number(__ENV.MAX_VUS);
const CHAT_LEAD_SECONDS = Number(__ENV.CHAT_LEAD_SECONDS || 20);
const CHAT_BASE_RPS = Number(__ENV.CHAT_BASE_RPS);
const CHAT_SALE_RPS = Number(__ENV.CHAT_SALE_RPS);
const CHAT_INCIDENT_RPS = Number(__ENV.CHAT_INCIDENT_RPS);
const CHAT_PRE_ALLOCATED_VUS = Number(__ENV.CHAT_PRE_ALLOCATED_VUS);
const CHAT_MAX_VUS = Number(__ENV.CHAT_MAX_VUS);

if (!CHAT_ONLY && (!Number.isFinite(RATE) || RATE <= 0)) throw new Error('RATE는 양수여야 합니다');
if (!Number.isInteger(QTY) || QTY <= 0) throw new Error('QTY는 양의 정수여야 합니다');
if (!CHAT_ONLY && (!Number.isInteger(PRE_ALLOCATED_VUS) || PRE_ALLOCATED_VUS <= 0)) {
  throw new Error('PRE_ALLOCATED_VUS는 양의 정수여야 합니다');
}
if (!CHAT_ONLY && (!Number.isInteger(MAX_VUS) || MAX_VUS < PRE_ALLOCATED_VUS)) {
  throw new Error('MAX_VUS는 PRE_ALLOCATED_VUS 이상의 정수여야 합니다');
}
if (!Number.isInteger(CHAT_LEAD_SECONDS) || CHAT_LEAD_SECONDS < 17) {
  throw new Error('CHAT_LEAD_SECONDS는 17 이상의 정수여야 합니다');
}
if (!Number.isFinite(CHAT_BASE_RPS) || CHAT_BASE_RPS <= 0) {
  throw new Error('CHAT_BASE_RPS는 양수여야 합니다');
}
if (!Number.isFinite(CHAT_SALE_RPS) || CHAT_SALE_RPS <= CHAT_BASE_RPS) {
  throw new Error('CHAT_SALE_RPS는 CHAT_BASE_RPS보다 커야 합니다');
}
if (!Number.isFinite(CHAT_INCIDENT_RPS) || CHAT_INCIDENT_RPS <= 0) {
  throw new Error('CHAT_INCIDENT_RPS는 양수여야 합니다');
}
if (!Number.isInteger(CHAT_PRE_ALLOCATED_VUS) || CHAT_PRE_ALLOCATED_VUS <= 0) {
  throw new Error('CHAT_PRE_ALLOCATED_VUS는 양의 정수여야 합니다');
}
if (!Number.isInteger(CHAT_MAX_VUS) || CHAT_MAX_VUS < CHAT_PRE_ALLOCATED_VUS) {
  throw new Error('CHAT_MAX_VUS는 CHAT_PRE_ALLOCATED_VUS 이상의 정수여야 합니다');
}

const complaints = [
  '저만 결제 안 돼요? ㅠ',
  '결제 버튼 왜 반응 없죠',
  '결제 계속 실패해요 ㅠㅠ',
  '결제 화면 멈춘 듯요',
  '카드 결제가 자꾸 실패해요',
  '주문 버튼 눌러도 안 돼요',
  '결제 로딩만 계속 도는데요',
  '결제창이 먹통이에요 ㅠ',
  '다시 해도 결제 실패함',
  '결제 단계에서 계속 멈춰요',
  '주문 결제가 안 돼요',
  '결제 화면 반응 없는 분 또 있나요?',
];
const INCIDENT_SEED_USERS = 4;

const generalChats = [
  '색상 몇 개예요?',
  '실물이랑 색감 비슷해요?',
  '사이즈표 어디 있어요?',
  '평소 100인데 뭐 입으면 돼요?',
  '이거 무슨 소재예요?',
  '세탁기 돌려도 되나요?',
  '건조기 가능해요?',
  '원산지 어디예요?',
  '구성품 뭐뭐 와요?',
  '많이 무거운가요?',
  '재입고 또 되나요?',
  '다른 색도 보여주세요!',
  '착샷 한 번만 더요',
  '뒤쪽도 보여주세요~',
  '선물 포장 돼요?',
  '배송 언제부터예요?',
  '제주도 배송비 붙나요?',
  '교환은 며칠까지 돼요?',
  '반품비 얼마예요?',
  '쿠폰이랑 적립금 같이 돼요?',
  '방송 끝나도 이 가격이에요?',
  '오늘 혜택 한 번만 정리해주세요',
  '오 가격 괜찮은데요',
  '설명 잘해주시네요 ㅋㅋ',
  '친구한테 링크 보냈어요',
  '일단 장바구니 담음 ㅎㅎ',
];

const saleChats = [
  ...generalChats,
  '지금 타임세일 가격 맞죠?',
  '할인 몇 시까지예요?',
  '수량 얼마 안 남았어요?',
  '지금 사면 사은품도 와요?',
  '쿠폰까지 하면 얼마예요?',
  '두 개 사면 더 싸져요?',
  '방금 샀어요 ㅋㅋ',
  '품절 전에 얼른 사야겠다',
  '가족 것도 같이 갑니다',
  '타임세일 기다렸어요!!',
  '이 가격이면 하나 더?',
];

const complaintsSent = new Counter('s3_chat_complaints_sent');
const incidentChatsSent = new Counter('s3_incident_chats_sent');
const generalChatsSent = new Counter('s3_general_chats_sent');
const chatFailed = new Counter('s3_chat_failed');
const accepted = new Counter('orders_accepted');
const paymentFailed = new Counter('orders_payment_failed');
const unexpected = new Counter('orders_unexpected_response');

export const options = {
  scenarios: {
    incident_seed_after_sale: {
      executor: 'per-vu-iterations',
      vus: INCIDENT_SEED_USERS,
      iterations: 1,
      startTime: `${CHAT_LEAD_SECONDS}s`,
      maxDuration: '17s',
      exec: 'sendComplaint',
    },
    general_before_sale: {
      executor: 'constant-arrival-rate',
      rate: CHAT_BASE_RPS,
      timeUnit: '1s',
      duration: `${CHAT_LEAD_SECONDS}s`,
      preAllocatedVUs: CHAT_PRE_ALLOCATED_VUS,
      maxVUs: CHAT_MAX_VUS,
      exec: 'sendGeneralChat',
    },
    general_after_sale: {
      executor: 'constant-arrival-rate',
      rate: CHAT_SALE_RPS,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: CHAT_PRE_ALLOCATED_VUS,
      maxVUs: CHAT_MAX_VUS,
      startTime: `${CHAT_LEAD_SECONDS}s`,
      exec: 'sendGeneralChat',
    },
    incident_after_sale: {
      executor: 'constant-arrival-rate',
      rate: CHAT_INCIDENT_RPS,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: CHAT_PRE_ALLOCATED_VUS,
      maxVUs: CHAT_MAX_VUS,
      startTime: `${CHAT_LEAD_SECONDS}s`,
      exec: 'sendIncidentChat',
    },
    ...(CHAT_ONLY ? {} : {
      orders: {
        executor: 'constant-arrival-rate',
        rate: RATE,
        timeUnit: '1s',
        duration: DURATION,
        preAllocatedVUs: PRE_ALLOCATED_VUS,
        maxVUs: MAX_VUS,
        startTime: `${CHAT_LEAD_SECONDS}s`,
        exec: 'createOrder',
      },
    }),
  },
  thresholds: {
    s3_chat_complaints_sent: [`count==${INCIDENT_SEED_USERS}`],
    s3_chat_failed: ['count==0'],
    ...(CHAT_ONLY ? {} : { orders_unexpected_response: ['count==0'] }),
    dropped_iterations: ['count==0'],
  },
};

function uuidV4() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.floor(Math.random() * 16);
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function sendComplaint() {
  // Candidate는 15초 고정 창이다. 경계에 4건이 갈라지는 알려진 false negative를
  // 피하려고 타임세일 시작 후 첫 온전한 창의 2초 지점에 맞춘다.
  const current = (Date.now() / 1000) % 15;
  let waitSeconds = (2 - current + 15) % 15;
  if (waitSeconds < 0.2) waitSeconds += 15;
  sleep(waitSeconds);

  const index = exec.scenario.iterationInTest;
  openChat(complaints[index], `s3-payment-${index}`, complaintsSent, 1000);
}

export function sendGeneralChat() {
  sleep(Math.random() * 0.5);
  const messages = exec.scenario.name === 'general_after_sale' ? saleChats : generalChats;
  const message = messages[Math.floor(Math.random() * messages.length)];
  openChat(message, 's3-general', generalChatsSent, 500);
}

export function sendIncidentChat() {
  sleep(Math.random() * 0.5);
  const message = complaints[Math.floor(Math.random() * complaints.length)];
  openChat(message, 's3-incident', incidentChatsSent, 500);
}

function openChat(message, prefix, counter, closeMs) {
  const ws = new WebSocket(
    `${WS_URL}/ws?broadcast_id=${encodeURIComponent(BROADCAST_ID)}`,
    [`${prefix}-${uuidV4()}`],
  );
  let sent = false;

  ws.onopen = () => {
    ws.send(JSON.stringify({ t: 'chat', msg: message }));
    sent = true;
    counter.add(1);
    setTimeout(() => ws.close(), closeMs);
  };
  ws.onerror = () => chatFailed.add(1);
  ws.onclose = () => {
    if (!sent) chatFailed.add(1);
  };
}

export function createOrder() {
  const response = http.post(
    `${BASE_URL}/api/orders`,
    JSON.stringify({ broadcast_id: BROADCAST_ID, sku_id: SKU_ID, qty: QTY }),
    {
      headers: {
        'content-type': 'application/json',
        'Idempotency-Key': uuidV4(),
        'X-Session-Key': uuidV4(),
      },
      tags: { name: 'order_create' },
    },
  );

  let code = null;
  try {
    code = response.json('error.code');
  } catch (_) {
    // 비-JSON 오류는 unexpected로 센다.
  }

  const isAccepted = response.status === 202;
  const isPaymentFailure = response.status === 502 && code === 'PAYMENT_FAILED';
  if (isAccepted) accepted.add(1);
  else if (isPaymentFailure) paymentFailed.add(1);
  else unexpected.add(1, { status: String(response.status) });

  check(response, {
    '202 accepted 또는 502 payment failure': () => isAccepted || isPaymentFailure,
  });
}
