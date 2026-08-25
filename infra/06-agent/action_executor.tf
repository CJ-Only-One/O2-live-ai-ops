# 조치 실행기. Dify 의 조치 실행 노드가 부르는 동기 엔드포인트 — Deployment
# replicas 를 patch 한다.
#
# S2(docs/scenario-experiment.md 0.6) "느린 파드 격리"와 그 조치의 원복
# (rollback)이 둘 다 이 하나의 엔드포인트다 — "0으로 줄이기"와 "원래 값으로
# 되돌리기"는 replicas 파라미터만 다른 같은 동작이기 때문이다. 코드: 참조는
# lambda/scale_deployment.py.
#
# ── 클러스터 접근 ────────────────────────────────────────────────
# 인증은 EKS Access Entry(02-eks 가 이미 authentication_mode="API"로 정함).
# 권한(RBAC Role·RoleBinding)은 이 스택이 아니라 infra/04-platform 에
# 만든다 — "클러스터 안 권한은 04-platform 이 코드로 갖는다"(D-008)는
# 기존 규칙과 같다. 여기서는 그 access entry 가 붙일 IAM Role 만 만들고
# ARN 을 output 으로 내보낸다.
#
# 권한 범위는 o2-dev 네임스페이스의 deployments/scale 서브리소스,
# get·patch 뿐이다. admin access entry(04-platform main.tf)와 달리 이건
# 진짜 보안 경계다 — 이 Role 은 팀 IAM 그룹(AdministratorAccess)에 안
# 속하므로, RBAC 을 좁혀 두면 실행기가 잘못된 인자를 받아도(프롬프트
# 인젝션 포함) 클러스터에서 이 네임스페이스의 스케일 조정 말고는 할 수
# 있는 게 없다.
#
# VPC 밖에 둔다. EKS 클러스터 엔드포인트가 퍼블릭이라(02-eks
# endpoint_public_access=true) ENI 가 필요 없다 — runbook_lookup.tf 와
# 같은 이유.

# ── 시크릿 ───────────────────────────────────────────────────────

data "aws_secretsmanager_secret" "scale_executor" {
  name = var.scale_executor_secret_name
}

data "aws_iam_policy_document" "scale_executor_secret_read" {
  statement {
    sid       = "ReadScaleExecutorSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [data.aws_secretsmanager_secret.scale_executor.arn]
  }
}

# EKS API 서버가 이 토큰을 검증할 때 내부적으로 sts:GetCallerIdentity 를
# 쓴다. 대부분 계정에서 암묵 허용되지만, 명시로 남겨 계정 정책이 바뀌어도
# 안 깨지게 한다.
data "aws_iam_policy_document" "scale_executor_sts" {
  statement {
    sid       = "AllowGetCallerIdentity"
    effect    = "Allow"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }
}

# ── Lambda: scale_deployment ──────────────────────────────────────

resource "aws_iam_role" "scale_executor" {
  name               = "${local.name}-scale-executor-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "scale_executor_basic" {
  role       = aws_iam_role.scale_executor.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "scale_executor" {
  source_policy_documents = [
    data.aws_iam_policy_document.scale_executor_secret_read.json,
    data.aws_iam_policy_document.scale_executor_sts.json,
  ]
}

resource "aws_iam_role_policy" "scale_executor" {
  name   = "${local.name}-scale-executor"
  role   = aws_iam_role.scale_executor.id
  policy = data.aws_iam_policy_document.scale_executor.json
}

resource "aws_cloudwatch_log_group" "scale_executor" {
  name              = "/aws/lambda/${local.name}-scale-executor"
  retention_in_days = 7
}

data "archive_file" "scale_executor" {
  type        = "zip"
  output_path = "${path.module}/lambda/scale_executor.zip"

  source {
    content  = file("${path.module}/lambda/scale_deployment.py")
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "scale_executor" {
  function_name = "${local.name}-scale-executor"
  role          = aws_iam_role.scale_executor.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]

  # PATCH 뒤 60초 안정화 창을 Action Handler가 소유한다. Dify가 조치 직후의
  # 이전 Warm window를 읽어 거짓 실패로 판정하지 않게 Lambda timeout을 넉넉히 둔다.
  timeout     = 75
  memory_size = 128

  filename         = data.archive_file.scale_executor.output_path
  source_code_hash = data.archive_file.scale_executor.output_base64sha256

  environment {
    variables = {
      CLUSTER_NAME                = var.cluster_name
      CLUSTER_ENDPOINT            = data.aws_eks_cluster.this.endpoint
      CLUSTER_CA                  = data.aws_eks_cluster.this.certificate_authority[0].data
      SCALE_EXECUTOR_SECRET_NAME  = var.scale_executor_secret_name
      SCALE_STABILIZATION_SECONDS = tostring(var.s2_scale_stabilization_seconds)
    }
  }

  depends_on = [
    aws_iam_role_policy.scale_executor,
    aws_iam_role_policy_attachment.scale_executor_basic,
    aws_cloudwatch_log_group.scale_executor,
  ]
}

resource "aws_lambda_function_url" "scale_executor" {
  function_name = aws_lambda_function.scale_executor.function_name

  # NONE — 인증은 함수 코드의 x-api-key 헤더 비교. Dify 의 HTTP 요청 노드가
  # SigV4 를 못 해 AWS_IAM 으로 못 바꾼다 (runbook_lookup.tf 와 같은 이유, D-043).
  authorization_type = "NONE"
}

output "scale_executor_url" {
  description = "Dify 환경변수(조치 실행 노드가 참조할 SCALE_EXECUTOR_URL)에 넣을 주소"
  value       = aws_lambda_function_url.scale_executor.function_url
  sensitive   = true
}

output "scale_executor_role_arn" {
  description = <<-EOT
    infra/04-platform 이 EKS Access Entry 를 만들 때 principal_arn 으로 쓴다.
    04-platform 은 이 스택(dify/terraform.tfstate)을 remote_state 로 읽는다 —
    03-data 가 network 스택을 읽는 것과 같은 패턴. apply 순서는 06-agent 가
    04-platform 보다 먼저다(AGENTS.md "apply 순서").
  EOT
  value       = aws_iam_role.scale_executor.arn
}
