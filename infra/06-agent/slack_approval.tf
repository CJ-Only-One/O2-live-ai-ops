# Slack 승인 요청(승인/거부/재고 버튼)을 중계하는 백엔드.
#
# Dify 의 "17. Slack Approval Request" 노드는 HTTP 요청 노드라서 응답이
# 올 때까지 최대 600초 동안 그 자리에서 기다리는 것밖에 못 한다. 근데
# Slack 버튼 클릭은 Slack 이 나중에 별도로 콜백을 쏴주는 방식이라, 이
# 둘을 이어줄 중계가 필요하다 — Lambda 두 개 + DynamoDB 테이블 하나로 푼다.
#
#   approval_request  Dify 가 부른다. Slack 에 버튼 메시지를 보내고,
#                      DynamoDB 에 결정이 기록될 때까지 폴링하다가 돌려준다.
#   interactivity      Slack 이 버튼 클릭 콜백으로 부른다. 결정을 DynamoDB 에
#                      기록하고 원본 메시지를 갱신한다. 3초 안에 응답해야 한다.
#
# 코드: lambda/slack_approval_request.py, lambda/slack_interactivity.py
# lambda_assume(lambda.tf 에 정의됨)를 그대로 재사용한다.

locals {
  slack_approval_table_name = "${local.name}-slack-approvals"
}

# ── 공통: 시크릿 ─────────────────────────────────────────────────
#
# 값이 아니라 이름만 참조한다 (lambda.tf 의 alert_relay 시크릿과 같은 이유 —
# SecretString 을 읽으면 state 에 평문으로 남는다).

data "aws_secretsmanager_secret" "slack_approval" {
  name = var.slack_approval_secret_name
}

data "aws_iam_policy_document" "slack_approval_secret_read" {
  statement {
    sid       = "ReadSlackApprovalSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [data.aws_secretsmanager_secret.slack_approval.arn]
  }
}

# ── DynamoDB: 승인 상태 저장소 ─────────────────────────────────────
#
# 두 Lambda 는 서로 다른 시점에, 서로 다른 실행 환경(=서로 다른 invocation)
# 에서 호출된다 — 메모리를 공유할 방법이 없으니 결정을 어딘가에 남겨야
# 폴링이 그 값을 읽을 수 있다. 트래픽이 인시던트당 한 번뿐이라
# PAY_PER_REQUEST 로 충분하다(용량 계획할 게 없다).
resource "aws_dynamodb_table" "slack_approvals" {
  name         = local.slack_approval_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "approval_id"

  attribute {
    name = "approval_id"
    type = "S"
  }

  # 7일 뒤 자동 삭제 (slack_approval_request.py 가 심는 ttl 필드, 초 단위 epoch).
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Name = local.slack_approval_table_name
  }
}

data "aws_iam_policy_document" "slack_approval_table_access" {
  statement {
    sid    = "SlackApprovalTableAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
    ]
    resources = [aws_dynamodb_table.slack_approvals.arn]
  }
}

# ── approval_request: Dify 가 부르는 쪽 ─────────────────────────────

resource "aws_iam_role" "slack_approval_request" {
  name               = "${local.name}-slack-approval-request-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "slack_approval_request_basic" {
  role       = aws_iam_role.slack_approval_request.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "slack_approval_request" {
  source_policy_documents = [
    data.aws_iam_policy_document.slack_approval_secret_read.json,
    data.aws_iam_policy_document.slack_approval_table_access.json,
  ]
}

resource "aws_iam_role_policy" "slack_approval_request" {
  name   = "${local.name}-slack-approval-request"
  role   = aws_iam_role.slack_approval_request.id
  policy = data.aws_iam_policy_document.slack_approval_request.json
}

resource "aws_cloudwatch_log_group" "slack_approval_request" {
  name              = "/aws/lambda/${local.name}-slack-approval-request"
  retention_in_days = 7
}

data "archive_file" "slack_approval_request" {
  type        = "zip"
  output_path = "${path.module}/lambda/slack_approval_request.zip"

  source {
    content  = file("${path.module}/lambda/slack_approval_request.py")
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "slack_approval_request" {
  function_name = "${local.name}-slack-approval-request"
  role          = aws_iam_role.slack_approval_request.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]

  # Dify 노드 타임아웃(600초)보다 넉넉하게. 코드 자체는 580초에서 스스로 끊는다.
  timeout     = 600
  memory_size = 128

  filename         = data.archive_file.slack_approval_request.output_path
  source_code_hash = data.archive_file.slack_approval_request.output_base64sha256

  # ★ VPC 밖에 둔다. Slack API·DynamoDB·Secrets Manager 모두 공개 엔드포인트라
  #   ENI 가 필요 없다. Dify 는 이 함수의 호출자일 뿐이라 같은 서브넷일 필요도
  #   없다 (lambda.tf 의 alert_relay 와 같은 이유).

  environment {
    variables = {
      APPROVALS_TABLE   = aws_dynamodb_table.slack_approvals.name
      SLACK_SECRET_NAME = var.slack_approval_secret_name
    }
  }

  depends_on = [
    aws_iam_role_policy.slack_approval_request,
    aws_cloudwatch_log_group.slack_approval_request,
  ]
}

resource "aws_lambda_function_url" "slack_approval_request" {
  function_name = aws_lambda_function.slack_approval_request.function_name

  # NONE — 인증은 함수 코드의 X-API-Key 헤더 비교가 전부다. Dify 의 HTTP
  # 요청 노드는 SigV4 서명을 못 하므로 AWS_IAM 으로 바꿀 수 없다
  # (alert_relay 와 같은 이유).
  authorization_type = "NONE"
}

# ── interactivity: Slack 이 버튼 클릭 콜백으로 부르는 쪽 ────────────

resource "aws_iam_role" "slack_interactivity" {
  name               = "${local.name}-slack-interactivity-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "slack_interactivity_basic" {
  role       = aws_iam_role.slack_interactivity.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "slack_interactivity" {
  source_policy_documents = [
    data.aws_iam_policy_document.slack_approval_secret_read.json,
    data.aws_iam_policy_document.slack_approval_table_access.json,
  ]
}

resource "aws_iam_role_policy" "slack_interactivity" {
  name   = "${local.name}-slack-interactivity"
  role   = aws_iam_role.slack_interactivity.id
  policy = data.aws_iam_policy_document.slack_interactivity.json
}

resource "aws_cloudwatch_log_group" "slack_interactivity" {
  name              = "/aws/lambda/${local.name}-slack-interactivity"
  retention_in_days = 7
}

data "archive_file" "slack_interactivity" {
  type        = "zip"
  output_path = "${path.module}/lambda/slack_interactivity.zip"

  source {
    content  = file("${path.module}/lambda/slack_interactivity.py")
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "slack_interactivity" {
  function_name = "${local.name}-slack-interactivity"
  role          = aws_iam_role.slack_interactivity.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]

  # Slack 은 3초 안에 응답을 기대한다. 실측으로는 수백 ms 안에 끝나지만 여유를 둔다.
  timeout     = 10
  memory_size = 128

  filename         = data.archive_file.slack_interactivity.output_path
  source_code_hash = data.archive_file.slack_interactivity.output_base64sha256

  environment {
    variables = {
      APPROVALS_TABLE   = aws_dynamodb_table.slack_approvals.name
      SLACK_SECRET_NAME = var.slack_approval_secret_name
    }
  }

  depends_on = [
    aws_iam_role_policy.slack_interactivity,
    aws_cloudwatch_log_group.slack_interactivity,
  ]
}

resource "aws_lambda_function_url" "slack_interactivity" {
  function_name = aws_lambda_function.slack_interactivity.function_name

  # NONE — 인증은 함수 코드 안의 Slack 서명 검증(X-Slack-Signature)이 전부다.
  # 이 주소를 Slack App 의 Interactivity Request URL 로 등록한다.
  authorization_type = "NONE"
}

output "slack_approval_request_url" {
  description = "Dify 환경변수 SLACK_APPROVAL_URL 에 넣을 값"
  value       = aws_lambda_function_url.slack_approval_request.function_url
}

output "slack_interactivity_url" {
  description = "Slack App -> Interactivity & Shortcuts -> Request URL 에 넣을 값 (2단계 임시 주소를 이걸로 교체)"
  value       = aws_lambda_function_url.slack_interactivity.function_url
}
