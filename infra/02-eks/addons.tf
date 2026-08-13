locals {
  # 노드 부팅 전에 있어야 하는 애드온
  addons_pre_node = ["vpc-cni", "kube-proxy"]

  # 노드에 스케줄되어야 하므로 노드 그룹 이후에 설치
  addons_post_node = ["coredns", "eks-pod-identity-agent"]

  # Phase 2에서 추가:
  #   aws-ebs-csi-driver  (Prometheus/Loki PVC)
  #   metrics-server      (HPA)
  #   amazon-cloudwatch-observability (선택)
}

data "aws_eks_addon_version" "this" {
  for_each = toset(concat(local.addons_pre_node, local.addons_post_node))

  addon_name         = each.key
  kubernetes_version = aws_eks_cluster.this.version
  most_recent        = true
}

resource "aws_eks_addon" "pre_node" {
  for_each = toset(local.addons_pre_node)

  cluster_name  = aws_eks_cluster.this.name
  addon_name    = each.key
  addon_version = data.aws_eks_addon_version.this[each.key].version

  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "PRESERVE"
}

resource "aws_eks_addon" "post_node" {
  for_each = toset(local.addons_post_node)

  cluster_name  = aws_eks_cluster.this.name
  addon_name    = each.key
  addon_version = data.aws_eks_addon_version.this[each.key].version

  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "PRESERVE"

  # CoreDNS는 스케줄될 노드가 없으면 Degraded 상태로 apply가 실패한다.
  depends_on = [aws_eks_node_group.default]
}
