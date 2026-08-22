# Datadog 알림을 Dify 워크플로로 중계한다. 함수 둘로 나눠 있다.
#
#   Ingress (VPC 밖)  받아서 Worker 를 비동기로 깨우고 즉시 200
#   Worker  (VPC 안)  Dify 를 부른다. 실패하면 예외를 던져 재시도·DLQ 로 보낸다
#
# 왜 나눴나. 동기 한 덩어리였을 때는 Worker 동시성이 차면 Datadog 이 429 를
# 받았고, **Datadog 은 429 를 재시도하지 않는다** — 그 알림은 영구 소실이었다.
# 비동기 호출로 바꾸면 동시성 초과가 소실이 아니라 지연이 된다.
#
# SQS 를 세우지 않은 이유는 Lambda 비동기 호출이 대기열·재시도·DLQ 를 이미
# 제공하기 때문이다. 큐 깊이를 정밀히 보거나 배치·순서 보장이 필요해지면
# 그때 중간에 SQS 를 끼운다. 분리가 되어 있어 갈아타기 쉽다.

locals {
  # ★ 이름이 ${project}-${environment}-* 규칙을 따르지 않는다. 의도한 것이다.
  #   이 함수의 Function URL 이 Datadog webhook 에 이미 등록되어 있다.
  #   이름을 바꾸면 함수가 교체되면서 URL 도 바뀌고 Datadog 쪽을 손으로
  #   다시 맞춰야 한다. 얻는 것이 이름 통일 하나뿐이라 그대로 둔다.
  alert_ingress_name = "datadog-to-dify"
  alert_worker_name  = "datadog-to-dify-worker"
}

# ── 공통: 시크릿 ─────────────────────────────────────────────────
#
# SecretString 을 읽지 않는다 — ARN 만 필요하다. data source 로 값을 읽으면
# 결과가 state 에 평문으로 남는다 (06-datastream/warm-path.tf 와 같은 이유).

data "aws_secretsmanager_secret" "alert_relay" {
  name = var.alert_secret_name
}

data "aws_iam_policy_document" "alert_secret_read" {
  statement {
    sid       = "ReadAlertRelaySecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [data.aws_secretsmanager_secret.alert_relay.arn]
  }
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# ── Ingress ──────────────────────────────────────────────────────

resource "aws_iam_role" "alert_relay" {
  name               = "${local.name}-alert-relay-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "alert_relay_basic" {
  role       = aws_iam_role.alert_relay.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "alert_relay" {
  source_policy_documents = [data.aws_iam_policy_document.alert_secret_read.json]

  statement {
    sid       = "InvokeWorker"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.alert_worker.arn]
  }

  # 복구 알림의 시각만 남긴다 (MTTR 재료). incidents/ 는 Worker 것이므로
  # 접두사를 갈라 준다 — Ingress 가 분석 결과를 덮어쓸 경로를 만들지 않는다.
  statement {
    sid       = "WriteResolutions"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.history.arn}/resolutions/*"]
  }
}

resource "aws_iam_role_policy" "alert_relay" {
  name   = "${local.name}-alert-relay"
  role   = aws_iam_role.alert_relay.id
  policy = data.aws_iam_policy_document.alert_relay.json
}

resource "aws_cloudwatch_log_group" "alert_relay" {
  name              = "/aws/lambda/${local.alert_ingress_name}"
  retention_in_days = 7
}

data "archive_file" "alert_relay" {
  type        = "zip"
  output_path = "${path.module}/lambda/ingress.zip"

  source {
    content  = file("${path.module}/lambda/ingress.py")
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "alert_relay" {
  function_name = local.alert_ingress_name
  role          = aws_iam_role.alert_relay.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]

  # Dify 를 기다리지 않는다. Secrets Manager 한 번과 invoke 한 번이 전부다.
  timeout     = 10
  memory_size = 128

  filename         = data.archive_file.alert_relay.output_path
  source_code_hash = data.archive_file.alert_relay.output_base64sha256

  # ★ 예약 동시성을 두지 않는다. 여기서 막으면 문 앞에서 알림을 버리는 것이라
  #   "알림을 잃지 않는다" 는 목표와 정반대다. 상한은 Worker 에만 건다.
  #
  # ★ VPC 에 넣지 않는다. ENI 를 만들지 않아 콜드스타트가 1초대에서
  #   100밀리초대로 떨어진다. Dify 를 부르는 것은 Worker 뿐이다.

  environment {
    variables = {
      ALERT_SECRET_NAME = var.alert_secret_name
      WORKER_FUNCTION   = aws_lambda_function.alert_worker.function_name
      HISTORY_BUCKET    = aws_s3_bucket.history.bucket
    }
  }

  depends_on = [
    aws_iam_role_policy.alert_relay,
    aws_cloudwatch_log_group.alert_relay,
  ]
}

resource "aws_lambda_function_url" "alert_relay" {
  function_name = aws_lambda_function.alert_relay.function_name

  # ★ NONE 은 "URL 을 아는 누구나 POST 할 수 있다" 는 뜻이다.
  #   인증은 함수 코드의 x-dd-secret 헤더 비교가 전부다.
  #   AWS_IAM 으로 바꿀 수 없다 — Datadog 은 SigV4 서명을 못 한다.
  authorization_type = "NONE"
}

# ── Worker ───────────────────────────────────────────────────────

resource "aws_iam_role" "alert_worker" {
  name               = "${local.name}-alert-worker-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "alert_worker_basic" {
  role       = aws_iam_role.alert_worker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ★ 이게 없으면 VPC 설정 저장 자체가 실패한다 — T-004.
#     The provided execution role does not have permissions to
#     call CreateNetworkInterface on EC2
resource "aws_iam_role_policy_attachment" "alert_worker_vpc" {
  role       = aws_iam_role.alert_worker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "alert_worker" {
  source_policy_documents = [data.aws_iam_policy_document.alert_secret_read.json]

  # 재시도를 다 쓴 이벤트를 DLQ 로 보내는 것은 Lambda 서비스가 아니라
  # 함수의 실행 역할 권한으로 이뤄진다. 빠뜨리면 DLQ 가 조용히 빈 채로 남는다.
  statement {
    sid       = "SendToDlq"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.alert_dlq.arn]
  }

  # 알림 텍스트를 벡터로 바꾼다. 모델 하나로 좁힌다 — iam.tf 의 Dify 인스턴스
  # 역할은 `*` 로 열려 있지만 그건 사람이 콘솔에서 모델을 고르기 때문이고,
  # 여기는 코드가 부르는 모델이 하나로 정해져 있다.
  #
  # ★ 계정 번호가 없는 ARN 이다. 파운데이션 모델은 AWS 소유라 계정 자리가 빈다.
  statement {
    sid       = "EmbedAlertText"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel"]
    resources = ["arn:aws:bedrock:${var.region}::foundation-model/${local.embed_model_id}"]
  }

  # ★ QueryVectors 하나로는 안 된다. GetVectors 도 있어야 한다 — 실측:
  #
  #     AccessDeniedException ... is not authorized to perform:
  #     s3vectors:GetVectors on resource: .../index/incidents
  #
  #   `returnMetadata = true` 로 부르면 AWS 가 메타데이터를 돌려주면서
  #   GetVectors 를 함께 검사한다. API 이름만 보고 권한을 맞추면 걸린다
  #   (iam.tf 의 InvokeFunctionUrl/InvokeFunction 과 같은 모양이다).
  #
  #   더 나쁜 것은 **이 실패가 알림 분석을 멈추지 않는다는 점이다.** 검색만
  #   조용히 비고 워크플로는 succeeded 로 끝난다. 로그를 봐야 보인다.
  statement {
    sid    = "SearchAndStoreVectors"
    effect = "Allow"
    actions = [
      "s3vectors:QueryVectors",
      "s3vectors:GetVectors",
      "s3vectors:PutVectors",
    ]
    resources = [aws_s3vectors_index.incidents.index_arn]
  }

  # 읽기가 필요한 이유는 복구 적재다. Recovered 를 받으면 저장해 둔 원본을
  # 읽어 outcome 을 채우고 다시 쓴다 (worker.py `_handle_recovery`).
  statement {
    sid    = "ReadWriteIncidents"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
    ]
    resources = ["${aws_s3_bucket.history.arn}/incidents/*"]
  }
}

resource "aws_iam_role_policy" "alert_worker" {
  name   = "${local.name}-alert-worker"
  role   = aws_iam_role.alert_worker.id
  policy = data.aws_iam_policy_document.alert_worker.json
}

# Ingress 는 VPC 밖이므로 이 보안그룹은 Worker 만 쓴다.
# Dify 인바운드 규칙(security_groups.tf)이 이걸 참조한다.
#
# ★ name 과 description 은 ForceNew 다. 문구를 다듬으려 건드리면 SG 가 교체되고,
#   Dify 인바운드 규칙이 이걸 참조하고 있어 교체가 꼬인다. 그대로 둔다.
resource "aws_security_group" "alert_relay" {
  name        = "${local.name}-alert-relay"
  description = "datadog-to-dify Lambda. Egress to Dify only"
  vpc_id      = local.vpc_id

  tags = {
    Name = "${local.name}-alert-relay"
  }
}

# ★ SG 이름의 "Egress to Dify only" 는 낡은 문구다. 규칙은 처음부터 전체
#   허용이었고(Secrets Manager 가 NAT 로 나가야 했다), 이제 Bedrock·S3·
#   S3 Vectors 도 같은 길로 나간다. **문구를 고치지 않는다** — 이 규칙의
#   description 도 ForceNew 라, 정확한 설명 하나를 얻자고 규칙을 교체하는
#   동안 이그레스가 잠깐 사라진다. 그 사이에 든 알림은 Dify 를 못 부른다.
resource "aws_vpc_security_group_egress_rule" "alert_relay_all" {
  security_group_id = aws_security_group.alert_relay.id
  description       = "Dify call, Secrets Manager"

  cidr_ipv4   = "0.0.0.0/0"
  ip_protocol = "-1"
}

resource "aws_cloudwatch_log_group" "alert_worker" {
  name              = "/aws/lambda/${local.alert_worker_name}"
  retention_in_days = 7
}

data "archive_file" "alert_worker" {
  type        = "zip"
  output_path = "${path.module}/lambda/worker.zip"

  source {
    content  = file("${path.module}/lambda/worker.py")
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "alert_worker" {
  function_name = local.alert_worker_name
  role          = aws_iam_role.alert_worker.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]

  # ★ 기본값 3초로는 무조건 실패한다. Dify 워크플로가 blocking 으로 끝날
  #   때까지 기다리기 때문이다. 실측 2.5초이고 55초 타임아웃으로 호출한다.
  timeout     = 60
  memory_size = 128

  filename         = data.archive_file.alert_worker.output_path
  source_code_hash = data.archive_file.alert_worker.output_base64sha256

  # ★ 이 값이 파이프라인의 처리량 상한이다. Dify 가 감당하는 동시 실행 수에
  #   맞춘다 — 서버가 아니라 Dify 워커 개수가 상한이므로 부하를 걸어 재서 정한다.
  #   초과분은 버려지지 않고 Lambda 내부 대기열에서 기다린다.
  reserved_concurrent_executions = var.alert_relay_max_concurrency

  vpc_config {
    # Dify 와 같은 서브넷. 사설 IP 로 직접 호출하므로 라우팅이 필요 없고,
    # Secrets Manager 는 이 서브넷의 NAT 로 나간다.
    subnet_ids         = [local.subnet_id]
    security_group_ids = [aws_security_group.alert_relay.id]
  }

  environment {
    variables = {
      # ★ 사설 IP 를 하드코딩하지 않는다. 손으로 넣었다가 예시 IP 가 그대로
      #   남아 연결 타임아웃을 디버깅한 적이 있다 — T-005. 포트는 80 이다.
      DIFY_URL          = "http://${aws_instance.dify.private_ip}/v1/workflows/run"
      ALERT_SECRET_NAME = var.alert_secret_name

      HISTORY_BUCKET = aws_s3_bucket.history.bucket
      VECTOR_BUCKET  = aws_s3vectors_vector_bucket.history.vector_bucket_name
      VECTOR_INDEX   = aws_s3vectors_index.incidents.index_name
      EMBED_MODEL_ID = local.embed_model_id
    }
  }

  depends_on = [
    aws_iam_role_policy.alert_worker,
    aws_iam_role_policy_attachment.alert_worker_vpc,
    aws_cloudwatch_log_group.alert_worker,
  ]
}

# ── 재시도와 DLQ ─────────────────────────────────────────────────

resource "aws_sqs_queue" "alert_dlq" {
  name = "${local.name}-alert-dlq"

  # 회고 때 증거로 쓴다. 저장 비용은 사실상 0이라 짧게 할 이유가 없다.
  message_retention_seconds = 1209600 # 14일
  sqs_managed_sse_enabled   = true
}

resource "aws_lambda_function_event_invoke_config" "alert_worker" {
  function_name = aws_lambda_function.alert_worker.function_name

  # 최초 1회 + 재시도 2회 = 총 3회. 간격은 약 1분 → 약 2분이라
  # DLQ 도달까지 약 3분이다. SQS 를 썼을 때(가시성 타임아웃 × 2 = 12분)보다
  # 빠르므로 감지 관점에서 유리하다.
  maximum_retry_attempts = 2

  destination_config {
    # ★ DLQ 가 없으면 재시도를 다 쓴 이벤트는 그냥 사라진다.
    #   내구성을 넣었다고 믿는데 실제로는 안 넣은 상태가 가장 나쁘다.
    on_failure {
      destination = aws_sqs_queue.alert_dlq.arn
    }
  }
}

# ── 알람 ─────────────────────────────────────────────────────────
#
# DLQ 는 마지막 그물이지 1차 감지 수단이 아니다. 도달까지 3분이 걸리고,
# 그 시점엔 이미 세 번 실패한 뒤다. 첫 실패에 우는 알람이 따로 필요하다.

resource "aws_sns_topic" "alert_relay_alarm" {
  name = "${local.name}-alert-relay-alarm"
}

# ★ 구독은 코드로 만들지 않는다. 이메일 구독은 수신자가 메일에서 확인을
#   눌러야 활성화되므로 apply 만으로는 완성되지 않는다. 만들어두고 안 눌러
#   놓으면 "알람이 있다" 고 믿는 상태가 된다 — 사람이 직접 붙인다:
#
#     aws sns subscribe --topic-arn <위 토픽> --protocol email \
#       --notification-endpoint <주소> --region ap-northeast-2

# 1차. 첫 실패에 운다. 이 시점엔 이벤트가 아직 대기열에 살아 있어서
# 원인을 고치면 재시도가 알아서 처리한다 — DLQ 까지 갈 일이 없어진다.
resource "aws_cloudwatch_metric_alarm" "alert_worker_errors" {
  alarm_name          = "${local.name}-alert-worker-errors"
  alarm_description   = "Worker 가 실패했다. 대기열에 이벤트가 살아 있는 동안 원인을 고치면 재시도로 처리된다."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.alert_worker.function_name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alert_relay_alarm.arn]
  ok_actions    = [aws_sns_topic.alert_relay_alarm.arn]
}

# 2차. 대기열이 밀린다 = Dify 가 도착 속도를 못 따라간다.
# 이 지표는 비동기 호출이 실제로 쌓이기 시작해야 나타난다.
resource "aws_cloudwatch_metric_alarm" "alert_worker_backlog" {
  alarm_name          = "${local.name}-alert-worker-backlog"
  alarm_description   = "대기열의 가장 오래된 이벤트가 2분을 넘겼다. Worker 동시성을 올리거나 Dify 를 키운다."
  namespace           = "AWS/Lambda"
  metric_name         = "AsyncEventAge"
  dimensions          = { FunctionName = aws_lambda_function.alert_worker.function_name }
  extended_statistic  = "p99"
  period              = 60
  evaluation_periods  = 2
  threshold           = 120000 # 밀리초
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alert_relay_alarm.arn]
}

# 3차. 확정 소실. 원인을 고친 뒤 재투입할지 판단한다.
resource "aws_cloudwatch_metric_alarm" "alert_dlq_not_empty" {
  alarm_name          = "${local.name}-alert-dlq-not-empty"
  alarm_description   = "세 번 실패한 알림이 DLQ 에 있다. 내용을 읽고 원인을 고친다. 1시간 이내면 재투입, 하루가 지났으면 읽고 비운다."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.alert_dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alert_relay_alarm.arn]
}
