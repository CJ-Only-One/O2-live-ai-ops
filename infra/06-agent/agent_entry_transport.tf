# agent.trigger.v1 공통 진입점의 비활성 transport 기반이다.
#
# Phase 1B/3 안전 경계:
#   - SQS -> Lambda event source mapping 과 Worker 실행 플래그의 기본값은 false 다.
#   - Phase 3 활성화 시 정확히 한 합성 idempotency key만 Dify 호출을 허용한다.
#   - 따라서 queue 에 메시지를 넣어도 자동 소비·Dify 호출은 0건이다.
#
# Phase 3에서 E2E를 시작하려면 event source와 실행 플래그를 각각 별도 변경해야 한다.
# 한 줄 실수로 production source가 Agent를 깨우지 못하게 두 개의 게이트를 둔다.

locals {
  agent_entry_worker_name      = "${local.name}-agent-entry-worker"
  agent_entry_idempotency_name = "${local.name}-agent-entry-idempotency"
}

# ── 전용 Dify API key ────────────────────────────────────────────
#
# SecretString은 읽지 않는다. ARN만 state에 들어가고 값은 Worker가 실행 시 읽는다.

data "aws_secretsmanager_secret" "agent_entry" {
  name = var.agent_entry_secret_name
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
    sid    = "ConsumeAgentInvocationQueue"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [data.aws_sqs_queue.agent_invocation.arn]
  }

  statement {
    sid    = "UseIdempotencyLedger"
    effect = "Allow"
    actions = [
      "dynamodb:DeleteItem",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:TransactWriteItems",
    ]
    resources = [aws_dynamodb_table.agent_entry_idempotency.arn]
  }

  statement {
    sid       = "ReadAuthoritativeIncidentRevision"
    effect    = "Allow"
    actions   = ["dynamodb:GetItem"]
    resources = [data.aws_dynamodb_table.incident_state.arn]
  }

  statement {
    sid       = "EmbedAgentIncidentHistory"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel"]
    resources = ["arn:aws:bedrock:${var.region}::foundation-model/${local.embed_model_id}"]
  }

  statement {
    sid    = "SearchAndStoreAgentIncidentHistory"
    effect = "Allow"
    actions = [
      "s3vectors:GetVectors",
      "s3vectors:PutVectors",
      "s3vectors:QueryVectors",
    ]
    resources = [aws_s3vectors_index.incidents_o2.index_arn]
  }

  statement {
    sid       = "WriteAgentIncidentHistory"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.history_o2.arn}/incidents/*"]
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

  timeout     = 90
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
      # 기본값은 false다. 활성화하더라도 합성 Incident 1개 외에는 Dify를 호출하지 않는다.
      AGENT_ENTRY_EXECUTION_ENABLED    = tostring(var.agent_entry_execution_enabled)
      AGENT_ENTRY_ALLOWED_INCIDENT_IDS = join(",", sort(tolist(var.agent_entry_allowed_incident_ids)))
      AGENT_ENTRY_OPERATIONAL_MODE     = tostring(var.agent_entry_operational_handoff_approved)

      DIFY_URL             = "http://${aws_instance.dify.private_ip}/v1/workflows/run"
      AGENT_ENTRY_SECRET   = var.agent_entry_secret_name
      IDEMPOTENCY_TABLE    = aws_dynamodb_table.agent_entry_idempotency.name
      INCIDENT_STATE_TABLE = data.aws_dynamodb_table.incident_state.name
      IDEMPOTENCY_TTL      = tostring(var.agent_entry_idempotency_ttl_seconds)
      IDEMPOTENCY_LEASE    = "120"
      DIFY_TIMEOUT_SECONDS = "45"
      HISTORY_BUCKET       = aws_s3_bucket.history_o2.bucket
      VECTOR_BUCKET        = aws_s3vectors_vector_bucket.history_o2.vector_bucket_name
      VECTOR_INDEX         = aws_s3vectors_index.incidents_o2.index_name
      EMBED_MODEL_ID       = local.embed_model_id
    }
  }

  depends_on = [
    aws_iam_role_policy.agent_entry_worker,
    aws_iam_role_policy_attachment.agent_entry_worker_basic,
    aws_iam_role_policy_attachment.agent_entry_worker_vpc,
    aws_cloudwatch_log_group.agent_entry_worker,
  ]

  lifecycle {
    precondition {
      condition = (
        (!var.agent_entry_execution_enabled &&
          !var.agent_entry_event_source_enabled &&
        length(var.agent_entry_allowed_incident_ids) == 0) ||
        (var.agent_entry_execution_enabled &&
          var.agent_entry_event_source_enabled &&
          ((var.agent_entry_operational_handoff_approved && length(var.agent_entry_allowed_incident_ids) == 0) ||
          (!var.agent_entry_operational_handoff_approved && length(var.agent_entry_allowed_incident_ids) == 1)))
      )
      error_message = "Agent Entry는 disabled+empty, Shadow enabled+합성 Incident 1개, 또는 운영 승인 enabled+empty 조합만 허용한다."
    }
  }
}

# Agent Invocation Queue의 유일한 Generic Worker consumer. 기본값은 disabled다.
resource "aws_lambda_event_source_mapping" "agent_invocation_worker" {
  event_source_arn = data.aws_sqs_queue.agent_invocation.arn
  function_name    = aws_lambda_function.agent_entry_worker.arn

  enabled = var.agent_entry_event_source_enabled

  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
}

# ── 관측 ─────────────────────────────────────────────────────────

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
