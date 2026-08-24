# 이 파일은 커밋된다 (루트 .gitignore 의 `!infra/*/terraform.tfvars`).
# **비밀값을 적지 않는다.** API·APP 키는 DD_API_KEY / DD_APP_KEY 환경변수로 넘긴다.

# 조직이 US5 다. 04-platform 의 datadog_site, 06-datastream 의 datadog_site 와
# 같은 조직을 가리켜야 한다. 갈리면 대시보드가 빈다.
datadog_api_url = "https://api.us5.datadoghq.com/"

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

# 시나리오 6 Monitor. SQS 지표(aws.sqs.*)가 이 조직에 실제로 수집되는지
# 2026-08-24 에 확인했다(M-015) — `approximate_age_of_oldest_message` 가
# `o2-dev-order` 를 포함해 큐 9개에 각 286 포인트로 들어온다.
enable_queue_backlog_monitor       = true
order_confirm_queue_name           = "o2-dev-order"
queue_backlog_age_warning_seconds  = 60
queue_backlog_age_critical_seconds = 300

# Phase 2 — 신규 계측이 먼저 필요했던 것들이다. 각 Monitor 정의 위
# 주석(monitor.tf)에 활성화 전 필요했던 코드 변경이 적혀 있다.
enable_chat_ingest_monitor         = true
enable_pod_cache_outlier_monitor   = true
pod_cache_outlier_tolerance        = 2.5
enable_order_confirm_stall_monitor = true

# 파드 단위 지연 이상치(시나리오 5 재분석). **켠다.**
#
# 껐던 이유는 태그가 없어서가 아니라 파드가 하나뿐이어서였다 — DBSCAN 은
# 시계열이 둘 이상이어야 무리와 이상치를 나눈다. 그 전제가 충족됐다.
#
#   `O2-live-deploy` 19d6ae9  — api replicas 1 -> 2
#   부하 10 RPS · 180초 후 확인 (M-016):
#     avg:o2.warm.latency_p95{*} by {pod_name}
#       -> api-56cc9b94c9-4tk29   2.0ms
#       -> api-56cc9b94c9-bg429   4.0ms
#       -> pod_name:N/A           (service 단위 값)
#
# 위에 적어 둔 켜는 조건("파드 수만큼 갈리는지 확인")을 그대로 통과했다.
#
# **다만 파드 2개는 최소 요건이지 넉넉한 것이 아니다.** DBSCAN 이
# "무리에서 떨어진 것" 을 말하려면 무리가 있어야 하는데, 둘이 갈리면
# 어느 쪽이 이상치인지가 원리상 모호하다. **정상 2 + 이상 1 = 3** 이
# 되는 S2 실험 중에 제 성능이 나온다. 지금은 평상시 조용히 있다가
# 실험 때 동작하는 상태로 두는 것이다.
#
# 시끄러우면 이 값을 끄기 전에 `pod_latency_outlier_tolerance` 를 먼저
# 올린다. 파드별 지연의 정상 분산을 아직 안 쟀으므로(M-016 "안 잰 것")
# 2.5 는 근거가 아니라 캐시 쪽과 맞춘 기본값이다.
enable_pod_latency_outlier_monitor = true
pod_latency_outlier_tolerance      = 2.5

# 파이프라인 구간별 Monitor(monitor_pipeline.tf). `aws.lambda.*` 수집을
# 2026-08-24 에 확인해(M-015) 기본값이 true 로 바뀌었다 — 여기서 명시적으로
# 한 번 더 적어 둔다. 끌 일이 생기면 그 사유를 이 줄에 같이 남긴다.
enable_aggregator_lag_monitor = true
