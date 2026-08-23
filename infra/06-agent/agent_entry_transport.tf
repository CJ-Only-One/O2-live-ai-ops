# agent.trigger.v1 공통 진입점의 비활성 transport 기반이다.
#
# Phase 1B 안전 경계:
#   - SQS -> Lambda event source mapping 은 생성하지만 enabled=false 다.
#   - Worker 환경변수 AGENT_ENTRY_EXECUTION_ENABLED=false 를 하드코딩한다.
#   - 따라서 queue 에 메시지를 넣어도 자동 소비·Dify 호출은 0건이다.
#
# Phase 3에서 E2E를 시작하려면 event source와 실행 플래그를 각각 별도 변경해야 한다.
# 한 줄 실수로 production source가 Agent를 깨우지 못하게 두 개의 게이트를 둔다.

locals {
  agent_entry_queue_name       = "${local.name}-agent-trigger"
  agent_entry_dlq_name         = "${local.name}-agent-trigger-dlq"
  agent_entry_worker_name      = "${local.name}-agent-entry-worker"
  agent_entry_idempotency_name = "${local.name}-agent-entry-idempotency"
}

# ── 전용 Dify API key ────────────────────────────────────────────
#
# SecretString은 읽지 않는다. ARN만 state에 들어가고 값은 Worker가 실행 시 읽는다.

data "aws_secretsmanager_secret" "agent_entry" {
  name = var.agent_entry_secret_name
}

# ── Queue / DLQ ──────────────────────────────────────────────────

resource "aws_sqs_queue" "agent_entry_dlq" {
  name = local.agent_entry_dlq_name

  message_retention_seconds = 1209600 # 14일
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "agent_entry" {
  name = local.agent_entry_queue_name

  # Worker timeout 60초의 6배. Lambda/SQS 재전달 중복 가능성을 줄인다.
  visibility_timeout_seconds = 360
  message_retention_seconds  = 345600 # 4일
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.agent_entry_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "agent_entry" {
  queue_url = aws_sqs_queue.agent_entry_dlq.url

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.agent_entry.arn]
  })
}

# ── 멱등성 ledger ────────────────────────────────────────────────

resource "aws_dynamodb_table" "agent_entry_idempotency" {
  name         = local.agent_entry_idempotency_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "idempotency_key"

  attribute {
    name = "idempotency_key"
    type = "S"
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

# ── Generic Worker IAM ───────────────────────────────────────────

resource "aws_iam_role" "agent_entry_worker" {
  name               = "${local.name}-agent-entry-worker-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "agent_entry_worker_basic" {
  role       = aws_iam_role.agent_entry_worker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "agent_entry_worker_vpc" {
  role       = aws_iam_role.agent_entry_worker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "agent_entry_worker" {
  statement {
    sid       = "ReadDedicatedDifyKey"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [data.aws_secretsmanager_secret.agent_entry.arn]
  }

  statement {
    sid    = "ConsumeAgentTriggerQueue"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.agent_entry.arn]
  }

  statement {
    sid    = "UseIdempotencyLedger"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
    ]
    resources = [aws_dynamodb_table.agent_entry_idempotency.arn]
  }
}

resource "aws_iam_role_policy" "agent_entry_worker" {
  name   = "${local.name}-agent-entry-worker"
  role   = aws_iam_role.agent_entry_worker.id
  policy = data.aws_iam_policy_document.agent_entry_worker.json
}

# ── Generic Worker ───────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "agent_entry_worker" {
  name              = "/aws/lambda/${local.agent_entry_worker_name}"
  retention_in_days = 7
}

data "archive_file" "agent_entry_worker" {
  type        = "zip"
  output_path = "${path.module}/lambda/agent_entry_worker.zip"

  source {
    content  = file("${path.module}/lambda/agent_entry_worker.py")
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "agent_entry_worker" {
  function_name = local.agent_entry_worker_name
  role          = aws_iam_role.agent_entry_worker.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]

  timeout     = 60
  memory_size = 128

  filename         = data.archive_file.agent_entry_worker.output_path
  source_code_hash = data.archive_file.agent_entry_worker.output_base64sha256

  reserved_concurrent_executions = var.agent_entry_worker_max_concurrency

  vpc_config {
    subnet_ids         = [local.subnet_id]
    security_group_ids = [aws_security_group.alert_relay.id]
  }

  environment {
    variables = {
      # Phase 1B 하드 게이트. event source를 실수로 켜도 Dify를 호출하지 않는다.
      AGENT_ENTRY_EXECUTION_ENABLED = "false"

      DIFY_URL             = "http://${aws_instance.dify.private_ip}/v1/workflows/run"
      AGENT_ENTRY_SECRET   = var.agent_entry_secret_name
      IDEMPOTENCY_TABLE    = aws_dynamodb_table.agent_entry_idempotency.name
      IDEMPOTENCY_TTL      = tostring(var.agent_entry_idempotency_ttl_seconds)
      IDEMPOTENCY_LEASE    = "120"
      DIFY_TIMEOUT_SECONDS = "45"
    }
  }

  depends_on = [
    aws_iam_role_policy.agent_entry_worker,
    aws_iam_role_policy_attachment.agent_entry_worker_basic,
    aws_iam_role_policy_attachment.agent_entry_worker_vpc,
    aws_cloudwatch_log_group.agent_entry_worker,
  ]
}

# 리소스 관계와 IAM은 validate하되 polling은 하지 않는다.
resource "aws_lambda_event_source_mapping" "agent_entry" {
  event_source_arn = aws_sqs_queue.agent_entry.arn
  function_name    = aws_lambda_function.agent_entry_worker.arn

  enabled = false

  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
}

# ── 관측 ─────────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "agent_entry_queue_age" {
  alarm_name          = "${local.name}-agent-entry-queue-age"
  alarm_description   = "Agent Trigger Queue의 가장 오래된 메시지가 5분을 넘겼다. Phase 1B에서는 메시지가 없어야 한다."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  dimensions          = { QueueName = aws_sqs_queue.agent_entry.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 300
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alert_relay_alarm.arn]
  ok_actions    = [aws_sns_topic.alert_relay_alarm.arn]
}

resource "aws_cloudwatch_metric_alarm" "agent_entry_dlq_not_empty" {
  alarm_name          = "${local.name}-agent-entry-dlq-not-empty"
  alarm_description   = "Agent Trigger DLQ에 메시지가 있다. 원인을 확인하기 전 재투입하지 않는다."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.agent_entry_dlq.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alert_relay_alarm.arn]
  ok_actions    = [aws_sns_topic.alert_relay_alarm.arn]
}

resource "aws_cloudwatch_metric_alarm" "agent_entry_worker_errors" {
  alarm_name          = "${local.name}-agent-entry-worker-errors"
  alarm_description   = "Agent Entry Worker 자체가 비정상 종료했다. SQS record 실패는 Queue age와 DLQ로 본다."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.agent_entry_worker.function_name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alert_relay_alarm.arn]
  ok_actions    = [aws_sns_topic.alert_relay_alarm.arn]
}
