###############################################################################
# Warm Path — Agent 실시간 공급 파이프라인
#
# 함수 코드는 ./warm/ 에 있습니다(스택 안).
# **기존 리소스를 재정의하지 않습니다.** lambda.tf 가 소유한 것은 그쪽에 두고,
# 여기서는 더하기만 합니다.
#
# 여기서 만드는 것
#   1. stream-client → o2-agg 이벤트 소스 매핑   (click_ratio 를 막고 있던 것)
#   2. o2-agg 역할에 추가 권한 (클라이언트 스트림 읽기, DynamoDB 조회, 시크릿)
#   3. Lambda o2-warm-api + Function URL          (Agent 조회 계층)
#
# 배포 절차와 검증 방법은 ./warm/DEPLOY.md 에 있습니다.
###############################################################################

# s3.tf 가 aws_caller_identity 만 선언하고 있어 리전 데이터 소스를 더합니다.
data "aws_region" "current" {}

# Datadog 키가 담긴 시크릿. **04-platform 이 소유하고 이 스택은 참조만 합니다.**
# SecretString 을 읽지 않으므로 키가 state 에 남지 않습니다
# (04-platform/external_secrets.tf 의 같은 패턴).
data "aws_secretsmanager_secret" "datadog" {
  count = var.datadog_secret_name == "" ? 0 : 1
  name  = var.datadog_secret_name
}

locals {
  # 함수 코드 위치. 스택 안에 있어 상대 경로가 고정입니다.
  warm_root = "${path.module}/warm"

  # lambda.tf 의 aws_lambda_function.aggregate 가 이 맵을 environment 로 씁니다.
  # **집계 Lambda 설정의 유일한 출처입니다.** 두 곳에 나누면 한쪽이 낡습니다.
  warm_env = {
    O2_WARM_TABLE  = aws_dynamodb_table.agent_context.name
    O2_WARM_WINDOW = "10"
    DD_ENV         = "prod"

    # 키가 **어디 있는지**만 넣습니다. 값을 넣으면 state 와 Lambda 콘솔에
    # 평문으로 남습니다. 조회는 o2warm/secrets.py 가 실행 시점에 합니다.
    O2_DD_SECRET          = var.datadog_secret_name
    O2_DD_SECRET_PROPERTY = var.datadog_secret_property
    O2_DD_PARAM           = var.datadog_ssm_param # 대안 경로

    # settings.py 의 기본값은 US1 이다. 조직이 AP1 이라 반드시 주입한다.
    # (variables.tf 의 datadog_site 설명 참고 — 틀리면 조용히 실패한다)
    DD_SITE = var.datadog_site
    # 클릭이 어느 서비스의 요청으로 이어지는지. 서비스가 늘면 여기만 고칩니다.
    #
    # **실제 서비스 이름과 같아야 합니다.** 기본값(coupon-api / order-api)은
    # SDK 예제의 이름이고, 우리 봉투의 service 는 `api` 하나입니다
    # (contracts.md 5.4). 어긋나면 클릭은 METRIC#coupon-api 로, 서버 이벤트는
    # METRIC#api 로 갈라져 click_ratio 가 영원히 null 입니다 — 파드도 apply 도
    # 정상이라 알아채기 어렵습니다.
    O2_WARM_CLICK_ROUTE = jsonencode({
      COUPON_BUTTON_CLICK = "api"
      CHECKOUT_CLICK      = "api"
    })

    # click_route 에 없는 클라이언트 이벤트(LIVE_ENTER·LIVE_LEAVE)가 갈 곳.
    # 기본값 live-web 으로 두면 서버 이벤트가 하나도 없는 파티션이 따로 생기고,
    # ua_diversity 가 그쪽으로 빠져 api 윈도우에서는 계속 null 입니다.
    O2_WARM_CLIENT_SERVICE = "api"
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

# 비즈니스 스트림 매핑은 lambda.tf 가 소유하고, 같은 이유로 그쪽에도
# maximum_batching_window_in_seconds = 2 가 들어가 있습니다.

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

  # 권장 경로. 시크릿 하나만 읽습니다 — secretsmanager:* 를 주지 않습니다.
  dynamic "statement" {
    for_each = var.datadog_secret_name == "" ? [] : [1]

    content {
      sid       = "ReadDatadogSecret"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [data.aws_secretsmanager_secret.datadog[0].arn]
    }
  }

  # 대안 경로. 둘 다 비어 있으면 어느 statement 도 생기지 않습니다.
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

  # X-O2-Key 를 실행 시점에 읽습니다. 이 권한이 없으면 인증이 **열리지 않고
  # 막힙니다** (401) — secrets.py 가 조회 실패와 미설정을 구분하기 때문입니다.
  dynamic "statement" {
    for_each = var.warm_api_key_param == "" ? [] : [1]

    content {
      sid       = "ReadApiKey"
      actions   = ["ssm:GetParameter"]
      resources = ["arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.warm_api_key_param}"]
    }
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
      # 권장: 파라미터 이름만 넣고 값은 실행 시점에 읽습니다.
      var.warm_api_key_param == "" ? {} : { O2_WARM_API_KEY_PARAM = var.warm_api_key_param },
      # 로컬 실험용. 이 경로는 값이 state 에 남습니다.
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
