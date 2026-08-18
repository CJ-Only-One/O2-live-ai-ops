variable "warm_api_key_param" {
  description = <<-EOT
    Agent 조회 API 의 X-O2-Key 값이 담긴 SSM SecureString 파라미터 **이름**.
    Lambda 가 실행 시점에 읽습니다. 이것이 권장 경로입니다.

    `warm_api_key` 와 달리 값이 state 에 남지 않습니다. Function URL 은
    `authorization_type = "NONE"` 으로 인터넷에 바로 붙으므로, state 를 읽을
    수 있는 주체가 곧 엔드포인트 권한을 갖는 상황을 만들지 않습니다.

      $b = New-Object byte[] 32
      [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
      aws ssm put-parameter --name /o2/warm/api-key --type SecureString `
        --value ([Convert]::ToBase64String($b)) --profile o2-data

    비워 두면 인증이 꺼집니다(로컬·사설망 전용). 파라미터를 지정했는데
    읽지 못하면 **열리지 않고 401 로 막습니다** — `secrets.py` 참고.
  EOT
  type        = string
  default     = ""
}

variable "warm_api_key" {
  description = <<-EOT
    조회 API 키를 값으로 직접 주는 경로. **배포에는 `warm_api_key_param` 을 쓰세요.**

    이 변수는 Lambda 환경변수가 되어 **S3 remote state 와 Lambda 콘솔에
    평문으로 남습니다.** 로컬 실험용으로만 남겨 둡니다.

    **terraform.tfvars 에 적지 않습니다.** 그 파일은 커밋 대상이고
    (루트 .gitignore 의 `!infra/*/terraform.tfvars`), 값이 저장소에 남습니다.
    `TF_VAR_warm_api_key` 환경변수로 넘기세요.
  EOT
  type        = string
  default     = ""
  sensitive   = true
}

variable "datadog_secret_name" {
  description = <<-EOT
    Datadog API 키가 담긴 **Secrets Manager 시크릿 이름**. 집계 Lambda 가
    실행 시점에 읽습니다. 이것이 권장 경로입니다.

    **`04-platform` 의 `datadog_secrets_manager_secret_name` 과 같은 값입니다.**
    같은 시크릿을 Agent(ESO 경유)와 Lambda 가 함께 읽으므로 사본이 생기지
    않고, 키를 회전하면 양쪽이 함께 바뀝니다.

    사본을 두면 회전 때 한쪽만 바뀌고, 그 증상은 "인프라 지표는 정상인데
    비즈니스 지표만 조용히 멈춤" 하나뿐입니다 — `datadog.py` 가 전송 실패를
    삼켜 집계를 막지 않기 때문입니다(의도된 설계).

    이 스택은 시크릿을 **소유하지 않습니다.** ARN 참조만 하고 값은 읽지
    않으므로 state 에 키가 남지 않습니다.
  EOT
  type        = string
  default     = "o2/dev/datadog"
}

variable "datadog_secret_property" {
  description = <<-EOT
    위 시크릿 JSON 에서 API 키를 담은 property 이름.
    `o2/dev/datadog` 은 `{"api-key": ..., "app-key": ...}` 형태입니다.

    Agent 는 app-key 도 쓰지만(컨트롤플레인 수집) 이 Lambda 는 메트릭 전송만
    하므로 api-key 하나로 충분합니다.
  EOT
  type        = string
  default     = "api-key"
}

variable "datadog_ssm_param" {
  description = <<-EOT
    Datadog API 키가 담긴 SSM SecureString 파라미터 이름. **대안 경로입니다** —
    Secrets Manager 를 쓸 수 없을 때만 쓰고, 평소에는 `datadog_secret_name` 을
    씁니다. 둘 다 지정하면 Secrets Manager 가 이깁니다.

      aws ssm put-parameter --name /o2/datadog/api-key \
        --type SecureString --value <KEY> --profile o2-data

    셋 다 비우면 Datadog 전송만 비활성화되고 DynamoDB 집계는 그대로 동작합니다.
  EOT
  type        = string
  default     = ""
}

variable "datadog_site" {
  description = <<-EOT
    Datadog intake 도메인. 집계 Lambda 가 `https://api.<이 값>/api/v2/series` 로 보냅니다.

    **`04-platform` 의 `datadog_site` 와 같은 값이어야 합니다.** 두 스택이
    같은 조직에 데이터를 보내는데 값이 갈리면 한쪽만 도착합니다.

    틀려도 apply 는 성공하고 Lambda 도 정상으로 뜹니다. 키가 맞지 않는
    사이트로 가면 403 이 나지만 `datadog.py` 가 예외를 삼켜 집계를 막지
    않으므로(설계 의도), 증상은 "대시보드가 계속 비어 있음" 하나뿐입니다.
    `o2warm` 접두사로 Lambda 로그를 보면 사유가 나옵니다.

    기본값을 비우지 않은 이유: 코드 기본값(`settings.py`)은 US1 인
    `datadoghq.com` 이라, 이 변수를 빼먹으면 조용히 그쪽으로 갑니다.
  EOT
  type        = string
  default     = "ap1.datadoghq.com"
}
