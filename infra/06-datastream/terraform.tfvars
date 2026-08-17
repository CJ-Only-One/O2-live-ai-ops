# 이 파일은 커밋된다 (루트 .gitignore 의 `!infra/*/terraform.tfvars`).
# **비밀값이 아니라 비밀값이 있는 곳의 이름만 적는다.**

# Datadog API 키가 담긴 Secrets Manager 시크릿 이름.
# 04-platform 의 datadog_secrets_manager_secret_name 과 같은 값이다 —
# Agent(ESO 경유)와 집계 Lambda 가 같은 시크릿을 읽으므로 사본이 없고,
# 키를 회전하면 양쪽이 함께 바뀐다. 이 스택은 시크릿을 소유하지 않는다.
datadog_secret_name     = "o2/dev/datadog"
datadog_secret_property = "api-key"

# SSM 대안 경로. Secrets Manager 를 쓰므로 비워 둔다.
# 둘 다 지정하면 Secrets Manager 가 이긴다.
datadog_ssm_param = ""

# Datadog intake 도메인. 04-platform 의 datadog_site 와 같아야 한다.
# 이 값이 틀리면 apply 는 성공하고 대시보드만 영원히 빈다.
datadog_site = "ap1.datadoghq.com"

# 조회 API 의 X-O2-Key 가 담긴 SSM SecureString 파라미터 이름.
# 값이 아니라 이름이다. Lambda 가 실행 시점에 읽으므로 state 에 남지 않는다.
#
#   $b = New-Object byte[] 32
#   [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
#   aws ssm put-parameter --name /o2/warm/api-key --type SecureString `
#     --value ([Convert]::ToBase64String($b)) --profile o2-data
#
# 비우면 Function URL 이 인증 없이 열린다. 파라미터를 지정했는데 읽지
# 못하면 열리지 않고 401 로 막는다.
warm_api_key_param = "/o2/warm/api-key"

# warm_api_key(값 직접 주입)는 여기 적지 않는다. 그 경로는 state 에 평문으로
# 남으므로 로컬 실험용이다. 배포에는 위 warm_api_key_param 을 쓴다.
