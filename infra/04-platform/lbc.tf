# AWS Load Balancer Controller.
#
# 이게 있어야 Service(type=LoadBalancer)와 Ingress가 실제 NLB/ALB로 만들어진다.
# 없으면 매니페스트에 Ingress를 써도 아무 일도 일어나지 않는다.
#
# IAM 역할(IRSA)은 02-eks 가 이미 만들어 두었다. 그쪽은 역할만 만들고
# 설치 명령은 output으로 뱉어 사람이 복사해 실행하는 구조였는데,
# 클러스터를 다시 만들 때마다 그 복사가 필요해지므로 여기서 자동화한다.

resource "helm_release" "aws_load_balancer_controller" {
  count = var.enable_lbc ? 1 : 0

  name      = "aws-load-balancer-controller"
  namespace = "kube-system"

  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  version    = var.lbc_chart_version

  timeout = 600
  wait    = true

  values = [yamlencode({
    clusterName = local.cluster_name
    region      = var.region
    vpcId       = data.aws_eks_cluster.this.vpc_config[0].vpc_id

    serviceAccount = {
      create = true
      name   = "aws-load-balancer-controller"
      annotations = {
        # 이 주석이 파드에 IAM 역할을 붙여준다(IRSA).
        # 빠지면 컨트롤러가 ELB API 호출에서 권한 오류로 죽는다.
        "eks.amazonaws.com/role-arn" = local.lbc_role_arn
      }
    }

    # t3.small 2대 환경이라 기본 2 레플리카는 부담이다.
    # 가용성이 필요해지면 노드를 키우면서 함께 올린다.
    replicaCount = 1

    resources = {
      requests = { cpu = "50m", memory = "96Mi" }
      limits   = { memory = "192Mi" }
    }
  })]

  depends_on = [aws_eks_access_policy_association.admin]
}
