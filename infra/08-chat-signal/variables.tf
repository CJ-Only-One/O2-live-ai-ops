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
