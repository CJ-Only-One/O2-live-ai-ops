// S3 외부 결제 PG 장애 주입용 주문 부하.
//
// RATE·DURATION·VU 수를 기본값으로 두지 않는다. 아직 S3의 안전 주입 구간을
// 측정하지 않았으므로, 누군가 예시값을 운영 기준으로 오해한 채 실행하지 못하게
// 시작 전에 모두 명시하도록 강제한다.
//
// 식별용 X-Scenario 헤더를 넣지 않는다. 일반 클라이언트와 같은 주문 본문과
// Idempotency-Key/X-Session-Key만 보내 Agent가 정답 라벨을 읽지 못하게 한다.

import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

for (const name of ['RATE', 'DURATION', 'PRE_ALLOCATED_VUS', 'MAX_VUS']) {
  if (!__ENV[name]) throw new Error(`S3 주문 부하에는 -e ${name}=... 입력이 필요합니다`);
}

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const BROADCAST_ID = __ENV.BROADCAST_ID || 'bc_1042';
const SKU_ID = __ENV.SKU_ID || '88213';
const QTY = Number(__ENV.QTY || 1);
const RATE = Number(__ENV.RATE);
const DURATION = __ENV.DURATION;
const PRE_ALLOCATED_VUS = Number(__ENV.PRE_ALLOCATED_VUS);
const MAX_VUS = Number(__ENV.MAX_VUS);

if (!Number.isFinite(RATE) || RATE <= 0) throw new Error('RATE는 양수여야 합니다');
if (!Number.isInteger(QTY) || QTY <= 0) throw new Error('QTY는 양의 정수여야 합니다');
if (!Number.isInteger(PRE_ALLOCATED_VUS) || PRE_ALLOCATED_VUS <= 0) {
  throw new Error('PRE_ALLOCATED_VUS는 양의 정수여야 합니다');
}
if (!Number.isInteger(MAX_VUS) || MAX_VUS < PRE_ALLOCATED_VUS) {
  throw new Error('MAX_VUS는 PRE_ALLOCATED_VUS 이상의 정수여야 합니다');
}

const accepted = new Counter('orders_accepted');
const paymentFailed = new Counter('orders_payment_failed');
const unexpected = new Counter('orders_unexpected_response');

export const options = {
  scenarios: {
    orders: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: PRE_ALLOCATED_VUS,
      maxVUs: MAX_VUS,
    },
  },
  thresholds: {
    // 품절·형식 오류·연결 실패는 PG 장애 시나리오가 아니라 실험 조건 실패다.
    orders_unexpected_response: ['count==0'],
    // 도착률을 못 지키면 delay_ms × RPS 조건 자체가 달라지므로 결과를 폐기한다.
    dropped_iterations: ['count==0'],
  },
};

function uuidV4() {
  // k6 런타임에서도 동작하는 UUID v4 모양. 인증 토큰이 아니라 요청 멱등성과
  // 익명 세션 식별에만 쓰므로 암호학적 난수일 필요는 없다.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.floor(Math.random() * 16);
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export default function () {
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
    // 비-JSON 오류는 아래 unexpected로 센다.
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
