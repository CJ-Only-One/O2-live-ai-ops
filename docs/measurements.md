# 실측 기록

**직접 재서 나온 숫자만** 남긴다. 추정치와 계획값은 여기 없다
(그건 `architecture.md` 12절이다).

설계 판단의 근거가 된 숫자를 남기는 문서다. 나중에 "왜 동시성을 5로 뒀지"
같은 질문이 나올 때 근거가 여기 있어야 한다. **시스템이 바뀌면 대부분의
숫자가 무효가 되므로, 항목마다 "다시 재야 하는 시점" 을 적는다.**

> **이 파일은 통째로 읽지 않는다.** 아래 인덱스에서 고른 뒤 그 절만 읽는다.

## 인덱스

| # | 무엇을 쟀나 | 다시 재야 할 때 |
|---|---|---|
| M-001 | Dify 워크플로 왕복 시간 | 노드 추가 · 모델 변경 |
| M-002 | Lambda 실행 시간 | 코드 구조 변경 · VPC 변경 |
| M-003 | 버스트 30건 처리 | 동시성 변경 · 워크플로 지연 증가 |
| M-004 | Dify 호스트 자원 사용률 | 인스턴스 등급 변경 · 동시 부하 증가 |
| M-005 | Bedrock 모델 가용성 | 리전·계정 변경 · 모델 실패 시 |
| M-006 | 외부 제약값 (잰 게 아니라 확인한 것) | 공급자 정책 변경 |
| M-007 | 아직 안 잰 것 | — |
| M-008 | EKS 노드 자원 사용률 · 인스턴스 타입별 실측 | 노드 등급·대수 변경 · 파드 추가 |
| M-009 | 읽기 경로 포화점 (api 파드) | replicas·워커 수 변경 · 인스턴스 변경 · 캐시 TTL 변경 |
| M-010 | 채팅 팬아웃 한계 (chat-gateway) | 틱 주기·`MAX_PER_TICK` 변경 · 직렬화 방식 변경 · replicas 변경 |
| M-011 | Chat Signal 외부 WebSocket E2E | Worker timeout·동시성·batch·Queue visibility 변경 |
| M-012 | Agent 공통 진입점 도입 전 Dify runtime baseline | 게시 workflow·모델·Worker·DLQ 정책 변경 |
| M-013 | 전용 Agent entry contract workflow UI 검증 | DSL·입력 계약·Code 검증 로직 변경 |
| M-014 | 주문 확정 워커 처리량 (order-worker) | requests·replicas 변경 · 인스턴스 변경 · RDS 등급 변경 · delete 방식 변경 |
| M-015 | warm 경로 인입·집계 실측과 집계기 지연 | 샤드 수·`parallelization_factor` 변경 · 부하 패턴 변경 |
| M-016 | APM trace 지표의 태그 축 (파드 축이 있는가) | `ddtrace` 버전 변경 · Datadog Agent 설정 변경 · 통합 서비스 태깅 도입 |
| M-017 | Incident Correlator 합성 E2E와 처리시간 | Correlator 코드·메모리·DynamoDB index·Queue 설정 변경 · 실제 source Adapter 연결 |
| M-018 | Agent Invocation Worker 첫 Shadow E2E와 fail-closed | Worker IAM·ledger finalize·Dify 계약·Queue 설정 변경 |
| M-019 | 파드 Ready 시간 (사전 확장 리드타임) | `readinessProbe` 설정 변경 · 이미지 크기 변경 · 인스턴스 타입 변경 · 노드 여유 부족으로 Karpenter 개입 시 |


기록 형식은 **날짜 · 조건 · 값** 이다. 다시 쟀으면 절을 새로 만들지 말고
그 절의 표에 **행을 추가**한다. 조건이 다르면 값도 다르므로 조건을 꼭 적는다.

번호를 추가하면 **상단 인덱스에도 한 줄 넣는다.** 빠뜨리면 CI 가 막는다
(`scripts/check-docs-index.sh docs/measurements.md M`).

---

## M-001. Dify 워크플로 왕복 시간

Dify 가 스스로 보고하는 `data.elapsed_time`. 네트워크와 Lambda 오버헤드는 빠진 값이다.

| 날짜 | 조건 | elapsed_time | 토큰 | 단계 |
|---|---|---|---|---|
| 2026-08-19 | LLM 1노드 · Nova Lite V1 · temp 0.7 · 변수 5개 | **2.477s** | 763 | 3 |
| 2026-08-19 | 같은 구성 · temp 0.2 · 변수 7개 | **2.529s** | — | 3 |
| 2026-08-19 | 같은 구성 (재측정) | **2.554s** | — | 3 |
| 2026-08-22 | Hot Path·Runbook Lookup API 추가 후 · app-run(실제 트리거) · 승인 없음 | **39.8s*** | — | — |

세 번 모두 2.5초 근처다. 변수를 둘 늘리고 temperature 를 낮춘 것은
소요 시간에 영향이 없었다.

\* `data.elapsed_time` 이 아니라 Dify Postgres `workflow_runs.finished_at -
created_at` 값이다 (EC2 안에서 직접 조회). 같은 컬럼이 아니므로 위 세 줄과
1:1로 비교하지 말 것.

**해석** — 이 시간의 대부분은 Bedrock 응답 대기다. CPU 가 아니라 I/O 대기라서
호스트를 키워도 이 값은 줄지 않는다 (M-004 참조).

**Datadog 조회(pull) 붙인 뒤 실측** — 위에서 "10~30초대가 될 것" 이라 예상했던
것보다 크게 늘었다. Hot Path·Runbook Lookup API 가 노드마다 추가 HTTP 호출을
만들면서 39.8s 까지 나왔고, 다른 실행에서는 58s 까지 관측됐다 — 이 58s 값이
Worker Lambda의 기존 55초 클라이언트 타임아웃을 근소하게 넘겨 타임아웃 오류를
냈다 (`docs/troubleshooting.md` T-019).

**다시 재야 할 때** — 노드를 추가할 때, 모델을 바꿀 때. 그 값이 나오면
M-002 · M-003 도 같이 무효가 된다.

---

## M-002. Lambda 실행 시간

CloudWatch `REPORT` 줄의 `Duration`.

### 동기 단일 함수 (VPC 안) — 폐기된 구조

| 날짜 | 호출 | Duration | Init | Max Memory |
|---|---|---|---|---|
| 2026-08-19 | 1회차 (콜드) | 2,917ms | 127ms | 54MB |
| 2026-08-19 | 2회차 (웜) | 2,489ms | — | 54MB |
| 2026-08-19 | 3회차 (웜) | 2,918ms | — | 54MB |
| 2026-08-19 | 계약 반영 후 | 2,554ms | — | — |

### Ingress / Worker 분리 후

| 날짜 | 함수 | 위치 | Duration | Init | Max Memory |
|---|---|---|---|---|---|
| 2026-08-19 | Ingress | VPC 밖 | **623ms** | 366ms | 93MB |
| 2026-08-19 | Worker | VPC 안 | 5,109ms | 303ms | 90MB |
| 2026-08-21 | Worker (이력, 검색 실패) | VPC 안 | 4,471ms | 240ms | **93MB** |
| 2026-08-21 | Worker (이력, 검색 성공) | VPC 안 | 6,335ms | 305ms | **93MB** |

### 이력 기능이 얹은 비용 (2026-08-21)

같은 콜드 실행 안에서 `print` 시각 차로 구간을 갈랐다.

| 구간 | 검색 실패 회차 | 검색 성공 회차 |
|---|---|---|
| 임베딩 + 벡터 검색 | 1,317ms | **1,379ms** |
| Dify 왕복 | 518ms | 2,266ms |
| S3 + S3 Vectors 저장 | 513ms | 537ms |

검색이 실제로 3건을 돌려준 회차(`matched 3 of 3`)와 권한 오류로 즉시 끊긴
회차의 차이가 **62ms 뿐이다.** 시간의 대부분은 S3 Vectors 질의가 아니라
**Bedrock 임베딩 왕복**이라는 뜻이다. 검색을 최적화할 일이 생기면 벡터
질의가 아니라 임베딩을 먼저 본다.

Dify 왕복 편차(518ms vs 2,266ms)가 구간 중 가장 크다. 전체 Duration 비교가
의미 없는 이유이고, 두 회차의 4,471ms / 6,335ms 차이는 대부분 여기서 나왔다.

Duration 이 5,109ms 에서 4,471ms 로 **줄어든 것은 이력 덕이 아니다.**
이 회차의 Dify 왕복이 0.166s 로 유난히 짧았다(테스트 알림). 두 값은
Dify 쪽 편차가 커서 직접 비교하면 안 된다.

**메모리는 90MB → 93MB, +3MB 다.** `bedrock-runtime`·`s3`·`s3vectors` 클라이언트
셋을 더 만든 대가가 이만큼이다. 아래 "의존성을 추가하면 다시 봐야 한다" 에
대한 답이고, 128MB 할당을 올릴 이유는 아직 없다.

**해석**

Datadog 이 기다리는 시간이 **2,900ms → 623ms** 로 줄었다. Ingress 를 VPC 밖에
둬서 ENI 를 만들지 않은 것이 콜드스타트에 그대로 반영됐다.

Worker 의 5,109ms 는 **콜드 실행**이다. Dify 왕복 2,529ms 를 빼면 나머지 약 2.6초가
초기화와 Secrets Manager 첫 조회다. 웜 실행은 더 짧을 것이나 아직 안 쟀다 (M-007).

메모리는 셋 다 128MB 할당에 90MB 안팎을 쓴다. 여유가 크지 않으므로
의존성을 추가하면 다시 봐야 한다.

**다시 재야 할 때** — 코드 구조를 바꿀 때, VPC 배치를 바꿀 때, pull 을 붙일 때.

---

## M-003. 버스트 30건 처리

**이 파이프라인이 만들어진 이유를 검증하는 측정이다.**

조건: 알림 30건을 `xargs -P 30` 으로 Function URL 에 동시 발사.
Datadog 을 거치지 않고 직접 쏴서 도착 시점을 몰아준다.

| 날짜 | 구조 | HTTP 200 | 큐 적재 | 완료 | 오류 | DLQ | 최대 동시 실행 |
|---|---|---|---|---|---|---|---|
| 2026-08-19 | 비동기 (Ingress/Worker) | **30 / 30** | 30 | **30** | 0 | 0 | **5** |

처리된 ID 를 `burst-1` 부터 `burst-30` 까지 전부 확인했다. 누락 없음.

### 이전 구조는 왜 안 쟀나

동기 단일 함수 + 예약 동시성 5 에서는 여섯 번째부터 429 가 나가고
**Datadog 은 429 를 재시도하지 않는다** (M-006). 즉 25건이 사라지는 것이
구조상 확정이라 실제로 손실을 만들어 재지는 않았다.

### 최대 동시 실행이 5인 이유

`alert_relay_max_concurrency` 기본값이 5다. 상한이 실제로 물렸다는 것이
이 숫자의 의미다 — 30건이 동시에 와도 Dify 에 다섯 개만 간다.

**이 값은 아직 근거 없이 정해진 값이다.** Dify 가 몇 개까지 감당하는지
안 쟀기 때문이다 (M-007).

**다시 재야 할 때** — 동시성을 바꿀 때, 워크플로가 느려질 때.
pull 을 붙이면 30건 처리에 걸리는 총 시간이 크게 늘어나므로 그때 다시 잰다.

---

## M-004. Dify 호스트 자원 사용률

`i-0672d1384757a4c0c` (t3.large, 2 vCPU / 8 GiB), CloudWatch 24시간.

| 날짜 | 지표 | 평균 | 최대 |
|---|---|---|---|
| 2026-08-19 | CPUUtilization | **6.9%** | **25.6%** |
| 2026-08-19 | CPUCreditBalance | 864 | 864 (상한 포화) |
| 2026-08-19 | CPUSurplusCreditBalance | 0 | 0 |

**해석 — 인스턴스를 키울 근거가 없다.**

CPU 를 7% 쓰고 있고 버스트 크레딧은 만점에서 한 번도 안 내려갔다.
등급을 올리면 노는 CPU 가 늘어날 뿐이다.

동시 처리가 막힌다면 하드웨어가 아니라 **Dify 의 워커 개수 설정**이 상한이다.
인스턴스 등급을 올리기 전에 `.env` 를 먼저 본다.

**다시 재야 할 때** — 인스턴스 등급을 바꿀 때, 동시 부하를 실제로 걸었을 때.
지금 수치는 알림이 하루 몇 건 수준일 때의 값이라 부하 상태를 대표하지 않는다.

---

## M-005. Bedrock 모델 가용성

`ap-northeast-2` 에서 `bedrock-runtime converse` 를 실제로 호출해 확인.
목록 조회가 아니라 호출이므로 권한과 프로필이 모두 반영된 결과다.

| 날짜 | 모델 ID | 결과 |
|---|---|---|
| 2026-08-19 | `apac.amazon.nova-lite-v1:0` | OK |
| 2026-08-19 | `apac.amazon.nova-micro-v1:0` | OK |
| 2026-08-19 | `global.anthropic.claude-opus-5` | OK |
| 2026-08-19 | `global.anthropic.claude-sonnet-5` | OK |
| 2026-08-19 | `global.anthropic.claude-sonnet-4-6` | OK |
| 2026-08-19 | `apac.anthropic.claude-3-5-sonnet-20241022-v2:0` | ResourceNotFoundException |
| 2026-08-19 | `global.anthropic.claude-haiku-4-5-20251001-v1:0` | ResourceNotFoundException |

**해석** — `apac.` 프로필에는 신형 Claude 가 없고 `global.` 에는 있다.
팀 공유 문서가 이와 반대로 안내하고 있었다 (T-001).

**다시 재야 할 때** — 리전이나 계정이 바뀔 때, 모델 호출이 실패할 때.
AWS 가 프로필을 수시로 추가·정리하므로 이 표는 빨리 낡는다.
확인 명령은 T-001 에 있다.

---

## M-006. 외부 제약값

잰 것이 아니라 **문서에서 확인한 것**이다. 설계가 이 값들 위에 서 있어서 같이 둔다.

| 값 | 출처 | 설계에 미친 영향 |
|---|---|---|
| Datadog webhook 타임아웃 **15초** | Datadog Webhooks 문서 | pull 로 워크플로가 느려지면 중복 실행이 생긴다 |
| Datadog webhook 재시도 **5회** | 같은 문서 | 실패 시 최대 6번 실행 = 토큰 6배 |
| 재시도 조건 **5XX 와 내부 오류만** | 같은 문서 | **429 는 재시도 안 한다.** 동기 구조에서 알림이 영구 소실된 원인 |
| Lambda 최대 타임아웃 **900초** | AWS | 워크플로가 15분을 넘기면 동기 호출로는 불가능 |
| 비동기 호출 재시도 최대 **6시간** | AWS | 대기열이 이만큼 버텨준다 |
| SSM 세션 유휴 상한 **60분** / 절대 **6시간** | AWS | 터널이 끊기는 주기 |
| t3.large CPU 크레딧 상한 **864** | AWS | M-004 의 "만점" 기준 |
| Nova Lite 단가 (`ap-northeast-2`) 입력 **$0.0000355~0.000071 / 1K**, 출력 **$0.000142~0.000284 / 1K** | AWS Pricing API, 2026-08-21 | 현재 워크플로가 763토큰(M-001)이라 알림 하나에 0.005센트다. 8월 Bedrock 청구가 **$0.07** 인 이유. **모델을 Claude 로 바꾸면 자릿수가 뛴다** — 그때는 위의 "재시도 6배"와 가짜 알람 볼륨이 실제 비용이 된다 |

**다시 확인해야 할 때** — 공급자가 정책을 바꿀 때. 특히 Datadog 재시도 조건은
이 설계의 전제라, 바뀌면 구조를 다시 봐야 한다.

---

## M-007. 아직 안 잰 것

**여기 있는 항목은 지금 추측으로 정해져 있다는 뜻이다.**

| 무엇 | 왜 필요한가 | 어떻게 재나 |
|---|---|---|
| **Dify 동시 처리량 상한** | Worker 예약 동시성(현재 5)의 유일한 근거가 된다. 지금은 근거가 없다 | 터널을 열고 `/v1/workflows/run` 을 `xargs -P 10` 으로 동시에 던진다. 200 이 유지되고 응답 시간이 크게 안 늘면 그 수를 감당하는 것 |
| pull 붙인 뒤 워크플로 소요 | Worker 타임아웃과 동시성을 다시 정해야 한다 | M-001 과 같은 방법 |
| Worker 웜 실행 시간 | 지금 값(5,109ms)은 콜드 실행이라 정상 상태를 대표하지 않는다 | 연속 호출 후 REPORT 확인 |
| DLQ 도달 실제 소요 | 설계상 약 3분이지만 확인 안 했다 | Dify 를 일부러 막고 이벤트 하나를 흘린다 |
| 알람 발화까지 실제 소요 | "1분 안에 운다" 가 아직 주장이다 | 위와 같은 실험에서 SNS 수신 시각을 본다 |
| ~~`chat-gateway` 파드당 WebSocket 연결 상한~~ | **해결됨 (M-010)** — 연결당 약 11KB 이고, 2파드가 4,000 연결을 메모리 16% 로 받는다. 다만 상한은 연결 수가 아니라 **전달 아이템/s** 였다 | — |
| ~~`api`·`order-worker` 가 무부하에서 1 vCPU 를 쓰는 이유~~ | **해결됨** — 이벤트 SDK 의 유휴 스핀이었다 (T-013, M-008). 수정 후 4m·1m | — |
| CPU 크레딧 회복 실소요 | 빚 576 을 시간당 약 20 씩 갚는다는 계산으로 "하루쯤" 이라고 적어 뒀지만 재지 않았다. 부하 테스트를 언제 시작할 수 있는지가 여기서 정해진다 | `CPUCreditBalance` 와 `CPUSurplusCreditBalance` 를 하루 간격으로 조회한다 (조회 명령은 T-013) |

맨 위 항목이 가장 급하다. **처리량 상한을 모르는 채로 동시성을 정해 뒀고,
그 값이 이 파이프라인 전체의 처리량이다.**

아래 두 항목은 부하 테스트의 전제다. 특히 마지막 항목을 모르는 채로 부하를
걸면 **무엇을 재는지 알 수 없다.**

---

## M-008. EKS 노드 자원 사용률 (무부하)

`o2-eks`, `t3.small` × 3 (노드그룹 `max_size = 3` 이므로 **현재가 최대치**),
2026-08-20 17:40 KST. `kubectl top` 값이며 요청량이 아니라 **실사용량**이다.
metrics-server 를 넣기 전에는 이 값을 볼 수단 자체가 없었다.

측정 조건 — 방송·부하 없음. 마지막 주문 처리가 같은 날 00:59 였다.

### 파드 슬롯

| 날짜 | 전체 | 노드별 | 상한 |
|---|---|---|---|
| 2026-08-20 | **32 / 33** | 10 · 11 · 11 | `t3.small` max-pods 11 × 3 노드 |

**한 칸 남았다.** 세 대 중 두 대는 이미 꽉 찼고 노드도 `max_size` 라 더 못 붙는다.
D-037 이 metrics-server 를 "1칸" 으로 계산한 것은 맞았지만, 그것이 **마지막에서
두 번째 칸**이었다.

### 메모리

노드 allocatable 은 1,466 MiB (`t3.small` 2 GiB 중).

| 날짜 | 노드 | 사용 | 비율 |
|---|---|---|---|
| 2026-08-20 | ip-10-0-124-21 | 1,176 MiB | 82% |
| 2026-08-20 | ip-10-0-75-76 | 1,141 MiB | 79% |
| 2026-08-20 | ip-10-0-158-75 | 1,003 MiB | 70% |

노드당 여유가 250 MiB 안팎이다. 가장 큰 소비자는 **Datadog 으로 네임스페이스
합계 884 MiB** — 데몬셋 3개(264·243·224 MiB)와 클러스터 에이전트(134 MiB)다.
`04-platform/datadog.tf` 의 limit 은 에이전트 512 MiB · 클러스터 에이전트
384 MiB 이므로 한도에 닿지는 않았다.

### 앱 파드 (무부하)

| 날짜 | 조건 | 파드 | CPU | 메모리 |
|---|---|---|---|---|
| 2026-08-20 17:40 | SDK `4792fca` (스핀 있음) | api | **987m** | 131 MiB |
| 2026-08-20 17:40 | SDK `4792fca` (스핀 있음) | order-worker | **955m** | 98 MiB |
| 2026-08-20 20:25 | SDK `5b4d86e` (수정 후) | api | **4m** | 114 MiB |
| 2026-08-20 20:25 | SDK `5b4d86e` (수정 후) | order-worker | **1m** | 96 MiB |
| 2026-08-20 | — | chat-gateway (2개) | 1~2m | 42 · 45 MiB |
| 2026-08-20 | — | mediamtx | 1m | 18 MiB |
| 2026-08-20 | — | frontend | 1m | 3 MiB |

**17:40 값은 정상이 아니었다.** 이벤트 SDK 의 유휴 스핀 버그(아래) 때문이며,
`5b4d86e` 를 배포한 뒤 `chat-gateway` 와 같은 한 자리 millicore 로 떨어졌다.
파드 안에서 스레드별 CPU 시간을 다시 보니 최댓값이 353 ticks(3.5초)로,
수정 전 같은 자리의 3,243,366 ticks(약 9시간)와 비교된다.

**무부하 기준선으로는 20:25 행을 쓴다.**

`chat-gateway` 의 42·45 MiB 가 **부하 테스트에서 연결당 메모리를 계산할
절편**이다. 이 시점 연결 수는 사실상 0 이다.

### CPU 크레딧이 고갈돼 있다

`api` 와 `order-worker` 가 트래픽 0 인데 각각 약 1 vCPU 를 계속 쓴다.
20초 간격 두 번 측정에서 값이 그대로였다(987m/988m, 955m/960m). 스파이크가
아니라 정상 상태다. 두 파드 모두 CPU limit 이 없어 제한 없이 올라간다.

`t3` 는 버스트 인스턴스이고, 결과는 CloudWatch 에 그대로 남아 있다.

| 날짜 | 인스턴스 | 크레딧 모드 | CPUCreditBalance | CPUSurplusCreditsCharged (시간당) |
|---|---|---|---|---|
| 2026-08-20 | i-064b4a174a734c223 | `unlimited` | **0** (09시부터 종일) | 약 64 |
| 2026-08-20 | i-0195fae4fbba9bdf2 | `unlimited` | — | 약 42 |

`unlimited` 는 T3 기본값이다. `describe-instance-credit-specifications` 로 확인했다.

단가는 `aws pricing` 으로 확인했다 — 서울 리전 Linux T3 초과 크레딧이
**vCPU-시간당 $0.05** (`APN2-CPUCredits:t3`, SKU `HFY9FYMUY3NRAMS5`).
두 노드 합계 시간당 약 106 크레딧이면 약 1.8 vCPU-시간이므로 **시간당 약 $0.09**,
한 달 환산 약 $64 가 된다. `t3.small` 세 대 온디맨드보다 큰 금액이다.

**단, 실제 청구는 확인되지 않았다.** 2026-08-20 기준 Cost Explorer 의 EC2
usage type 목록에 `APN2-CPUCredits:t3` 줄이 **없다**(8/14~8/21 일별 조회,
`Estimated: true`). 잔고가 0 이 된 것이 같은 날 09시라 반영 지연일 가능성이
가장 크지만, 지표 해석이 틀렸을 가능성도 남아 있다.

**위 금액은 계산값이지 청구 실측이 아니다.** 하루 뒤 같은 조회로 확정할 것.

**원인은 이벤트 SDK 였다 (해결됨).** `o2events` 의 emitter 스레드가 큐가 비어
있으면 `deadline` 을 갱신하지 않아 `get()` 의 timeout 이 0.0 으로 고정되고,
루프가 CPU 를 한 코어 통째로 태웠다. **이벤트가 없을수록 더 태우는** 모양이라
한가한 서비스에서 먼저 드러났다. `chat-gateway` 가 멀쩡했던 것은 TypeScript 라
이 SDK 대신 얇은 자체 클라이언트를 쓰기 때문이다.

수정은 o2-sdk-for-event#2 (`5b4d86e`, 0.3.1), 반영은 이 저장소 #91 이다.
진단 절차는 T-013 에 있다.

### 수정 후 (2026-08-20 20:25)

| 인스턴스 | CPU | 사용률 | 메모리 |
|---|---|---|---|
| ip-10-0-124-21 | 1,055m → **101m** | 54% → **5%** | 1,219 MiB (85%) |
| ip-10-0-75-76 | 1,375m → **290m** | 71% → **15%** | 1,163 MiB (81%) |
| ip-10-0-158-75 | 474m → **423m** | 24% → **21%** | 1,033 MiB (72%) |

`t3.small` 의 baseline 은 노드당 400m 이다. 두 노드가 그 아래로 내려왔으므로
**크레딧을 쓰는 쪽에서 모으는 쪽으로 돌아섰다.** 다만 빚(`CPUSurplusCreditBalance`
576)을 먼저 갚아야 하므로 `CPUCreditBalance` 가 0 에서 올라가기까지 하루쯤
걸린다. 회복이 실제로 시작됐는지는 아직 확인하지 않았다.

**메모리는 안 줄었다.** 85% · 81% · 72% 그대로이고 파드 슬롯도 32/33 이다.
CPU 가 풀렸다고 부하 테스트 준비가 끝난 것은 아니다.

### 해석 — 4,000 축소 부하 테스트의 전제가 안 갖춰졌다

`architecture.md` 12.1 의 Peak 축소값이 4,000 인데, 지금 클러스터는

- 파드를 **1개**만 더 띄울 수 있고 (노드도 최대치)
- 노드당 메모리 여유가 **250 MiB** 이며
- CPU 크레딧이 **아직 0** 이다 — 스핀은 멈췄지만 빚 576 을 갚는 중이라
  회복까지 하루쯤 걸린다

`t3.medium` 승격(max-pods 17, 메모리 2배, `variables.tf` 기준 3주 약 $27)이
선택지지만, **파드당 연결 상한을 모르는 채로 올리는 것은 근거 없는 증설이다.**
프로모션 축소값 2,000 으로 먼저 재서 연결당 비용을 잡는 편이 순서에 맞다.

### 인스턴스를 바꾸고 다시 잼 (2026-08-21)

위 제안(`t3.medium` 승격)은 **틀렸다.** t3 는 크기를 올려도 baseline 이 vCPU 수에만
걸려 있어(t3.medium 도 2 vCPU × 20% = 400m) CPU 여유가 그대로다. 메모리와 파드
슬롯만 늘어난다. 실제로는 비버스터블로 가야 했다.

| 날짜 | 항목 | t3.small | m6i.large | c6i.large |
|---|---|---|---|---|
| 2026-08-21 | 표기 메모리 | 2 GiB | 8 GiB | 4 GiB |
| 2026-08-21 | capacity 메모리 | 1,908Mi | 7,778Mi | 3,814Mi |
| 2026-08-21 | **allocatable 메모리** | 1,432Mi | 7,104Mi | **3,140Mi** |
| 2026-08-21 | 오버헤드 차이 | 476Mi | 674Mi | 674Mi |
| 2026-08-21 | **max_pods** | 11 | 29 | **29** |
| 2026-08-21 | allocatable CPU | 1,930m (지속은 400m) | 1,930m | **1,930m** |
| 2026-08-21 | 서울 온디맨드 2대 월 | $56(3대) | $170 | **$138** |

**오버헤드 공식이 세 타입에서 모두 맞았다.** 이제 재보지 않고 계산으로 고른다.

```
오버헤드 = 255 + (11 × max_pods) + 100(eviction)
t3.small  = 255 + 11×11 + 100 = 476   ← 관측값과 일치
m6i.large = 255 + 11×29 + 100 = 674   ← 관측값과 일치
c6i.large = 255 + 11×29 + 100 = 674   ← 관측값과 일치
```

`max_pods` 는 메모리가 아니라 ENI 구성이 정한다(`ENI 수 × (ENI당 IPv4 − 1) + 2`).
m6i.large 와 c6i.large 는 둘 다 ENI 3 × IP 10 이라 29 로 같다.

**유휴 사용량** (DaemonSet 포함, 부하 없음)

| 날짜 | 타입 | 노드 | CPU | 메모리 |
|---|---|---|---|---|
| 2026-08-21 | m6i.large | 파드가 몰린 쪽 | 367~535m | 약 1,800Mi |
| 2026-08-21 | m6i.large | 나머지 | 35~66m | 약 690Mi |
| 2026-08-21 | c6i.large | 재분배 후 노드1 | 252m | 1,694Mi (53%) |
| 2026-08-21 | c6i.large | 재분배 후 노드2 | 434m | 1,055Mi (33%) |

CPU 의 대부분은 Datadog DaemonSet 이다 — 실측 **노드당 294~397m**. 40분간 5회
측정에 감소 추세가 없어 초기화 값이 아니라 정상 상태다. **t3.small 의 baseline 이
400m 이라 에이전트만으로 지속 한도를 거의 다 쓰던 것**이 t3 계열을 버린 이유다.

### 노드그룹 교체 직후에는 파드가 한쪽으로 쏠린다

교체하면 전 파드가 한꺼번에 Pending 이 됐다가 배치되는데, 그때 먼저 Ready 된
노드로 쏠리고 **쿠버네티스는 나중에 뜬 노드로 재분배하지 않는다.**

2026-08-21 c6i.large 교체 직후 노드1 에 24개 · 노드2 에 4개(DaemonSet 뿐)가 붙었고
**Datadog DaemonSet 이 Pending 으로 남았다.**

```
노드1 allocatable 3,140Mi − 사용 2,956Mi = 184Mi 여유
Datadog 요구                              256Mi   → 못 뜬다
0/2 nodes are available: 1 Insufficient memory, 1 node(s) didn't satisfy NodeAffinity
```

총 requests 는 3,468Mi 로 2대 합계(6,280Mi)의 55% 라 **자리는 있는데 배치가 문제다.**
`kubectl rollout restart deploy -n o2-dev` 로 옮기면 해소된다(노드1 이 꽉 차 있어
새 파드가 노드2 로 간다). 해소 후 노드1 69% · 노드2 41%.

m6i.large(7,104Mi)에서는 같은 쏠림이 나도 다 들어갔다. **4 GiB 는 이 워크로드의
패킹 습성에 여유가 부족하다.** 매니페스트에 `topologySpreadConstraints`
(`app.kubernetes.io/part-of: o2`, maxSkew 1, DoNotSchedule)를 넣어 배치 시점에
갈리게 했다. 다만 **이미 떠 있는 파드는 옮기지 않으므로** 노드를 추가하거나
교체한 뒤에는 여전히 `rollout restart` 가 필요하다.

### Karpenter 노드 확보 시간 (2026-08-23)

Karpenter 도입(D-037 재검토) 후 처음으로 실제 노드를 띄워 봤다. `pause` 파드에
`requests.cpu = 2` 를 걸어 기존 노드에 안 들어가게 만든 뒤, `kubectl get nodeclaims`
를 10초 간격으로 폴링했다.

| 날짜 | 구간 | 시간 |
|---|---|---|
| 2026-08-23 | Pending 파드 → NodeClaim 생성 | 10초 미만 (첫 관측이 7초) |
| 2026-08-23 | NodeClaim 생성 → 노드 등록 | 약 28초 |
| 2026-08-23 | NodeClaim 생성 → **노드 Ready** | **약 39초** |

조건 — `c6i.xlarge` · 온디맨드 · `ap-northeast-2c` · NodePool `default`.

### 어떤 인스턴스가 뜨는지는 파드 requests 가 정한다

이 테스트에서 `xlarge` 가 뜬 것은 **테스트 파드가 2 vCPU 를 요구했기 때문이지
평소 동작이 아니다.** NodePool 은 후보만 넷으로 제한하고(c6i·m6i × large·xlarge,
온디맨드, amd64) 그 안에서 고르는 것은 Karpenter 다 — `weight` 도 우선순위도
걸려 있지 않다. Pending 파드를 bin-pack 해서 들어가는 후보를 추린 뒤 **제일 싼
것**을 띄운다.

DaemonSet 이 노드마다 먼저 차지하는 양 (requests 합, 2026-08-23):

| 구성요소 | CPU | 메모리 |
|---|---|---|
| `aws-node` | 50m | — |
| `kube-proxy` | 100m | — |
| `datadog` | 150m | 320Mi |
| **합계** | **300m** | **320Mi** |

| 타입 | 시간당 | allocatable | DaemonSet 뺀 여유 |
|---|---|---|---|
| c6i.large | $0.096 | 1,930m / 3,140Mi | **1,630m** / 2,820Mi |
| m6i.large | $0.118 | 1,930m / 7,104Mi | **1,630m** / 6,784Mi |
| c6i.xlarge | $0.192 | 약 3,920m / 미측정 | — |
| m6i.xlarge | $0.236 | 미측정 | — |

`xlarge` 두 타입의 allocatable 은 안 쟀다. `max_pods` 가 ENI 구성이 정하는 값이라
위 오버헤드 공식만으로는 확정할 수 없다.

앱 파드 requests 는 두 자릿수 millicore 다 — `api` 100m/384Mi,
`chat-gateway` 100m/192Mi, `order-worker` 50m/192Mi, `mediamtx` 100m/256Mi,
`frontend` 10m/16Mi (2026-08-23). 그래서 실제 스케일아웃은 이렇게 갈린다.

- 보통은 **c6i.large**. CPU 로는 16개, 메모리로는 7개(`api` 기준)가 들어간다
- 메모리가 먼저 차면 **m6i.large**. `c6i.xlarge` 보다 싸면서 메모리가 2배다
- 파드 하나가 1,630m 을 넘게 요구하면 **c6i.xlarge**. 이 테스트가 그 경우였다

c6i 는 단가가 선형이라(large 2 vCPU $0.096, xlarge 4 vCPU $0.192) 큰 것이 와도
vCPU당 가격은 같다. 커지는 것은 최소 구매 단위지 단가가 아니다.


**앱 이미지 pull 은 이 값에 없다.** `pause` 이미지(수백 KB)를 썼다. 실제 앱
파드가 붙으면 ECR pull 이 그만큼 더 붙으므로, 스파이크 대응 시간은 39초보다
크다. 사전 확장이 주력이고 Karpenter 가 안전망인 이유가 이 숫자다(D-041).

기존에 "노드 확보 최소 26초" 로 인용되던 값은 **이 문서에 근거가 없다.**
관리형 노드그룹 교체 때 눈으로 본 값으로 보인다. 위 표를 쓴다.

노드 반납은 `consolidationPolicy = WhenEmpty` · `consolidateAfter = 2h` 라
재보지 않았다. `kubectl delete nodeclaim` 은 즉시 끝났다.

비용 — 노드 수명 약 4.5분에 **$0.014** (`c6i.xlarge` 서울 온디맨드 시간당
$0.192, `aws pricing` 조회값).

**다시 재야 할 때** — 노드 등급이나 대수를 바꿀 때, 파드를 추가할 때,
그리고 부하를 실제로 걸었을 때. 무부하 값은 부하를 대표하지 않는다.
부하 결과는 M-009 · M-010 에 있다.

---

## M-009. 읽기 경로 포화점 (api 파드)

`GET /api/broadcasts/bc_1042` 하나만 60초씩 고정 도착률로 던졌다.
`loadtest/read-path.js` · `loadtest/run.sh`.

**조건 (2026-08-21)** — 노드 m6i.large × 2 / api replicas 1 (uvicorn 워커 1개) /
k6 는 클러스터 밖(MacBook M5, 10코어)에서 ALB 경유. 응답 시간에 인터넷 왕복이 섞여 있다.

| 날짜 | RATE | p95 | p99 | 실패% | api CPU | api MEM | 계약 판정 |
|---|---|---|---|---|---|---|---|
| 2026-08-21 | 10 | 100ms | 261ms | 0.00 | 33m | 116Mi | 통과 |
| 2026-08-21 | 25 | 158ms | 229ms | 0.00 | 64m | 119Mi | 통과 |
| 2026-08-21 | 50 | 93ms | 106ms | 0.00 | 114m | 119Mi | 통과 |
| 2026-08-21 | 100 | 99ms | 119ms | 0.00 | 226m | 126Mi | 통과 |
| 2026-08-21 | 200 | 127ms | 181ms | 0.00 | 433m | 136Mi | 통과 |
| 2026-08-21 | **300** | **314ms** | **573ms** | 0.04 | **664m** | 215Mi | **통과** |
| 2026-08-21 | 400 | **1,352ms** | 1,772ms | 0.10 | **919m** | 216Mi | **p95 초과** |

계약 기준은 `p95 < 800ms · p99 < 2,000ms · 실패 < 1%` (architecture.md 12.1).

**해석 — 파드당 상한은 300 RPS 이고, 병목은 CPU 총량이 아니라 프로세스 하나다.**

`api CPU / RPS` 가 2.17 → 2.21 → 2.30 으로 거의 일정한데 **919m 에서 천장을 쳤다.**
1,000m = 1 vCPU 이고 노드는 1,930m 이므로 **나머지 1 vCPU 는 끝까지 놀았다.**
원인은 `apps/api/Dockerfile` 의 진입점에 `--workers` 가 없어 uvicorn 이 워커 1개로
도는 것이다. **인스턴스를 키워도 이 숫자는 안 변한다. replicas 를 늘려야 한다.**

**데이터 계층은 무죄다.** 같은 구간에서 Valkey `EngineCPUUtilization` 이 1.3% 를
넘지 않았고 **캐시 미스가 27,522건 중 1건**이었다. 로컬 1초 + Valkey 30초 2단 캐시가
설계대로 흡수했고 스탬피드도 나지 않았다. Kinesis 쓰기 스로틀 0.

**HPA 를 붙이기 전에 requests 를 고쳐야 한다.** 매니페스트의 `cpu: 100m` 은 300 RPS
실측(664m)의 1/6 이다. 그대로 두면 `targetCPUUtilization` 이 600% 로 계산되어 즉시
최대치로 튄다. 500m 수준이 현실적이다.

**다시 재야 할 때** — `--workers` 나 replicas 를 바꿀 때, 인스턴스 타입을 바꿀 때,
캐시 TTL(`LOCAL_TTL` · `VALKEY_TTL`)을 바꿀 때, 이벤트 발행을 끄거나 켤 때.

> 첫 400 RPS 측정값(p95 3,514ms · 드롭 1,628)은 **버렸다.** `preAllocatedVUs` 를
> 너무 낮게 잡아 k6 가 VU 상한에 먼저 막힌 값이었다. 위 표는 고친 뒤 다시 잰 것이다.

---

## M-010. 채팅 팬아웃 한계 (chat-gateway 파드)

WebSocket 연결을 30초에 걸쳐 붙이고 5분 유지하며 채팅을 흘렸다.
`loadtest/broadcast.js` · `loadtest/run.sh`.

**조건 (2026-08-21)** — 노드 m6i.large × 2 / chat-gateway replicas 2, **서로 다른
노드에 배치** / `CHAT_TICK_MS` 200 · `CHAT_MAX_PER_TICK` 50 / 발화자 수 = 채팅율 × 6
(레이트 리밋 분당 20건의 절반) / k6 는 클러스터 밖.

`아이템/s` = 시청자 × 채팅율. 채팅 한 건이 전 시청자에게 가므로 이것이 팬아웃 총량이다.
CPU·MEM 은 **2파드 합계**다.

| 날짜 | 시청자 | 채팅율 | 아이템/s | 프레임/s | 전파 p95 | 전파 p99 | cg CPU | cg MEM | 전달률 |
|---|---|---|---|---|---|---|---|---|---|
| 2026-08-21 | 500 | 10/s | 5,000 | 1,607 | 275ms | 508ms | 151m | 94Mi | 100.0% |
| 2026-08-21 | 1,000 | 10/s | 10,000 | 3,941 | 250ms | 290ms | 206m | 98Mi | 99.9% |
| 2026-08-21 | 2,000 | 10/s | 20,000 | 7,998 | 267ms | 308ms | 343m | 108Mi | 99.9% |
| 2026-08-21 | **4,000** | 10/s | **40,000** | 14,370 | **1,286ms** | **2,105ms** | 559m | 126Mi | 99.9% |
| 2026-08-21 | 4,000 | 2/s | 8,000 | 6,749 | 282ms | 343ms | 232m | 121Mi | 99.9% |
| 2026-08-21 | **2,000** | 20/s | **40,000** | 7,850 | **479ms** | **1,240ms** | 467m | 111Mi | 100.0% |

전 구간에서 **연결 실패 0 · 조기 종료 0 · 깨진 프레임 0** 이다. 무너질 때도 죽지 않고
느려지기만 했다.

**해석 1 — 지배 변수는 연결 수가 아니라 아이템/s 다.**

8,000 과 20,000 에서는 시청자가 500이든 4,000이든 전파 p95 가 250~282ms 로 평평하다.
**40,000 에서만 무너진다.** 연결 4,000개를 유지하는 것 자체는 사실상 공짜다.

**해석 2 — 같은 아이템/s 에서 연결이 많을수록 더 나쁘다. 여기가 진짜 병목이다.**

```
2,000 연결 · 40,000 아이템/s  →  p95   479ms   (프레임  7,850 = 아이템 5개/프레임)
4,000 연결 · 40,000 아이템/s  →  p95 1,286ms   (프레임 14,370 = 아이템 2.8개/프레임)
```

전달량이 같은데 **2.7배 느리다.** 차이는 프레임 개수뿐이고, 프레임 하나마다
`JSON.stringify` 가 한 번 돈다. `apps/chat-gateway/src/main.ts` 의 틱 루프는 같은
방송의 모든 연결에 **내용이 동일한 배치**를 보내면서도 연결마다 문자열을 새로 만든다.
방송당 한 번만 만들어 재사용하면 직렬화 비용이 `O(연결 수)` → `O(1)` 이 된다.
architecture.md 9.4-8 이 예고한 지점이다.

**해석 3 — 메모리는 병목 근처도 안 갔다.**

유휴 82Mi(2파드) 대비 4,000 연결에서 126Mi 이므로 **연결당 약 11KB** 다.
파드 `limit: 384Mi` 의 16% 만 썼다. `CHAT_MAX_PER_TICK` 은 이 범위에서 한 번도
발동하지 않았다 — 10 msg/s 면 200ms 창에 평균 2건이라 상한 50 에 닿지 않는다.
그 값을 정하려면 채팅율 250/s 이상이 필요하다.

**2파드 기준 안전선은 20,000 아이템/s 다.** 목표인 4,000명 × 10 msg/s = 40,000 은
지금 코드로는 못 받는다. 직렬화 중복을 고치거나 파드를 4개로 늘려야 한다.

**다시 재야 할 때** — `CHAT_TICK_MS` · `CHAT_MAX_PER_TICK` 을 바꿀 때, 직렬화 방식을
고칠 때, replicas 를 바꿀 때, 채팅 이벤트 발행(`EMIT_CHAT_EVENTS`)을 끌 때.

> `프레임/s` 가 예상보다 적으면 서버에서 밀린 것이다. 10 msg/s · 4,000 연결의
> 이론값은 약 17,500 인데 실측이 14,370(82%)이었다. 반대로 2 msg/s 에서는
> 이론 6,700 대 실측 6,749 로 오차 0.7% 였다. 이 차이가 밀린 양이다.

---

## M-011. Chat Signal 외부 WebSocket E2E

**조건 (2026-08-23, 최초 Shadow 활성화)** — 외부 ALB `/ws`, `bc_1042`, 서로 다른
합성 사용자 4명, 약한 지연 신호 4건 동시 전송. Chat Gateway 2 replicas,
Worker Python 3.13 arm64 128MB, timeout 5초, 예약 동시성 1, SQS batch 10,
Queue visibility 30초·원문 보존 60초.

| 구간 | 실측 |
|---|---|
| WebSocket 연결 | 4/4 성공 |
| 클라이언트 수신 chat items | 16건 — 4건 × 4연결 |
| 첫 Lambda invocation | 5,000ms, timeout |
| 다음 성공 invocation | 3,922ms, `BELOW_THRESHOLD` 2건 |
| Lambda CloudWatch | `Errors=1`, `Throttles=2`, `ConcurrentExecutions max=1` |
| 나머지 메시지 | `LATE_EVENT_DROPPED` 2건 |
| E2E 직후 Queue | visible 0, not-visible 4 |
| DynamoDB | 전체 상태 7건, Candidate 0건, 원문 속성 0건 |

팬아웃은 성공했지만 Candidate 경로는 실패했다. timeout 10초, 예약 동시성 2,
event source 최대 동시성 2로 수정한 뒤 같은 조건을 새 broadcast ID로 재측정했다.

**조건 (2026-08-23, 수정 후 cold E2E)** — 외부 ALB `/ws`, `bc_1043`, 서로 다른
합성 사용자 4명, 약한 지연 신호 4건. Worker timeout 10초, 예약 동시성 2,
event source 최대 동시성 2. 합성 메시지는 고정 15초 window 경계를 걸쳐 전송됐다.

| 구간 | 실측 |
|---|---|
| WebSocket 연결 | 4/4 성공 |
| 클라이언트 수신 chat items | 16건 — 4건 × 4연결 |
| cold Lambda invocations | 5,369ms, 5,866ms; timeout 없음 |
| 처리 결과 | `BELOW_THRESHOLD` 1건, `LATE_EVENT_DROPPED` 3건 |
| Candidate | 0건 |
| E2E 직후 Queue | visible 0, in-flight 0 |
| DynamoDB 원문 속성 | 0건 |

런타임 수정은 timeout을 제거했지만, epoch 기준 15초 tumbling window 경계에서 증거가
3건과 1건으로 갈렸다. 실제 15초 이내에 모인 네 메시지가 서로 다른 고정 window에
들어갈 수 있는 미탐 조건이다(T-021).

**조건 (2026-08-23, 수정 후 same-window E2E)** — 외부 ALB `/ws`, `bc_1044`, 서로
다른 합성 사용자 4명, 약한 지연 신호 4건. window 시작 후 offset 2초에 전송을 시작해
네 메시지를 같은 고정 15초 window에 배치했다. 나머지 Worker 조건은 위와 같다.

| 구간 | 실측 |
|---|---|
| WebSocket 연결 | 4/4 성공 |
| 클라이언트 수신 chat items | 16건 — 4건 × 4연결 |
| warm Lambda invocations | 221ms, 721ms |
| Candidate | 1건 — `USER_PERCEIVED_LATENCY`, `LOW`, `UNKNOWN` |
| Candidate 증거 | matched messages 4, unique users 4, strong 0, weak 4, rule `generic_slow` |
| Candidate 경계 | `metric_status=NOT_CHECKED`, `root_cause=UNDETERMINED`, `agent_handoff_status=NOT_CONFIGURED` |
| Candidate 개인정보 | `raw_chat_included=false` |
| CloudWatch 08:10-08:12Z | `Errors=0`, `Throttles=0`, `ConcurrentExecutions max=2` |
| E2E 직후 Queue | visible 0, in-flight 0 |
| DynamoDB | 전체 상태 24건, 원문 속성 0건 |
| CloudWatch 원문 검색 | `느리네` 0건 |

이 결과는 현재 구현의 AC-004 same-window 경로가 실제 AWS에서 동작함을 검증한다.
임의의 rolling 15초에 대한 보장은 아니며, window 정책 변경은 Shadow replay 근거 후
결정한다(`VERIFY-CHAT-WINDOW-001`). 적용 후 `04-platform`과 `08-chat-signal` Terraform
plan은 모두 `No changes`였다.

**조건 (2026-08-23, Shadow 관찰 matrix)** — 외부 ALB `/ws`, 격리된 합성 broadcast
5개, 합성 채팅 24건. 일반 채팅 제외, 동일 사용자 반복, strong 임계치, 고정 window
경계 3+1, 다음 window 쿨다운 갱신을 한 suite에서 실행했다. Worker는 timeout 10초,
예약 동시성 2, event source 최대 동시성 2였다.

| 구간 | 실측 |
|---|---|
| WebSocket | 21/21 연결 성공, 기대 fanout item 84/84 수신 |
| Worker 처리 | 24/24 상태 확인 — unrelated 4, below 14, duplicate-user 3, created 2, updated 1 |
| 일반 채팅 | 4건 모두 `UNRELATED`, Candidate 0 |
| 동일 사용자 반복 | window matched 1, unique 1, duplicate-user 3, Candidate 0 |
| strong 임계치 | `MEDIUM/READ_PATH`, matched 4, unique 4, strong 3, weak 1 |
| 고정 경계 | offset 13.200초의 3건과 다음 window offset 0.399초의 1건으로 분리, Candidate 0 |
| 쿨다운 | Candidate 1건 유지, version 2, matched 8, unique 8 |
| Lambda | 13 invocations, duration 67-288ms, `Errors=0`, `Throttles=0`, concurrency max 2 |
| E2E 직후 Queue | visible 0, in-flight 0 |
| 원문 비저장 | DynamoDB 전체 67건에서 금지 key 0·합성 원문 0, CloudWatch 합성 원문 0 |

고정 경계 결과는 timeout이나 late drop 없이 정상 처리된 네 메시지만으로 3+1 미탐을
재현했다. 따라서 현재 tumbling window는 Shadow로 유지한다. 이 합성 표본은 실패 모드의
존재를 검증하지만 실제 채팅의 오탐률·미탐률을 추정하는 표본은 아니다. 원문을 보존하지
않으므로 Phase 5 비교 입력은 운영 원문 replay가 아니라 개인정보가 없는 라벨 합성
데이터로 구성해야 한다.

**다시 재야 할 때** — Worker timeout·예약 동시성·event source 최대 동시성·batch 크기,
Queue visibility, DynamoDB 처리 구조를 바꿀 때.

---

## M-012. Agent 공통 진입점 도입 전 Dify runtime baseline

**조건 (2026-08-23)** — 신규 Chat Candidate handoff를 설계하기 전에 현재
`o2-dify-ingress -> o2-dify-worker -> private EC2 Dify` 경로를 read-only로 확인했다.
CloudWatch Lambda 조회와 Dify Postgres 조회는 실행 시점과 집계 기준이 달라 서로 같은
표본으로 1:1 비교하지 않는다.

| 구간 | 실측·확인값 |
|---|---|
| Dify 배포 | 1.16.1, EC2 running, SSM Online |
| 컨테이너 | API·DB·Redis·sandbox 등 15개 모두 Up; healthcheck가 있는 API·DB·Redis·sandbox는 healthy |
| Lambda 최근 24시간 | Ingress 9 invocations, errors 0; Worker 23 invocations, errors 8, throttles 0 |
| Worker 로그 분류 | `dify ok` 15건; traceback 8건 — Bedrock validation 계열 4, workflow timeout 2, 기타 workflow failure 2 |
| Dify DB 최근 24시간 | 대상 게시 앱 workflow run succeeded 17, failed 6 |
| O2 DLQ | visible 14, in-flight 0, retention 14일 |
| 알람 | O2 DLQ not-empty는 ALARM; Worker error·backlog 알람은 확인 시점 OK |
| 실제 API key 대상 앱 | `O2 Agentic AIOps — Source-Aligned Mock v4`, workflow mode |
| 게시 입력 | 10개; `custom_alert_json` optional paragraph, 최대 30,000자 |
| 게시 graph | `custom_alert_json` 참조 확인 |

위 게시 앱 조회는 Dify 입력 기능을 확인하기 위한 baseline이다. 신규 Agent 진입점의
테스트 대상이나 연결 대상으로 승인한 것이 아니다. 실제 Shadow E2E는 전용 테스트 앱,
전용 API key, export된 별도 DSL을 사용한다(D-050).

이 baseline은 새 Chat 호출이 실패했다는 측정이 아니다. Chat handoff는 아직 없다. 기존
Datadog Agent 경로가 성공과 실패를 모두 갖고 있고 DLQ가 비어 있지 않으므로, 새 source를
곧바로 같은 Worker에 연결해서는 안 된다는 활성화 전 상태 증거다.

**다시 재야 할 때** — 게시 workflow 또는 Bedrock 모델을 바꿀 때, 기존 DLQ를 분류·재처리한
뒤, Generic Agent Worker의 timeout·동시성·재시도 정책을 정할 때.

---

## M-013. 전용 Agent entry contract workflow UI 검증

**조건 (2026-08-23)** — 기존 팀 앱과 분리한 `O2 Agent Entry Contract Test v1`을 Dify
1.16.1에 생성했다. Start는 `custom_alert_json` required paragraph 하나이고, Code와
Output만 사용했다. 자동 source, Bedrock, Datadog Pull, 조치 권한은 연결하지 않았다.

| 입력 | 결과 |
|---|---|
| `agent-trigger-chat-v1.example.json` | `ACCEPTED`, source와 source schema 일치 |
| `agent-trigger-datadog-v1.example.json` | `ACCEPTED`, source와 source schema 일치 |
| Chat source + Datadog source schema | `CONTRACT_REJECTED:SOURCE_SCHEMA` |
| LLM 사용량 | 세 실행 모두 0 Tokens |
| 기존 팀 앱 변경 | 없음 |

**Service API 직접 검증 (2026-08-23)** — 테스트 앱 전용 API key를 Secrets Manager에
저장하고 SSM local port forwarding을 통해 blocking 호출했다. Dify 문서 화면의 base URL은
`http://localhost/v1`이지만, Mac 호출에서는 터널 포트를 붙인 localhost URL을 사용했다.

| 항목 | 결과 |
|---|---|
| 게시 `/parameters` | `custom_alert_json`, paragraph, required, max length 30,000 |
| Chat `/workflows/run` | `data.status=succeeded`, 0.166256초, 3 steps, 0 tokens |
| Datadog `/workflows/run` | `data.status=succeeded`, 0.151124초, 3 steps, 0 tokens |
| source/schema 불일치 | `data.status=failed`, 0.121813초, 2 steps, 0 tokens |
| 실패 code | `CONTRACT_REJECTED:SOURCE_SCHEMA` |

입력의 표시 label은 게시 API에서 중복 문자열로 보였지만 API 매핑에 사용하는 variable은
정확히 `custom_alert_json`이었다. label은 실행 계약이 아니며 canonical DSL에서는 단일
label로 정규화했다. 호출 후 평문 임시 파일과 테스트용 터널은 제거했고, 사용자가 열어 둔
localhost 터널은 종료하지 않았다.

**다시 재야 할 때** — Start 변수, 최대 길이, Code 검증 필드, output 형태, Dify 버전을
바꿀 때.

---


## M-014. 주문 확정 워커 처리량 (order-worker)

KEDA `ScaledObject` 의 근거값을 잡으려고 쟀다. `loadtest/order-queue.py`.

api 를 거치지 않고 SQS 에 직접 넣는다 — `POST /api/orders` 로 던지면 api 의
천장(M-009, 300 RPS)에 먼저 막혀 워커가 아니라 api 를 재게 된다. 도착률을
맞추는 대신 **큐를 미리 채우고 비는 데 걸린 시간**을 쟀다. 처리량은 램프업과
꼬리를 뺀 90% → 10% 구간으로 계산한다.

#### requests `50m` (수정 전)

**조건 (2026-08-23)** — 노드 `c6i.large` × 2 / `order-worker` requests `cpu 50m`
(이 시점 매니페스트 값) / RDS `db.t4g.micro` / 건당 10,000건 적재.

이 표는 완료를 **큐 깊이**로 판정했다. 뒤에 그 신호가 늦는 것을 발견해(아래
"완료 판정을 큐가 아니라 행 수로 바꿨다") 행 수 기준으로 바꿨으므로, 배수 시간이
짧은 행일수록 처리량이 조금 높게 잡혀 있을 수 있다. 아래 표와 1:1로 비교하지 말 것.

| 날짜 | replicas | 배수(초) | 처리량 | 파드당 | 파드 CPU 합 | MEM |
|---|---|---|---|---|---|---|
| 2026-08-23 | 1 | 207 | 50.3/s | 50.3 | 200m | 91Mi |
| 2026-08-23 | 2 | 104 | 82.4/s | 41.2 | 755m | 180Mi |
| 2026-08-23 | 4 | 56 | 162.7/s | 40.7 | 870m | 356Mi |
| 2026-08-23 | 6 | 55 | 187.6/s | 31.3 | 1,938m | 534Mi |
| 2026-08-23 | 8 | 74 | **119.2/s** | 14.9 | 1,728m | 715Mi |

DLQ 0건, `orders` 행이 정확히 적재량과 같았다. 버려지거나 중복된 메시지는 없다.

이 조건에서 파드당 값은 41 근처다. 다만 **이 숫자는 쓰지 않는다** — requests 가
틀린 상태의 값이고, 아래 수정 후 표에서 49 로 올라간다.

### 8 파드가 6 파드보다 느리다 — 범인은 RDS 가 아니다

총 처리량이 187.6 → 119.2 로 **떨어졌다.** 파드를 늘렸는데 느려졌으니 공유 자원이
한계인데, DB 는 무죄다.

| 지표 | 8 파드 구간 최댓값 | 여유 |
|---|---|---|
| RDS `CPUUtilization` | 8.8% | — |
| RDS `CPUCreditBalance` | 288 (한 톨도 안 씀) | `db.t4g.micro` 는 버스터블이지만 크레딧을 건드리지도 않았다 |
| RDS `WriteIOPS` | 788 | gp3 baseline 3,000 |
| RDS `DatabaseConnections` | 14 | — |
| **노드 CPU** | **1,798m** | allocatable **1,930m** — 여기가 말랐다 |

노드 CPU 다. 그리고 그렇게 된 이유가 셋 겹쳤다.

1. **requests 가 `50m` 인데 실사용이 200~220m 다.** 스케줄러는 8 파드를 400m 으로
   보고 한 노드에 다 넣는다
2. `topologySpreadConstraints` 가 `ScheduleAnyway`(연성)이고 `part-of: o2` 전체를
   세므로 쏠림을 막지 못한다
3. **Karpenter 가 노드를 사지 않는다.** Karpenter 도 requests 로 판단하는데 400m 은
   남는 자리에 들어가 Pending 이 생기지 않는다. 노드가 필요한 상황인데 필요한 줄을
   모른다

**그래서 이 꺾임은 상한이 아니라 requests 오류의 부산물이다.** `maxReplicaCount` 를
여기서 정하면 안 된다. requests 를 실측에 맞춘 뒤 다시 재야 진짜 상한이 나온다.
requests 는 O2-live-deploy 에서 `250m` 으로 고쳤고(O2-live-deploy#24), 그 뒤 값이
아래 표다.

#### requests `250m` (수정 후)

**조건 (2026-08-23)** — requests `cpu 250m` / 나머지 동일. replicas 6·8 은 10,000건,
12 는 30,000건 적재(6·8 과 같은 1만 건이면 배수가 30초 이내라 측정 창이 안 나온다).

이 조건에서는 **Karpenter 가 `c6i.large` 2대를 샀다.** requests 가 실사용에 맞으니
Pending 파드가 생겼고, 그제서야 노드가 필요한 것이 보였다. 노드는 4대가 됐다.

| 날짜 | replicas | 배수(초) | 처리량 | 파드당 | 파드 CPU 합 | MEM |
|---|---|---|---|---|---|---|
| 2026-08-23 | 6 | 42 | 296.9/s | 49.5 | 2,098m | 534Mi |
| 2026-08-23 | 8 | 29 | **379.8/s** | 47.5 | 2,872m | 708Mi |
| 2026-08-23 | 12 | 63 | **588.9/s** | 49.1 | 3,152m | 1,068Mi |

**같은 8 파드가 119.2/s → 379.8/s 로 3.2배가 됐다.** 앞 표의 꺾임이 상한이 아니라
requests 오류였다는 것이 이것으로 확정된다.

**파드당 47~49 가 1 → 12 에서 평평하다. 꺾이는 지점을 못 찾았다.** 12 파드
588.9/s 구간에서도 RDS `CPUUtilization` 이 18.2% 를 넘지 않았고 노드도 마르지 않았다.

replicas 16 은 적재까지 끝내고 배수 중에 **AWS 세션이 만료돼** 측정하지 못했다.
`kubectl` 도 자격증명을 `aws` 로 얻으므로 같이 죽는다 — 30분 넘는 측정을 돌리기
전에 세션 남은 시간을 본다.

### 완료 판정을 큐가 아니라 행 수로 바꿨다

처음에는 `ApproximateNumberOfMessages` 가 0 이 되는 것을 완료로 봤다. 그런데
Visible·NotVisible 이 **둘 다 0 을 보고한 뒤 2,325건이 뒤늦게 나타났다.** 이름대로
근사값이고 소비 직후 크게 늦는다.

그 0 을 완료로 믿으면 배수 시간이 짧게 나와 **처리량이 부풀려지는데, 표는 정상으로
보인다.** 그래서 진행도를 `orders` 행 수로 바꿨다 — 정확하고 단조증가라 늦지 않는다.
큐 깊이는 적재 전 잔여 확인에만 쓴다.

### ScaledObject 로 환산하는 법

`ScaledObject` 에 들어가는 값은 msg/s 가 아니라 **파드당 목표 큐 길이**다.

```
queueLength = 파드당 처리량(msg/s) x 허용 지연(초)
            = 49 x 30 = 1,470  →  1,200 (여유를 둔다)
```

```yaml
minReplicaCount: 1      # 0 은 쓰지 않는다 — 콜드 스타트가 스파이크와 겹친다
maxReplicaCount: 12
queueLength: "1200"
```

**`maxReplicaCount` 는 한계가 아니라 목표에서 나온 값이다.** 위에서 꺾이는 지점을
못 찾았으므로 "12에서 무너진다" 는 뜻이 아니라 **"12까지 선형인 것을 쟀으니 그
위는 쓰지 않는다"** 는 뜻이다.

```
목표 (1/10 축소)   240 msg/s     architecture.md 6.2 의 2,400 msg/s x 30초
파드당             49 msg/s      실측
필요 파드          240 / 49 = 4.9   ->  5
안전계수 1.5                       ->  8
실측으로 선형이 확인된 상한          ->  12
```

동작 확인 — 스파이크 30초면 큐에 7,200건이 쌓인다. `ceil(7200 / 1200) = 6 파드`,
6 x 49 = 294/s 로 약 24초에 뺀다. 상한 12는 14,400건까지 받는다.

**KEDA 는 위에서 못 믿겠다고 한 그 지표를 본다.** SQS 스케일러의 입력이
`ApproximateNumberOfMessages` 이고 다른 선택지가 없다. 측정 스크립트는 행 수로
피했지만 KEDA 는 못 피한다. 그래서 스파이크 초반에는 큐 길이를 실제보다 적게 보고
늘리는 것이 조금 늦고, 다 뺀 뒤에는 남아 있다고 보고 줄이는 것이 조금 늦는다.
D-041 이 KEDA 를 2차 보정으로 둔 것과 같은 방향이라 설계를 바꾸지는 않는다 —
반응이 굼뜨게 보일 때 여기를 먼저 의심하라는 뜻이다.

### 병목은 워커의 구조다

파드당 49 msg/s 는 CPU 가 모자라서가 아니다. `worker/main.py` 가 단일 스레드이고,
`delete_message` 를 **메시지마다 개별 호출**한다. 한 건당 SQS 왕복이 하나씩 붙는다.
`delete_message_batch` 로 10건씩 지우면 왕복이 1/10 이 되는데, 고치면 이 표의
숫자가 전부 바뀌므로 **고치기 전 값으로 남긴다.**

**다시 재야 할 때** — requests 를 바꿀 때, 노드 인스턴스 타입을 바꿀 때, RDS 등급을
바꿀 때, `delete_message` 를 배치로 바꿀 때. 그리고 **replicas 12 위를 쓰려고 할 때** —
그 구간은 안 쟀다.

## M-015. warm 경로 인입·집계 실측과 집계기 지연

**조건 (2026-08-23)** — CloudWatch 원본 지표를 직접 조회했다(`o2-data` 프로파일,
`ap-northeast-2`). Datadog 을 거치지 않은 값이다.

### 인입은 간헐적이다

6시간 버킷, 48시간 구간.

| 시각 (KST) | `stream-business` IncomingRecords | `o2-agg` Invocations |
|---|---|---|
| 08-22 12:53 | 5 | 1 |
| 08-22 18:53 | 5 | 1 |
| 08-23 12:53 | 36 | 7 |
| 08-23 18:53 | **164,581** | **1,730** |

48시간 중 42시간이 6시간당 5건 수준이고, 나머지가 6시간에 16만 건이다.
**부하 시험이 돌 때만 흐른다.** 이 분포가 D-052 의 근거다 — 실제 트래픽
지표에 `notify_no_data` 를 걸면 대부분의 시간이 "장애" 로 보인다.

### 부하 중 집계기가 밀린다

1시간 버킷, 위 표의 마지막 구간.

| 시각 (KST) | `IteratorAge` 최대 | `Errors` | `Throttles` |
|---|---|---|---|
| 08-23 18:53 | 17,143 ms | 0 | 0 |
| 08-23 19:53 | **102,460 ms** | 0 | 0 |

**오류 0 인 채로 지연만 100초까지 올랐다.** 실패가 아니라 밀림이라 어떤 오류
기반 알림에도 안 걸린다.

구성값 (같은 시점 확인):

| 항목 | 값 |
|---|---|
| `stream-business` OpenShardCount | 1 |
| 이벤트 소스 매핑 | BatchSize 100, BatchingWindow 2s, **ParallelizationFactor 1**, LATEST |

샤드 1개에 병렬 계수 1이므로 소비가 사실상 직렬이다. 인입이 한 소비자의
처리량을 넘으면 구조적으로 밀린다.

### 이 값이 왜 중요한가

명세의 자기 교정 루프가 **조치 후 90초 뒤 재확인**을 전제로 한다. 집계가
100초 밀려 있으면 그때 읽는 값은 **조치 이전 값**이다. 에이전트가 자기
조치의 효과를 반대로 판정할 수 있다.

그래서 `05-datadog` 의 `aggregator_lag_critical_seconds` 기본값을 검증 대기
시간과 같은 **90초**로 뒀다. 임의로 고른 값이 아니라 그 루프가 깨지는 지점이다.

### Datadog 수집 확인 (2026-08-24) — 위 "안 잰 것" 첫 항목의 답

**조건** — Datadog API `/api/v1/query` 직접 조회, US5, 24시간 구간.
App Key 는 Secrets Manager `o2/dev/datadog-new` 에 있다. 콘솔이 아니라 API 로
확인한 이유는 재현 가능해야 하기 때문이다.

```powershell
$raw = aws secretsmanager get-secret-value --secret-id o2/dev/datadog-new `
         --profile o2-data --query SecretString --output text
$j = $raw | ConvertFrom-Json
$h = @{ "DD-API-KEY" = $j.'api-key'; "DD-APPLICATION-KEY" = $j.'app-key' }
$raw = $null; $j = $null

$to = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds(); $from = $to - 86400
$enc = [uri]::EscapeDataString("avg:aws.lambda.iterator_age{*} by {functionname}")
Invoke-RestMethod "https://api.us5.datadoghq.com/api/v1/query?from=$from&to=$to&query=$enc" -Headers $h
```

`Get-Date -UFormat %s` 는 쓰지 않는다 — Windows PowerShell 5.1 에서 로컬 시각
기준이라 Datadog 이 `query start is in the future` 로 거절한다.

| 쿼리 | 결과 |
|---|---|
| `sum:aws.lambda.invocations{*} by {functionname}` | series **12** — `o2-agg` · `o2-warm-api` · `o2-hot-api` · `o2-dev-chat-signal-worker` 등 |
| `avg:aws.lambda.iterator_age{*} by {functionname}` | `functionname:o2-agg` **있음** |
| `sum:aws.lambda.errors{*} by {functionname}` | series **12** |
| `sum:aws.kinesis.incoming_records{*} by {streamname}` | `streamname:stream-business` **있음** |
| `avg:aws.firehose.delivery_to_s_3data_freshness{*} by {deliverystreamname}` | `o2-business-to-s3` **있음** |
| `avg:aws.sqs.approximate_age_of_oldest_message{*} by {queuename}` | 큐 **9개** (각 286 포인트) — `o2-dev-order` 포함 |

**수집된다.** `enable_aggregator_lag_monitor` 와 `enable_queue_backlog_monitor`
의 비활성 사유가 이것으로 해소됐다.

### 데이터포인트 밀도가 지표마다 다르다 — Monitor 설계에 영향을 준다

같은 24시간 구간인데 포인트 수가 갈린다.

| 지표 | 포인트 수 | 해석 |
|---|---|---|
| `aws.lambda.invocations` · `errors` | 288 | 5분 간격이 꽉 찼다 |
| `aws.lambda.iterator_age` | **18** | 스트림이 움직일 때만 나온다 |
| `aws.kinesis.incoming_records` | **17** | 위와 같다 |

CloudWatch 가 스트림이 실제로 움직일 때만 이 지표를 내보내기 때문이고,
위 "인입은 간헐적이다" 의 분포와 정확히 일치한다.

**그래서 `iterator_age` 기반 Monitor 의 `notify_no_data` 는 반드시 `false` 여야
한다.** `min(last_5m)` 이 빈 창을 만나면 No Data 로 가고, 한산한 밤마다 울린다 —
`order_latency_p95` 가 사흘 만에 꺼진 것과 같은 경로다. 생존 감시는 카나리가
하고, 이 Monitor 는 "밀린다" 만 잡는다.

### 안 잰 것

- ~~Datadog AWS 통합이 `aws.lambda.*` 를 실제로 수집하는지~~ →
  **위에서 확인했다 (2026-08-24).** `enable_aggregator_lag_monitor` 기본값을
  `true` 로 바꿨다
- 부하 종료 후 따라잡는 데 걸리는 시간
- 집계 Lambda `Duration` — 같은 구간 조회에서 데이터포인트가 안 나왔다
- **파드별 지연의 정상 분산.** `pod_latency_outlier_tolerance` 를 캐시 쪽과
  같은 2.5 로 둔 것은 근거가 있어서가 아니라 다른 값을 고를 근거가 없어서다.
  파드가 2개 이상 뜬 상태에서 재고 그 Monitor 를 켠다

---

## M-016. APM trace 지표의 태그 축 (파드 축이 있는가)

`latency_by_pod` 를 06-datastream 에 직접 만들기 전에, **그 작업이 통째로
불필요한지** 먼저 확인한 것이다. `apps/api/Dockerfile` 이 `ddtrace-run` 으로
기동하고 APM 이 켜져 있으므로(`apm.portEnabled = true`), trace 지표에 이미
`pod_name` 이 붙어 있다면 계측을 새로 만들 이유가 없다.

**조건 (2026-08-24)** — Datadog API `/api/v1/query`, US5, 24시간 구간.
M-015 의 "Datadog 수집 확인" 과 같은 세션·같은 방법이다.

| 쿼리 | 결과 |
|---|---|
| `sum:trace.fastapi.request.hits{*} by {pod_name}` | series 1 · scope `pod_name:N/A` |
| `sum:trace.fastapi.request.hits{*} by {kube_node}` | series 1 — 노드가 하나뿐이라 갈리지 않는다 |
| `avg:kubernetes.cpu.usage.total{*} by {pod_name}` | series **146** |

`trace.fastapi.request` 가 갖는 태그 키는 아홉 개다 — `env` · `error` ·
`http.status_code` · `is_trace_root` · `resource` · `resource_name` ·
`service` · `span.kind` · `version`. **파드 축이 없다.**

`.hits` 쪽에 `kube_node` · `host` 가 붙지만 이는 **호스트 태그가 상속된
것**이지 파드 단위가 아니다. 노드 하나에 파드가 여럿 뜨면 전부 같은 값이 된다.

마지막 행이 대조군이다 — **K8s 통합에는 `pod_name` 이 정상적으로 붙는다.**
즉 "Datadog 전체에 파드 축이 없다" 가 아니라 **APM trace 지표에만 없다.**
그래서 인프라 지표(CPU·메모리)와 비즈니스 지표(지연)를 같은 파드 축에서
비교하려면 비즈니스 쪽을 우리가 만들어야 한다.

### 결론

우회 불가. `latency_p95` 의 파드 축은 06-datastream 의 3단
(`sketch.py` → `metrics.py` → `datadog.py`)에서 만든다. 이 실측이 그 작업의
근거다.

### 파드 축은 실제로 동작한다 — 다만 파드가 하나뿐이다 (2026-08-24)

같은 세션에서 `o2.warm.*` 쪽을 확인했다. 24시간 구간.

| 쿼리 | series | scope |
|---|---|---|
| `avg:o2.warm.cache_hit_rate{*} by {pod_name}` | **2** | `pod_name:N/A` · `pod_name:api-84cc478498-hw6jp` |
| `avg:o2.warm.latency_p95{*} by {pod_name}` | 1 | `pod_name:N/A` (계측 배포 전) |
| `avg:o2.warm.rps{*} by {service}` | 3 | `api` · `order-worker` · `chat-gateway` |

첫 행이 중요하다 — **3단 태그 경로가 운영에서 실제로 동작하고 있다.**
`cache_hit_rate` 가 파드 이름으로 갈린다. 지연도 집계 Lambda 를 다시 배포하면
같은 모양이 된다. `pod_name:N/A` 는 service 단위로 보낸 값이다(D-057).

**그런데 파드 이름이 하나뿐이다.**

```
sum:kubernetes_state.deployment.replicas_available{kube_namespace:o2-dev} by {kube_deployment}
  api           1      chat-gateway  2      frontend  1
  order-worker  1      mediamtx      1
```

`api` 디플로이먼트가 **replica 1개**다.

### 이것이 S2 를 막는다

`outliers(… by {pod_name}, 'DBSCAN', …)` 는 **시계열이 둘 이상이어야** 무리와
이상치를 나눌 수 있다. 하나뿐이면 비교 대상이 없어 **아무것도 잡지 못한다.**
오류가 아니라 조용한 무능이라 더 나쁘다 — Monitor 는 OK 로 보인다.

| Monitor | 지금 상태 | 실제로 동작하나 |
|---|---|---|
| `cache_hit_rate_pod_outlier` | **활성**(`tfvars` 에 `true`) | **아니오** — 파드 1개 |
| `latency_p95_pod_outlier` | 비활성 | 아니오 — 같은 이유 |

**즉 켜져 있는 쪽이 이미 무능한 상태다.** 계측·Monitor·위젯이 전부 갖춰져도
파드가 하나면 S2("느린 파드 하나가 서비스 전체 꼬리를 끌어올린다")는 성립하지
않는다. `api` 를 2개 이상으로 올리는 것이 **S2 의 마지막 전제**다.

### CFS 지표는 이제 존재한다 — 다만 KEDA 파드만 (2026-08-24)

`dashboard_infra.tf` 가 2026-08-19 에 *"이 org 에 `kubernetes.cpu.cfs.*` 가
메트릭 메타데이터 검색에조차 안 잡힌다"* 고 적어 뒀는데 **그 사이 바뀌었다.**

```
avg:kubernetes.cpu.cfs.throttled.periods{*} by {kube_namespace}
  -> kube_namespace:keda     series 7 (전부 KEDA 파드)
  -> kube_namespace:o2-dev   없음
```

KEDA 를 넣으면서(D-051) 그 Helm 차트가 자기 파드에 `limits.cpu` 를 걸었고,
그것만으로 시계열이 생겼다. **앱 네임스페이스(`o2-dev`)에는 여전히 없다.**

결론은 안 바뀐다 — 대시보드 위젯은 `o2-dev` scope 라 여전히 빈다. 바뀐 것은
**사유**다. "이 org 에 그런 지표가 없다" 가 아니라 "우리 앱 파드에 limit 이
없다" 가 맞다.

이 구분이 S2 에 중요하다. 명세 S2 는 느린 파드를 **정상 파드와 비교**해서
찾는다. 정상 파드에도 넉넉한 limit 이 있어야 분모가 생기고, 시계열이 둘
이상이어야 `outliers()` 가 이상치를 낼 수 있다. **KEDA 파드는 그 비교의
대상이 아니다.**

### 파드 축이 실제로 갈린다 — 부하를 걸어 확인했다 (2026-08-24)

`api` replicas 가 2로 오른 뒤(`O2-live-deploy` `19d6ae9`) 파드 축이 실제로
동작하는지 확인했다. **용량 측정이 아니다** — `latency_p95 by {pod_name}` 이
갈리는지와 `latency_p99` 가 나오는지만 본 기능 검증이다.

**조건** — `GET /api/broadcasts/bc_1042` 를 ALB 경유로 **10 RPS · 180초**.
1,799 요청 전부 200. M-009 의 포화점(300 RPS)의 3% 수준이다. k6 하네스가
아니라 파이썬 경량 생성기를 썼다(이 환경에 k6 가 없다).

| 쿼리 | 결과 |
|---|---|
| `avg:o2.warm.latency_p95{*} by {pod_name}` | **series 3** — `api-56cc9b94c9-4tk29` · `api-56cc9b94c9-bg429` · `N/A` |
| `avg:o2.warm.latency_p99{*}` | **있음** (20 포인트, 최대 57.6ms) |
| `avg:o2.warm.rps{service:api}` | 최대 10.2 (목표 10 RPS 와 일치) |

**둘 다 처음 확인된 것이다.** 파드별 지연은 계측을 넣은 뒤로 계속
`pod_name:N/A` 하나뿐이었고, `latency_p99` 는 `DATADOG_SCALARS` 에 없어
한 번도 전송된 적이 없었다.

#### 표본이 적을 때 안 나오던 이유가 확인됐다

부하 전에는 파드당 10초 창에 2~3건뿐이라
`LATENCY_POD_MIN_SAMPLES = 5` 가 전부 걸러냈다(`latency_samples_by_pod`
= `{6gk5f: 2, hw6jp: 3}`, `latency_p95_by_pod` = `{}`). 10 RPS 만 걸어도
파드당 창당 50건이라 여유 있게 넘는다. **임계는 그대로 둔다.**

#### 서버 지연과 클라이언트 체감이 크게 다르다

| 관측 지점 | p50 | p95 | p99 |
|---|---|---|---|
| 클라이언트 (ALB + 인터넷 왕복 포함) | 38.8ms | 87.8ms | 1,053ms |
| warm 집계 (서버 처리 시간) | — | **2~4ms** | 최대 57.6ms |

**20배 이상 차이가 난다.** 이 파이프라인의 `latency_p95` 는 페이로드의
`latency_ms`, 즉 **애플리케이션이 스스로 잰 처리 시간**이라 네트워크가
안 섞인다. M-009 의 값(p95 93~314ms)은 클라이언트 관측이므로 **이 표와
직접 비교하면 안 된다.**

S2 의 "느린 파드" 판정은 서버 값으로 한다 — 인터넷 왕복이 섞이면 파드
간 차이가 묻힌다.

### 안 잰 것 (이 절)

- **M-009 재측정.** `replicas` 1 → 2 는 M-009 의 재측정 트리거이고
  (`O2-live-deploy` `19d6ae9` 가 그렇게 적었다), 파드당 계수가 바뀌었을 수
  있다. 이번 10 RPS 는 포화점 근처가 아니라 그 답이 안 된다. **k6 하네스로
  계단(10·25·50·100·200·300·400)을 다시 밟아야 한다**
- 파드별 지연의 **정상 분산** — outlier 임계(`pod_latency_outlier_tolerance`
  = 2.5)의 근거. 위 부하에서 두 파드가 2.0ms 대 4.0ms 였는데 표본이 적어
  분산을 말할 수 없다

### 채팅 이벤트는 이미 Kinesis 로 흐른다 (2026-08-24)

`monitor.tf` 가 `chat_ingest_surge` 를 껐던 사유(*"목적지가 stdout 뿐이라
Kinesis 로 가는 경로 자체가 없다"*)도 낡아 있었다. 7일 구간 조회:

| 쿼리 | 결과 |
|---|---|
| `avg:o2.warm.rps{*} by {service}` | `api` · `order-worker` · `chat-gateway` · `o2-canary` |
| `avg:o2.warm.rps_ratio{service:chat-gateway}` | **있음** |
| `avg:o2.warm.latency_p99{*}` | **없음** — 계산만 되고 발행 안 됨 (아래) |

`events.ts` 에 `PutRecordCommand`(`:16`)와 `config.eventsSink === 'kinesis'`
분기(`:100`)가 들어와 있고 배포 환경변수도 설정돼 있다. Monitor 도 이미
`true` 다. **남아 있던 것은 주석뿐이었다.**

### `latency_p99` 는 계산만 되고 발행되지 않았다

`metrics.py` 가 오래 전부터 `latency_p99` 를 계산했는데 `DATADOG_SCALARS`
에 없어 **Datadog 에는 한 번도 오지 않았다**(7일 구간 series 0).
DynamoDB 상세에만 있었다.

명세 S2 의 1차 조치 검증이 p50·p95·**p99** 셋을 함께 보는 것을 전제하는데
그 자리가 비어 있었다. **p95 로 대신할 수 없다** — 느린 파드의 몫이 전체의
5% 미만이면 p95 는 안 움직이고 p99 만 움직인다.

`O2-live-deploy` 매니페스트 소관이라 이 두 스택 범위 밖이다. F-6(정상 파드에
`limits.cpu` 부여)과 **같은 곳에 같이 요청해야 하는 항목**이다 — 둘 다
"파드가 여럿이고 서로 비교 가능해야 한다" 는 같은 전제를 만든다.

### 다시 재야 할 때

- `ddtrace` 버전을 올렸을 때 — 통합 서비스 태깅이 파드 축을 붙이기 시작하면
  이 계측이 중복이 된다
- Datadog Agent 의 `DD_TAGS` · `podLabelsAsTags` 설정을 바꿨을 때
- 노드가 둘 이상이 되었을 때 — `kube_node` 로 갈리는지 다시 본다
  (파드 축의 대용은 못 되지만 어느 노드가 아픈지는 갈린다)

### 안 잰 것

- `trace.fastapi.request.duration` — **이 이름의 지표는 존재하지 않는다.**
  관례상 그럴듯해서 한동안 이걸로 조회하다 시간을 버렸다. 경위는 T-024

---

## M-017. Incident Correlator 합성 E2E와 처리시간

**조건 (2026-08-24)** — `agent.trigger.v1` Signal Queue에 계약 검증을 통과한 합성
Chat·Datadog trigger를 직접 전송했다. Correlator Lambda는 Python 3.12, 128MB, reserved
concurrency 2, SQS batch size 1이다. 테스트 동안만 실행 gate와 event source를 켰고,
allowlist는 실행별 key 두 개로 제한했다. test-only correlation window는 300초였으며 두
trigger의 event time은 같게 고정했다.

| 순서 | 첫 신호 | 두 번째 신호 | Incident 결과 | Lambda Duration |
|---|---|---|---|---|
| Chat → Datadog | revision 1 `PROVISIONAL` | revision 2 `CORRELATED` | 같은 `incident_id`, source 2개 | cold 6,535.02ms · warm 204.28ms |
| Datadog → Chat | revision 1 `PROVISIONAL` | revision 2 `CORRELATED` | 같은 `incident_id`, source 2개 | cold 6,447.42ms · warm 212.93ms |

첫 실행의 6.4-6.5초에는 cold start 뒤 boto3의 최초 credential discovery와 DynamoDB·SQS
호출이 포함됐다. 같은 execution environment의 두 번째 revision은 205-213ms였다.

**검증한 것** — source 순서와 무관한 동일 Incident 귀속, material change에서만 revision
증가, Invocation Queue revision 1·2 생성, consumer 0개와 Dify 실행 차단, 합성 데이터
개별 정리, 종료 후 비활성 기본값 복귀다.

**검증하지 못한 것** — 실제 Chat Candidate Adapter와 신규 Datadog Source Adapter의
전달 지연·편차다. 두 source의 event time을 같게 넣었으므로 300초는 기능 검증용 값일 뿐
운영 correlation window 근거가 아니다.

**다시 재야 할 때** — Correlator 코드, Lambda memory, DynamoDB GSI, SQS batch/concurrency를
바꿀 때. 실제 두 Adapter를 연결하면 source 발생 시각·Signal Queue 도착 시각의 차이를
별도 행으로 추가하고 그 분포로 운영 window를 결정한다.

---

## M-018. Agent Invocation Worker 첫 Shadow E2E와 fail-closed

**조건 (2026-08-24)** — 전용 Dify 앱을 `agent.incident.v1` 계약으로 게시하고, Generic
Worker와 Agent Invocation Queue mapping을 기본 비활성 상태로 적용했다. Shadow 동안만 새
합성 Incident ID 한 개를 allowlist에 넣고 event source와 실행 플래그를 함께 켰다. 입력은
저장소의 `CORRELATED` 예시이며 채팅 원문, Bedrock, 자동 조치는 포함하지 않았다.

| 관측 지점 | 결과 |
|---|---|
| Dify 게시 Service API 정상 Incident | `succeeded`, 새 Incident 응답 계약 확인 |
| Dify 게시 Service API raw chat 금지 입력 | `failed`, `CONTRACT_REJECTED:GUARDRAIL_VALUES` |
| Queue → Worker → Dify Shadow | Dify run 정확히 1건 `succeeded` |
| Worker ledger 시작 | `IN_PROGRESS`, attempt 1, Incident lock 획득 |
| Worker ledger 확정 | `IDEMPOTENCY_FINALIZE` 실패 |
| 직접 원인 | IAM에 `dynamodb:DeleteItem` 누락; finalize transaction의 lock 삭제 거부 |
| 중복 방지 | `IN_PROGRESS` ledger와 lock 보존, 자동 재호출 없음 |
| 즉시 롤백 | mapping `Disabled`, 실행 `false`, allowlist empty, DLQ 0 |

이 결과는 Shadow E2E 통과가 아니다. Dify 호출과 출력 계약은 통과했지만 실행 상태 확정이
실패했다. 수정은 ledger table에 대한 `DeleteItem` 하나이며 targeted plan은 `0 add, 1 change,
0 destroy`다. 실패 메시지는 Message ID·body·attribute를 대조한 뒤 개별 삭제했고,
ledger·lock·Incident State는 합성 marker와 owner를 확인하는 하나의 조건부 transaction으로
정리했다. 종료 시 Queue·DLQ와 세 DynamoDB key는 모두 비어 있었다. fix를 main에 병합·적용한
뒤 새 Incident ID로 재측정하며 기존 ID는 재사용하지 않는다.

---

## M-019. 파드 Ready 시간 (사전 확장 리드타임)

큐시트 기반 사전 확장(D-041)이 "몇 초 전에 늘릴지"를 정하려면 파드가 Ready 가
되는 데 걸리는 시간이 필요하다. 그 값을 쟀다.

기존 Deployment 를 건드리지 않고 **일회용 파드 하나**를 띄웠다 지웠다. api
Deployment 의 파드 스펙을 그대로 복사하되 라벨을 `app.kubernetes.io/name:
api-readytest` 로 바꿔 **Service selector 에 안 걸리게** 했다 — 트래픽을 받지
않으므로 지표도 모니터도 움직이지 않는다.

**조건 (2026-08-24)** — c6i.large, `role=general` 노드에 `nodeSelector` 로 고정 /
api 이미지가 **그 노드에 이미 캐시돼 있었다**(api 파드가 두 노드에 모두 상주) /
노드 여유 안이라 Karpenter 미개입 / `readinessProbe` 는 api 매니페스트 그대로
(`periodSeconds: 10`, `initialDelaySeconds` 없음, `timeoutSeconds: 5`) /
측정은 `kubectl apply` 직후부터 `kubectl wait --for=condition=Ready` 반환까지.

| 날짜 | run | apply → Ready |
|---|---|---|
| 2026-08-24 | 1 | 12.45s |
| 2026-08-24 | 2 | **4.06s** |
| 2026-08-24 | 3 | 13.12s |
| 2026-08-24 | 4 | 13.10s |
| 2026-08-24 | 5 | 14.02s |
| 2026-08-24 | 6 | 13.11s |
| 2026-08-24 | 7 | **4.09s** |
| 2026-08-24 | 8 | 13.07s |

**해석 1 — 값이 양분된다. 중간이 없다.**

4초 또는 13~14초이고 8회 중 6회가 후자였다. 분포가 아니라 두 개의 점이다.

**해석 2 — 앱은 3초에 준비된다. 나머지 10초는 probe 주기다.**

같은 파드에서 컨테이너 시작 시각과 `Ready` 전이 시각을 직접 비교하면 3초다.
`initialDelaySeconds` 가 없어 첫 probe 가 컨테이너 시작 직후 도착하는데, 그때
앱이 아직 3초를 못 채웠으면 실패하고 **다음 probe 는 `periodSeconds` 만큼 뒤**다.

| 구간 | 시간 |
|---|---|
| apply → 스케줄 | 약 1초 |
| 컨테이너 시작 → 앱 준비 | **3초** |
| probe 주기 대기 | **0 또는 10초** |
| 합계 | 4초 또는 13~14초 |

**리드타임은 최악값으로 잡는다 — 14초 + 여유.** 6/8 이 그쪽이다.

**해석 3 — 리드타임의 70% 가 probe 설정이다.**

앱이 3초에 뜨는데 10초를 기다린다. `periodSeconds` 를 3~5초로 낮추면 리드타임이
절반 이하가 된다. probe 호출이 잦아지는 대가가 있지만 3초 주기면 파드당
0.33 RPS 수준이라 300 RPS 천장(M-009)에 무시할 만하다.

S2 의 canary 는 반대로 `timeoutSeconds`·`failureThreshold` 를 **올려서** 창을
넓힌다(`scenario-readiness.md` 4절 6). 대상이 달라 서로 부딪히지 않는다 —
main 은 짧게, canary 는 길게.

**안 잰 것 둘.** 둘 다 값이 나오면 이 절의 표에 행을 추가한다.

| 무엇 | 왜 못 쟀나 |
|---|---|
| 이미지 캐시가 **없는** 노드에서의 Ready | 새 노드가 필요하다. M-008 의 39초는 `pause` 이미지(수백 KB) 기준이라 실제 앱 이미지는 그보다 크다 |
| 노드 프로비저닝을 **포함한** Ready | Karpenter 가 노드를 띄우는 경우. 요금이 발생하므로 따로 재야 한다 |

노드를 새로 띄워야 하는 경로는 분 단위가 되므로, 큐시트 계획 단계에서 **증설
슬롯이 기존 노드 안에 있는지 먼저 확인**해야 한다(`scenario-experiment.md` 6절의
Karpenter 항과 같은 조건).

**다시 재야 할 때** — `readinessProbe` 의 `periodSeconds`·`initialDelaySeconds` 를
바꿀 때, 이미지 크기가 크게 변할 때, 인스턴스 타입을 바꿀 때, 노드 여유가 없어
Karpenter 가 개입하게 될 때.
