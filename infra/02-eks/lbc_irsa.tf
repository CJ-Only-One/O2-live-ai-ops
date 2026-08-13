# AWS Load Balancer Controller용 IRSA 역할.
#
# ingress-nginx를 쓰지 않는 이유:
#   업스트림 Kubernetes 프로젝트가 2026-03에 Ingress NGINX를 은퇴시켰다.
#   버그 수정/보안 패치가 더 이상 나오지 않는다.
#   AWS 환경에서는 LBC가 ALB를 직접 프로비저닝하므로 홉이 하나 줄어드는 이점도 있다.
#
# 정책 JSON은 저장소에 커밋하지 않고 공식 릴리스에서 내려받는다.
# scripts/00-fetch-lbc-policy.sh 를 먼저 실행할 것.
# (직접 작성하면 오타 시 "AccessDenied"만 뜨고 원인 추적이 어렵다)

resource "aws_iam_policy" "lbc" {
  name        = "${var.cluster_name}-lbc-policy"
  description = "AWS Load Balancer Controller"
  policy      = file("${path.module}/policies/aws-load-balancer-controller.json")
}

data "aws_iam_policy_document" "lbc_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.eks.arn]
    }

    # 특정 네임스페이스의 특정 ServiceAccount로만 좁힌다.
    # StringLike가 아니라 StringEquals를 쓰는 이유: 와일드카드를 허용하면
    # 클러스터 내 임의 SA가 이 역할을 가져갈 수 있다.
    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:sub"
      values   = ["system:serviceaccount:kube-system:aws-load-balancer-controller"]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lbc" {
  name               = "${var.cluster_name}-lbc-role"
  assume_role_policy = data.aws_iam_policy_document.lbc_assume.json
}

resource "aws_iam_role_policy_attachment" "lbc" {
  role       = aws_iam_role.lbc.name
  policy_arn = aws_iam_policy.lbc.arn
}
