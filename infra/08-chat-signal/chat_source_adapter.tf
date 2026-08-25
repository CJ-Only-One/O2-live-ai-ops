# Phase 2: privacy-safe Chat Candidate INSERT를 공통 agent.trigger.v1 Queue로 바꾸는
# 비활성 Source Adapter다. Candidate 생성 경로와 Agent 실행 경로를 분리한다.

resource "aws_sqs_queue" "chat_source_adapter_dlq" {
  name = "${local.chat_source_adapter_name}-dlq"

  message_retention_seconds = 1209600 # 14일
  sqs_managed_sse_enabled   = true
}

data "archive_file" "chat_source_adapter" {
  type        = "zip"
  output_path = "${path.module}/lambda/chat_source_adapter.zip"

  source {
    content  = file("${path.module}/lambda/adapter/chat_source_adapter.py")
    filename = "lambda_function.py"
  }
}

data "aws_iam_policy_document" "chat_source_adapter_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "chat_source_adapter" {
  name               = "${local.chat_source_adapter_name}-role"
  assume_role_policy = data.aws_iam_policy_document.chat_source_adapter_assume.json
}

data "aws_iam_policy_document" "chat_source_adapter" {
  statement {
    sid = "ReadCandidateInsertStream"
    actions = [
      "dynamodb:DescribeStream",
      "dynamodb:GetRecords",
      "dynamodb:GetShardIterator",
      "dynamodb:ListStreams",
    ]
    # DynamoDB가 Stream을 다시 만들면 timestamp가 바뀌므로, 이 테이블의
    # Stream ARN들로만 제한한 wildcard를 사용한다.
    resources = ["${local.chat_incident_table_arn}/stream/*"]
  }

  statement {
    sid       = "PublishCommonAgentTrigger"
    actions   = ["sqs:SendMessage"]
    resources = [data.aws_sqs_queue.agent_trigger.arn]
  }

  # DynamoDB Streams event source의 bounded retry가 끝난 record metadata를 보낸다.
  # Candidate table에는 원문·사용자 키가 없으므로 DLQ에도 해당 값이 들어오지 않는다.
  statement {
    sid       = "SendFailedStreamBatchToDlq"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.chat_source_adapter_dlq.arn]
  }

  statement {
    sid = "WriteSanitizedAdapterLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.chat_source_adapter.arn}:*"]
  }
}

resource "aws_iam_role_policy" "chat_source_adapter" {
  name   = "chat-candidate-source-adapter"
  role   = aws_iam_role.chat_source_adapter.id
  policy = data.aws_iam_policy_document.chat_source_adapter.json
}

resource "aws_cloudwatch_log_group" "chat_source_adapter" {
  name              = "/aws/lambda/${local.chat_source_adapter_name}"
  retention_in_days = 7
}

resource "aws_lambda_function" "chat_source_adapter" {
  function_name = local.chat_source_adapter_name
  role          = aws_iam_role.chat_source_adapter.arn
  handler       = "lambda_function.handler"
  runtime       = "python3.13"
  architectures = ["arm64"]

  memory_size = 128
  timeout     = 10

  reserved_concurrent_executions = 2

  filename         = data.archive_file.chat_source_adapter.output_path
  source_code_hash = data.archive_file.chat_source_adapter.output_base64sha256

  environment {
    variables = {
      # 기본값은 false다. 활성화하더라도 합성 broadcast 1개 외에는 Queue에 쓰지 않는다.
      CHAT_SOURCE_ADAPTER_ENABLED               = tostring(var.chat_source_adapter_execution_enabled)
      CHAT_SOURCE_ADAPTER_ALLOWED_BROADCAST_IDS = join(",", sort(tolist(var.chat_source_adapter_allowed_broadcast_ids)))
      CHAT_SOURCE_ADAPTER_NOT_BEFORE_EPOCH      = tostring(var.chat_source_adapter_not_before_epoch)
      CHAT_SOURCE_ADAPTER_OPERATIONAL_MODE      = tostring(var.chat_source_adapter_operational_handoff_approved)
      AGENT_TRIGGER_QUEUE_URL                   = data.aws_sqs_queue.agent_trigger.url
    }
  }

  depends_on = [
    aws_iam_role_policy.chat_source_adapter,
    aws_cloudwatch_log_group.chat_source_adapter,
  ]

  lifecycle {
    precondition {
      condition = (
        (!var.chat_source_adapter_execution_enabled &&
          !var.chat_source_adapter_event_source_enabled &&
          length(var.chat_source_adapter_allowed_broadcast_ids) == 0 &&
        var.chat_source_adapter_not_before_epoch == 4102444800) ||
        (var.chat_source_adapter_execution_enabled &&
          var.chat_source_adapter_event_source_enabled &&
          ((var.chat_source_adapter_operational_handoff_approved && length(var.chat_source_adapter_allowed_broadcast_ids) == 0) ||
          (!var.chat_source_adapter_operational_handoff_approved && length(var.chat_source_adapter_allowed_broadcast_ids) == 1)) &&
        var.chat_source_adapter_not_before_epoch < 4102444800)
      )
      error_message = "Chat Adapter는 disabled+empty+2100 cutoff, Shadow enabled+합성 broadcast 1개, 또는 운영 승인 enabled+empty+명시 cutover 조합만 허용한다."
    }
  }
}

resource "aws_lambda_event_source_mapping" "chat_source_adapter" {
  event_source_arn  = local.chat_incident_stream_arn
  function_name     = aws_lambda_function.chat_source_adapter.arn
  starting_position = "LATEST"

  # 기본값은 false다. Phase 3에서도 합성 allowlist와 cutover 없이는 plan이 실패한다.
  enabled = var.chat_source_adapter_event_source_enabled

  batch_size                         = 10
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
  bisect_batch_on_function_error     = true
  maximum_retry_attempts             = 3
  maximum_record_age_in_seconds      = 300

  filter_criteria {
    filter {
      pattern = jsonencode({
        dynamodb = {
          Keys = {
            pk = { S = [{ prefix = "CANDIDATE#" }] }
            sk = { S = ["META"] }
          }
        }
      })
    }
  }

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.chat_source_adapter_dlq.arn
    }
  }

  depends_on = [aws_iam_role_policy.chat_source_adapter]
}

resource "aws_cloudwatch_metric_alarm" "chat_source_adapter_dlq_not_empty" {
  alarm_name          = "${local.chat_source_adapter_name}-dlq-not-empty"
  alarm_description   = "Chat Candidate Source Adapter DLQ에 실패한 Stream batch가 있다. 확인 전 재처리하지 않는다."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.chat_source_adapter_dlq.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [data.aws_sns_topic.agent_alarm.arn]
  ok_actions    = [data.aws_sns_topic.agent_alarm.arn]
}

resource "aws_cloudwatch_metric_alarm" "chat_source_adapter_errors" {
  alarm_name          = "${local.chat_source_adapter_name}-errors"
  alarm_description   = "Chat Candidate Source Adapter Lambda가 비정상 종료했다."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.chat_source_adapter.function_name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [data.aws_sns_topic.agent_alarm.arn]
  ok_actions    = [data.aws_sns_topic.agent_alarm.arn]
}
