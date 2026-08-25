# Phase 4A: 기존 Datadog -> O2 Dify ingress를 수정하지 않는 병렬 Source Adapter.
#
# Datadog에서 별도 Shadow webhook으로 선택한 합성 monitor만 이 Function URL에 보낸다.
# 기존 webhook은 그대로 Worker/Dify를 호출하고, 이 Lambda는 agent.trigger.v1 Signal
# Queue까지만 보낸다. 따라서 신규 경로 장애가 기존 알림 분석 경로를 막지 않는다.
#
# 기본값은 execution false, monitor allowlist empty, cutover 2100-01-01이다. 활성화
# Shadow에서도 합성 monitor 하나만 허용한다. Correlator와 Generic Worker는 별도
# gate이므로 이 Adapter를 켜는 것만으로 Dify를 호출할 수 없다.

locals {
  datadog_source_adapter_name = "${local.name}-datadog-source-adapter"
}

resource "aws_iam_role" "datadog_source_adapter" {
  name               = "${local.name}-datadog-source-adapter-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "datadog_source_adapter_basic" {
  role       = aws_iam_role.datadog_source_adapter.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "datadog_source_adapter" {
  statement {
    sid       = "ReadExistingO2WebhookSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [data.aws_secretsmanager_secret.alert_relay_o2.arn]
  }

  statement {
    sid       = "SendAgentTrigger"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.agent_entry.arn]
  }
}

resource "aws_iam_role_policy" "datadog_source_adapter" {
  name   = "${local.name}-datadog-source-adapter"
  role   = aws_iam_role.datadog_source_adapter.id
  policy = data.aws_iam_policy_document.datadog_source_adapter.json
}

resource "aws_cloudwatch_log_group" "datadog_source_adapter" {
  name              = "/aws/lambda/${local.datadog_source_adapter_name}"
  retention_in_days = 7
}

data "archive_file" "datadog_source_adapter" {
  type        = "zip"
  output_path = "${path.module}/lambda/datadog_source_adapter.zip"

  source {
    content  = file("${path.module}/lambda/datadog_source_adapter.py")
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "datadog_source_adapter" {
  function_name = local.datadog_source_adapter_name
  role          = aws_iam_role.datadog_source_adapter.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]

  # Secret read와 SQS SendMessage만 수행한다. VPC/Dify/Bedrock 권한은 없다.
  timeout     = 10
  memory_size = 128

  filename         = data.archive_file.datadog_source_adapter.output_path
  source_code_hash = data.archive_file.datadog_source_adapter.output_base64sha256

  environment {
    variables = {
      DATADOG_SOURCE_ADAPTER_EXECUTION_ENABLED   = tostring(var.datadog_source_adapter_execution_enabled)
      DATADOG_SOURCE_ADAPTER_ALLOWED_MONITOR_IDS = join(",", sort(tolist(var.datadog_source_adapter_allowed_monitor_ids)))
      DATADOG_SOURCE_ADAPTER_NOT_BEFORE_EPOCH    = tostring(var.datadog_source_adapter_not_before_epoch)
      INCIDENT_SHADOW_MODE                       = tostring(var.incident_shadow_mode)
      DATADOG_SOURCE_ADAPTER_SECRET_NAME         = var.alert_secret_name_o2
      AGENT_TRIGGER_QUEUE_URL                    = aws_sqs_queue.agent_entry.url
    }
  }

  depends_on = [
    aws_iam_role_policy.datadog_source_adapter,
    aws_iam_role_policy_attachment.datadog_source_adapter_basic,
    aws_cloudwatch_log_group.datadog_source_adapter,
  ]

  lifecycle {
    precondition {
      condition = (
        (!var.datadog_source_adapter_execution_enabled &&
          length(var.datadog_source_adapter_allowed_monitor_ids) == 0 &&
        var.datadog_source_adapter_not_before_epoch == 4102444800) ||
        (var.datadog_source_adapter_execution_enabled &&
          ((var.incident_shadow_mode && length(var.datadog_source_adapter_allowed_monitor_ids) == 1) ||
          (!var.incident_shadow_mode && var.incident_operational_handoff_approved && length(var.datadog_source_adapter_allowed_monitor_ids) >= 1)) &&
        var.datadog_source_adapter_not_before_epoch < 4102444800)
      )
      error_message = "Datadog Source Adapter는 disabled+empty+2100 cutoff 또는 enabled+합성 monitor ID 1개+명시 cutoff만 허용한다."
    }
  }
}

resource "aws_lambda_function_url" "datadog_source_adapter" {
  function_name = aws_lambda_function.datadog_source_adapter.function_name

  # Datadog은 SigV4를 지원하지 않는다. 기존 O2 webhook과 같은 Secrets Manager의
  # x-dd-secret을 코드에서 constant-time 비교하며 URL 자체도 민감정보로 취급한다.
  authorization_type = "NONE"
}

# Function URL handler는 계약/인증/SQS 오류를 HTTP 코드로 반환하므로 AWS/Lambda
# Errors에는 잡히지 않는다. content-free FAILED 로그만 metric으로 바꿔 경보한다.
resource "aws_cloudwatch_log_metric_filter" "datadog_source_adapter_failures" {
  name           = "${local.name}-datadog-source-adapter-failures"
  log_group_name = aws_cloudwatch_log_group.datadog_source_adapter.name
  pattern        = "\"datadog_source_adapter\" \"status=FAILED\""

  metric_transformation {
    name          = "DatadogSourceAdapterFailures"
    namespace     = "O2/AgentEntry"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "datadog_source_adapter_failures" {
  alarm_name          = "${local.name}-datadog-source-adapter-failures"
  alarm_description   = "Datadog Source Adapter가 인증·계약·Signal Queue 전송 중 실패했다. payload는 로그에 없다."
  namespace           = "O2/AgentEntry"
  metric_name         = "DatadogSourceAdapterFailures"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.incident_alarm.arn]
  ok_actions    = [aws_sns_topic.incident_alarm.arn]
}
