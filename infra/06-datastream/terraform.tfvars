# Datadog API 키가 담긴 SSM SecureString 파라미터의 **이름**.
# 키 자체가 아니다 — 키를 여기 적으면 remote state 에 평문으로 남는다.
#
#   aws ssm put-parameter --name /o2/datadog/api-key `
#     --type SecureString --value "<KEY>" --profile o2-data
#
# 비워 두면 Datadog 전송만 꺼지고 DynamoDB 집계는 그대로 동작한다.
datadog_ssm_param = ""

# warm_api_key 는 여기 적지 않는다. 이 파일은 루트 .gitignore 의
# `!infra/*/terraform.tfvars` 때문에 커밋된다.
#   $env:TF_VAR_warm_api_key = "<32자 이상 랜덤 문자열>"
