variable "datadog_api_url" {
  description = <<-EOT
    Datadog API 엔드포인트. **조직이 AP1 이라 기본값(US1)을 쓰면 안 된다.**

    `04-platform` 의 `datadog_site` 와 `06-datastream` 의 `datadog_site` 가
    가리키는 곳과 같은 조직이어야 한다. 세 곳이 갈리면 Agent·집계 Lambda·
    대시보드가 서로 다른 조직을 보고, 증상은 "대시보드가 빈다" 하나다.
  EOT
  type        = string
  default     = "https://api.ap1.datadoghq.com/"
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
  default     = "order-api"
}

variable "environment" {
  description = "메트릭에 붙는 env 태그. 집계 Lambda 의 DD_ENV 와 같아야 한다."
  type        = string
  default     = "prod"
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
