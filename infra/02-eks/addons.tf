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

# coredns 와 metrics-server 는 복제본이 둘인데 배치 제약이 없어 같은 노드에
# 올라간다. 실제로 2026-08-25 에 넷 다 한 노드에 몰려 있었다. coredns 가
# 통째로 사라지면 새 파드가 뜰 때까지 클러스터의 모든 이름 해석이 실패한다 —
# 앱 파드가 몰린 것보다 파급이 크다.
#
# 애드온이라 매니페스트 저장소가 아니라 configuration_values 로 넣는다.
# 두 애드온 모두 스키마에 topologySpreadConstraints 가 있다.
#
# whenUnsatisfiable 을 ScheduleAnyway 로 둔다. DoNotSchedule 이면 한쪽 AZ 에
# 자리가 없을 때 파드가 아예 안 뜨는데, 이 둘은 클러스터 기반 구성요소라
# 뜨지 못하는 편이 몰려 있는 것보다 나쁘다. 스케줄러가 자리가 있는 한
# 반드시 가르므로 평시에는 DoNotSchedule 과 결과가 같다.
locals {
  # 라벨은 실제 파드에서 확인한 값이다 — coredns 는 k8s-app: kube-dns,
  # metrics-server 는 app.kubernetes.io/name 을 쓴다. 애드온마다 다르므로
  # 하나로 묶을 수 없다.
  core_addon_spread_by_addon = {
    coredns = jsonencode({
      topologySpreadConstraints = [{
        maxSkew           = 1
        topologyKey       = "topology.kubernetes.io/zone"
        whenUnsatisfiable = "ScheduleAnyway"
        labelSelector     = { matchLabels = { "k8s-app" = "kube-dns" } }
        # 없으면 롤링 중 구 ReplicaSet 파드까지 세어 제약이 무력해진다.
        # 구 파드가 양쪽에 하나씩 남은 상태에서는 새 파드를 어느 쪽에 놓아도
        # skew 가 1 이라 둘 다 통과하고, 구 파드가 빠지면 결과만 쏠린다.
        # 2026-08-25 에 노드 drain 뒤 재시작에서 실제로 두 파드가 한 AZ 로
        # 몰렸다. 같은 ReplicaSet 파드끼리만 비교하게 좁힌다.
        matchLabelKeys = ["pod-template-hash"]
      }]
    })
    metrics-server = jsonencode({
      topologySpreadConstraints = [{
        maxSkew           = 1
        topologyKey       = "topology.kubernetes.io/zone"
        whenUnsatisfiable = "ScheduleAnyway"
        labelSelector     = { matchLabels = { "app.kubernetes.io/name" = "metrics-server" } }
        matchLabelKeys    = ["pod-template-hash"]
      }]
    })
  }
}

resource "aws_eks_addon" "post_node" {
  for_each = toset(local.addons_post_node)

  cluster_name  = aws_eks_cluster.this.name
  addon_name    = each.key
  addon_version = data.aws_eks_addon_version.this[each.key].version

  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "PRESERVE"

  # 라벨 셀렉터가 애드온마다 달라 각자 만든다. 나머지 애드온은 복제본이
  # 하나뿐(DaemonSet 포함)이라 흩을 것이 없으므로 넣지 않는다.
  configuration_values = lookup(local.core_addon_spread_by_addon, each.key, null)

  # CoreDNS는 스케줄될 노드가 없으면 Degraded 상태로 apply가 실패한다.
  depends_on = [aws_eks_node_group.default]
}
