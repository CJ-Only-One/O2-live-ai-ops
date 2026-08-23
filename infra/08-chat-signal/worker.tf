data "archive_file" "worker" {
  type        = "zip"
  output_path = "${path.module}/lambda/chat_signal_worker.zip"

  source {
    content  = file("${path.module}/lambda/runtime/handler.py")
    filename = "handler.py"
  }

  source {
    content  = file("${path.module}/lambda/runtime/classifier.py")
    filename = "classifier.py"
  }

  source {
    content  = file("${path.module}/lambda/runtime/processor.py")
    filename = "processor.py"
  }

  source {
    content  = file("${path.module}/lambda/runtime/repository.py")
    filename = "repository.py"
  }
}

data "aws_iam_policy_document" "worker_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "worker" {
  name               = "${local.worker_name}-role"
  assume_role_policy = data.aws_iam_policy_document.worker_assume.json
}

data "aws_iam_policy_document" "worker" {
  statement {
    sid = "ConsumeChatSignalQueue"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [local.chat_signal_queue_arn]
  }

  statement {
    sid = "WriteDerivedIncidentState"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:TransactWriteItems",
    ]
    resources = [local.chat_incident_table_arn]
  }

  statement {
    sid = "WriteSanitizedWorkerLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.worker.arn}:*"]
  }
}

resource "aws_iam_role_policy" "worker" {
  name   = "chat-signal-worker"
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.worker.json
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${local.worker_name}"
  retention_in_days = 7
}

resource "aws_lambda_function" "worker" {
  function_name = local.worker_name
  role          = aws_iam_role.worker.arn
  handler       = "handler.handler"
  runtime       = "python3.13"
  architectures = ["arm64"]

  memory_size                    = 128
  timeout                        = 5
  reserved_concurrent_executions = 1

  filename         = data.archive_file.worker.output_path
  source_code_hash = data.archive_file.worker.output_base64sha256

  environment {
    variables = {
      CHAT_INCIDENT_TABLE_NAME = local.chat_incident_table_name
      WORKER_MODE              = var.enable_event_source ? "SHADOW" : "SOURCE_DISABLED"
    }
  }

  depends_on = [aws_iam_role_policy.worker]
}

resource "aws_lambda_event_source_mapping" "chat_signal" {
  event_source_arn = local.chat_signal_queue_arn
  function_name    = aws_lambda_function.worker.arn

  # 기본값은 false다. Phase 4 tfvars에서만 true로 켜며, 긴급 중단은 이 값을
  # false로 되돌려 apply한다. Queue 원문 보존은 켜져 있어도 최대 60초다.
  enabled = var.enable_event_source

  batch_size                         = 10
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]

  depends_on = [aws_iam_role_policy.worker]
}
