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
}

incident_correlation_window_seconds = 420
incident_recovery_window_seconds    = 300
incident_cooldown_seconds           = 300
incident_reopen_window_seconds      = 1800

incident_shadow_mode                  = false
incident_operational_handoff_approved = true

datadog_source_adapter_execution_enabled   = true
datadog_source_adapter_allowed_monitor_ids = ["21940248", "22078624"]
datadog_source_adapter_not_before_epoch    = 1787634074
incident_correlator_execution_enabled      = true
incident_correlator_event_source_enabled   = true
