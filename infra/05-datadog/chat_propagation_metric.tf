# DogStatsD distribution은 평균만 자동 생성한다(T-031). S1 복구 판정은 p95가
# 계약이므로 percentile 집계를 명시적으로 켠다. source는 합성 검증용 임시
# 태그라 queryable 목록에 넣지 않는다.
# ★ 이 `tags` 는 설명이 아니라 **허용 목록이다.** 여기 없는 태그는 앱이 보내도
#   Datadog 이 집계 단계에서 버린다 — 위젯도 Monitor 도 그 축으로 못 나누고,
#   오류가 아니라 series 0 이라 알아채기 어렵다.
#
#   그래서 `apps/chat-gateway/src/telemetry.ts` 의 `TAG_KEYS` 에 축을 더하는
#   것만으로는 부족하고 여기도 같이 고쳐야 한다. 둘 중 하나만 고치면 조용히
#   안 된다.
#
#   `broadcast_id` 는 S1 의 인시던트·조치 단위다(D-086). 방송 수만큼 조회 축이
#   늘어나므로 실제 방송이 수백 개로 가면 재검토한다 — 그때 먼저 뺄 후보는
#   `pod_name` 이다. 전파 지연을 파드별로 보는 소비처가 아직 없다.
resource "datadog_metric_tag_configuration" "chat_propagation" {
  metric_name         = "o2.chat.propagation"
  metric_type         = "distribution"
  tags                = ["env", "service", "pod_name", "broadcast_id"]
  include_percentiles = true
}

# 최초 검증 때 API로 먼저 만든 설정을 다음 로컬 apply가 state로 인수한다.
import {
  to = datadog_metric_tag_configuration.chat_propagation
  id = "o2.chat.propagation"
}
