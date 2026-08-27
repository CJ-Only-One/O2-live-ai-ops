# 05-datadog — 보는 쪽

Datadog 안의 객체만 소유한다. AWS 리소스를 만들지 않으므로 `aws` 프로바이더가 없다.

```
04-platform ──▶ Datadog Agent (인프라 지표)  ─┐
                                              ├─▶ Datadog ◀── 여기가 보는 화면을 만든다
06-datastream ─▶ 집계 Lambda (비즈니스 지표) ─┘
```

| | 누가 |
|---|---|
| Agent 설치 | `04-platform` (Helm + ESO) |
| 비즈니스 메트릭 계산·전송 | `06-datastream` 의 `o2-agg` |
| **대시보드·Monitor** | **여기** |

## 준비

키를 Terraform 변수로 받지 않는다. 프로바이더가 환경변수를 직접 읽는다.
변수로 받으면 plan 파일에 남고, Secrets Manager data source 로 읽으면
**state 에 평문으로 남는다**(data source 결과도 state 에 저장된다). D-026 과 같은 이유다.

**한 번에 하려면 `apply.ps1` 을 쓴다.** 아래 수동 절차를 그대로 스크립트로
옮긴 것뿐이다 — 새로운 저장 방식이 아니라 "매번 손으로 치는 다섯 줄"을
한 명령으로 줄인 것이다. 키는 이 스크립트 실행 중에만 그 프로세스의
환경변수로 존재하고, 끝나면 지운다. **파일에는 절대 적지 않는다** — 이
디렉터리의 모든 `*.ps1`·`*.tfvars` 는 커밋되므로, 값을 적으면 그 순간부터
git 히스토리가 곧 비밀이 된다.

```powershell
.\apply.ps1            # init + plan 까지. 사람이 tfplan 을 보고 승인은 따로
.\apply.ps1 -Apply     # plan 을 보여준 뒤 확인받고 적용까지
.\apply.ps1 -Apply -Yes  # 확인 없이 적용 — 무인 실행용, 대화형 세션에서는 쓰지 않는다
```

수동으로 하고 싶거나(디버깅 등) 스크립트가 하는 일을 보고 싶으면:

```powershell
$env:AWS_PROFILE = "o2-data"      # S3 백엔드용. 이 스택에 aws 프로바이더는 없지만 백엔드는 쓴다

$raw = aws secretsmanager get-secret-value --secret-id o2/dev/datadog-new --query SecretString --output text
$j = $raw | ConvertFrom-Json
$env:DD_API_KEY = $j.'api-key'
$env:DD_APP_KEY = $j.'app-key'
$raw = $null; $j = $null

terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

`DD_APP_KEY` 가 없으면 대시보드 생성이 401 로 실패한다. API 키만으로는
읽기 전용 작업만 된다.

## 세 곳이 같은 조직을 가리켜야 한다

| 스택 | 변수 | 값 |
|---|---|---|
| `04-platform` | `datadog_site` | `us5.datadoghq.com` |
| `06-datastream` | `datadog_site` | `us5.datadoghq.com` |
| 여기 | `datadog_api_url` | `https://api.us5.datadoghq.com/` |

**갈려도 apply 는 성공한다.** 증상은 "대시보드가 빈다" 하나다. US5 조직인데
US1 기본값으로 보내면 403이 나고, `datadog.py` 가 그것을 삼켜 집계를 막지
않기 때문이다(의도된 설계).

## 대시보드 둘

| 파일 | 제목 | 데이터 출처 | 축 |
|---|---|---|---|
| `dashboard.tf` | O2 라이브커머스 — 비즈니스 관측 | `06-datastream` 집계 Lambda (`o2.warm.*`) | `service` · `env` |
| `dashboard_infra.tf` | O2 라이브커머스 — 인프라 · 쿠버네티스 운영 | `04-platform` 의 Datadog Agent (kubelet·kube-state-metrics·APM) | `kube_cluster_name` · `kube_namespace` (HTTP 그룹만 `service`·`env`) |

`dashboard_infra.tf` 는 Agent 가 이미 보내는 원시 지표(`kubernetes.*`,
`kubernetes_state.*`, `trace.http.request.*`)만 쓴다 — 이쪽은 집계 Lambda를
거치지 않으므로 `06-datastream` 이 죽어도 화면은 계속 채워진다. 구성:

| 그룹 | 무엇 |
|---|---|
| 1. 리소스 사용률 | CPU(request 대비 %)·메모리(limit 대비 %)·CPU throttling·Disk I/O·Network I/O |
| 2. 파드 생명주기 | Restart Count·Replicas(updated/available/unavailable/desired)·Pending Count·Restart/Waiting Reason 테이블 |
| 3. 노드 · 프로브 | 노드별 Ready 파드·Probe Failed Events(Kubernetes 이벤트 스트림) |
| 4. HTTP 트래픽 (APM) | RPS·성공률(non-5xx)·요청 rate·5xx count·응답시간·에러 |

비율 위젯(CPU%, 메모리%, throttling%, 성공률)은 `request.formula` +
`request.query.metric_query` 로 만든다 — provider 3.x 의 신형 문법이다.
`request.q` 한 줄로 되는 절대값 위젯과 헷갈리지 않는다.

**Probe Failed Events 는 게이지 메트릭이 없다.** 프로브 실패는
`kubernetesEvents`(datadog.tf)로 들어오는 Kubernetes 이벤트라서 이 위젯만
`event_stream_definition` 이다 — 다른 위젯처럼 timeseries 로 못 그린다.

`kube_cluster_name`·`kube_namespace` 기본값은 `variables.tf` 에 있고
`02-eks`/`04-platform` 의 실제 값과 맞춰 뒀다(`o2-eks` / `o2-dev`). 값이
갈리면 이 대시보드도 "비즈니스 관측" 과 같은 증상 — 화면이 조용히 빈다.

## 시나리오별 진행 화면 (`dashboard_scenario_flow.tf`)

시나리오 하나씩 대시보드 하나. 위젯이 위에서 아래로 **시간 순서**다 —
① 발생 → ② 감지 → ③ 진단 → ④ 조치 → ⑤ 검증. 실행 중에 위에서부터 채워진다.

`dashboard_scenarios.tf` 와 겹치지 않는다. 그쪽은 셋을 한 화면에 모은 **실험
진행자용 점검표**이고, 이쪽은 **하나가 어떻게 풀려 가는지**를 따라가는 화면이다.

⑤ 검증 그룹의 조건이 이 파일의 요점이고 `docs/scenario-experiment.md` 1.2 에서
그대로 가져왔다. **셋 다 단일 조건이 아니다.**

| | 성공 조건 | 이것을 안 보면 |
|---|---|---|
| S1 | 전파 p95 복귀 **AND** 정상 사용자 차단률 상한 이내 | "정상 사용자 절반을 차단해서 빨라진 것" 이 성공이 된다 |
| S2 | 격리 후 p95 복귀, **증설분 원복 뒤에도** 유지 | 격리가 들은 것인지 대수로 덮은 것인지 구분 안 된다 |
| S3 | 1차는 조치 없이 `ESCALATED`, 2차에서 전환 효과 | 장애를 걷어내고 좋아진 자연 회복을 우회 효과로 기록한다 |

### 쿼리 규칙 — 조용히 비는 사고를 막는 네 가지

전부 2026-08-27 에 `/api/v1/query` 로 실측해서 정했다. 어기면 **오류가 아니라
빈 화면**이 나오고, 빈 화면은 "정상" 과 구분되지 않는다.

**1. 템플릿 변수(`$env` 등)를 쓰지 않는다.** 이 파일의 범위는 Terraform 이 apply
시점에 값으로 박는다. 화면을 열 때 치환되는 것이 없으므로 **확인한 쿼리가 곧
배포된 쿼리다.**

**2. `key:value` 와 `key IN (...)` 를 한 중괄호에 같이 쓰지 않는다.** 섞으면
0 series 다.

```
{operation IN (chat.fanout,chat.message)}            -> 2 series
{env:dev,operation IN (chat.fanout,chat.message)}    -> 0 series   ★
{kube_deployment IN (api,api-canary)}                -> 2 series
{kube_namespace:o2-dev,kube_deployment IN (...)}     -> 0 series   ★
```

여러 값을 고를 때는 **와일드카드**(`operation:chat*`, `kube_deployment:api*`)를
쓰거나 필터 없이 `by {...}` 로 펼친다. `IN (...)` 은 단독일 때만 쓴다.

**3. `aws.sqs.*` · `aws.kinesis.*` · `aws.firehose.*` 에 env 를 붙이지 않는다.**
이 셋은 `env` 태그가 아예 없어서 붙이면 전부 0 series 다.

**4. `aws.lambda.*` 에도 env 를 붙이지 않는다.** `aws.lambda.invocations{*} by {env}`
가 `env:dev` 와 `env:N/A` 로 갈리는데, **`env:dev` 에 들어오는 함수는 `o2-agg`
하나뿐이고 나머지 17개가 전부 `env:N/A`** 다. `{env:dev}` 로 묶으면 에이전트 대응
경로(`o2-dify-ingress`·`o2-warm-api`·`o2-dev-dify-scale-executor` …)가 통째로
사라진다. 함수는 `functionname` 으로만 고른다.

### 기본 시간 창은 1일이다 (`live_span = "1d"`)

**Datadog 대시보드의 기본 창은 1시간이다.** 시나리오는 하루에 몇 번 돌까 말까
하므로, 그 상태로 열면 화면이 통째로 비어 있고 그것이 "고장" 으로 보인다.
실제로 그 신고가 들어왔다.

그래서 이 세 화면은 위젯마다 `live_span = "1d"` 를 박아 둔다. 실측으로 정했다.

| 창 | 실행이 없는 동안 비는 위젯 |
|---|---|
| 4시간 | S1 12개 중 **6개**, S3 11개 중 **6개** |
| **1일** | **0개** |

실험 한 번은 1~1.5시간이라 1일 창에서 한 덩어리로 보이고, 자세히 볼 때는 그
구간을 드래그해서 확대한다. 마지막 실행이 하루보다 오래됐으면 시간 선택기를
넓혀야 한다 — **빈 화면은 "계측이 없다" 가 아니라 "그 창 안에 실행이 없었다"** 다.

`live_span` 은 API 응답에서 `definition.time.live_span` 에 들어간다.
`definition.live_span` 을 읽으면 항상 `None` 이라 "안 걸렸다" 고 오독하게 된다.

### native 이관으로 죽은 `o2.warm.*` 지표를 쓰지 않는다

`0bb9f18` "complete native metric cutover" 이후 **`DATADOG_SCALARS` 에서 빠진
지표는 Datadog 에 안 온다.** 계약(warm snapshot)에는 남아 있어서 에이전트는
`o2-warm-api` 로 계속 읽지만, **대시보드에서는 죽은 쿼리다.**

2026-08-27 확인 — 아래는 **2026-08-25 00:00 이후 값이 없다.**

```
cache_hit_rate  channel_limited_rate  fallback_rate
latency_p50  latency_p95  latency_p99  overall_failure_rate
event_count(08-25 02:00)  rps_ratio(08-23)  cancel_rate(08-20)
```

살아 있는 것은 `confidence` · `distinct_users` · `event_rate` ·
`ip_diversity` · `pipeline_freshness_seconds` · `rps` · `top1pct_share` ·
`top5_share` 다.

**일곱 개가 같은 시각에 멈춘 것이 단서였다.** 실험을 안 해서 비는 것이라면
시각이 흩어진다. 동시에 끊기면 코드나 발행 목록이 바뀐 것이다.

이 때문에 초안의 위젯 두 개를 갈아 끼웠다.

| 죽은 쿼리 | 대체 | 비고 |
|---|---|---|
| `o2.warm.latency_p95 by {pod_name}` | `p99:o2.app.operation.duration by {pod_name}` | native 대체 있음 |
| `o2.warm.fallback_rate` | `o2.app.business_event by {event}` (실패율의 분모) | **native 대체 없음** — 폴백 관점은 warm snapshot 에만 남는다 |

### 실험 전에 비어 있는 것은 정상이다

이 세 화면은 부하와 장애 주입이 돌 때 채워진다. 다만 **"실험을 안 해서 빈 것" 과
"계측이 없어서 영영 안 채워지는 것" 은 다른 사실**이므로, 7일 창으로 전부 한 번씩
데이터가 들어온 것을 확인하고 넣었다(35개 위젯 전부). 확인 못 한 지표는 위젯을
만들지 않았다.

24시간 창으로만 봤다면 `o2.app.operation.duration{operation:payment.process}` 와
`o2.warm.latency_p95 by {pod_name}` 을 "없는 지표" 로 잘못 판정했을 것이다. 둘 다
실험 중에만 나온다.

## 대시보드 구성 — 위에서 아래가 진단 순서 (`dashboard.tf`)

| 그룹 | 무엇 | 알림 대상 |
|---|---|---|
| 0 | 읽는 법 (임계치가 잠정치라는 것, 빈 위젯의 세 가지 의미) | — |
| 1 | **사용자 영향** — 실패율·p95·재시도율·취소율 + 추세 | ✅ 여기서만 |
| 2 | 부하 — 평시 대비 배수, rps, 순 사용자 수 | 조건부 |
| 3 | 실패의 구조 — 이벤트별 실패율, p50/p95, 캐시·폴백, PG 지연 | 조건부 |
| 4 | **감별** — 집중도·간격 CV·click_ratio·다양성·버전 차이 | ❌ 걸지 않는다 |
| 5 | 파이프라인 자체 — event_count, confidence | ✅ no-data 감시 |

### 4번에 알림을 걸지 않는 이유

**어느 지표도 단독으로 시나리오를 특정하지 못한다.** 조합으로만 판단이 서고,
조합 판단은 사람 또는 에이전트가 한다. 받았을 때 할 행동이 정해지지 않은
신호는 알림이 아니라 화면에 둔다.

매크로 공격은 CPU도 에러율도 정상인 채로 진행된다. 그래서 이 그룹이 필요하고,
동시에 그래서 임계 하나로 울릴 수 없다.

### 5번이 있는 이유

푸시 기반이라 **"조용함"과 "정상"이 구분되지 않는다.** 스크레이프 방식이면
대상이 죽으면 `up=0` 으로 잡히지만, 아무도 안 보내면 아무 일도 없는 것처럼
보인다. 그 구분을 화면 안에서 할 수 있어야 한다.

## 지표 사전

접두사는 전부 `o2.warm.` 이고 태그는 `service` · `env` 다. 계산은
`06-datastream/warm/src/o2warm/metrics.py` 의 `derive()` 한 곳에서 일어난다.

**계산할 수 없는 지표는 0이 아니라 `None` 이다.** 표본이 없어서 0인 것과 실제로
0인 것을 에이전트가 구분해야 하기 때문이다. 그래서 위젯이 비는 것과 값이 0인
것은 다른 사실이다.

### 그룹 1 — 사용자 영향

알림의 근거가 될 수 있는 것은 이 넷뿐이다. **네 값 모두 인프라 지표가 전부
정상인 채로 움직인다.**

| 지표 | 뜻 | 무엇이 이 값을 올리는가 |
|---|---|---|
| `overall_failure_rate` | `result=FAILED` 인 시도의 비율 | PG·DB·재고 장애. **어느 것인지는 이 값으로 못 가린다** → 그룹 3 |
| `channel_limited_rate` | 전체 `chat.send` 중 `CHANNEL_LIMITED` 비율 | S1 채널 총량 조치가 정상 사용자 발화를 얼마나 차단했는지 |
| `latency_p95` | 느린 5%가 겪은 응답시간 (ms) | 평균이 멀쩡한 채로 꼬리만 나빠질 수 있다 |
| `retry_rate` | 재시도 이벤트 ÷ 재시도 가능 이벤트 | **서버가 200을 줘도 오른다.** 사용자가 다시 눌렀다는 것 자체가 체감 저하의 증거다 |
| `cancel_rate` | 취소 ÷ 주문 생성 | 취소는 사후·비동기라 요청 시점에는 아무 신호가 없다 |

### 그룹 2 — 부하

| 지표 | 뜻 | 읽는 법 |
|---|---|---|
| `rps_ratio` | 평시(EWMA) 대비 배수 | **1이 평시.** 특가 이벤트가 있는 서비스라 평시 자체가 시간대마다 다르다. 절대값보다 이쪽이 판단 근거다 |
| `rps` | 초당 비즈니스 이벤트 수 | 이 값만으로는 "높은가"에 답할 수 없다 |
| `distinct_users` | 윈도우 내 순 사용자 수 (적응 표본추출 추정) | **`rps` 와 함께 오르면 트래픽 증가, `rps` 만 오르면 소수가 때리는 것** → 그룹 4 |

### 그룹 3 — 실패의 구조

그룹 1이 "얼마나 나쁜가"라면 여기는 **"어디가 나쁜가"** 다.

| 지표 | 뜻 | 무엇을 가려내는가 |
|---|---|---|
| `failure_rate` by `event` | 이벤트별 실패율 (6종) | **PG 장애와 DB 장애는 전체 실패율이 같다.** 어느 이벤트가 실패하는지가 갈라낸다 |
| `latency_p50` | 응답시간 중앙값 | `p95` 와 함께 오르면 전반적 지연 |
| `latency_p95` | 응답시간 꼬리 | **`p50` 은 그대로인데 이것만 오르면 일부만 죽는 것** — 평균으로는 안 보인다 |
| `cache_hit_rate` | 캐시 적중률 | 떨어지면 원본을 때리고 있다 |
| `fallback_rate` | 폴백 사용률 | **폴백 성공은 '성공'으로 기록되어 실패율에 잡히지 않는다.** 이 값만 오르는 구간이 그 상태다 |
| `pg_latency_ratio` | 외부 PG 지연 비율의 중앙값 | 외부 결제사가 느려지는 것은 우리 코드가 정상인 채로 일어난다 |

`event` 는 값의 종류가 6개로 고정이라 태그로 안전하다. **실패 사유 코드
분포(`failure_codes`)는 대시보드에 없다** — 맵이라 메트릭이 될 수 없다.
에이전트가 DynamoDB 에서 읽는다.

### 그룹 4 — 감별 (알림 대상 아님)

**어느 지표도 단독으로 시나리오를 특정하지 못한다.** 조합으로만 판단이 서고,
조합 판단은 사람 또는 에이전트가 한다. 매크로 공격은 CPU도 에러율도 정상인
채로 진행되므로 이 축이 필요하고, 동시에 그래서 임계 하나로 울릴 수 없다.

| 지표 | 뜻 | 어느 쪽으로 기울면 |
|---|---|---|
| `top5_share` | 상위 5계정의 요청 점유율 | 높을수록 소수 집중 = 매크로. **사용자가 수백 명이면 상위 1%가 2~3개뿐이라 이쪽이 또렷하다** |
| `top1pct_share` | 상위 1% 계정의 점유율 | 규모가 커져도 의미가 유지된다. 규모가 작으면 무리를 놓친다 |
| `interval_cv_top` | 상위 계정의 요청 간격 변동계수 | **낮으면 기계.** 사람은 간격이 불규칙하다. 감별에 쓰는 값은 이쪽이다 |
| `interval_cv` | 전체 요청 간격 변동계수 (요청 가중) | 전체가 규칙적인지. 소수 매크로는 여기서 희석된다 |
| `click_ratio` | 클릭 ÷ 해당 서버 요청 | **낮으면 버튼 없이 API를 직접 부르는 것.** 두 스트림이 같은 10초 창에 모여야만 나온다 |
| `ua_diversity` | UA 종류 ÷ UA 실은 이벤트 수 | 낮으면 같은 클라이언트가 반복 |
| `ip_diversity` | IP 종류 ÷ 비즈니스 이벤트 수 | 낮으면 소수 IP 집중 |
| `version_fail_delta` | 최신 버전 실패율 − 직전 버전 실패율 | **0보다 크면 배포 장애.** 인프라 지표로는 절대 보이지 않는다 |

### 그룹 5 — 파이프라인 자체

푸시 기반이라 **"조용함"과 "정상"이 구분되지 않는다.** 그 구분을 화면 안에서
하기 위한 두 값이다.

| 지표 | 뜻 | 0이거나 비면 |
|---|---|---|
| `event_count` | 윈도우가 받은 이벤트 수 | 위의 모든 위젯이 비는 것이 **정상**이다. 0이 아닌데 비면 계산이나 전송 문제다 |
| `confidence` | 지표 신뢰도 0~1 (신선도·완전성 종합) | 표본이 적어 계산을 못 한 것이다. 낮으면 위 지표들을 액면가로 믿지 않는다 |

### 대시보드에 없는 것

계산은 되지만 **Datadog 으로 보내지 않는** 값들이다. 맵이거나 고카디널리티라
태그로 펼치면 `user_key` 수만큼 시계열이 생겨 요금이 터진다. 에이전트는
`o2-warm-api` 로 DynamoDB 에서 읽는다.

| 값 | 왜 없는가 |
|---|---|
| `failure_codes` | 이벤트별 사유 코드 분포. 맵 |
| `top_contributors` | 상위 기여 계정 목록. 고카디널리티 |
| `version_detail` | 버전별 시도·실패 내역. 맵 |
| `segments` · `segment_skew` | 축별 편차 순위. 맵과 리스트 |
| `cancel_reasons` · `click_detail` | 분포. 맵 |
| `baseline_rps` | `DATADOG_SCALARS` 목록에 없다 |

**이 경계가 Hot/Warm 분리의 실체다.** 대시보드는 "무엇이 나쁜가"까지 답하고,
"누가·어느 구간이 나쁜가"는 에이전트가 DynamoDB 에서 본다.

## 위젯이 비어 있을 때

**지표는 0이 아니라 `None` 으로 온다.** 표본이 없어서 0인 것과 실제로 0인 것을
에이전트가 구분해야 하기 때문이다(`o2warm/metrics.py`). 그래서 빈 위젯은
정상일 수도, 고장일 수도 있다.

2026-08-17 실측 — 이벤트 60건(`coupon.issue`·`payment.process`)만 흘린 상태:

| 값이 있다 (13) | 값이 없다 (9) | 왜 없나 |
|---|---|---|
| `rps` `event_count` `distinct_users` | `rps_ratio` | EWMA 표본 30개(약 5분)가 쌓여야 계산된다 |
| `overall_failure_rate` `failure_rate` | `cache_hit_rate` `fallback_rate` | `inventory.check` 이벤트가 필요하다 |
| `latency_p50` `latency_p95` | `cancel_rate` | `order.cancel` 이벤트가 필요하다 |
| `retry_rate` | `pg_latency_ratio` | `payment.process` 가 필요 — `payment-api` 에는 값이 있다 |
| `top5_share` `top1pct_share` | `interval_cv` `interval_cv_top` | 한 사용자가 윈도우 안에서 여러 번 요청해야 간격이 생긴다 |
| `ip_diversity` `click_ratio` | `ua_diversity` | `ua_key` 는 `client.action` 에만 실린다 — 클라이언트 스트림 필요 |
| `confidence` | `version_fail_delta` | 서로 다른 `service_version` 두 개가 필요하다 |

**즉 위 9개가 비는 것은 지금 정상이다.** 파이프라인 고장과 구분하려면 5번 그룹의
`event_count` 를 먼저 본다. 그것도 0이면 이렇게 확인한다.

```powershell
aws logs tail /aws/lambda/o2-agg --since 10m --profile o2-data `
  --filter-pattern "datadog_series"
```

`datadog_series` 가 전송에 성공한 시계열 수다. 0이면 같은 로그의 `[o2warm]`
줄에 사유가 있다. 자세한 절차는 `../06-datastream/warm/DEPLOY.md`.

## Monitor 구성 (`monitor.tf`)

원래 방침은 "임계치 근거가 없으니 평시 분포를 며칠 보고 정한다"였다 — 순서를
뒤집으면 오탐으로 시작하고, 오탐으로 시작한 알림은 곧 전부 무시된다는 이유다.
`failure-scenarios-transcript.md` 의 5개 장애 시나리오에 대한 alert 작업
지시가 그 순서를 뒤집어, 시나리오 문서의 구체적 수치를 근거로 먼저 만들었다.
그 트레이드오프와 시나리오별 상세 설계는 Confluence
["Datadog 장애 대응 Alert 시스템 제안서"](https://kimdohun3554.atlassian.net/wiki/spaces/~7120203f2d5f61e05b42e98bdc88a15ec9dd62/pages/3768322)
(2026-08-19)에 있다 — `monitor.tf` 는 그 문서의 구현 계획을 코드로 옮긴 것뿐이고,
새 판단은 거기서 먼저 정한다.

알림 라우팅(Slack 등)은 이 스택이 다루지 않는다 — 인프라팀이 별도 webhook
push 경로로 Datadog Monitor를 에이전트에 연결하는 작업을 진행 중이다. 여기서는
그 webhook이 받게 될 Monitor(임계치·쿼리·진단 안내가 담긴 message 본문)만
만든다. 라우팅이 정해지면 각 Monitor의 `message`에 수신자 설정만 얹으면 된다.

세 단계로 나뉜다 — 지표가 없다고 포기하지 않고, 지금 되는 것과 계측이 먼저
필요한 것을 코드로 구분해 둔다.

| Monitor | 시나리오 | 단계 | 상태 |
|---|---|---|---|
| `order_latency_p95` | 2 (실제 트리거) · 5 (재사용) | Phase 0 | 활성 — 기존 `o2.warm.*` 지표만 사용 |
| `cache_absorption_failure` | 4 | Phase 0 | 활성 — 기존 `o2.warm.*` 지표만 사용 |
| `order_confirm_backlog_age` | 6 | Phase 1 | **기본 비활성** — `enable_queue_backlog_monitor`. 코드 변경은 필요 없고, SQS 지표가 이 조직에 실제로 수집되는지 Metrics Explorer 확인만 하면 켤 수 있다 |
| `chat_ingest_surge` | 2 (조기 경보) | Phase 2 | **기본 비활성** — `enable_chat_ingest_monitor`. `chat.send` 발행이 지금 stdout 싱크뿐이라 Datadog까지 안 온다(아래 참고) |
| `cache_hit_rate_pod_outlier` | 1 | Phase 2 | **기본 비활성** — `enable_pod_cache_outlier_monitor`. `cache_hit_rate`에 `pod_name` 태그가 없어 SDK·집계 Lambda 변경이 먼저 필요하다 |
| `order_confirm_stall` | 6 (보조) | Phase 2 | **기본 비활성** — `enable_order_confirm_stall_monitor`. `order.confirm` 이벤트 자체가 계약에 없다 |

시나리오 1(파드별 캐시 스큐)과 시나리오 6("접수 대비 확정" 직접 비교)은
트랜스크립트 원문이 "알림으로 안 잡힌다"고 스스로 밝힌 시나리오다 — 지금
이 조직에 그 신호를 낼 지표 자체가 없어서였다. 없는 지표에 Monitor를 걸면
영구 `No Data`로 조용히 죽으므로, 필요한 계측(pod별 `cache_hit_rate` 태그,
`order.confirm` 이벤트 신설)이 들어가기 전까지는 위 Phase 2 Monitor를 기본
비활성으로 둔다. 각 Monitor 정의 위 주석(`monitor.tf`)에 활성화 전 필요한
코드 변경이 구체적으로 적혀 있다 — 대부분 이 저장소(`06-datastream`,
`apps/chat-gateway`) 안이고, 이벤트 이름 자체는 `o2-sdk-for-event`(외부
저장소, 백데이터 파트 소관) 쪽 PR이 먼저 필요하다.

`chat_ingest_surge`는 애초에 "Phase 0으로 바로 켜진다"고 여겼다가 실측하며
정정한 사례다 — `contracts.md`는 `chat.send`가 이미 발행된다고 적어 뒀지만,
`apps/chat-gateway/src/events.ts`의 `emitChatSend()`를 읽어보면 기본값이
꺼져 있고(`EMIT_CHAT_EVENTS=false`), 켜져도 목적지가 Kinesis가 아니라
`process.stdout.write` 뿐이다 — Datadog 로그 수집도 꺼져 있어(`logs.enabled
= false`) 이 이벤트는 지금 어디에도 도착하지 않는다. "계약에 있다"와
"실제로 흐른다"는 다른 문장이라는 교훈을 여기서도 반복한다(`docs/decisions.md`
D-031의 결론과 같은 종류).

Monitor 를 만들 때 주의할 것 하나 — **`for` 는 그대로 옮겨지지 않는다.**
"10분 내내 초과"를 원하면 `min(last_10m)` 을 써야 한다. `avg(last_10m)` 은
10분 평균이라 1분간 30% + 9분간 0% 를 놓친다. `require_full_window = true` 와
`notify_no_data` 도 함께 켠다 — 푸시 기반이라 no-data 가 실제 신호다.
`monitor.tf` 의 Monitor는 전부 이 관례를 따른다.

## 이름과 번호

state key 는 `observability/datadog-new-org/terraform.tfstate` 다. 디렉터리
이름(`05-datadog`)이나 번호를 쓰지 않았다. 번호는 의존 순서라 바뀔 수 있고
(D-029 에서 `05` 는 media 예약이었다), key 가 바뀌면 state 가 갈린다.

`datadog-new-org/` 접미사는 체험판 조직(AP1) → 팀 조직(US5) 이주 때 붙었다.
구 조직의 대시보드·Monitor ID 를 든 옛 state 가 `observability/terraform.tfstate`
에 있어서 같은 키를 다시 쓸 수 없었다. 그 옛 state 는 2026-08-20 에 지웠지만
(버킷 버전 관리로 복구 가능), **키를 되돌리면 state 가 또 갈리므로 그대로 둔다.**


`03-data` 가 `datastore/`, `06-datastream` 이 `data/` 를 쓰는 것과 같은 종류의
주의다 — 그쪽은 이미 한 번 밟은 함정이다(D-015).

## 비용

커스텀 메트릭은 시계열 단위로 과금된다. `DATADOG_SCALARS` 22개 × 서비스 수 +
`failure_rate`(이벤트 6종) + `confidence` 다. 서비스 3개면 약 78개.

**대시보드를 만들다 태그를 늘리고 싶어지는 순간이 비용이 새는 지점이다.**
맵과 고카디널리티 값(`failure_codes` `top_contributors` `version_detail`)은
Datadog 으로 보내지 않고 DynamoDB 에만 둔다. 에이전트는 그쪽을 읽는다.
