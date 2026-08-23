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

variable "enable_event_source" {
  description = <<-EOT
    Chat Signal SQS가 Lambda Worker를 호출하게 한다.

    false가 fail-safe 기본값이다. true는 Phase 3 AC-001~010 통과, 03-data 리소스
    적용, Chat Gateway 이미지 배포를 확인한 Shadow Mode에서만 사용한다.
  EOT
  type        = bool
  default     = false
}
