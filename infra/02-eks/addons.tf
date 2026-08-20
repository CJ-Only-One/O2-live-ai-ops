locals {
  # 노드 부팅 전에 있어야 하는 애드온
  addons_pre_node = ["vpc-cni", "kube-proxy"]

  # 노드에 스케줄되어야 하므로 노드 그룹 이후에 설치
  #
  # metrics-server 는 `metrics.k8s.io` 를 제공한다. Datadog 이 같은 값을
  # 수집하지만 읽는 쪽이 다르다 — Datadog 은 사람이 웹에서 보고, 이 API 는
  # 쿠버네티스 자신이 읽는다. `kubectl top` 과 리소스 기준 HPA 의 전제다
  # (D-037). 부하 테스트에서 "파드 하나가 몇 RPS 를 견디나" 를 재려면 CPU
  # 포화를 봐야 하는데, 지금은 `describe nodes` 의 **요청량**(예약한 양)만
  # 보이고 실사용량을 볼 수단이 없다.
  addons_post_node = ["coredns", "eks-pod-identity-agent", "metrics-server"]

  # 넣지 않기로 한 것 (D-037):
  #   aws-ebs-csi-driver  — PVC 를 쓰는 파드가 없다. 필요했던 유일한 이유가
  #                         Prometheus 였는데 그것을 빼면서 같이 빠졌다
  #   Prometheus          — Datadog 과 중복. KEDA 가 필요해지면 Datadog
  #                         스케일러 쪽이 맞다
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
