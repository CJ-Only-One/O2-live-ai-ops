locals {
  eks_cluster_name = "o2-eks"

  # 신뢰 정책의 sub 조건에 고정되는 값. 변경하면 role 재적용 필요
  producer_namespace       = "data-stream"
  producer_service_account = "o2-producer"
}

data "aws_eks_cluster" "o2" {
  name = local.eks_cluster_name
}

data "aws_iam_openid_connect_provider" "eks" {
  url = data.aws_eks_cluster.o2.identity[0].oidc[0].issuer
}

locals {
  # 조건 키 접두사는 scheme 없는 issuer 호스트+경로
  oidc_host = replace(data.aws_eks_cluster.o2.identity[0].oidc[0].issuer, "https://", "")
}

data "aws_iam_policy_document" "producer_assume_role" {
  statement {
    sid     = "EksServiceAccountWebIdentity"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.eks.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values   = ["system:serviceaccount:${local.producer_namespace}:${local.producer_service_account}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "producer" {
  name = "o2-producer-irsa-role"

  # IAM description 은 Latin-1 만 허용해 한글을 넣을 수 없다
  description        = "IRSA role for the EKS event producer pod"
  assume_role_policy = data.aws_iam_policy_document.producer_assume_role.json
}

data "aws_iam_policy_document" "producer" {
  statement {
    sid = "WriteEventStreams"

    actions = [
      "kinesis:PutRecord",
      "kinesis:PutRecords",
    ]

    resources = [
      aws_kinesis_stream.business.arn,
      aws_kinesis_stream.client.arn,
    ]
  }
}

resource "aws_iam_role_policy" "producer" {
  name   = "o2-producer-irsa-policy"
  role   = aws_iam_role.producer.id
  policy = data.aws_iam_policy_document.producer.json
}
