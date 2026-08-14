variable "warm_api_key" {
  description = <<-EOT
    Agent 조회 API 의 X-O2-Key 공유 시크릿. 비우면 인증 없이 열립니다.

    **terraform.tfvars 에 적지 않습니다.** 그 파일은 커밋 대상이고
    (루트 .gitignore 의 `!infra/*/terraform.tfvars`), 값이 저장소에 남습니다.
    `TF_VAR_warm_api_key` 환경변수로 넘기세요.
  EOT
  type        = string
  default     = ""
  sensitive   = true
}

variable "datadog_ssm_param" {
  description = <<-EOT
    Datadog API 키가 담긴 SSM SecureString 파라미터 이름.
    키 자체를 Terraform 변수로 넘기면 S3 remote state 에 평문으로 남으므로,
    파라미터는 Terraform 밖에서 만들고 이름만 넘깁니다.

      aws ssm put-parameter --name /o2/datadog/api-key \
        --type SecureString --value <KEY> --profile o2-data

    비워 두면 Datadog 전송만 비활성화되고 DynamoDB 집계는 그대로 동작합니다.
  EOT
  type        = string
  default     = ""
}
