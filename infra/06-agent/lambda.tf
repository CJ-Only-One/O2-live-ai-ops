# Datadog 알림을 Dify 워크플로로 중계하는 Lambda.
#
# ALB 를 세우지 않은 이유는 lambda/datadog_to_dify.py 의 모듈 docstring 에 있다.
# 요약하면 VPC 인바운드를 열지 않기 위해서다 — 이 함수가 안쪽에서 Dify 를
# 호출하므로 인터넷 → VPC 방향 경로가 아예 생기지 않는다.

locals {
  # ★ 이름이 ${project}-${environment}-* 규칙을 따르지 않는다. 의도한 것이다.
  #   이 함수는 콘솔에서 먼저 만들어졌고 그 Function URL 이 이미 Datadog
  #   webhook 에 등록되어 있다. 이름을 바꾸면 함수가 교체되면서 Function URL
  #   도 바뀌고, Datadog 쪽을 손으로 다시 맞춰야 한다. 얻는 것이 이름 통일
  #   하나뿐이라 그대로 둔다.
  alert_relay_name = "datadog-to-dify"
}

# ── 실행 역할 ────────────────────────────────────────────────────
#
# 콘솔이 만들어 둔 역할(datadog-to-dify-role-<랜덤>)은 import 하지 않는다.
# 랜덤 접미사가 코드에 박히기 때문이다. 여기서 새로 만들고 함수가 이 역할을
# 보게 한 뒤, 옛 역할은 손으로 지운다 (README 의 import 절차 참조).

data "aws_iam_policy_document" "alert_relay_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "alert_relay" {
  name               = "${local.name}-alert-relay-role"
  assume_role_policy = data.aws_iam_policy_document.alert_relay_assume.json
}

resource "aws_iam_role_policy_attachment" "alert_relay_basic" {
  role       = aws_iam_role.alert_relay.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ★ 이게 없으면 VPC 설정 저장 자체가 실패한다.
#     The provided execution role does not have permissions to
#     call CreateNetworkInterface on EC2
#   VPC 안의 Lambda 는 서브넷에 ENI 를 만들어야 하고 그 권한이 여기서 온다.
resource "aws_iam_role_policy_attachment" "alert_relay_vpc" {
  role       = aws_iam_role.alert_relay.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# SecretString 을 읽지 않는다 — ARN 만 필요하다. data source 로 값을 읽으면
# 결과가 state 에 평문으로 남는다 (06-datastream/warm-path.tf 와 같은 이유).
data "aws_secretsmanager_secret" "alert_relay" {
  name = var.alert_secret_name
}

data "aws_iam_policy_document" "alert_relay" {
  statement {
    sid       = "ReadAlertRelaySecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [data.aws_secretsmanager_secret.alert_relay.arn]
  }
}

resource "aws_iam_role_policy" "alert_relay" {
  name   = "${local.name}-alert-relay"
  role   = aws_iam_role.alert_relay.id
  policy = data.aws_iam_policy_document.alert_relay.json
}

# ── 네트워크 ─────────────────────────────────────────────────────

resource "aws_security_group" "alert_relay" {
  name        = "${local.name}-alert-relay"
  description = "datadog-to-dify Lambda. Egress to Dify only"
  vpc_id      = local.vpc_id

  tags = {
    Name = "${local.name}-alert-relay"
  }
}

# 인바운드 규칙은 두지 않는다. Function URL 로 들어오는 요청은 Lambda 서비스가
# 받아서 전달하는 것이라 이 SG 를 통과하지 않는다.
resource "aws_vpc_security_group_egress_rule" "alert_relay_all" {
  security_group_id = aws_security_group.alert_relay.id
  description       = "Dify call, Secrets Manager"

  cidr_ipv4   = "0.0.0.0/0"
  ip_protocol = "-1"
}

# ── 함수 ─────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "alert_relay" {
  name              = "/aws/lambda/${local.alert_relay_name}"
  retention_in_days = 7
}

data "archive_file" "alert_relay" {
  type        = "zip"
  output_path = "${path.module}/lambda/datadog-to-dify.zip"

  source {
    content  = file("${path.module}/lambda/datadog_to_dify.py")
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "alert_relay" {
  function_name = local.alert_relay_name
  role          = aws_iam_role.alert_relay.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"

  # 콘솔이 만든 함수가 x86_64 다. arm64 가 더 싸지만 알림 경로라 월 몇 센트
  # 차이이고, 바꾸면 import 직후 plan 에 교체가 뜬다. 그대로 둔다.
  architectures = ["x86_64"]

  # ★ 기본값 3초로는 무조건 실패한다. Dify 워크플로가 blocking 으로 끝날
  #   때까지 기다리기 때문이다. 현재 실측 2~3초이고 55초 타임아웃으로
  #   호출하므로 함수는 그보다 커야 한다.
  timeout     = 60
  memory_size = 128

  filename         = data.archive_file.alert_relay.output_path
  source_code_hash = data.archive_file.alert_relay.output_base64sha256

  # ★ 알림 폭주 상한. 방송이 시작되면 CPU·DB 커넥션·응답시간 모니터가
  #   동시에 울린다. 이 값이 없으면 알림 수만큼 AI 워크플로가 돌고
  #   그대로 토큰 요금이 된다.
  reserved_concurrent_executions = var.alert_relay_max_concurrency

  vpc_config {
    # Dify 와 같은 서브넷에 둔다. 사설 IP 로 직접 호출하므로 라우팅이 필요
    # 없고, Secrets Manager 는 이 서브넷의 NAT 로 나간다.
    subnet_ids         = [local.subnet_id]
    security_group_ids = [aws_security_group.alert_relay.id]
  }

  environment {
    variables = {
      # ★ 사설 IP 를 하드코딩하지 않는다. 손으로 넣었다가 예시 IP 가 그대로
      #   남아 연결 타임아웃을 디버깅한 적이 있다. 포트는 80 이다 —
      #   17080 은 SSM 터널이 만드는 각자 로컬 포트다.
      DIFY_URL = "http://${aws_instance.dify.private_ip}/v1/workflows/run"

      # 값이 아니라 이름이다. 값은 Lambda 가 실행 시점에 읽는다.
      ALERT_SECRET_NAME = var.alert_secret_name
    }
  }

  depends_on = [
    aws_iam_role_policy.alert_relay,
    aws_iam_role_policy_attachment.alert_relay_vpc,
    aws_cloudwatch_log_group.alert_relay,
  ]
}

# ── 퍼블릭 입구 ──────────────────────────────────────────────────

resource "aws_lambda_function_url" "alert_relay" {
  function_name = aws_lambda_function.alert_relay.function_name

  # ★ NONE 은 "URL 을 아는 누구나 POST 할 수 있다" 는 뜻이다.
  #   인증은 함수 코드의 x-dd-secret 헤더 비교가 전부다.
  #
  #   AWS_IAM 으로 바꿀 수 없다 — Datadog 은 SigV4 서명을 못 한다.
  #   WAF 나 IP 제한이 필요해지면 API Gateway 를 앞에 두고 이 리소스를
  #   지운다. 함수 코드는 그대로 쓴다.
  authorization_type = "NONE"
}
