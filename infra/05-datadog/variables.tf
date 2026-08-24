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

    켤 조건은 `o2.warm.rps{service:chat-gateway}` 에 시계열이 있는 것이고,
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
    `o2.warm.rps_ratio{service:chat-gateway}` 가 평시 대비 몇 배로 뛰면
    경고할지.

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

variable "cache_hit_rate_critical" {
  description = <<-EOT
    시나리오 4(캐시 흡수 실패) 임계. `o2.warm.cache_hit_rate{service:api}` 가
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
