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

```powershell
$env:AWS_PROFILE = "o2-data"      # S3 백엔드용. 이 스택에 aws 프로바이더는 없지만 백엔드는 쓴다

$raw = aws secretsmanager get-secret-value --secret-id o2/dev/datadog --query SecretString --output text
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
| `04-platform` | `datadog_site` | `ap1.datadoghq.com` |
| `06-datastream` | `datadog_site` | `ap1.datadoghq.com` |
| 여기 | `datadog_api_url` | `https://api.ap1.datadoghq.com/` |

**갈려도 apply 는 성공한다.** 증상은 "대시보드가 빈다" 하나다. AP1 조직인데
US1 기본값으로 보내면 403이 나고, `datadog.py` 가 그것을 삼켜 집계를 막지
않기 때문이다(의도된 설계).

## 대시보드 구성 — 위에서 아래가 진단 순서

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
| `baseline_rps` · `latency_p99` | `DATADOG_SCALARS` 목록에 없다 |

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

## Monitor 를 아직 만들지 않은 이유

임계치에 근거가 없다. 교재의 5%·10분은 그 교재의 서비스 조건에서 나온 값이고
우리 평시 분포는 아직 모른다. 며칠 대시보드를 보고 정한다.

순서를 뒤집으면 오탐으로 시작하고, 오탐으로 시작한 알림은 곧 전부 무시된다.

Monitor 를 만들 때 주의할 것 하나 — **`for` 는 그대로 옮겨지지 않는다.**
"10분 내내 초과"를 원하면 `min(last_10m)` 을 써야 한다. `avg(last_10m)` 은
10분 평균이라 1분간 30% + 9분간 0% 를 놓친다. `require_full_window = true` 와
`notify_no_data` 도 함께 켠다 — 푸시 기반이라 no-data 가 실제 신호다.

## 이름과 번호

state key 는 `observability/terraform.tfstate` 다. 디렉터리 이름(`05-datadog`)이나
번호를 쓰지 않았다. 번호는 의존 순서라 바뀔 수 있고(D-025 에서 `05` 는 media
예약이었다), key 가 바뀌면 state 가 갈린다.

`03-data` 가 `datastore/`, `06-datastream` 이 `data/` 를 쓰는 것과 같은 종류의
주의다 — 그쪽은 이미 한 번 밟은 함정이다(D-015).

## 비용

커스텀 메트릭은 시계열 단위로 과금된다. `DATADOG_SCALARS` 20개 × 서비스 수 +
`failure_rate`(이벤트 6종) + `confidence` 다. 서비스 3개면 약 78개.

**대시보드를 만들다 태그를 늘리고 싶어지는 순간이 비용이 새는 지점이다.**
맵과 고카디널리티 값(`failure_codes` `top_contributors` `version_detail`)은
Datadog 으로 보내지 않고 DynamoDB 에만 둔다. 에이전트는 그쪽을 읽는다.
