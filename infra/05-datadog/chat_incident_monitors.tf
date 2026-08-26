###############################################################################
# S1 — 특가 오픈 채팅 과부하 보강 Monitor
#
# 기존 chat_ingest_surge는 조기 경보로 유지한다. 아래 두 Monitor는 사용자 영향
# evidence를 별도로 알린다. threshold는 초기 정책값이며 실제 반복 표본 후 갱신한다.
###############################################################################

resource "datadog_monitor" "chat_propagation_p95" {
  count = var.enable_chat_incident_monitors ? 1 : 0

  name = "[O2][S1] Chat 전파 p95 지연"
  type = "metric alert"

  # ★ `by {broadcast_id}` — multi-alert 다. 방송마다 따로 판정하고 따로 알린다.
  #
  #   합계로 두면 알림이 "어느 방송이 무너졌는지" 를 말하지 못한다. S1 의 조치
  #   (`limit_channel_volume`)는 방송 하나의 채널 총량을 건드리고 **비가역이며
  #   사람 승인을 받으므로**, 대상이 틀리면 조치를 안 하느니만 못하다.
  #
  #   그리고 이 그룹 태그가 webhook payload 로 나가야 Adapter 의
  #   `assessment_input.scope.broadcast_id` 를 채울 수 있다(D-086).
  #
  #   팬아웃 총량(`s1_chat_fanout_volume`)은 반대로 **합계로 둔다** — M-010 의
  #   붕괴점은 chat-gateway 파드 용량이고 파드는 방송들이 공유한다. 방송별로
  #   쪼개면 "각각은 안전선 아래인데 합쳐서 무너지는" 상황을 놓친다.
  query = "avg(last_5m):p95:o2.chat.propagation{env:${local.monitor_env},service:chat-gateway} by {broadcast_id} >= ${var.chat_propagation_p95_critical_ms}"

  message = <<-EOT
    방송 `{{broadcast_id.name}}` 의 Chat fanout propagation p95가 ${var.chat_propagation_p95_critical_ms}ms를 초과했습니다.
    `CHAT_PROPAGATION_P95` evidence로 S1 Chat Degradation 판단에 사용합니다.

    조치 대상은 **이 방송 하나**입니다. 다른 방송이 함께 나쁘면 각자 알림이 옵니다.
    @webhook-o2-incident-entry
  EOT

  monitor_thresholds {
    warning  = var.chat_propagation_p95_warning_ms
    critical = var.chat_propagation_p95_critical_ms
  }

  notify_no_data      = false
  require_full_window = true
  renotify_interval   = 0
  tags                = concat(local.monitor_tags, ["env:${local.monitor_env}", "scenario:s1", "service:chat-gateway", "role:impact"])
}

resource "datadog_monitor" "chat_block_rate" {
  count = var.enable_chat_incident_monitors ? 1 : 0

  name = "[O2][S1] Chat 정상 사용자 차단률"
  type = "metric alert"
  # Native chat.send telemetry is the source of truth. The numerator counts
  # CHANNEL_LIMITED failures and the denominator counts every chat.send attempt.
  # This evidence also requires a broadcast scope, so both numerator and
  # denominator are grouped by the same broadcast_id.
  #
  # `failure_code` 는 **소문자로 조회한다.** 앱은 `CHANNEL_LIMITED` 를 그대로
  # 보내지만 Datadog 은 메트릭 태그 값을 소문자로 정규화해 저장한다. 대문자로
  # 조회하면 metric 은 있는데 분자가 영구 0 이라 차단률이 0 으로 고정되고,
  # 조치가 정상 사용자를 과도하게 잘라도 알림이 뜨지 않는다. 2026-08-25 실측에서
  # 소문자 조회가 0.49 를 반환해 확인했다(T-040 · M-010 관측 3).
  # Hot 카탈로그(`o2hot/metric_catalog.py` 의 `block_rate`)도 소문자를 쓴다.
  query = "avg(last_5m):sum:o2.app.failure{env:${local.monitor_env},service:chat-gateway,event:chat.send,failure_code:channel_limited} by {broadcast_id}.as_count() / sum:o2.app.business_event{env:${local.monitor_env},service:chat-gateway,event:chat.send} by {broadcast_id}.as_count() >= ${var.chat_block_rate_critical}"

  message = <<-EOT
    Chat 정상 사용자 차단률이 ${var.chat_block_rate_critical}를 초과했습니다.
    `CHAT_NORMAL_USER_BLOCK_RATE` evidence로 S1 Chat Degradation 판단에 사용합니다.
    방송 `{{broadcast_id.name}}`의 차단률입니다.
    @webhook-o2-incident-entry
  EOT

  monitor_thresholds {
    warning  = var.chat_block_rate_warning
    critical = var.chat_block_rate_critical
  }

  notify_no_data      = false
  require_full_window = true
  renotify_interval   = 0
  tags                = concat(local.monitor_tags, ["env:${local.monitor_env}", "scenario:s1", "service:chat-gateway", "role:impact"])
}
