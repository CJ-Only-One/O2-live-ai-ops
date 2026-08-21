# Datadog 알림을 O2 Dify 앱으로 중계하는 두 번째 파이프라인.
#
# lambda.tf 의 alert_relay/alert_worker(datadog-to-dify, alert-triage 앱 전용)와
# 완전히 분리된 병렬 경로다. 같은 Datadog 계정에서 서로 다른 Dify 앱(O2)으로
# 알림을 보내야 해서 만들었다 — 시크릿을 공유하면 한쪽 앱의 API 키를 바꿀
# 때마다 다른 쪽이 깨진다 (콘솔로 먼저 확인한 실제 증상. docs/troubleshooting.md
# 에 T 번호로 남길 것).
#
# 구조는 lambda.tf 와 동일하다(Ingress/Worker 분리, DLQ, 알람 3종). 코드
# (lambda/ingress.py, lambda/worker.py)는 그대로 재사용한다 — 둘 다 환경변수
# (ALERT_SECRET_NAME 등)로만 동작해서 O2 전용으로 고칠 이유가 없다. archive_file
# 데이터 소스도 lambda.tf 것을 그대로 참조한다(같은 zip, 같은 해시).
#
# 아래 리소스들은 alert-triage 쪽과 공유한다 — 별도로 안 만든다:
#   - aws_security_group.alert_relay  (Worker egress, "Dify 호출용" 이라 앱과 무관)
#   - aws_sns_topic.alert_relay_alarm (같은 사람이 알람을 받으면 되고, 이메일
#     구독 확인 절차를 또 만들 이유가 없다)
#
# ★ 인시던트 이력(history.tf)은 이쪽에 **일부러 안 붙였다.**
#   코드는 같은 zip 이라 이미 들어 있고, HISTORY_BUCKET 등 환경변수가 없으면
#   그 기능만 꺼진 채 중계는 정상으로 돈다 (lambda/worker.py 상단 주석).
#
#   켜기 전에 먼저 풀어야 할 것: 두 파이프라인이 같은 Datadog 모니터를 받으면
#   **cycle_key 가 같아서 서로의 인시던트를 덮어쓴다.** 환경변수만 복사해
#   붙이면 조용히 데이터가 사라진다. S3 키와 벡터 키에 파이프라인 구분을
#   먼저 넣고, 그 다음에 IAM(bedrock·s3vectors·s3)을 준다.

locals {
  alert_ingress_name_o2 = "o2-dify-ingress"
  alert_worker_name_o2  = "o2-dify-worker"
}

# ── Ingress ──────────────────────────────────────────────────────

resource "aws_iam_role" "alert_relay_o2" {
  name               = "${local.name}-alert-relay-o2-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "alert_relay_o2_basic" {
  role       = aws_iam_role.alert_relay_o2.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_secretsmanager_secret" "alert_relay_o2" {
  name = var.alert_secret_name_o2
}

data "aws_iam_policy_document" "alert_secret_read_o2" {
  statement {
    sid       = "ReadAlertRelaySecretO2"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [data.aws_secretsmanager_secret.alert_relay_o2.arn]
  }
}

data "aws_iam_policy_document" "alert_relay_o2" {
  source_policy_documents = [data.aws_iam_policy_document.alert_secret_read_o2.json]

  statement {
    sid       = "InvokeWorkerO2"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.alert_worker_o2.arn]
  }
}

resource "aws_iam_role_policy" "alert_relay_o2" {
  name   = "${local.name}-alert-relay-o2"
  role   = aws_iam_role.alert_relay_o2.id
  policy = data.aws_iam_policy_document.alert_relay_o2.json
}

resource "aws_cloudwatch_log_group" "alert_relay_o2" {
  name              = "/aws/lambda/${local.alert_ingress_name_o2}"
  retention_in_days = 7
}

resource "aws_lambda_function" "alert_relay_o2" {
  function_name = local.alert_ingress_name_o2
  role          = aws_iam_role.alert_relay_o2.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]

  # Dify 를 기다리지 않는다. Secrets Manager 한 번과 invoke 한 번이 전부다.
  timeout     = 10
  memory_size = 128

  filename         = data.archive_file.alert_relay.output_path
  source_code_hash = data.archive_file.alert_relay.output_base64sha256

  # 예약 동시성을 두지 않는다 — alert_relay(원본)와 같은 이유. 상한은 Worker 에만.
  # VPC 에도 넣지 않는다. Dify 를 부르는 것은 Worker 뿐이다.

  environment {
    variables = {
      ALERT_SECRET_NAME = var.alert_secret_name_o2
      WORKER_FUNCTION   = aws_lambda_function.alert_worker_o2.function_name
    }
  }

  depends_on = [
    aws_iam_role_policy.alert_relay_o2,
    aws_cloudwatch_log_group.alert_relay_o2,
  ]
}

resource "aws_lambda_function_url" "alert_relay_o2" {
  function_name = aws_lambda_function.alert_relay_o2.function_name

  # NONE = 인증은 함수 코드의 x-dd-secret 헤더 비교가 전부다. Datadog 이
  # SigV4 서명을 못 하므로 AWS_IAM 으로 바꿀 수 없다 (원본과 같은 이유).
  authorization_type = "NONE"
}

# ── Worker ───────────────────────────────────────────────────────

resource "aws_iam_role" "alert_worker_o2" {
  name               = "${local.name}-alert-worker-o2-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "alert_worker_o2_basic" {
  role       = aws_iam_role.alert_worker_o2.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# 없으면 VPC 설정 저장 자체가 실패한다 (T-004 와 같은 원인).
resource "aws_iam_role_policy_attachment" "alert_worker_o2_vpc" {
  role       = aws_iam_role.alert_worker_o2.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "alert_worker_o2" {
  source_policy_documents = [data.aws_iam_policy_document.alert_secret_read_o2.json]

  statement {
    sid       = "SendToDlqO2"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.alert_dlq_o2.arn]
  }
}

resource "aws_iam_role_policy" "alert_worker_o2" {
  name   = "${local.name}-alert-worker-o2"
  role   = aws_iam_role.alert_worker_o2.id
  policy = data.aws_iam_policy_document.alert_worker_o2.json
}

resource "aws_cloudwatch_log_group" "alert_worker_o2" {
  name              = "/aws/lambda/${local.alert_worker_name_o2}"
  retention_in_days = 7
}

resource "aws_lambda_function" "alert_worker_o2" {
  function_name = local.alert_worker_name_o2
  role          = aws_iam_role.alert_worker_o2.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]

  # 기본값 3초로는 무조건 실패한다. Dify 워크플로가 blocking 으로 끝날 때까지
  # 기다리기 때문이다. 55초 타임아웃으로 호출하므로 함수는 그보다 커야 한다.
  timeout     = 60
  memory_size = 128

  filename         = data.archive_file.alert_worker.output_path
  source_code_hash = data.archive_file.alert_worker.output_base64sha256

  # 이 값이 O2 파이프라인의 처리량 상한이다. 원본과 같은 변수를 공유한다 —
  # 두 앱이 같은 Dify 인스턴스를 쓰므로 합쳐서 Dify 가 감당하는 수에 맞춘다.
  reserved_concurrent_executions = var.alert_relay_max_concurrency

  vpc_config {
    # 원본 Worker 와 같은 서브넷/보안그룹을 쓴다. 같은 Dify 를 사설 IP 로
    # 부르므로 새로 만들 이유가 없다.
    subnet_ids         = [local.subnet_id]
    security_group_ids = [aws_security_group.alert_relay.id]
  }

  environment {
    variables = {
      DIFY_URL          = "http://${aws_instance.dify.private_ip}/v1/workflows/run"
      ALERT_SECRET_NAME = var.alert_secret_name_o2
    }
  }

  depends_on = [
    aws_iam_role_policy.alert_worker_o2,
    aws_iam_role_policy_attachment.alert_worker_o2_vpc,
    aws_cloudwatch_log_group.alert_worker_o2,
  ]
}

# ── 재시도와 DLQ ─────────────────────────────────────────────────

resource "aws_sqs_queue" "alert_dlq_o2" {
  name = "${local.name}-alert-dlq-o2"

  message_retention_seconds = 1209600 # 14일. 회고 때 증거로 쓴다.
  sqs_managed_sse_enabled   = true
}

resource "aws_lambda_function_event_invoke_config" "alert_worker_o2" {
  function_name = aws_lambda_function.alert_worker_o2.function_name

  # 최초 1회 + 재시도 2회 = 총 3회. 원본과 같은 재시도 정책.
  maximum_retry_attempts = 2

  destination_config {
    on_failure {
      destination = aws_sqs_queue.alert_dlq_o2.arn
    }
  }
}

# ── 알람 ─────────────────────────────────────────────────────────
# 토픽(aws_sns_topic.alert_relay_alarm)은 원본 것을 그대로 쓴다. 이미 구독을
# 걸어둔 사람이 있으면 O2 실패도 같은 채널로 받는 게 맞다.

resource "aws_cloudwatch_metric_alarm" "alert_worker_o2_errors" {
  alarm_name          = "${local.name}-alert-worker-o2-errors"
  alarm_description   = "O2 Worker 가 실패했다. 대기열에 이벤트가 살아 있는 동안 원인을 고치면 재시도로 처리된다."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.alert_worker_o2.function_name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alert_relay_alarm.arn]
  ok_actions    = [aws_sns_topic.alert_relay_alarm.arn]
}

resource "aws_cloudwatch_metric_alarm" "alert_worker_o2_backlog" {
  alarm_name          = "${local.name}-alert-worker-o2-backlog"
  alarm_description   = "O2 대기열의 가장 오래된 이벤트가 2분을 넘겼다. Worker 동시성을 올리거나 Dify 를 키운다."
  namespace           = "AWS/Lambda"
  metric_name         = "AsyncEventAge"
  dimensions          = { FunctionName = aws_lambda_function.alert_worker_o2.function_name }
  extended_statistic  = "p99"
  period              = 60
  evaluation_periods  = 2
  threshold           = 120000 # 밀리초
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alert_relay_alarm.arn]
}

resource "aws_cloudwatch_metric_alarm" "alert_dlq_o2_not_empty" {
  alarm_name          = "${local.name}-alert-dlq-o2-not-empty"
  alarm_description   = "세 번 실패한 O2 알림이 DLQ 에 있다. 내용을 읽고 원인을 고친다."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.alert_dlq_o2.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alert_relay_alarm.arn]
}
