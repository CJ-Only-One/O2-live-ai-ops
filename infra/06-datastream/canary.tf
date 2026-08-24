###############################################################################
# 파이프라인 생존 카나리
#
# 1분마다 합성 이벤트 하나를 stream-business 에 넣는다. 그 이벤트가
# `o2.warm.rps{service:o2-canary}` 로 나오면 인입 → 집계 → Datadog 전송이
# 전부 살아 있다는 뜻이다. 근거와 흔적은 `canary/handler.py` 머리말에 있다.
#
# **왜 이게 필요한지는 D-052 에 있다.** 요약하면 이 경로는 전 구간이 실패를
# 삼키도록 설계돼 있고(가용성 우선), 로그 수집도 꺼져 있어서 멈춰도 아무도
# 모른다. 그리고 실제 트래픽에 no-data 를 걸면 한산할 때 오탐이 나서
# 결국 꺼진다 — `order_latency_p95` 에서 이미 겪었다.
#
# 알림은 `05-datadog` 이 만든다. 여기는 신호를 만들기만 한다.
###############################################################################

variable "enable_pipeline_canary" {
  description = <<-EOT
    파이프라인 생존 카나리 활성화 여부. 기본 `true`.

    끄면 `05-datadog` 의 `warm_pipeline_stalled` Monitor 가 영구 No Data 가
    된다 — 둘은 같이 켜고 같이 끈다.

    합성 레코드가 S3 데이터 레이크에도 적재된다는 점을 알고 있어야 한다
    (Firehose 가 같은 스트림을 읽는다). Athena 에서는
    `service <> 'o2-canary'` 로 뺀다.
  EOT
  type        = bool
  default     = true
}

variable "canary_interval_minutes" {
  description = <<-EOT
    카나리 주입 간격(분). 기본 1 — EventBridge 최소값이다.

    이 값이 `05-datadog` 의 no-data 윈도우보다 촘촘해야 한다. 간격을 늘리면
    그쪽 `no_data_timeframe` 도 같이 늘려야 오탐이 안 난다.
  EOT
  type        = number
  default     = 1
}

locals {
  canary_service = "o2-canary"
}

data "archive_file" "canary" {
  type        = "zip"
  output_path = "${path.module}/lambda/canary.zip"

  source {
    content  = file("${path.module}/canary/handler.py")
    filename = "handler.py"
  }
}

resource "aws_iam_role" "canary" {
  count = var.enable_pipeline_canary ? 1 : 0

  name = "o2-canary-lambda-role"
  # lambda_assume_role 문서는 lambda.tf 에 이미 있다. 같은 것을 재사용한다.
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "canary" {
  # 로그 그룹 ARN 을 참조하므로 이 문서도 같이 게이트한다. 안 하면
  # enable_pipeline_canary = false 일 때 없는 리소스를 가리켜 plan 이 깨진다.
  count = var.enable_pipeline_canary ? 1 : 0

  statement {
    sid       = "PutCanaryRecord"
    actions   = ["kinesis:PutRecord"]
    resources = [aws_kinesis_stream.business.arn]
  }

  statement {
    sid = "Logs"

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = ["${aws_cloudwatch_log_group.canary[0].arn}:*"]
  }
}

resource "aws_iam_role_policy" "canary" {
  count = var.enable_pipeline_canary ? 1 : 0

  name   = "o2-canary-lambda-policy"
  role   = aws_iam_role.canary[0].id
  policy = data.aws_iam_policy_document.canary[0].json
}

resource "aws_cloudwatch_log_group" "canary" {
  count = var.enable_pipeline_canary ? 1 : 0

  name              = "/aws/lambda/o2-canary"
  retention_in_days = 7
}

resource "aws_lambda_function" "canary" {
  count = var.enable_pipeline_canary ? 1 : 0

  function_name = "o2-canary"
  role          = aws_iam_role.canary[0].arn
  handler       = "handler.handler"
  runtime       = "python3.11"

  filename         = data.archive_file.canary.output_path
  source_code_hash = data.archive_file.canary.output_base64sha256

  # 레코드 하나 넣고 끝난다. 크게 줄 이유가 없다.
  timeout     = 10
  memory_size = 128

  environment {
    variables = {
      CANARY_STREAM  = aws_kinesis_stream.business.name
      CANARY_SERVICE = local.canary_service
    }
  }

  depends_on = [
    aws_iam_role_policy.canary,
    aws_cloudwatch_log_group.canary,
  ]
}

resource "aws_cloudwatch_event_rule" "canary" {
  count = var.enable_pipeline_canary ? 1 : 0

  name                = "o2-canary-schedule"
  description         = "파이프라인 생존 카나리 주입"
  schedule_expression = "rate(${var.canary_interval_minutes} minute${var.canary_interval_minutes == 1 ? "" : "s"})"
}

resource "aws_cloudwatch_event_target" "canary" {
  count = var.enable_pipeline_canary ? 1 : 0

  rule = aws_cloudwatch_event_rule.canary[0].name
  arn  = aws_lambda_function.canary[0].arn
}

resource "aws_lambda_permission" "canary" {
  count = var.enable_pipeline_canary ? 1 : 0

  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.canary[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.canary[0].arn
}

output "canary_service_tag" {
  description = <<-EOT
    카나리가 쓰는 service 태그. 대시보드·Athena·에이전트 조회에서 이 값을
    빼야 실제 트래픽 통계가 오염되지 않는다.
  EOT
  value       = local.canary_service
}
