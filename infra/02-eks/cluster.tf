# ── 컨트롤플레인 IAM 역할 ────────────────────────────────────────
data "aws_iam_policy_document" "cluster_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "cluster" {
  name               = "${var.cluster_name}-cluster-role"
  assume_role_policy = data.aws_iam_policy_document.cluster_assume.json
}

resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonEKSClusterPolicy"
}

# ── 컨트롤플레인 로그 그룹 ───────────────────────────────────────
# EKS가 자동 생성하는 로그 그룹은 보존기간이 "무기한"이다.
# 미리 만들어 retention을 걸어야 프로젝트 종료 후 과금이 이어지지 않는다.
resource "aws_cloudwatch_log_group" "cluster" {
  name              = "/aws/eks/${var.cluster_name}/cluster"
  retention_in_days = var.control_plane_log_retention_days
}

# ── 클러스터 ─────────────────────────────────────────────────────
resource "aws_eks_cluster" "this" {
  name     = var.cluster_name
  role_arn = aws_iam_role.cluster.arn
  version  = var.kubernetes_version

  vpc_config {
    # 컨트롤플레인 ENI는 private 서브넷에만 둔다.
    # public 서브넷을 넣을 이유가 없다 (ALB는 태그 discovery로 별도 동작).
    subnet_ids              = local.private_subnet_ids
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = var.cluster_public_access_cidrs
  }

  access_config {
    # aws-auth ConfigMap 방식을 쓰지 않는다.
    # ConfigMap은 잘못 편집하면 전원이 클러스터에서 잠기고 복구가 어렵다.
    # API 모드는 IAM 리소스로 관리되어 Terraform으로 되돌릴 수 있다.
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = true
  }

  enabled_cluster_log_types = var.control_plane_log_types

  depends_on = [
    aws_iam_role_policy_attachment.cluster,
    aws_cloudwatch_log_group.cluster,
  ]
}

# ── IRSA용 OIDC Provider ─────────────────────────────────────────
data "tls_certificate" "oidc" {
  url = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  url             = aws_eks_cluster.this.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.oidc.certificates[0].sha1_fingerprint]
}
