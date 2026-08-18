data "aws_iam_policy_document" "assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "dify" {
  name               = "${local.name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# SSH 키도 bastion 도 만들지 않는다. 노드그룹과 같은 방식으로
# Session Manager 로만 들어간다.
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.dify.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "bedrock" {
  count = var.enable_bedrock_access ? 1 : 0

  statement {
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
      "bedrock:ListFoundationModels",
    ]
    # 모델 ARN 은 어떤 모델을 쓸지 정한 뒤 좁힌다.
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "bedrock" {
  count = var.enable_bedrock_access ? 1 : 0

  name   = "${local.name}-bedrock"
  role   = aws_iam_role.dify.id
  policy = data.aws_iam_policy_document.bedrock[0].json
}

resource "aws_iam_instance_profile" "dify" {
  name = "${local.name}-profile"
  role = aws_iam_role.dify.name
}
