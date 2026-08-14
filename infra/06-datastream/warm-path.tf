###############################################################################
# Warm Path — Agent 실시간 공급 파이프라인
#
# 함수 코드는 ./warm/ 에 있습니다(스택 안).
# **기존 리소스를 재정의하지 않습니다.** lambda.tf 에 필요한 소폭 수정은
# ./warm/DEPLOY.md 의 "lambda.tf 수정" 절에 정리해 두었습니다.
#
# 여기서 새로 만드는 것
#   1. stream-client → o2-agg 이벤트 소스 매핑   (click_ratio 를 막고 있던 것)
#   2. o2-agg 역할에 추가 권한 (클라이언트 스트림 읽기, DynamoDB 조회, SSM)
#   3. Lambda o2-warm-api + Function URL          (Agent 조회 계층)
###############################################################################

# s3.tf 가 aws_caller_identity 만 선언하고 있어 리전 데이터 소스를 더합니다.
data "aws_region" "current" {}

# 변수 선언(warm_api_key · datadog_ssm_param)은 variables.tf 로 옮겼습니다.

locals {
  # 함수 코드 위치. 스택 안에 있어 상대 경로가 고정입니다.
  warm_root = "${path.module}/warm"

  # lambda.tf 의 aws_lambda_function.aggregate 가 참조합니다.
  # (./warm/DEPLOY.md "lambda.tf 수정" 절 참고 — 그 파일에 environment
  #  블록을 추가하면 이 맵이 유일한 출처가 되어 설정이 갈라지지 않습니다.)
  warm_env = {
    O2_WARM_TABLE  = aws_dynamodb_table.agent_context.name
    O2_WARM_WINDOW = "10"
    O2_DD_PARAM    = var.datadog_ssm_param
    DD_ENV         = "prod"
    # 클릭이 어느 서비스의 요청으로 이어지는지. 서비스가 늘면 여기만 고칩니다.
    O2_WARM_CLICK_ROUTE = jsonencode({
      COUPON_BUTTON_CLICK = "coupon-api"
      CHECKOUT_CLICK      = "order-api"
    })
  }

  # 패키지에 담을 파이썬 소스. __pycache__ 를 넣으면 아키텍처가 안 맞을 때
  # 오래된 바이트코드가 우선 로드됩니다.
  #
  # o2warm 만 담습니다. 집계기는 o2events SDK 를 런타임에 쓰지 않으므로
  # 발행 코드(emit·emitter·sinks·middleware)가 ZIP 에 들어갈 이유가 없습니다.
  warm_sources = toset([
    for f in fileset("${local.warm_root}/src", "o2warm/**/*.py") : f
  ])
}

###############################################################################
# 1. stream-client → o2-agg
#
# 이것 하나가 click_ratio 와 ua_diversity 를 막고 있었습니다.
# 두 스트림이 같은 윈도우 아이템에 병합되므로 함수 코드 변경은 필요 없습니다.
###############################################################################

resource "aws_lambda_event_source_mapping" "client" {
  event_source_arn  = aws_kinesis_stream.client.arn
  function_name     = aws_lambda_function.aggregate.arn
  starting_position = "LATEST"
  batch_size        = 100
  enabled           = true

  # 클릭은 10초 윈도우가 닫히기 전에 도착해야 같은 창에서 조인됩니다.
  maximum_batching_window_in_seconds = 2

  maximum_retry_attempts         = 3
  bisect_batch_on_function_error = true
}

# 비즈니스 스트림도 같은 이유로 배치 창을 좁힙니다.
# (lambda.tf 의 매핑에 maximum_batching_window_in_seconds = 2 를 추가하세요)

###############################################################################
# 2. o2-agg 추가 권한
#
# 기존 인라인 정책(o2-agg-lambda-policy)은 건드리지 않고 두 번째 정책을
# 같은 역할에 붙입니다. lambda.tf 와 충돌하지 않게 하기 위함입니다.
###############################################################################

data "aws_iam_policy_document" "aggregate_warm" {
  statement {
    sid = "ReadClientStream"

    actions = [
      "kinesis:DescribeStream",
      "kinesis:DescribeStreamSummary",
      "kinesis:GetRecords",
      "kinesis:GetShardIterator",
      "kinesis:ListShards",
    ]

    resources = [aws_kinesis_stream.client.arn]
  }

  statement {
    sid = "ReadAgentContext"

    # 병합 전 현재 스케치를 읽어야 하고(GetItem), 평시 기준 갱신 때
    # 직전 윈도우를 찾아야 합니다(Query).
    actions = [
      "dynamodb:GetItem",
      "dynamodb:Query",
    ]

    resources = [aws_dynamodb_table.agent_context.arn]
  }

  dynamic "statement" {
    for_each = var.datadog_ssm_param == "" ? [] : [1]

    content {
      sid       = "ReadDatadogKey"
      actions   = ["ssm:GetParameter"]
      resources = ["arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.datadog_ssm_param}"]
    }
  }
}

resource "aws_iam_role_policy" "aggregate_warm" {
  name   = "o2-agg-warm-policy"
  role   = aws_iam_role.aggregate_lambda.id
  policy = data.aws_iam_policy_document.aggregate_warm.json
}

###############################################################################
# 3. Agent 조회 API
###############################################################################

data "archive_file" "warm_api" {
  type        = "zip"
  output_path = "${path.module}/lambda/warm-api.zip"

  source {
    content  = file("${local.warm_root}/handlers/serve.py")
    filename = "handler.py"
  }

  dynamic "source" {
    for_each = local.warm_sources

    content {
      content  = file("${local.warm_root}/src/${source.value}")
      filename = source.value
    }
  }
}

resource "aws_cloudwatch_log_group" "warm_api" {
  name              = "/aws/lambda/o2-warm-api"
  retention_in_days = 7
}

resource "aws_iam_role" "warm_api" {
  name               = "o2-warm-api-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "warm_api" {
  statement {
    sid = "ReadAgentContext"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:Query",
    ]

    resources = [aws_dynamodb_table.agent_context.arn]
  }

  statement {
    sid = "WriteIncidentSnapshot"

    # 조치 직전 스냅샷을 남기는 경로입니다. 이것이 없으면 검증 단계에서
    # "무엇과 비교해 복구인가"에 답할 수 없습니다.
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.agent_context.arn]

    condition {
      test     = "ForAllValues:StringLike"
      variable = "dynamodb:LeadingKeys"
      values   = ["INCIDENT#*"]
    }
  }

  statement {
    sid = "WriteLambdaLogs"

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = ["${aws_cloudwatch_log_group.warm_api.arn}:*"]
  }
}

resource "aws_iam_role_policy" "warm_api" {
  name   = "o2-warm-api-policy"
  role   = aws_iam_role.warm_api.id
  policy = data.aws_iam_policy_document.warm_api.json
}

resource "aws_lambda_function" "warm_api" {
  function_name = "o2-warm-api"
  role          = aws_iam_role.warm_api.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  architectures = ["arm64"]
  timeout       = 10
  memory_size   = 256

  filename         = data.archive_file.warm_api.output_path
  source_code_hash = data.archive_file.warm_api.output_base64sha256

  environment {
    variables = merge(
      { O2_WARM_TABLE = aws_dynamodb_table.agent_context.name },
      var.warm_api_key == "" ? {} : { O2_WARM_API_KEY = var.warm_api_key },
    )
  }

  depends_on = [aws_iam_role_policy.warm_api]
}

resource "aws_lambda_function_url" "warm_api" {
  function_name      = aws_lambda_function.warm_api.function_name
  authorization_type = "NONE" # 인증은 X-O2-Key 헤더로 합니다

  cors {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST"]
    allow_headers = ["content-type", "x-o2-key"]
  }
}

###############################################################################
# 출력값
###############################################################################

output "warm_api_url" {
  description = "Agent 조회 엔드포인트. 뒤에 /v1/warm/snapshot?service=... 를 붙입니다."
  value       = aws_lambda_function_url.warm_api.function_url
}

output "warm_client_mapping_uuid" {
  description = "stream-client → o2-agg 매핑 식별자"
  value       = aws_lambda_event_source_mapping.client.uuid
}
