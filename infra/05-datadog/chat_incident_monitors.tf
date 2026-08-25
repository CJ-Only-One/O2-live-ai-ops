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

# ★ 원래 이 Monitor 는 `avg:o2.warm.channel_limited_rate` 를 봤다. **그 지표는
#   Datadog 에 오지 않는다** — `o2warm/metrics.py:339` 가 계산은 하지만
#   `DATADOG_SCALARS`(:414) 목록에 없어 DynamoDB 상세에만 남는다. 쿼리는 유효하고
#   `notify_no_data = false` 라서 **영원히 조용한 Monitor** 였다.
#
#   같은 값을 native 계측으로 직접 만든다. 분자는
#   `o2.app.failure{event:chat.send,failure_code:CHANNEL_LIMITED}`
#   (`apps/chat-gateway/src/chat-ingress.ts:62`), 분모는 전체 `chat.send` 시도
#   (`:45·52·61·68` 이 성공·실패 모두 발행한다). 실패 코드 분포가 아니라 전체
#   시도를 분모로 쓰는 것은 D-069 가 정한 것이다.
#
#   warm 쪽에 `channel_limited_rate` 를 되살리는 방법도 있었지만, 같은 값이 두
#   시스템에서 계산되는 것을 `DATADOG_SCALARS` 주석이 이미 금지한다
#   ("Native 이관 대상은 Datadog으로 중복 발행하지 않는다").
resource "datadog_monitor" "chat_block_rate" {
  count = var.enable_chat_incident_monitors ? 1 : 0

  name = "[O2][S1] Chat 정상 사용자 차단률"
  # 비율 쿼리는 `cache_hit_rate_low` 와 같은 `metric alert` 다.
  type  = "metric alert"
  query = "avg(last_5m):sum:o2.app.failure{env:${local.monitor_env},service:chat-gateway,event:chat.send,failure_code:CHANNEL_LIMITED}.as_count() / sum:o2.app.business_event{env:${local.monitor_env},service:chat-gateway,event:chat.send}.as_count() >= ${var.chat_block_rate_critical}"

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
