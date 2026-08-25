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
    DD_ENV         = var.environment

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

  # ---------------------------------------------------------------------------
  # parallelization_factor 를 설정하지 않습니다. 기본값 1 이 **의도한 값**입니다.
  #
  # 집계기가 밀릴 때(M-015 에서 IteratorAge 102초를 봤습니다) 이 값을 올리는
  # 것이 가장 먼저 떠오르는 손잡이인데, **이 파이프라인에서는 데이터가 조용히
  # 줄어듭니다.**
  #
  # 이유 — 집계기의 이중 집계 가드(`WindowSketch.already_applied`)가 샤드별
  # sequence number 를 **최댓값 하나**로만 들고 있습니다. 같은 샤드를 여러
  # 배치가 동시에 처리하면 늦게 시작한 배치가 먼저 끝날 수 있고, 그러면 앞선
  # 배치가 재시도로 오인돼 통째로 버려집니다. 예외도 오류도 없습니다.
  #
  # 실측: 같은 샤드에서 배치 둘(각 10건)이 뒤바뀌어 도착하면 20건이 아니라
  # **10건**이 남습니다. `warm/tests/test_sequence_guard.py` 가 고정해 뒀습니다.
  #
  # **밀리는 것은 샤드 수로 풉니다.** 샤드가 다르면 `source` 키가 갈려
  # (`aggregate._source_of()` 가 스트림+샤드로 만듭니다) 번호를 독립적으로
  # 비교하므로 안전합니다. 근거와 대안 비교는 D-063.
  # ---------------------------------------------------------------------------

  maximum_retry_attempts         = 3
  bisect_batch_on_function_error = true

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.aggregate_dlq.arn
    }
  }
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

  statement {
    sid = "QueryAthenaDataLake"

    actions = [
      "athena:StartQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetPartitions",
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]

    resources = ["*"]
  }

  # X-O2-Key 를 실행 시점에 읽습니다. 이 권한이 없으면 인증이 **열리지 않고
  # 막힙니다** (401) — secrets.py 가 조회 실패와 미설정을 구분하기 때문입니다.
  dynamic "statement" {
    for_each = var.warm_api_key_param == "" ? [] : [1]

    content {
      sid       = "ReadApiKey"
      actions   = ["ssm:GetParameter", "kms:Decrypt"]
      resources = ["*"]
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
  timeout       = 30
  memory_size   = 256

  filename         = data.archive_file.warm_api.output_path
  source_code_hash = data.archive_file.warm_api.output_base64sha256

  environment {
    variables = merge(
      {
        O2_WARM_TABLE       = aws_dynamodb_table.agent_context.name
        O2_DATA_LAKE_BUCKET = aws_s3_bucket.data_lake.bucket
      },
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

# Function URL 을 anonymous(NONE)로 열어도 이 두 permission 이 둘 다 있어야
# 실제로 함수까지 도달한다. 하나만 있으면 AWS 가 함수 코드 앞에서
# AccessDeniedException 으로 막는다 — Dify Agent 쪽에서 처음 붙였을 때
# 이걸로 403을 겪었다(둘 다 이 policy 없이는 재현된다).
#
#   InvokeFunctionUrl — Function URL 경로 자체를 호출할 권한.
resource "aws_lambda_permission" "warm_api_url" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.warm_api.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

#   InvokeFunction — Function URL 이 내부적으로 함수를 실제 실행할 권한.
#   `lambda:InvokedViaFunctionUrl` Bool 조건으로 Function URL 경유 호출에만
#   한정하는 게 정석이지만, aws_lambda_permission 리소스에 그 조건을 걸
#   인자가 없다(AWS CLI add-permission 도 동일한 제약). 이 action 자체가
#   AWS 자격증명 없는 익명 호출자한테는 Function URL 을 통하지 않고는
#   실행할 방법이 없어서, 조건이 없어도 실질적인 노출 범위는 같다.
resource "aws_lambda_permission" "warm_api_invoke" {
  statement_id  = "FunctionURLAllowInvokeAction"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.warm_api.function_name
  principal     = "*"
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
