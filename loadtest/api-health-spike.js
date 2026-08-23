// ALB·인그레스 경로가 스파이크를 받아내는지만 본다. **`/api/health` 를 때린다.**
//
// 이름에 spike 가 붙어 있지만 주문·재고·커넥션 풀은 전혀 안 지난다.
// 선착순 스파이크(재고 차감, 멱등성, SQS, 오버셀)를 재려면 주문 시나리오를
// 따로 만들어야 한다 — 이 파일로는 못 한다.
// 이 파일이 실제로 잡아내는 것은 급증 자체를 경로가 버티는가다 —
// ALB 타깃 등록, 인그레스 라우팅, 파드 기동 공백 같은 것.
//
//   k6 run -e BASE_URL=http://localhost:8000 loadtest/api-health-spike.js
//
// 클러스터 밖에서 돌릴 때는 port-forward를 걸어 두거나 Ingress 주소를 넣는다.

import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

export const options = {
  scenarios: {
    spike: {
      executor: 'ramping-arrival-rate',
      // 도착률 기준으로 잡는다. VU 기준으로 하면 서버가 느려질 때
      // 요청 자체가 줄어들어 부하가 약해지는 착시가 생긴다.
      startRate: 5,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      maxVUs: 300,
      stages: [
        { target: 5, duration: '20s' },    // 평상시
        { target: 300, duration: '10s' },  // 쿠폰 오픈 — 여기서 터진다
        { target: 300, duration: '40s' },  // 몰린 상태 유지
        { target: 5, duration: '20s' },    // 진정
      ],
    },
  },
  thresholds: {
    // 스파이크 중에도 이 선을 넘으면 사용자는 실패로 느낀다.
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<800', 'p(99)<2000'],
  },
};

export default function () {
  // 루트가 아니라 /api/health 를 때린다. ALB 하나를 프론트엔드와 공유하므로
  // `/` 는 프론트 정적 페이지로 가고, 그러면 api 는 부하를 전혀 안 받는다.
  // 경로 규약은 docs/contracts.md 1.1.
  const res = http.get(`${BASE_URL}/api/health`);
  check(res, {
    '200': (r) => r.status === 200,
    '응답이 ok': (r) => r.body && r.body.includes('ok'),
  });
}
