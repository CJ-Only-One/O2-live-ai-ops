data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  # 기존 리소스의 물리 이름을 유지해 state migration 중 교체를 방지한다.
  name = "${var.project}-${var.environment}-dify"
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

data "aws_secretsmanager_secret" "alert_relay_o2" {
  name = var.alert_secret_name_o2
}
