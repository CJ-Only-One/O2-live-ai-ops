# 이 파일은 커밋된다 (루트 .gitignore 의 `!infra/*/terraform.tfvars`).
# **비밀값을 적지 않는다.** API·APP 키는 DD_API_KEY / DD_APP_KEY 환경변수로 넘긴다.

# 조직이 AP1 이다. 04-platform 의 datadog_site, 06-datastream 의 datadog_site 와
# 같은 조직을 가리켜야 한다. 갈리면 대시보드가 빈다.
datadog_api_url = "https://api.ap1.datadoghq.com/"

# 06-datastream 의 O2_DD_PREFIX 기본값과 같아야 한다.
metric_prefix = "o2.warm."

# 대시보드를 열었을 때 처음 보이는 서비스. `*` 로 두면 평균이 개별 장애를 가린다.
#
# order-api 가 아니라 coupon-api 다 — order-api 는 아직 이벤트를 보낸 적이 없어
# 기본 화면이 통째로 빈다. 빈 화면은 "정상"과 구분되지 않으므로, 데이터가
# 흐르는 서비스를 기본값으로 둔다. order-api 가 살아나면 그때 바꾼다.
default_service = "api"
environment     = "dev"

# 임계치는 잠정치다. 평시 분포를 보고 고친다.
# 여기 숫자는 색깔만 바꾸고 알림을 보내지 않는다.
failure_rate_warning  = 0.01
failure_rate_critical = 0.05
latency_p95_warning   = 300
latency_p95_critical  = 1000
retry_rate_warning    = 0.05
retry_rate_critical   = 0.15
cancel_rate_warning   = 0.05
cancel_rate_critical  = 0.15

# 인프라 대시보드(dashboard_infra.tf) 축. 02-eks 의 cluster_name,
# 04-platform 의 app_namespace 와 같아야 한다 — 지금은 각각 o2-eks / o2-dev.
kube_cluster_name = "o2-eks"
kube_namespace    = "o2-dev"

cpu_request_pct_warning = 100
cpu_throttling_warning  = 25

# Monitor(monitor.tf). 임계치는 잠정치다 — 근거는 Confluence "Datadog 장애
# 대응 Alert 시스템 제안서"(2026-08-19). 알림 라우팅(Slack 등)은 이 세션
# 범위 밖이다 — 인프라팀이 webhook push 로 별도 구축 중이라 여기서는
# 임계치·쿼리만 정의한다.
chat_rps_ratio_warning  = 5
cache_hit_rate_critical = 0.5

# 시나리오 6 Monitor는 기본 비활성이다 — SQS 지표(aws.sqs.*)가 이 조직에
# 실제로 수집되는지 확인 전까지는 켜지 않는다. 확인되면 true 로 바꾼다.
enable_queue_backlog_monitor       = true
order_confirm_queue_name           = "o2-dev-order"
queue_backlog_age_warning_seconds  = 60
queue_backlog_age_critical_seconds = 300

# Phase 2 — 신규 계측이 먼저 필요해 전부 기본 비활성이다. 각 Monitor 정의
# 위 주석(monitor.tf)에 활성화 전 필요한 코드 변경이 적혀 있다.
enable_chat_ingest_monitor         = true
enable_pod_cache_outlier_monitor   = true
pod_cache_outlier_tolerance        = 2.5
enable_order_confirm_stall_monitor = true
