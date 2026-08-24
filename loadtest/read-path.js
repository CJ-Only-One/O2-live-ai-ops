// 읽기 경로 포화점 측정 (architecture.md 12.1 · 12.2).
// 방송 진입 스냅샷 `GET /api/broadcasts/{id}` 하나만 때린다.
//
// 한 번에 램프업하지 않고 **고정 도착률로 짧게 여러 번** 돌린다.
// 계단 하나가 요약 하나로 떨어져야 "어느 RPS 에서 꺾였나"를 그래프 없이 읽는다.
// 램프 하나로 몰아서 돌리면 요약이 전 구간 평균이라 꺾인 지점이 뭉개진다.
//
//   ALB=k8s-o2dev-frontend-0af27d967f-1008618203.ap-northeast-2.elb.amazonaws.com
//   for r in 10 25 50 100 200 400; do
//     echo "=== ${r} RPS ==="
//     k6 run -e BASE_URL=http://$ALB -e RATE=$r loadtest/read-path.js || break
//   done
//
// `|| break` 가 중요하다. 임계를 넘긴 계단이 나오면 거기가 포화점이고,
// 그 위를 더 때려봐야 나오는 건 큐 대기 시간뿐이다.
//
// ── 돌리기 전에 ──────────────────────────────────────────────────────────
// 1. 캐시를 비운다. 워밍된 상태로 재면 스탬피드를 못 잡는다 (12.1).
//    로컬 캐시는 인프로세스 1초(services/broadcast.py `LOCAL_TTL`)라
//    파드를 재시작해야 비고, Valkey 는 메타 키만 지운다.
//      kubectl rollout restart deploy/api -n o2-dev
//    **`stock:*` 은 지우지 마라. 재고는 Valkey 가 원본이다 (D-07).**
//    지우면 재고가 0 으로 표시되고 다음 주문 측정까지 망가진다.
//
// 2. Datadog 모니터를 뮤트한다. 안 하면 알람이 `@webhook-dify` 로 흘러가
//    에이전트가 깨어난다. 지금은 재는 단계지 진단하는 단계가 아니다.
//    장애 주입 단계에서 푼다.
//
// 3. idle 영점을 먼저 찍는다 — `kubectl top nodes`. Datadog 에이전트가
//    노드당 몇 m 을 먹는지 모르면 나중에 그 CPU 가 앱 건지 구분 못 한다.
//
// ── 앱 병목으로 착각하면 안 되는 천장 둘 ─────────────────────────────────
// - 요청 1건마다 Valkey MGET 1회. 로컬 캐시가 맞아도 재고는 **항상** 왕복한다
//   (`_stock_display`). 그래서 캐시 히트율이 높아도 Valkey RTT 가 하한이다.
// - 요청 1건마다 `inventory.check` 이벤트 1건. Kinesis 가 `shard_count = 1`
//   이라 1,000 records/sec 가 상한이다 (06-datastream/kinesis.tf).
//   채팅·주문 이벤트가 이 샤드를 같이 쓴다.
//
// 캐시가 어느 계층에서 났는지는 **응답에 안 실린다.** 이벤트로만 나가므로
// 계층별 흡수율(12.2)은 k6 가 아니라 Datadog 쪽에서 본다.

import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const BROADCAST_ID = __ENV.BROADCAST_ID || 'bc_1042'; // LIVE + ON_SALE 상품이 있는 것
const RATE = Number(__ENV.RATE || 50);
const DURATION = __ENV.DURATION || '60s';
const PATTERN = __ENV.PATTERN || 'plain';
const JITTER_MS = Number(__ENV.JITTER_MS || 0);
const EMIT_CLIENT_EVENTS = __ENV.EMIT_CLIENT_EVENTS === 'true';

if (!['plain', 'human', 'ambiguous'].includes(PATTERN)) {
  throw new Error(`지원하지 않는 PATTERN=${PATTERN}`);
}
if (PATTERN !== 'plain') {
  if (!__ENV.JITTER_MS || JITTER_MS <= 0) {
    throw new Error(`${PATTERN} 패턴에는 -e JITTER_MS=... 입력이 필요합니다`);
  }
  if (!EMIT_CLIENT_EVENTS) {
    throw new Error(`${PATTERN} 패턴에는 -e EMIT_CLIENT_EVENTS=true가 필요합니다`);
  }
}

// 실제 브라우저가 보낼 법한 값만 섞는다. X-Scenario 같은 식별 헤더는 Agent가
// 정답 라벨로 읽을 수 있으므로 만들지 않는다.
const USER_AGENTS = [
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/127 Safari/537.36',
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148',
  'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/127 Mobile Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.5 Safari/605.1.15',
];

let humanEntered = false;

function requestContext() {
  if (PATTERN === 'plain') return { headers: {}, shouldEnter: false };

  const vu = exec.vu.idInTest;
  const iteration = exec.scenario.iterationInTest;
  const fresh = `${Date.now()}-${vu}-${iteration}-${Math.floor(Math.random() * 1e9)}`;
  const session = PATTERN === 'human' ? `viewer-${vu}` : `viewer-${fresh}`;
  const uaIndex = PATTERN === 'human' ? vu % USER_AGENTS.length : Math.floor(Math.random() * USER_AGENTS.length);

  // human은 VU별 세션을 유지하고 최초 진입만 발행한다. ambiguous는 자동화가
  // 요청마다 새 세션·UA를 골라 사용자 집중도와 규칙성을 의도적으로 흐린다.
  const shouldEnter = PATTERN === 'ambiguous' || !humanEntered;
  if (PATTERN === 'human') humanEntered = true;

  return {
    headers: {
      'x-session-key': session,
      'user-agent': USER_AGENTS[uaIndex],
    },
    shouldEnter,
  };
}

export const options = {
  scenarios: {
    read: {
      // 도착률 기준. VU 기준으로 하면 서버가 느려질 때 요청이 같이 줄어들어
      // 부하가 약해지는 착시가 생긴다 (spike.js 와 같은 이유).
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: DURATION,
      // 응답이 느려지면 VU 가 모자라 도착률을 못 지킨다. 그러면 서버가 아니라
      // 생성기가 실패한 것이고 그 계단은 무효다.
      //
      // RATE 를 그대로 쓰는 것은 "응답 1초"를 가정한다는 뜻이다. RATE/4
      // (250ms 가정)로 잡았더니 300 RPS·p95 267ms 에서 80개가 필요한데
      // 75개뿐이라 64건이 밀렸다. VU 는 싸다 — 400 RPS 에서도 k6 메모리가
      // 295MB 였다. 넉넉히 잡는 편이 맞다.
      preAllocatedVUs: Math.max(20, RATE),
      maxVUs: Math.max(100, RATE * 5),
    },
  },
  thresholds: {
    // 넘었다고 멈추지 않는다. 꺾이는 지점을 보는 게 목적이다.
    http_req_duration: ['p(95)<800', 'p(99)<2000'],
    http_req_failed: [
      'rate<0.01',
      // 다만 완전히 죽은 서버를 계속 때릴 이유는 없다.
      { threshold: 'rate<0.5', abortOnFail: true, delayAbortEval: '20s' },
    ],
    // check() 는 실패해도 k6 종료 코드를 0 으로 둔다. 임계로 올려야 러너의
    // `|| break` 가 걸린다. 이게 없으면 200 에 빈 응답을 통과시킨다.
    //
    // `==1.00` 이 아니라 `>0.99` 인 이유: 계약이 정한 실패 예산이 1% 다
    // (architecture.md 12.1). 300 RPS 에서 18,000 건 중 8 건(0.044%)이
    // 비-200 이었는데, 그때 p95 314ms · p99 573ms 로 나머지 임계는 전부
    // 통과했다. 계약보다 빡빡한 선을 두면 합격을 불합격으로 읽는다.
    checks: ['rate>0.99'],
    // 도착률을 못 지킨 이터레이션. k6 가 부족했다는 뜻이라 많이 나오면
    // 그 계단의 숫자는 전부 무효다.
    //
    // 0 이 아니라 10 인 이유: 첫 틱에 VU 를 깨우는 동안 두세 건이 밀린다.
    // 200 RPS 에서 12,000 건 중 2 건이 그랬는데 VU 는 50 중 3 개만 썼다 —
    // 부족이 아니라 시작 지터다. 진짜 결핍이면 수백~수천 건이 나온다.
    dropped_iterations: ['count<10'],
  },
};

export default function () {
  const ctx = requestContext();
  if (PATTERN !== 'plain') sleep((Math.random() * JITTER_MS) / 1000);

  if (ctx.shouldEnter) {
    const eventRes = http.post(
      `${BASE_URL}/api/broadcasts/${BROADCAST_ID}/events`,
      JSON.stringify({ events: [{ action: 'LIVE_ENTER' }] }),
      {
        headers: { ...ctx.headers, 'content-type': 'application/json' },
        tags: { name: 'client_enter' },
      },
    );
    check(eventRes, { 'client event accepted': (r) => r.status === 202 });
  }

  const res = http.get(`${BASE_URL}/api/broadcasts/${BROADCAST_ID}`, {
    headers: ctx.headers,
    tags: { name: 'read_snapshot' },
  });
  check(res, {
    '200': (r) => r.status === 200,
    // 상태 코드만 보면 빈 껍데기 응답을 통과시킨다. 캐시가 깨졌을 때
    // 200 에 products 가 비어 오는 경우를 여기서 잡는다.
    '상품 배열이 온다': (r) => Array.isArray(r.json('products')),
  });
}
