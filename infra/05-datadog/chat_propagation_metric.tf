# DogStatsD distribution은 평균만 자동 생성한다(T-031). S1 복구 판정은 p95가
# 계약이므로 percentile 집계를 명시적으로 켠다. source는 합성 검증용 임시
# 태그라 queryable 목록에 넣지 않는다.
resource "datadog_metric_tag_configuration" "chat_propagation" {
  metric_name         = "o2.chat.propagation"
  metric_type         = "distribution"
  tags                = ["env", "service", "pod_name"]
  include_percentiles = true
}

# 최초 검증 때 API로 먼저 만든 설정을 다음 로컬 apply가 state로 인수한다.
import {
  to = datadog_metric_tag_configuration.chat_propagation
  id = "o2.chat.propagation"
}
