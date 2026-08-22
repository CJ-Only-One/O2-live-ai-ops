# Runbook 조회 중계. Dify 의 "11. Runbook Lookup" 노드가 부르는 동기 엔드포인트.
#
# Node 11 은 rca_type 하나를 받아 DynamoDB 를 직접 못 두드린다 — Dify Custom
# Tool/HTTP 노드의 인증 옵션은 NONE·API_KEY_HEADER·API_KEY_QUERY 뿐이라
# SigV4 서명을 못 한다 (D-043, decisions.md). runbook.tf 의 테이블에 직접
# IAM 을 붙이는 대신, 여기 있는 작은 Lambda 가 자신의 실행 역할로 Query 를
# 대신 실행하고 Dify 에는 x-api-key 헤더로만 인증한다.
#
# slack_approval.tf 와 같은 모양(Lambda + Function URL + 코드 내부 헤더 검증)
# 이지만 상태를 남기지 않는다 — 조회 한 번으로 끝나는 순수 읽기라 폴링도
# DynamoDB 쓰기도 없다.
#
# 코드: lambda/runbook_lookup.py

# ── 시크릿 ───────────────────────────────────────────────────────
#
# alert_secret_name 과 같은 이유로 값이 아니라 이름만 참조한다.

data "aws_secretsmanager_secret" "runbook_lookup" {
  name = var.runbook_lookup_secret_name
}

data "aws_iam_policy_document" "runbook_lookup_secret_read" {
  statement {
    sid       = "ReadRunbookLookupSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [data.aws_secretsmanager_secret.runbook_lookup.arn]
  }
}

# ── DynamoDB 읽기 권한 ───────────────────────────────────────────
#
# 쓰기는 주지 않는다. 시딩은 사람이 SSO 자격으로 로컬에서 돌리는 별도
# 스크립트(scripts/seed_runbook.py)이지 이 Lambda 가 스스로 채우지 않는다.
# 조회만 하므로 GetItem·Query 로 좁힌다 — runbook.tf 의 원래 주석과 같은
# 논리이되, 대상이 aws_iam_role.dify 가 아니라 이 Lambda 전용 역할이다.

data "aws_iam_policy_document" "runbook_table_read" {
  statement {
    sid    = "RunbookTableRead"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:Query",
    ]
    resources = [aws_dynamodb_table.runbook.arn]
  }
}

# ── Lambda: runbook_lookup ───────────────────────────────────────

resource "aws_iam_role" "runbook_lookup" {
  name               = "${local.name}-runbook-lookup-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "runbook_lookup_basic" {
  role       = aws_iam_role.runbook_lookup.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "runbook_lookup" {
  source_policy_documents = [
    data.aws_iam_policy_document.runbook_lookup_secret_read.json,
    data.aws_iam_policy_document.runbook_table_read.json,
  ]
}

resource "aws_iam_role_policy" "runbook_lookup" {
  name   = "${local.name}-runbook-lookup"
  role   = aws_iam_role.runbook_lookup.id
  policy = data.aws_iam_policy_document.runbook_lookup.json
}

resource "aws_cloudwatch_log_group" "runbook_lookup" {
  name              = "/aws/lambda/${local.name}-runbook-lookup"
  retention_in_days = 7
}

data "archive_file" "runbook_lookup" {
  type        = "zip"
  output_path = "${path.module}/lambda/runbook_lookup.zip"

  source {
    content  = file("${path.module}/lambda/runbook_lookup.py")
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "runbook_lookup" {
  function_name = "${local.name}-runbook-lookup"
  role          = aws_iam_role.runbook_lookup.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]

  # 단일 Query 한 번이 전부라 폴링하는 slack_approval_request 와 달리
  # slack_interactivity 처럼 짧다. Dify 노드 타임아웃보다 넉넉하게만 둔다.
  timeout     = 10
  memory_size = 128

  filename         = data.archive_file.runbook_lookup.output_path
  source_code_hash = data.archive_file.runbook_lookup.output_base64sha256

  # ★ VPC 밖에 둔다. DynamoDB·Secrets Manager 모두 공개 엔드포인트라 ENI 가
  #   필요 없다 (alert_relay·slack_approval 과 같은 이유).

  environment {
    variables = {
      RUNBOOK_TABLE       = aws_dynamodb_table.runbook.name
      RUNBOOK_SECRET_NAME = var.runbook_lookup_secret_name
    }
  }

  depends_on = [
    aws_iam_role_policy.runbook_lookup,
    aws_cloudwatch_log_group.runbook_lookup,
  ]
}

resource "aws_lambda_function_url" "runbook_lookup" {
  function_name = aws_lambda_function.runbook_lookup.function_name

  # NONE — 인증은 함수 코드의 x-api-key 헤더 비교가 전부다. Dify 의 HTTP
  # 요청 노드는 SigV4 서명을 못 하므로 AWS_IAM 으로 바꿀 수 없다
  # (slack_approval.tf·alert_relay 와 같은 이유, D-043).
  authorization_type = "NONE"
}

output "runbook_lookup_url" {
  description = "Dify 환경변수(Node 11 이 참조할 RUNBOOK_LOOKUP_URL)에 넣을 주소"
  value       = aws_lambda_function_url.runbook_lookup.function_url
  sensitive   = true
}
