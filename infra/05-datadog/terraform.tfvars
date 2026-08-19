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
