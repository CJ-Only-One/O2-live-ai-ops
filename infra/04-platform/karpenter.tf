# Karpenter — 클러스터 안쪽(Helm + NodePool).
#
# IAM·SQS·EventBridge 는 `02-eks/karpenter.tf` 가 만든다. 여기는 설치와 정책만 둔다.
#
# **4차 안전망이다.** 노드 확보에 최소 26초(2026-08-21 실측) + 이미지 pull 이
# 걸리는데 방송 시작 스파이크는 30초 안에 끝난다. 주력은 큐시트 기반 사전
# 확장이고(D-041) Karpenter 는 예상 밖 Pending Pod 와 노드 장애를 받는다.

resource "helm_release" "karpenter" {
  count = var.enable_karpenter ? 1 : 0

  name      = "karpenter"
  namespace = "kube-system"

  repository = "oci://public.ecr.aws/karpenter"
  chart      = "karpenter"
  version    = var.karpenter_chart_version

  timeout = 600
  wait    = true

  values = [yamlencode({
    settings = {
      clusterName = local.cluster_name
      # 없으면 스팟 회수 통보(2분)를 못 받아 파드가 갑자기 사라진다.
      interruptionQueue = local.karpenter_interruption_queue
    }

    serviceAccount = {
      create      = true
      name        = "karpenter"
      annotations = { "eks.amazonaws.com/role-arn" = local.karpenter_role_arn }
    }

    # 차트 기본값은 2 다. dev 는 1 로 충분하다 — 파드가 죽어도 재시작까지
    # 수십 초 노드 확장이 멈출 뿐이고, 그동안 기존 노드는 그대로 돈다.
    replicas = 1

    # 차트가 requests 를 기본으로 걸지 않는다. 안 걸면 BestEffort 로 떠서
    # 노드가 압박받을 때 **노드를 관리하는 컨트롤러가 먼저 축출된다.**
    controller = {
      resources = {
        requests = { cpu = "200m", memory = "512Mi" }
        # CPU limit 은 걸지 않는다 — 이 저장소 관례(스로틀링이 지연을 만든다).
        limits = { memory = "1Gi" }
      }
    }

    # 관리형 노드그룹에만 뜨도록 묶는다(`02-eks/nodegroup.tf` 의 labels).
    #
    # 차트가 이미 `karpenter.sh/nodepool DoesNotExist` nodeAffinity 로 자기가 만든
    # 노드를 피한다. 이건 그 위에 얹는 이중 방어이자, 노드 종류가 늘었을 때
    # 컨트롤러 자리를 명시하는 뜻이다.
    nodeSelector = { role = "general" }
  })]

  depends_on = [aws_eks_access_policy_association.admin]
}

###############################################################################
# EC2NodeClass — 어떤 AMI·서브넷·보안그룹으로 노드를 만들 것인가
###############################################################################

resource "kubectl_manifest" "karpenter_node_class" {
  count = var.enable_karpenter ? 1 : 0

  yaml_body = yamlencode({
    apiVersion = "karpenter.k8s.aws/v1"
    kind       = "EC2NodeClass"
    metadata   = { name = "default" }
    spec = {
      # AL2 는 1.32 가 마지막이다. 1.33+ 는 AL2023 만 제공된다
      # (`02-eks/nodegroup.tf` 와 같은 이유).
      amiFamily = "AL2023"
      amiSelectorTerms = [
        { alias = "al2023@latest" }
      ]

      # discovery 태그로 찾는다. 서브넷은 `01-network/subnets.tf`,
      # 보안그룹은 `02-eks/karpenter.tf` 가 붙인다.
      subnetSelectorTerms        = [{ tags = { "karpenter.sh/discovery" = local.cluster_name } }]
      securityGroupSelectorTerms = [{ tags = { "karpenter.sh/discovery" = local.cluster_name } }]

      # 관리형 노드그룹과 같은 역할을 쓴다 — 이미 EKS 접근 항목에 등록돼 있어
      # 새 노드가 바로 조인한다. 새로 만들면 등록을 잊고 NotReady 로 남는다.
      role = local.karpenter_node_role_name

      # `tags` 를 쓰지 않는다.
      #
      # `kubernetes.io/cluster/<이름> = owned` 를 여기 적으면 CRD 검증이 거부한다.
      #
      #     spec.tags: Invalid value: tag contains a restricted tag
      #     matching kubernetes.io/cluster/
      #
      # Karpenter 가 노드를 만들 때 **스스로 붙이는** 태그라 사용자가 지정할 수
      # 없다. 자기 소유 표시를 남이 조작하면 안 되기 때문이다.
      #
      # `02-eks` 의 IAM 조건(CreateNodes·TerminateNodes)이 이 태그를 보는데,
      # 자동으로 붙으므로 조건은 그대로 걸린다. 추가 태그가 필요해지면 그때
      # 여기에 `tags` 를 넣되 `kubernetes.io/cluster/` 로 시작하는 것은 뺀다.
    }
  })

  depends_on = [helm_release.karpenter]
}

###############################################################################
# NodePool — 얼마나, 어떤 인스턴스로, 언제 반납할 것인가
###############################################################################

resource "kubectl_manifest" "karpenter_node_pool" {
  count = var.enable_karpenter ? 1 : 0

  yaml_body = yamlencode({
    apiVersion = "karpenter.sh/v1"
    kind       = "NodePool"
    metadata   = { name = "default" }
    spec = {
      template = {
        spec = {
          nodeClassRef = {
            group = "karpenter.k8s.aws"
            kind  = "EC2NodeClass"
            name  = "default"
          }

          requirements = [
            # **t3 를 넣지 않는다.** baseline 이 0.4 vCPU 인데 Datadog 에이전트가
            # 노드당 300m 을 쓴다. 부하가 없어도 스로틀되는 것을 2026-08-21 에
            # 확인했다 (measurements.md M-008).
            {
              key      = "karpenter.k8s.aws/instance-family"
              operator = "In"
              values   = ["c6i", "m6i"]
            },
            {
              key      = "karpenter.k8s.aws/instance-size"
              operator = "In"
              values   = ["large", "xlarge"]
            },
            # 채팅은 Spot 금지다 — 회수당하면 WebSocket 이 끊긴다
            # (architecture.md 9.3). NodePool 을 하나만 두므로 전체 온디맨드.
            {
              key      = "karpenter.sh/capacity-type"
              operator = "In"
              values   = ["on-demand"]
            },
            {
              key      = "kubernetes.io/arch"
              operator = "In"
              values   = ["amd64"] # ECR 이미지가 단일 아키(amd64)다
            },
          ]

          # **만료로 노드를 교체하지 않는다.**
          #
          # 기본값 720h 를 두면 30일마다 빈 노드가 아니어도 교체된다. AMI 보안
          # 패치를 반영하려는 것인데, 그 교체가 방송 중에 걸리면 파드가 재배치되고
          # WebSocket 이 끊긴다. D-041 이 "축소는 WebSocket 활성 연결과 graceful
          # drain 을 확인하는 결정론적 단계로만" 이라고 못박았는데, 만료는 그
          # 조건을 우회하는 경로다.
          #
          # 이 노드들은 스파이크를 받는 임시 용량이라 30일씩 살아 있을 일이
          # 없다 — 부하가 빠지면 아래 consolidation 이 반납한다. AMI 갱신은
          # 관리형 노드그룹 쪽에서 사람이 창을 잡고 한다.
          expireAfter = "Never"
        }
      }

      disruption = {
        # **WhenEmptyOrUnderutilized 로 두지 않는다.** 방송 중에 노드를 합치면
        # 파드가 재배치되고 WebSocket 이 끊긴다. 4,000명이 동시에 재연결하면
        # 그것이 곧 장애다 (architecture.md 9.3).
        #
        # 노는 노드는 돈 낭비지 장애가 아니다. 노드 한 대가 시간당 $0.10 인데,
        # 옮기면 그 파드가 들고 있던 연결 수천 개가 끊긴다. 방송이 끝나 시청자가
        # 빠지면 아래 타이머로 반납된다.
        consolidationPolicy = "WhenEmpty"

        # 2시간. D-041 은 축소를 "cooldown 동안 정상 범위" 를 확인한 뒤 하라고
        # 하는데 Karpenter 는 그 판단을 못 한다. 그래서 **방송 한 편보다 긴**
        # 시간을 줘서, 중간에 잠깐 빈 것으로 반납하지 않게 한다.
        # 다시 사면 노드 준비에 90초가 또 든다.
        consolidateAfter = "2h"
      }

      # **비용 상한.** 이게 없으면 Pending 파드가 생기는 만큼 인스턴스가 계속
      # 늘어난다. 개인 계정이므로 반드시 건다. 관리형 노드그룹 2대와 별개로
      # Karpenter 가 추가로 살 수 있는 총량이다.
      limits = {
        cpu    = var.karpenter_cpu_limit
        memory = var.karpenter_memory_limit
      }
    }
  })

  depends_on = [kubectl_manifest.karpenter_node_class]
}
