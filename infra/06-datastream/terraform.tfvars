# 이 파일은 커밋된다 (루트 .gitignore 의 `!infra/*/terraform.tfvars`).
# **비밀값이 아니라 비밀값이 있는 곳의 이름만 적는다.**

# Datadog API 키가 담긴 Secrets Manager 시크릿 이름.
# 04-platform 의 datadog_secrets_manager_secret_name 과 같은 값이다 —
# Agent(ESO 경유)와 집계 Lambda 가 같은 시크릿을 읽으므로 사본이 없고,
# 키를 회전하면 양쪽이 함께 바뀐다. 이 스택은 시크릿을 소유하지 않는다.
# 지표의 env 태그. 04-platform 의 environment 와 같아야 APM 과 이어진다.
environment = "dev"

datadog_secret_name         = "o2/dev/datadog-new"
datadog_secret_property     = "api-key"
datadog_secret_app_property = "app-key" # o2-hot-api 의 Datadog 역쿼리(DD-APPLICATION-KEY)에만 쓰인다

# SSM 대안 경로. Secrets Manager 를 쓰므로 비워 둔다.
# 둘 다 지정하면 Secrets Manager 가 이긴다.
datadog_ssm_param = ""

# Datadog intake 도메인. 04-platform 의 datadog_site 와 같아야 한다.
# 이 값이 틀리면 apply 는 성공하고 대시보드만 영원히 빈다.
datadog_site = "us5.datadoghq.com"

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

# o2-hot-api 는 X-O2-Key 가 아니라 AWS_IAM(SigV4) 인증이다 — D-031: 이 계정은
# Organizations 멤버 계정이라 Function URL 을 NONE(공개)으로 열면 조직 밖
# 정책에 403 으로 막힌다. 값을 비워 두지 않는다 — 비우면 아무도 호출하지
# 못한다(AWS_IAM 기본은 전부 거부). Dify EC2 인스턴스 역할(infra/06-agent).
hot_api_invoker_role_arn = "arn:aws:iam::066107819912:role/o2-dev-dify-role"
