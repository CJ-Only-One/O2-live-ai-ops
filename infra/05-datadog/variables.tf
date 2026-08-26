variable "datadog_api_url" {
  description = <<-EOT
    Datadog API 엔드포인트. **조직이 US5 라 기본값(US1)을 쓰면 안 된다.**

    `04-platform` 의 `datadog_site` 와 `06-datastream` 의 `datadog_site` 가
    가리키는 곳과 같은 조직이어야 한다. 세 곳이 갈리면 Agent·집계 Lambda·
    대시보드가 서로 다른 조직을 보고, 증상은 "대시보드가 빈다" 하나다.
  EOT
  type        = string
  default     = "https://api.us5.datadoghq.com/"
}

variable "metric_prefix" {
  description = <<-EOT
    비즈니스 메트릭 접두사. `06-datastream` 의 `O2_DD_PREFIX` 기본값과
    같아야 한다 (`o2warm/settings.py` 의 `dd_prefix`).

    여기만 고치면 위젯이 조용히 빈다 — 존재하지 않는 메트릭을 조회해도
    Datadog 은 오류가 아니라 빈 series 를 준다.
  EOT
  type        = string
  default     = "o2.warm."
}

variable "default_service" {
  description = <<-EOT
    대시보드를 열었을 때 처음 보이는 서비스. 템플릿 변수 기본값이다.

    `*` 로 두면 모든 서비스가 한 선에 합쳐져 평균이 개별 장애를 가린다.
    하나를 정해 두고 필요할 때 바꾸는 편이 낫다.
  EOT
  type        = string
  default     = "api"
}

variable "environment" {
  description = <<-EOT
    메트릭에 붙는 env 태그. 집계 Lambda 의 `DD_ENV`(`06-datastream` 의
    `environment`) 와 같아야 한다.

    다르면 대시보드가 빈다. apply 는 성공하므로 파이프라인이 죽은 것과
    구분되지 않는다 (D-034).
  EOT
  type        = string
  default     = "dev"
}

# ── 임계치 ──────────────────────────────────────────────────
#
# **이 값들은 잠정치다.** 교재의 5% 는 교재의 서비스 조건에서 나온 값이고,
# 우리 평시 분포는 아직 모른다. 며칠 데이터를 보고 고친다.
#
# 여기 값은 대시보드 색깔만 바꾼다. Monitor 를 만들 때는 이 변수를 공유해
# "보이는 임계"와 "울리는 임계"가 갈리지 않게 한다.

variable "failure_rate_warning" {
  description = "실패율 경고 임계. 이 값 아래는 초록."
  type        = number
  default     = 0.01
}

variable "failure_rate_critical" {
  description = "실패율 위험 임계."
  type        = number
  default     = 0.05
}

variable "latency_p95_warning" {
  description = "p95 응답시간 경고 임계 (ms)."
  type        = number
  default     = 300
}

variable "latency_p95_critical" {
  description = "p95 응답시간 위험 임계 (ms). 교재 예시의 1초."
  type        = number
  default     = 1000
}

variable "retry_rate_warning" {
  description = <<-EOT
    재시도율 경고 임계.

    이 지표는 서버가 200을 주는 동안에도 오른다 — 사용자가 같은 동작을
    반복했다는 것 자체가 체감 저하의 증거다. 인프라 임계로는 안 잡힌다.
  EOT
  type        = number
  default     = 0.05
}

variable "retry_rate_critical" {
  description = "재시도율 위험 임계."
  type        = number
  default     = 0.15
}

variable "cancel_rate_warning" {
  description = "주문 취소율 경고 임계. 취소는 사후·비동기라 요청 시점 신호가 없다."
  type        = number
  default     = 0.05
}

variable "cancel_rate_critical" {
  description = "주문 취소율 위험 임계."
  type        = number
  default     = 0.15
}

# ── 인프라 대시보드 축 ──────────────────────────────────────────
#
# `dashboard_infra.tf` 가 쓰는 값이다. 04-platform/02-eks 의 값과 갈리면
# "대시보드가 빈다" 증상이 여기서도 그대로 재현된다 — 원격 상태 참조 없이
# 값만 맞추는 이유는 versions.tf 의 주석과 같다(클러스터가 죽어도 이 스택은
# 살아 있어야 한다).

variable "kube_cluster_name" {
  description = <<-EOT
    Datadog 이 붙이는 `kube_cluster_name` 태그 값.

    `04-platform/datadog.tf` 의 Helm values `datadog.clusterName` 이 이 값을
    보낸다. 그 값은 `02-eks` 의 `cluster_name` 변수(`local.cluster_name`)에서
    온다 — 지금은 `o2-eks`.
  EOT
  type        = string
  default     = "o2-eks"
}

variable "kube_namespace" {
  description = <<-EOT
    애플리케이션 파드가 도는 네임스페이스.

    `04-platform` 의 `app_namespace` 변수와 같아야 한다 — 지금은 `o2-dev`.
    datadog-agent·kube-system 등 플랫폼 네임스페이스까지 같이 보고 싶으면
    대시보드를 연 뒤 상단 템플릿 변수에서 `*` 로 바꾼다.
  EOT
  type        = string
  default     = "o2-dev"
}

# ── 인프라 임계치 ────────────────────────────────────────────────
#
# 위 "임계치" 절과 같은 성격이다 — 잠정치이고, 대시보드 마커 색깔만 바꾼다.

variable "cpu_request_pct_warning" {
  description = "CPU 사용률(request 대비) 경고 임계 (%). request 를 넘기기 시작하는 지점."
  type        = number
  default     = 100
}

variable "cpu_throttling_warning" {
  description = "CPU CFS 스로틀링 비율 경고 임계 (%)."
  type        = number
  default     = 25
}

# ── Monitor — 장애 시나리오 alert ──────────────────────────────────
#
# `works/prompt.md` 요구사항과 Confluence "Datadog 장애 대응 Alert 시스템
# 제안서"(2026-08-19)를 근거로 만든 임계치다. 위 그룹1 임계치(failure_rate_*,
# latency_p95_*)와 마찬가지로 **잠정치**다 — 트랜스크립트 예시 시나리오의
# 숫자이지 우리 서비스의 평시 분포가 아니다. `monitor.tf` 가 이 값들을 쓴다.
#
# 알림 라우팅(Slack 등)은 이번 세션 범위 밖이다 — 인프라팀이 별도 webhook
# push 경로로 Datadog Monitor 를 에이전트에 연결하는 작업을 진행 중이다.
# 여기서는 그 webhook 이 받을 Monitor(임계치·쿼리)만 만든다.

variable "scenario_entry_window_minutes" {
  description = <<-EOT
    **시나리오 진입 알림**의 평가 창(분). 기본 5.

    Datadog 은 창을 쿼리 문자열 안에 넣습니다(`min(last_5m)`). 그동안 이
    값이 각 Monitor 에 흩어져 박혀 있어서, 데모용으로 창을 줄이려면 리소스를
    복제하는 수밖에 없었습니다.

    **복제하면 안 됩니다.** 운영용과 데모용의 임계가 갈리고, 한쪽만 고치는
    순간 둘이 다른 것을 감시하게 됩니다 — `variables.tf` 가 원래부터
    경계하던 함정입니다. 그래서 리소스를 늘리는 대신 이 변수를 줄입니다.

    **줄일 때 알고 있어야 할 것** — 창이 짧아지면 표본이 줄어 오탐이 늡니다.
    warm 집계 윈도우가 10초이므로 1분이면 표본이 6개뿐입니다. 데모에서
    2분 아래로는 내리지 않기를 권합니다.

    이 변수가 거는 것은 **진입 알림**뿐입니다. outlier 탐지(10분)와
    파이프라인 Monitor 는 각자 다른 이유로 창이 정해져 있어 따로 둡니다.
  EOT
  type        = number
  default     = 5

  validation {
    condition     = var.scenario_entry_window_minutes >= 1 && var.scenario_entry_window_minutes <= 60
    error_message = "평가 창은 1~60분이어야 한다. Datadog 이 그 밖의 값을 거절한다."
  }
}

variable "chat_early_warning_window_minutes" {
  description = <<-EOT
    채팅 인입 조기 경보(`chat_ingest_surge`)의 평가 창(분). 기본 **2**.

    **진입 알림(5분)보다 일부러 짧습니다.** 이 Monitor 의 존재 이유가
    "주문 p95 가 무너지기 전에 먼저 울린다" 이기 때문입니다. 트랜스크립트
    시간축에서 채팅 인입 급증(T+6s)과 주문 p99 급등(T+52s) 사이가 46초이고,
    그 사이에 울려야 대가 게이트를 열 시간이 생깁니다.

    `scenario_entry_window_minutes` 와 묶지 않은 이유가 그것입니다 — 같이
    움직이면 조기 경보가 진입 알림과 같은 시점에 울려 **조기가 아니게**
    됩니다.

    더 줄이는 것은 권하지 않습니다. `rps_ratio` 는 EWMA 표본 30개(약 5분)가
    쌓여야 값이 생기므로, 창을 줄여도 방송 시작 직후에는 어차피 값이
    없습니다.
  EOT
  type        = number
  default     = 2

  validation {
    condition     = var.chat_early_warning_window_minutes >= 1 && var.chat_early_warning_window_minutes <= 60
    error_message = "평가 창은 1~60분이어야 한다. Datadog 이 그 밖의 값을 거절한다."
  }
}

variable "enable_chat_ingest_monitor" {
  description = <<-EOT
    시나리오 2 조기 경보(`chat_ingest_surge`) 활성화 여부.
    **`terraform.tfvars` 에서 `true` 로 켜져 있다.**

    기본값은 `false` 로 남겨 둔다 — 이 스택을 새 조직에 처음 세울 때는
    chat-gateway 가 아직 이벤트를 안 보내는 것이 정상이고, 그때 켜져 있으면
    영구 No Data 로 조용히 죽는다.

    켤 조건은 `o2.app.business_event{service:chat-gateway,event:chat.send}` 에 시계열이 있는 것이고,
    **이 조직에서는 이미 충족됐다**(2026-08-24 확인). `events.ts` 가
    `PutRecordCommand` 로 Kinesis 에 직접 넣고 배포 환경변수도 설정돼 있다.

    2026-08-24 이전 이 자리에는 "목적지가 `process.stdout.write` 뿐이라
    Datadog 까지 오지 않는다" 가 적혀 있었다. **그 사이 사실이 아니게 됐는데
    주석만 남아 있었다** — 경위는 monitor.tf 의 이 리소스 위 주석.
  EOT
  type        = bool
  default     = false
}

variable "chat_rps_ratio_warning" {
  description = <<-EOT
    시나리오 2(특가 오픈 캐스케이드) 조기 경보 임계.
    native chat.send rate의 Datadog anomaly가 평시 범위를 벗어나면 경고한다.

    **실측이 아니다.** 트랜스크립트 예시(20→210 msg/s, 10.5배)의 절반을
    잠정치로 둔 것이고, 새 명세의 채널 포화점과는 무관하다. 재고 나면
    `measurements.md` 에 남기고 여기를 고친다. 안 쟀으면 "안 쟀다" 고 한다.

    **한 가지 더 — 이 지표는 즉시 생기지 않는다.** `rps_ratio` 는 EWMA
    표본 30개(약 5분)가 쌓여야 값이 나온다. 방송 시작 직후에는 조기 경보가
    안 나오므로, S1 이 "특가 오픈 순간" 을 노린다면 그 워밍업 시간을
    진행 순서에 넣어야 한다.
  EOT
  type        = number
  default     = 5
}

variable "enable_chat_incident_monitors" {
  description = "S1 채팅 전파 p95·정상 사용자 차단률 Incident 보강 Monitor"
  type        = bool
  default     = false
}

variable "chat_propagation_p95_warning_ms" {
  description = <<-EOT
    S1 전파 p95 경고 임계 (ms).

    **M-010 실측 기준이다.** 평시 250~282ms(8,000~20,000 아이템/s), 무너지기
    시작하는 지점이 479ms(2,000 연결 · 40,000 아이템/s). 그 사이에 둔다.

    ★ 처음에는 800 이었다. **그 값으로는 붕괴가 시작돼도 안 울었다** — 479ms 가
      경고 임계 아래였다.
  EOT
  type        = number
  default     = 400
}

variable "chat_propagation_p95_critical_ms" {
  description = <<-EOT
    S1 전파 p95 위험 임계 (ms).

    **M-010 실측 기준이다.** 가장 나쁜 실측이 1,286ms(4,000 연결 · 40,000
    아이템/s)이므로 임계는 그보다 낮아야 한다.

    ★ 처음에는 1,500 이었다. **실측된 최악의 붕괴(1,286ms)조차 이 값을 못 넘어**
      critical 이 한 번도 안 떴다. 설정은 정상이고 쿼리도 유효해서 알아채기 어렵다.
  EOT
  type        = number
  default     = 800
}

variable "chat_block_rate_warning" {
  description = "S1 정상 사용자 차단률 경고 임계. 실제 분포 측정 전 초기 정책값"
  type        = number
  default     = 0.05
}

variable "chat_block_rate_critical" {
  description = "S1 정상 사용자 차단률 critical 임계. 실제 분포 측정 전 초기 정책값"
  type        = number
  default     = 0.1
}

variable "cache_hit_rate_critical" {
  description = <<-EOT
    시나리오 4(캐시 흡수 실패) 임계. native `o2.app.cache_access` 비율이
    이 아래로 떨어지고 동시에 `latency_p95` 가 위험 임계를 넘으면 알림.
    README 실측 사례(71%→34%, 절반 이하)를 근거로 0.5를 잠정치로 둔다.
    단독으로는 쓰지 않는다 — latency_p95 동반 조건 없이는 표본 부족 노이즈에
    오탐한다(제안서 4·7절).
  EOT
  type        = number
  default     = 0.5
}

variable "enable_queue_backlog_monitor" {
  description = <<-EOT
    시나리오 6(주문 확정 큐 적체) Monitor 활성화 여부. 기본 `false`.

    이 Monitor는 `aws.sqs.approximate_age_of_oldest_message` 를 쓰는데, 이
    지표가 실제로 이 Datadog 조직에 들어오고 있는지 이 스택에서 확인하지
    못했다(DD_APP_KEY 로 Metrics Explorer 조회가 필요 — 제안서 4·8절).
    확인 후 `true` 로 켠다. 켜지 않은 채 두면 Monitor 자체가 안 만들어지므로
    "확인 안 된 지표에 조용히 죽은 Monitor를 걸지 않는다"는 원칙을 지킨다.
  EOT
  type        = bool
  default     = false
}

variable "order_confirm_queue_name" {
  description = "주문 확정 SQS 큐 이름. `03-data/sqs.tf` 의 `aws_sqs_queue.order.name` 과 같아야 한다."
  type        = string
  default     = "o2-dev-order"
}

variable "queue_backlog_age_warning_seconds" {
  description = "주문 확정 큐 — 가장 오래된 미처리 메시지 나이 경고 임계 (초)."
  type        = number
  default     = 60
}

variable "queue_backlog_age_critical_seconds" {
  description = "주문 확정 큐 — 가장 오래된 미처리 메시지 나이 위험 임계 (초)."
  type        = number
  default     = 300
}

###############################################################################
# S1·S2·S3 조기 감지 Alert (`scenario_alerts.tf`)
#
# 임계값의 출처를 섞지 않는다. 아래 설명에 `M-0NN` 이 있으면 실측이고,
# **"안 쟀다"** 라고 적힌 것은 정책값이다. 정책값은 첫 실험에서 실제 분포를 재고
# `docs/measurements.md` 의 해당 절에 행을 추가한 뒤 갱신한다.
###############################################################################

variable "enable_scenario_alerts" {
  description = <<-EOT
    S1·S2·S3 조기 감지 Monitor 활성화 여부.

    켜면 `@webhook-o2-dify` 가 붙은 진입 Monitor 가 **셋 늘어난다.** 지금 경로에는
    상관관계 계층이 없어 Monitor 하나가 곧 Dify 워크플로 실행 하나이므로
    (`o2-dify-ingress` → Lambda 비동기 큐 → `o2-dify-worker`), 켜기 전에
    `alert_relay_max_concurrency`(06-agent, 기본 5) 가 감당하는지 본다.

    실험 중이 아닐 때 부하가 이 Monitor 들을 깨우면 측정 중 에이전트가 무언가
    바꾼다(T-017, `docs/scenario-readiness.md` 5절).
  EOT
  type        = bool
  default     = false
}

variable "enable_operation_duration_percentiles" {
  description = <<-EOT
    `o2.app.operation.duration` 의 percentile 집계 활성화 여부.

    **끄면 `p95:` 쿼리가 오류가 아니라 조용히 series 0 이 된다**(T-031).
    S3 의 `s3_pg_latency_p95` 가 이 metric 을 쓰므로 같이 켜야 한다.

    이 metric 에 이미 콘솔·API 로 만든 tag configuration 이 있으면 apply 가 409 로
    실패한다. 그때는 이 값을 `false` 로 두지 말고 `chat_propagation_metric.tf` 처럼
    `import` 블록으로 인수한다 — 끄면 S3 Monitor 가 조용히 죽는다.
  EOT
  type        = bool
  default     = true
}

variable "scenario_early_window_minutes" {
  description = <<-EOT
    **조기 감지** Monitor 의 평가 창(분). 기본 2.

    진입 알림(`scenario_entry_window_minutes`, 기본 5)보다 일부러 짧다. 이 축의
    존재 이유가 "사용자 영향이 나기 전에 먼저 운다" 이기 때문이다.
    `chat_early_warning_window_minutes` 와 같은 근거다.
  EOT
  type        = number
  default     = 2
}

variable "s1_fanout_items_warning" {
  description = <<-EOT
    S1 채팅 팬아웃 총량 경고 임계 (아이템/s).

    **M-010 실측이다** — 2파드 기준 안전선 20,000 아이템/s 에서 전파 p95 267ms.
    `replicas` 나 직렬화 방식을 바꾸면 M-010 을 다시 재고 이 값도 고친다.
  EOT
  type        = number
  default     = 20000
}

variable "s1_fanout_items_critical" {
  description = <<-EOT
    S1 채팅 팬아웃 총량 위험 임계 (아이템/s).

    **안 쟀다.** M-010 은 20,000(정상)과 40,000(붕괴, p95 479~1,286ms) 두 점만
    있고 그 사이 표본이 없다. 30,000 은 보간이다. 첫 S1 실험에서 계단을 잘게
    올려 붕괴가 시작되는 실제 값을 찾고 이 값을 갈아치운다.
  EOT
  type        = number
  default     = 30000
}

variable "s1_fanout_dropped_critical" {
  description = <<-EOT
    S1 채팅 전파 유실 위험 임계 (아이템/s).

    M-010 전 구간에서 전달률이 99.9% 아래로 내려간 적이 없다. 0 초과는 실측 범위
    밖이라는 뜻이므로 임계를 0 에 붙여 둔다.
  EOT
  type        = number
  default     = 0
}

variable "s2_experiment_broadcast_id" {
  description = <<-EOT
    S2 실험 부하가 도는 방송 ID. 진입 Monitor 태그로 실려 Dify normalize 가
    broadcast_id 를 지어내지 않게 한다(T-044). 실험 방송이 바뀌면 같이 바꾼다.
  EOT
  type        = string
  default     = "bc_1042"

  validation {
    condition     = can(regex("^bc_[0-9]+$", var.s2_experiment_broadcast_id))
    error_message = "api 의 BroadcastId 계약과 같은 ^bc_[0-9]+$ 형식이어야 한다."
  }
}

variable "s2_tail_latency_p99_warning_ms" {
  description = <<-EOT
    S2 API 꼬리 지연 경고 임계 (ms, 서버측 p99).

    바닥은 실측이 있다 — **무부하 서버측 p99 = 8ms**(M-016, 2026-08-25 조회).
    천장은 계약 상한 p99 2,000ms(architecture.md 12.1)다.

    **그 사이는 안 쟀다.** 부하 구간의 p99 분포 표본이 없어서 300 은 두 끝 사이에서
    고른 값이다. M-009 의 숫자는 ALB 경유 클라이언트 관점이라 서버측 span metric 에
    그대로 못 쓴다. 첫 S2 실험에서 카나리 주입 전후 분포를 재고 갱신한다.
  EOT
  type        = number
  default     = 300
}

variable "s2_tail_latency_p99_critical_ms" {
  description = <<-EOT
    S2 API 꼬리 지연 위험 임계 (ms, 서버측 p99).

    **안 쟀다.** 계약 상한(p95 800ms · p99 2,000ms) 아래로 잡았다 —
    **계약을 깨기 전에 우는 것**이 조기 감지의 정의다.
  EOT
  type        = number
  default     = 800
}

variable "s3_pg_latency_p95_warning_ms" {
  description = <<-EOT
    S3 결제 처리 경고 임계 (ms, `operation:payment.process` p95).

    **안 쟀다.** 평시 PG 스텁 지연은 0ms 다(`PgStubConfig.delay_ms` 기본값).
    결제가 주문 응답의 일부이므로 계약 상한 p95 800ms 안에서 PG 몫으로 잡았다.
  EOT
  type        = number
  default     = 300
}

variable "s3_pg_latency_p95_critical_ms" {
  description = "S3 결제 처리 위험 임계 (ms). **안 쟀다** — 위와 같은 근거."
  type        = number
  default     = 800
}

variable "s3_payment_failure_rate_warning" {
  description = <<-EOT
    S3 결제 실패율 경고 임계.

    **안 쟀다.** 이 스택이 이미 쓰는 `failure_rate_warning`(0.01)과 같은 값으로
    맞췄다 — 근거 없는 숫자를 새로 만드는 것보다 이미 합의된 값을 쓰는 편이 낫다.
  EOT
  type        = number
  default     = 0.01
}

variable "s3_payment_failure_rate_critical" {
  description = "S3 결제 실패율 위험 임계. **안 쟀다** — `failure_rate_critical` 과 같은 값."
  type        = number
  default     = 0.05
}
