# agent.trigger.v1 source 신호를 agent.incident.v1 revision으로 승격하는 비활성 기반이다.
#
# Phase 3B 안전 경계:
#   - 기존 agent-trigger Queue는 물리 이름을 유지하고 Signal Queue로 사용한다.
#   - Correlator event source와 실행 플래그의 기본값은 false다.
#   - correlation window 기본값은 0이라 측정 전에는 활성화 plan 자체가 실패한다.
#   - Agent Invocation Queue에는 event source가 없으므로 Dify 호출은 0건이다.

locals {
  incident_state_table_name   = "${local.name}-incident-state"
  incident_correlation_index  = "correlation-key-last-signal-index"
  incident_correlator_name    = "${local.name}-incident-correlator"
  agent_invocation_queue_name = "${local.name}-agent-invocation"
  agent_invocation_dlq_name   = "${local.name}-agent-invocation-dlq"
}

# ── Agent Invocation Queue ───────────────────────────────────────

resource "aws_sqs_queue" "agent_invocation_dlq" {
  name = local.agent_invocation_dlq_name

  message_retention_seconds = 1209600 # 14일
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "agent_invocation" {
  name = local.agent_invocation_queue_name

  # Phase 3D Generic Worker timeout 60초의 6배. 현재는 consumer를 연결하지 않는다.
  visibility_timeout_seconds = 360
  message_retention_seconds  = 345600 # 4일
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.agent_invocation_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "agent_invocation" {
  queue_url = aws_sqs_queue.agent_invocation_dlq.url

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.agent_invocation.arn]
  })
}

# ── Incident State / source signal claim ─────────────────────────

resource "aws_dynamodb_table" "incident_state" {
  name         = local.incident_state_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "correlation_key"
    type = "S"
  }

  attribute {
    name = "last_signal_at_epoch"
    type = "N"
  }

  global_secondary_index {
    name            = local.incident_correlation_index
    projection_type = "ALL"

    key_schema {
      attribute_name = "correlation_key"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "last_signal_at_epoch"
      key_type       = "RANGE"
    }
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

# ── Correlator IAM ───────────────────────────────────────────────

resource "aws_iam_role" "incident_correlator" {
  name               = "${local.name}-incident-correlator-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "incident_correlator_basic" {
  role       = aws_iam_role.incident_correlator.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "incident_correlator" {
  statement {
    sid    = "ConsumeSignalQueue"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.agent_entry.arn]
  }

  statement {
    sid    = "WriteInvocationQueue"
    effect = "Allow"
    actions = [
      "sqs:SendMessage",
    ]
    resources = [aws_sqs_queue.agent_invocation.arn]
  }

  statement {
    sid    = "UseIncidentState"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:TransactWriteItems",
    ]
    resources = [
      aws_dynamodb_table.incident_state.arn,
      "${aws_dynamodb_table.incident_state.arn}/index/${local.incident_correlation_index}",
    ]
  }
}

resource "aws_iam_role_policy" "incident_correlator" {
  name   = "${local.name}-incident-correlator"
  role   = aws_iam_role.incident_correlator.id
  policy = data.aws_iam_policy_document.incident_correlator.json
}

# ── Incident Correlator ──────────────────────────────────────────

resource "aws_cloudwatch_log_group" "incident_correlator" {
  name              = "/aws/lambda/${local.incident_correlator_name}"
  retention_in_days = 7
}

data "archive_file" "incident_correlator" {
  type        = "zip"
  output_path = "${path.module}/lambda/incident_correlator.zip"

  source {
    content  = file("${path.module}/lambda/incident_correlator.py")
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "incident_correlator" {
  function_name = local.incident_correlator_name
  role          = aws_iam_role.incident_correlator.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]

  timeout     = 30
  memory_size = 128

  filename         = data.archive_file.incident_correlator.output_path
  source_code_hash = data.archive_file.incident_correlator.output_base64sha256

  reserved_concurrent_executions = var.incident_correlator_max_concurrency

  environment {
    variables = {
      INCIDENT_CORRELATOR_EXECUTION_ENABLED        = tostring(var.incident_correlator_execution_enabled)
      INCIDENT_CORRELATOR_ALLOWED_IDEMPOTENCY_KEYS = join(",", sort(tolist(var.incident_correlator_allowed_idempotency_keys)))
      INCIDENT_CORRELATION_WINDOW_SECONDS          = tostring(var.incident_correlation_window_seconds)
      INCIDENT_RECOVERY_WINDOW_SECONDS             = tostring(var.incident_recovery_window_seconds)
      INCIDENT_COOLDOWN_SECONDS                    = tostring(var.incident_cooldown_seconds)
      INCIDENT_REOPEN_WINDOW_SECONDS               = tostring(var.incident_reopen_window_seconds)
      INCIDENT_CHAT_SURFACE_MAP_JSON               = jsonencode(var.incident_chat_surface_map)
      INCIDENT_DATADOG_MONITOR_MAP_JSON            = jsonencode(var.incident_datadog_monitor_map)
      INCIDENT_STATE_TABLE                         = aws_dynamodb_table.incident_state.name
      INCIDENT_CORRELATION_INDEX                   = local.incident_correlation_index
      INCIDENT_SIGNAL_CLAIM_TTL                    = tostring(var.agent_entry_idempotency_ttl_seconds)
      AGENT_INVOCATION_QUEUE_URL                   = aws_sqs_queue.agent_invocation.url
      DEPLOYMENT_ENVIRONMENT                       = var.environment
      INCIDENT_SHADOW_MODE                         = tostring(var.incident_shadow_mode)
    }
  }

  depends_on = [
    aws_iam_role_policy.incident_correlator,
    aws_iam_role_policy_attachment.incident_correlator_basic,
    aws_cloudwatch_log_group.incident_correlator,
  ]

  lifecycle {
    precondition {
      condition = (
        (!var.incident_correlator_execution_enabled &&
          !var.incident_correlator_event_source_enabled &&
        length(var.incident_correlator_allowed_idempotency_keys) == 0) ||
        (var.incident_correlator_execution_enabled &&
          var.incident_correlator_event_source_enabled &&
          var.incident_correlation_window_seconds > 0 &&
          ((var.incident_shadow_mode && length(var.incident_correlator_allowed_idempotency_keys) >= 1 && length(var.incident_correlator_allowed_idempotency_keys) <= 8) ||
        (!var.incident_shadow_mode && var.incident_operational_handoff_approved && length(var.incident_correlator_allowed_idempotency_keys) == 0 && var.incident_recovery_window_seconds > 0 && var.incident_cooldown_seconds > 0 && var.incident_reopen_window_seconds > 0)))
      )
      error_message = "Incident Correlator는 disabled+empty allowlist 또는 enabled+측정 window+합성 key 1~8개 조합만 허용한다."
    }
  }
}

# Phase 3B에는 관계와 IAM만 검증하고 Signal Queue polling은 하지 않는다.
resource "aws_lambda_event_source_mapping" "incident_correlator" {
  event_source_arn = aws_sqs_queue.agent_entry.arn
  function_name    = aws_lambda_function.incident_correlator.arn

  enabled = var.incident_correlator_event_source_enabled

  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
}

# ── 관측 ─────────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "agent_invocation_queue_age" {
  alarm_name          = "${local.name}-agent-invocation-queue-age"
  alarm_description   = "Agent Invocation Queue의 가장 오래된 메시지가 5분을 넘겼다. Phase 3B에서는 메시지가 없어야 한다."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  dimensions          = { QueueName = aws_sqs_queue.agent_invocation.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 300
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.incident_alarm.arn]
  ok_actions    = [aws_sns_topic.incident_alarm.arn]
}

resource "aws_cloudwatch_metric_alarm" "agent_invocation_dlq_not_empty" {
  alarm_name          = "${local.name}-agent-invocation-dlq-not-empty"
  alarm_description   = "Agent Invocation DLQ에 메시지가 있다. Incident revision과 Worker ledger를 확인하기 전 재투입하지 않는다."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.agent_invocation_dlq.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.incident_alarm.arn]
  ok_actions    = [aws_sns_topic.incident_alarm.arn]
}

resource "aws_cloudwatch_metric_alarm" "incident_correlator_errors" {
  alarm_name          = "${local.name}-incident-correlator-errors"
  alarm_description   = "Incident Correlator가 비정상 종료했다. record 실패는 Signal Queue age와 DLQ로 본다."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.incident_correlator.function_name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.incident_alarm.arn]
  ok_actions    = [aws_sns_topic.incident_alarm.arn]
}
