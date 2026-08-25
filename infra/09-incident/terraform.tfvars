team        = "o2"
project     = "o2"
environment = "dev"
region      = "ap-northeast-2"

alert_secret_name_o2 = "o2/dev/dify-alert-o2"

incident_datadog_monitor_map = {
  "22078624" = {
    evidence_role            = "PRIMARY"
    evidence_type            = "SERVICE_TAIL_LATENCY"
    incident_family          = "READ_PATH_DEGRADATION"
    symptom_family           = "LATENCY"
    suspected_surface        = "READ_PATH"
    service                  = "api"
    minimum_samples          = 1
    freshness_seconds        = 300
    severity_level           = "WARNING"
    strong_exception_allowed = false
  }
  "21940248" = {
    evidence_role            = "CORROBORATING"
    evidence_type            = "SERVICE_TAIL_LATENCY"
    incident_family          = "READ_PATH_DEGRADATION"
    symptom_family           = "LATENCY"
    suspected_surface        = "READ_PATH"
    service                  = "api"
    minimum_samples          = 1
    freshness_seconds        = 300
    severity_level           = "WARNING"
    strong_exception_allowed = false
  }
  # 2026-08-26: S1 진입 전환 — infra/05-datadog terraform state에서 확인한 실제
  # monitor ID(지어낸 값 아님). s1_chat_fanout_volume가 유일한 진입(PRIMARY)이고
  # 옛 @webhook-o2-dify는 뗐다(scenario_alerts.tf 라우팅 규칙 참고, 중복 호출 방지).
  # chat_propagation_p95/chat_block_rate는 role:impact 태그대로 CORROBORATING만.
  "22078626" = { # s1_chat_fanout_volume, [O2][S1] 채팅 팬아웃 총량 — 채널 감당선 접근
    evidence_role            = "PRIMARY"
    evidence_type            = "COMPOSITE_CONDITION" # 발화 수 x 접속자 수 합성값, 전용 enum 없음
    incident_family          = "CHAT_DEGRADATION"
    symptom_family           = "AVAILABILITY"
    suspected_surface        = "CHAT"
    service                  = "chat-gateway"
    minimum_samples          = 1
    freshness_seconds        = 120 # scenario_early_window_minutes 기본값(2분)
    severity_level           = "HIGH"
    strong_exception_allowed = false
  }
  "22076983" = { # chat_propagation_p95, [O2][S1] Chat 전파 p95 지연
    evidence_role            = "CORROBORATING"
    evidence_type            = "CHAT_PROPAGATION_P95"
    incident_family          = "CHAT_DEGRADATION"
    symptom_family           = "LATENCY"
    suspected_surface        = "CHAT"
    service                  = "chat-gateway"
    minimum_samples          = 1
    freshness_seconds        = 300 # avg(last_5m)
    severity_level           = "HIGH"
    strong_exception_allowed = false
  }
  "22076982" = { # chat_block_rate, [O2][S1] Chat 정상 사용자 차단률
    evidence_role            = "CORROBORATING"
    evidence_type            = "CHAT_NORMAL_USER_BLOCK_RATE"
    incident_family          = "CHAT_DEGRADATION"
    symptom_family           = "ERROR_RATE"
    suspected_surface        = "CHAT"
    service                  = "chat-gateway"
    minimum_samples          = 1
    freshness_seconds        = 300 # avg(last_5m)
    severity_level           = "HIGH"
    strong_exception_allowed = false
  }
}

incident_correlation_window_seconds = 420
incident_recovery_window_seconds    = 300
incident_cooldown_seconds           = 300
incident_reopen_window_seconds      = 1800

incident_shadow_mode                  = false
incident_operational_handoff_approved = true

datadog_source_adapter_execution_enabled   = true
datadog_source_adapter_allowed_monitor_ids = ["21940248", "22078624", "22078626", "22076983", "22076982"]
datadog_source_adapter_not_before_epoch    = 1787634074
incident_correlator_execution_enabled      = true
incident_correlator_event_source_enabled   = true
