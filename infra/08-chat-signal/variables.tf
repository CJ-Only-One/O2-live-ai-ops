variable "team" {
  description = "팀 식별자. 태그로만 사용"
  type        = string
  default     = "o2"
}

variable "project" {
  description = "리소스 prefix"
  type        = string
  default     = "o2"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", var.project))
    error_message = "소문자, 숫자, 하이픈만 허용한다."
  }
}

variable "environment" {
  description = "리소스 환경 구분"
  type        = string
  default     = "dev"
}

variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "state_bucket" {
  description = "03-data remote state가 있는 S3 버킷"
  type        = string
  default     = "o2-tfstate-066107819912"
}

variable "datastore_state_key" {
  description = "03-data state key. data/와 혼동하지 않는다"
  type        = string
  default     = "datastore/terraform.tfstate"
}

variable "agent_trigger_queue_name" {
  description = "06-agent Phase 1B가 소유하는 agent.trigger.v1 전용 Queue 이름"
  type        = string
  default     = "o2-dev-dify-agent-trigger"
}

variable "agent_alarm_topic_name" {
  description = "Agent Entry transport 알람이 공통으로 사용하는 SNS topic 이름"
  type        = string
  default     = "o2-dev-dify-alert-relay-alarm"
}

variable "chat_source_adapter_execution_enabled" {
  description = "Phase 3 합성 Candidate E2E에서만 true로 바꾸는 Adapter 실행 게이트"
  type        = bool
  default     = false
}

variable "chat_source_adapter_event_source_enabled" {
  description = "Phase 3 합성 Candidate E2E에서만 true로 바꾸는 DynamoDB Stream 게이트"
  type        = bool
  default     = false
}

variable "chat_source_adapter_allowed_broadcast_ids" {
  description = "Phase 3에서 Agent Queue 전송을 허용할 합성 broadcast_id. 활성화 시 정확히 1개"
  type        = set(string)
  default     = []

  validation {
    condition = alltrue([
      for value in var.chat_source_adapter_allowed_broadcast_ids :
      can(regex("^bc_[0-9]+$", value))
    ])
    error_message = "Phase 3 allowlist는 bc_<digits> 형식만 허용한다."
  }
}

variable "chat_source_adapter_not_before_epoch" {
  description = "Phase 3 합성 Candidate cutover epoch. 비활성 기본값은 2100-01-01 UTC"
  type        = number
  default     = 4102444800

  validation {
    condition = (
      var.chat_source_adapter_not_before_epoch >= 0 &&
      floor(var.chat_source_adapter_not_before_epoch) == var.chat_source_adapter_not_before_epoch
    )
    error_message = "cutover epoch는 0 이상의 정수여야 한다."
  }
}

variable "enable_event_source" {
  description = <<-EOT
    Chat Signal SQS가 Lambda Worker를 호출하게 한다.

    false가 fail-safe 기본값이다. true는 Phase 3 AC-001~010 통과, 03-data 리소스
    적용, Chat Gateway 이미지 배포를 확인한 Shadow Mode에서만 사용한다.
  EOT
  type        = bool
  default     = false
}
