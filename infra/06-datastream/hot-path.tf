###############################################################################
# Hot Path — Datadog 시계열 지표 역쿼리 게이트웨이
#
# docs/DatadogMcpQueryInstruction.md 의 구현안 A(HTTP REST API Gateway,
# `o2-hot-api`)를 따릅니다. 구현안 B(EC2 상시 MCP 데몬, 키를 환경변수
# 평문 보관)는 채택하지 않습니다 — 그 지침서 1절 비교표가 이미 A 를
# 운영 표준으로 지목했고, B 는 "로컬 클로드 데스크톱 개발용"으로
# 명시돼 있습니다.
#
# ## 인증이 X-O2-Key 가 아니라 AWS_IAM(SigV4)인 이유
#
# `o2-warm-api` 와 같은 Function URL(`authorization_type = NONE` +
# 공유 시크릿) 패턴을 그대로 쓰려 했으나, D-031 이 그 패턴이 **이 계정에서
# 인터넷 요청 전부 403** 이라는 것을 이미 확인해 두었다(계정 밖 SCP/RCP
# 가설). 실제로 다시 확인했다 — 이 계정은 AWS Organizations 의 멤버
# 계정이라 `organizations:DescribeOrganization`/`ListPolicies` 자체가
# `AdministratorAccess` 로도 막힌다(멤버 계정에서는 원천적으로 조직
# 정책을 조회·수정할 수 없다). 즉 "정책을 완화"할 방법이 이 계정
# 안에는 없다.
#
# 그래서 D-031 이 "가장 깨끗하다"고 짚어 둔 대안 — Function URL 인증을
# `AWS_IAM` 으로 바꾼다. 익명(Principal "*") 리소스가 아니므로 그 SCP/RCP
# 가 막는 패턴 자체에 해당하지 않을 가능성이 높고, 무엇보다 **보관할
# 공유 키가 없어진다**(o2-warm-api 의 X-O2-Key 는 Dify 가 SigV4 를 못
# 해서 쓰는 우회책이었다 — warm/handlers/serve.py docstring 참고).
#
# 호출자는 `aws_lambda_permission.hot_api_invoker` 로 명시한 IAM 주체만
# 가능하다 — 기본적으로 AWS_IAM 인증은 전부 거부이고, 이 리소스 기반
# 권한이 있어야 그 주체가 `lambda:InvokeFunctionUrl` 을 할 수 있다.
#
# **미확인 위험**: Dify 의 Custom Tool(OpenAPI 3.0) 이 AWS SigV4 서명을
# 지원하지 않으면 이 경로도 실제로는 못 붙는다. 그때는 Dify EC2
# 인스턴스(`infra/06-agent`, 같은 IAM 역할)에서 로컬로 서명해 중계하는
# 프록시가 필요하다 — 아직 만들지 않았다.
#
# 함수 코드는 ./hot/ 에 있습니다(스택 안).
#
# Datadog 시크릿(o2/dev/datadog-new)은 이 스택이 이미 warm-path.tf 에서
# `data.aws_secretsmanager_secret.datadog` 로 참조하고 있어 여기서는
# 재사용만 합니다 — 사본을 만들지 않습니다.
###############################################################################

locals {
  hot_root = "${path.module}/hot"

  # o2warm_sources 와 같은 이유로 o2hot 만 담습니다. __pycache__ 를 넣으면
  # 아키텍처가 안 맞을 때 오래된 바이트코드가 우선 로드됩니다.
  hot_sources = toset([
    for f in fileset("${local.hot_root}/src", "o2hot/**/*.py") : f
  ])
}

data "archive_file" "hot_api" {
  type        = "zip"
  output_path = "${path.module}/lambda/hot-api.zip"

  source {
    content  = file("${local.hot_root}/handlers/serve.py")
    filename = "handler.py"
  }

  dynamic "source" {
    for_each = local.hot_sources

    content {
      content  = file("${local.hot_root}/src/${source.value}")
      filename = source.value
    }
  }
}

resource "aws_cloudwatch_log_group" "hot_api" {
  name              = "/aws/lambda/o2-hot-api"
  retention_in_days = 7
}

resource "aws_iam_role" "hot_api" {
  name               = "o2-hot-api-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "hot_api" {
  statement {
    sid = "WriteLambdaLogs"

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = ["${aws_cloudwatch_log_group.hot_api.arn}:*"]
  }

  # 권장 경로. o2-warm-api/o2-agg 와 같은 시크릿을 읽습니다(app-key 도
  # 필요하다는 점만 다릅니다 — o2hot/settings.py 의 dd_secret_app_property).
  dynamic "statement" {
    for_each = var.datadog_secret_name == "" ? [] : [1]

    content {
      sid       = "ReadDatadogSecret"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [data.aws_secretsmanager_secret.datadog[0].arn]
    }
  }

  # api-key 의 대안 경로.
  dynamic "statement" {
    for_each = var.datadog_ssm_param == "" ? [] : [1]

    content {
      sid       = "ReadDatadogKey"
      actions   = ["ssm:GetParameter"]
      resources = ["arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.datadog_ssm_param}"]
    }
  }
}

resource "aws_iam_role_policy" "hot_api" {
  name   = "o2-hot-api-policy"
  role   = aws_iam_role.hot_api.id
  policy = data.aws_iam_policy_document.hot_api.json
}

resource "aws_lambda_function" "hot_api" {
  function_name = "o2-hot-api"
  role          = aws_iam_role.hot_api.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  architectures = ["arm64"]

  # Datadog 왕복 하나가 전부라 warm_api 보다 여유를 적게 둡니다.
  timeout     = 15
  memory_size = 256

  filename         = data.archive_file.hot_api.output_path
  source_code_hash = data.archive_file.hot_api.output_base64sha256

  environment {
    variables = {
      O2_DD_SECRET              = var.datadog_secret_name
      O2_DD_SECRET_API_PROPERTY = var.datadog_secret_property
      O2_DD_SECRET_APP_PROPERTY = var.datadog_secret_app_property
      O2_DD_API_PARAM           = var.datadog_ssm_param
      DD_SITE                   = var.datadog_site
    }
  }

  depends_on = [aws_iam_role_policy.hot_api]
}

resource "aws_lambda_function_url" "hot_api" {
  function_name      = aws_lambda_function.hot_api.function_name
  authorization_type = "AWS_IAM" # 인증은 SigV4. 이유는 위 파일 머리말 참고
}

# 기본 거부다. 이 권한이 있어야 var.hot_api_invoker_role_arn 이
# lambda:InvokeFunctionUrl 을 할 수 있다. "*" 를 principal 로 두지
# 않는다 — 그러면 NONE 과 실질적으로 같아지고, 이 리소스를 만든
# 이유(D-031) 자체가 사라진다.
resource "aws_lambda_permission" "hot_api_invoker" {
  count = var.hot_api_invoker_role_arn == "" ? 0 : 1

  statement_id           = "AllowConfiguredInvoker"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.hot_api.function_name
  principal              = var.hot_api_invoker_role_arn
  function_url_auth_type = "AWS_IAM"
}

###############################################################################
# 출력값
###############################################################################

output "hot_api_url" {
  description = "Datadog 역쿼리 엔드포인트. 뒤에 /v1/hot/datadog/query 를 붙입니다. 호출에는 AWS SigV4 서명이 필요합니다."
  value       = aws_lambda_function_url.hot_api.function_url
}
