# GitHub Actions -> AWS 인증을 OIDC로 처리한다.
#
# AWS 액세스 키를 GitHub Secrets에 넣지 않는 이유:
#   1) 장기 자격증명은 유출 시 만료되지 않는다
#   2) 로테이션 주체가 사람이라 실제로는 로테이션되지 않는다
#   3) OIDC 토큰은 워크플로 실행당 발급되고 15분 내 만료된다
# 프로젝트 보안 트랙(이상문)의 발표 근거로도 쓸 수 있다.

resource "aws_iam_openid_connect_provider" "github" {
  count = var.enable_github_oidc ? 1 : 0

  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
  # 참고: AWS는 2023년 이후 GitHub OIDC에 대해 thumbprint를 실제로 검증하지 않지만
  # 필드는 필수라 공식 값을 넣는다.
}

data "aws_iam_policy_document" "github_assume" {
  count = var.enable_github_oidc ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github[0].arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # 이 저장소에서 나온 워크플로만 허용.
    # repo:*:* 로 열면 GitHub의 아무 저장소나 이 역할을 가져갈 수 있다.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:*"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  count = var.enable_github_oidc ? 1 : 0

  name               = "${var.cluster_name}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_assume[0].json
}

data "aws_iam_policy_document" "github_actions" {
  count = var.enable_github_oidc ? 1 : 0

  # ECR 로그인 토큰 (리소스 단위 제한 불가)
  statement {
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  # 이 저장소에만 push 허용
  statement {
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.app.arn]
  }

  # kubeconfig 생성용. 클러스터 내부 권한은 아래 access entry가 결정한다.
  statement {
    effect    = "Allow"
    actions   = ["eks:DescribeCluster"]
    resources = [aws_eks_cluster.this.arn]
  }
}

resource "aws_iam_role_policy" "github_actions" {
  count = var.enable_github_oidc ? 1 : 0

  name   = "ci-permissions"
  role   = aws_iam_role.github_actions[0].id
  policy = data.aws_iam_policy_document.github_actions[0].json
}

# ── 클러스터 내부 권한 (RBAC) ────────────────────────────────────
resource "aws_eks_access_entry" "github_actions" {
  count = var.enable_github_oidc ? 1 : 0

  cluster_name  = aws_eks_cluster.this.name
  principal_arn = aws_iam_role.github_actions[0].arn
  type          = "STANDARD"
}

# ClusterAdmin이 아니라 Edit + 네임스페이스 스코프로 제한한다.
# CI가 노드/CRD/RBAC을 건드릴 이유가 없고,
# 파이프라인 사고의 blast radius를 app 네임스페이스로 가둔다.
resource "aws_eks_access_policy_association" "github_actions" {
  count = var.enable_github_oidc ? 1 : 0

  cluster_name  = aws_eks_cluster.this.name
  principal_arn = aws_iam_role.github_actions[0].arn
  policy_arn    = "arn:${data.aws_partition.current.partition}:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"

  access_scope {
    type       = "namespace"
    namespaces = ["app"]
  }

  depends_on = [aws_eks_access_entry.github_actions]
}
