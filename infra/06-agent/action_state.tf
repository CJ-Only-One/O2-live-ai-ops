# 조치 상태 머신의 결정론적 절반. Dify 가 Baseline 과 Judging 두 지점에서
# 부르는 동기 엔드포인트다.
#
# 왜 Lambda 인가. 이 판정은 **LLM 이 만들면 안 되는 값**이다 — 실행 락, 기준값,
# 재분석 상한, 세 갈래 판정. 같은 상황에서 같은 답이 나와야 실험이 반복
# 가능하고 녹화도 테이크마다 달라지지 않는다. 노브 카탈로그 조회로 게이트
# 진입을 정한 것(D-067)과 같은 논리를 조치 이후 구간으로 넓힌 것이다.
#
# 왜 새 테이블이 아닌가. `incident_state` 를 그대로 쓴다. pk 규약이 하나 늘 뿐
# 이고(ACTION#·LOCK#), 조치 상태는 인시던트 상태의 일부라 같이 만료되는 편이
# 맞다. correlator 와 같은 테이블을 쓰지만 **항목이 겹치지 않는다** — 저쪽은
# SIGNAL#·INCIDENT# 다.
#
# 모양은 runbook_lookup.tf 와 같다(Lambda + Function URL + 코드 내부 헤더 검증).
# 다른 점은 하나 — 이쪽은 테이블에 **쓴다**.
#
# 코드: lambda/action_state.py

# ── 시크릿 ───────────────────────────────────────────────────────

data "aws_secretsmanager_secret" "action_state" {
  name = var.action_state_secret_name
}

data "aws_iam_policy_document" "action_state_secret_read" {
  statement {
    sid       = "ReadActionStateSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [data.aws_secretsmanager_secret.action_state.arn]
  }
}

# ── DynamoDB 읽기·쓰기 ───────────────────────────────────────────
#
# 실행 락을 조건부 쓰기로 잡아야 해서 PutItem 이 필요하다. Query 는 안 준다 —
# 이 Lambda 는 pk 를 직접 만들어 GetItem 하지 스캔하지 않는다. 권한이 넓으면
# 나중에 스캔하는 코드가 조용히 들어온다.

data "aws_iam_policy_document" "incident_state_action_rw" {
  statement {
    sid    = "IncidentStateActionRecords"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
    ]
    resources = [aws_dynamodb_table.incident_state.arn]
  }
}

# ── Lambda: action_state ─────────────────────────────────────────

resource "aws_iam_role" "action_state" {
  name               = "${local.name}-action-state-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "action_state_basic" {
  role       = aws_iam_role.action_state.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "action_state" {
  source_policy_documents = [
    data.aws_iam_policy_document.action_state_secret_read.json,
    data.aws_iam_policy_document.incident_state_action_rw.json,
  ]
}

resource "aws_iam_role_policy" "action_state" {
  name   = "${local.name}-action-state"
  role   = aws_iam_role.action_state.id
  policy = data.aws_iam_policy_document.action_state.json
}

resource "aws_cloudwatch_log_group" "action_state" {
  name              = "/aws/lambda/${local.name}-action-state"
  retention_in_days = 7
}

data "archive_file" "action_state" {
  type        = "zip"
  output_path = "${path.module}/lambda/action_state.zip"

  source {
    content  = file("${path.module}/lambda/action_state.py")
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "action_state" {
  function_name = "${local.name}-action-state"
  role          = aws_iam_role.action_state.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]

  # GetItem 몇 번이 전부다. 검증 대기 타이머는 여기 있지 않다 — 대기는 Dify
  # 워크플로가 하고, 이 함수는 대기가 끝난 뒤 한 번 불린다. Lambda 를 재워
  # 기다리게 하면 그 시간만큼 과금되고 600초 벽에도 걸린다.
  timeout     = 10
  memory_size = 128

  filename         = data.archive_file.action_state.output_path
  source_code_hash = data.archive_file.action_state.output_base64sha256

  # ★ VPC 밖에 둔다. DynamoDB·Secrets Manager 모두 공개 엔드포인트다
  #   (runbook_lookup 과 같은 이유).

  environment {
    variables = {
      INCIDENT_STATE_TABLE     = aws_dynamodb_table.incident_state.name
      ACTION_STATE_SECRET_NAME = var.action_state_secret_name
    }
  }

  depends_on = [
    aws_iam_role_policy.action_state,
    aws_cloudwatch_log_group.action_state,
  ]
}

resource "aws_lambda_function_url" "action_state" {
  function_name = aws_lambda_function.action_state.function_name

  # NONE — 인증은 함수 코드의 x-api-key 헤더 비교가 전부다. Dify 의 HTTP 요청
  # 노드가 SigV4 를 못 한다(D-043).
  authorization_type = "NONE"
}

output "action_state_url" {
  description = "Dify 환경변수 ACTION_STATE_URL 에 넣을 주소. Baseline·Judging 두 노드가 쓴다"
  value       = aws_lambda_function_url.action_state.function_url
  sensitive   = true
}
