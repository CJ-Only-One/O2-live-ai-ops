variable "team" { type = string }
variable "project" { type = string }
variable "environment" { type = string }
variable "region" { type = string }

variable "alert_secret_name_o2" {
  type = string
}

variable "agent_entry_idempotency_ttl_seconds" {
  type    = number
  default = 2592000

  validation {
    condition     = var.agent_entry_idempotency_ttl_seconds >= 1209600
    error_message = "Signal claim TTL은 DLQ 최대 보존 기간 14일 이상이어야 한다."
  }
}

variable "datadog_source_adapter_execution_enabled" {
  type    = bool
  default = false
}

variable "datadog_source_adapter_allowed_monitor_ids" {
  type    = set(string)
  default = []

  validation {
    condition = alltrue([
      for value in var.datadog_source_adapter_allowed_monitor_ids :
      can(regex("^[^,]{1,128}$", value))
    ])
    error_message = "Datadog Source Adapter allowlist는 쉼표 없는 1~128자 monitor ID만 허용한다."
  }
}

variable "datadog_source_adapter_not_before_epoch" {
  type    = number
  default = 4102444800

  validation {
    condition = (
      var.datadog_source_adapter_not_before_epoch >= 0 &&
      floor(var.datadog_source_adapter_not_before_epoch) == var.datadog_source_adapter_not_before_epoch
    )
    error_message = "Datadog Source Adapter cutover는 0 이상의 정수 Unix epoch여야 한다."
  }
}

variable "incident_correlator_max_concurrency" {
  type    = number
  default = 2

  validation {
    condition     = var.incident_correlator_max_concurrency >= 2 && var.incident_correlator_max_concurrency <= 10
    error_message = "Correlator concurrency는 2 이상 10 이하이어야 한다."
  }
}

variable "incident_correlator_execution_enabled" {
  type    = bool
  default = false
}

variable "incident_correlator_event_source_enabled" {
  type    = bool
  default = false
}

variable "incident_correlation_window_seconds" {
  type    = number
  default = 0

  validation {
    condition = (
      var.incident_correlation_window_seconds == 0 ||
      (var.incident_correlation_window_seconds >= 60 &&
        var.incident_correlation_window_seconds <= 900 &&
        floor(var.incident_correlation_window_seconds) == var.incident_correlation_window_seconds &&
      var.incident_correlation_window_seconds % 60 == 0)
    )
    error_message = "correlation window는 0 또는 60초 단위의 60~900초 정수여야 한다."
  }
}

variable "incident_correlator_allowed_idempotency_keys" {
  type    = set(string)
  default = []

  validation {
    condition = alltrue([
      for value in var.incident_correlator_allowed_idempotency_keys :
      can(regex("^(chat:cand_[0-9A-HJKMNP-TV-Z]{26}|datadog:[^,:]{1,128}:(Triggered|Re-Triggered|Recovered|Warn|No Data|Renotify))$", value))
    ])
    error_message = "Correlator allowlist는 합성 Chat 또는 Datadog idempotency key만 허용한다."
  }
}

variable "incident_chat_surface_map" {
  type = map(object({
    evidence_role            = string
    evidence_type            = string
    incident_family          = string
    symptom_family           = string
    suspected_surface        = string
    service                  = string
    minimum_samples          = number
    freshness_seconds        = number
    severity_level           = string
    strong_exception_allowed = bool
  }))
  default = {
    READ_PATH = {
      evidence_role            = "PRIMARY"
      evidence_type            = "USER_SYMPTOM_CLUSTER"
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
}

variable "incident_datadog_monitor_map" {
  type = map(object({
    evidence_role            = string
    evidence_type            = string
    incident_family          = string
    symptom_family           = string
    suspected_surface        = string
    service                  = string
    minimum_samples          = number
    freshness_seconds        = number
    severity_level           = string
    strong_exception_allowed = bool
  }))
  default = {}

  validation {
    condition = alltrue([
      for monitor_id, mapping in var.incident_datadog_monitor_map :
      can(regex("^[0-9]{1,20}$", monitor_id)) &&
      contains(["PRIMARY", "CORROBORATING", "CONTEXT"], mapping.evidence_role) &&
      contains(["CHAT_PROPAGATION_P95", "CHAT_NORMAL_USER_BLOCK_RATE", "SERVICE_TAIL_LATENCY", "POD_TAIL_LATENCY", "POD_CPU_UTILIZATION", "POD_VERSION", "POD_AGE", "TELEMETRY_FRESHNESS", "INTEGRITY_VIOLATION", "COMPOSITE_CONDITION"], mapping.evidence_type) &&
      contains(["READ_PATH_DEGRADATION", "CHECKOUT_ORDER_DEGRADATION", "PAYMENT_DEGRADATION", "INVENTORY_DEGRADATION", "CHAT_DEGRADATION", "PLAYBACK_DEGRADATION", "CAPACITY_SATURATION", "DEPLOYMENT_REGRESSION", "TELEMETRY_PIPELINE_FAILURE", "DATA_INTEGRITY_SECURITY_RISK"], mapping.incident_family) &&
      contains(["LATENCY", "AVAILABILITY", "ERROR_RATE", "UNKNOWN"], mapping.symptom_family) &&
      contains(["READ_PATH", "PLAYBACK", "CHAT", "UNKNOWN"], mapping.suspected_surface) &&
      length(trimspace(mapping.service)) >= 1 &&
      length(mapping.service) <= 128
      && mapping.minimum_samples >= 1 && floor(mapping.minimum_samples) == mapping.minimum_samples
      && mapping.freshness_seconds >= 1 && floor(mapping.freshness_seconds) == mapping.freshness_seconds
      && contains(["INFORMATIONAL", "WARNING", "HIGH", "CRITICAL"], mapping.severity_level)
      && (!mapping.strong_exception_allowed || (mapping.incident_family == "DATA_INTEGRITY_SECURITY_RISK" && mapping.evidence_type == "INTEGRITY_VIOLATION"))
    ])
    error_message = "Datadog mapping은 통제된 evidence role/family/symptom/surface를 사용해야 한다."
  }
}

variable "incident_recovery_window_seconds" {
  type    = number
  default = 0
  validation {
    condition     = var.incident_recovery_window_seconds >= 0 && floor(var.incident_recovery_window_seconds) == var.incident_recovery_window_seconds
    error_message = "recovery window는 측정 전 0, 측정 후 0 이상의 정수 초여야 한다."
  }
}

variable "incident_cooldown_seconds" {
  type    = number
  default = 0
}

variable "incident_reopen_window_seconds" {
  type    = number
  default = 0
}

variable "incident_operational_handoff_approved" {
  type    = bool
  default = false
}

variable "incident_shadow_mode" {
  type    = bool
  default = true
}
