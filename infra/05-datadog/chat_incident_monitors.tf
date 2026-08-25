###############################################################################
# S1 — 특가 오픈 채팅 과부하 보강 Monitor
#
# 기존 chat_ingest_surge는 조기 경보로 유지한다. 아래 두 Monitor는 사용자 영향
# evidence를 별도로 알린다. threshold는 초기 정책값이며 실제 반복 표본 후 갱신한다.
###############################################################################

resource "datadog_monitor" "chat_propagation_p95" {
  count = var.enable_chat_incident_monitors ? 1 : 0

  name  = "[O2][S1] Chat 전파 p95 지연"
  type  = "metric alert"
  query = "avg(last_5m):p95:o2.chat.propagation{env:${local.monitor_env},service:chat-gateway} >= ${var.chat_propagation_p95_critical_ms}"

  message = <<-EOT
    Chat fanout propagation p95가 ${var.chat_propagation_p95_critical_ms}ms를 초과했습니다.
    `CHAT_PROPAGATION_P95` evidence로 S1 Chat Degradation 판단에 사용합니다.

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

  name  = "[O2][S1] Chat 정상 사용자 차단률"
  type  = "metric alert"
  query = "avg(last_5m):avg:o2.warm.channel_limited_rate{env:${local.monitor_env},service:chat-gateway} >= ${var.chat_block_rate_critical}"

  message = <<-EOT
    Chat 정상 사용자 차단률이 ${var.chat_block_rate_critical}를 초과했습니다.
    `CHAT_NORMAL_USER_BLOCK_RATE` evidence로 S1 Chat Degradation 판단에 사용합니다.

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
