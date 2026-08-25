# KEDA — 파드 자동 확장.
#
# **2차 보정이지 주력이 아니다.** HPA 반응은 43~63초(architecture.md 9.1)인데
# 방송 시작 스파이크는 30초 안에 끝난다. 주력은 큐시트 기반 사전 확장이고(D-041)
# KEDA 는 **예상보다 크거나 오래 지속되는 부하**를 받는다.
#
# KEDA 는 HPA 를 대체하지 않고 **HPA 를 만들어 쓴다.** ScaledObject 하나당
# `keda-hpa-<이름>` HPA 가 생긴다. 그것을 직접 고치면 KEDA 가 되돌리므로
# ScaledObject 쪽을 고친다. 같은 Deployment 에 HPA 를 따로 만들면 둘이 싸운다.
#
# 기본 HPA 로 안 되는 것을 사는 것이다 — SQS 큐 길이, cron, 0 으로 축소.
# `order-worker` 를 큐 길이로 늘리는 것이 이 스택을 넣는 실질적 이유다.
# CPU 만 보면 큐가 밀리는 것을 못 본다.

locals {
  # 큐 ARN 을 03-data 의 remote state 에서 읽으므로 데이터 배선도 켜져 있어야 한다.
  keda_identity = var.enable_keda && var.enable_app_data_wiring
}

resource "helm_release" "keda" {
  count = var.enable_keda ? 1 : 0

  name             = "keda"
  namespace        = var.keda_namespace
  create_namespace = true

  repository = "https://kedacore.github.io/charts"
  chart      = "keda"
  version    = var.keda_chart_version

  timeout = 600
  wait    = true

  values = [yamlencode({
    # 파드 셋(operator, metrics-apiserver, admission-webhooks)이 뜬다.
    # 차트 기본 requests 가 각 100m/100Mi 라 그대로 쓴다 — 2026-08-23 기준
    # 노드당 여유가 830~1,100m / 1,3xx Mi 라 넉넉하다.
    resources = {
      operator = {
        requests = { cpu = "100m", memory = "100Mi" }
        limits   = { memory = "512Mi" }
      }
      metricServer = {
        requests = { cpu = "100m", memory = "100Mi" }
        limits   = { memory = "512Mi" }
      }
      webhooks = {
        requests = { cpu = "50m", memory = "64Mi" }
        limits   = { memory = "256Mi" }
      }
    }

    # **관리형 노드그룹에만 뜨도록 묶는다** (`02-eks/nodegroup.tf` 의 labels).
    # Karpenter 컨트롤러와 같은 이유이고, 여기서는 더 직접적이다.
    #
    # KEDA 오퍼레이터는 죽지 않는 파드다. Karpenter 가 스파이크 때 산 노드에
    # 이것이 올라앉으면 `consolidationPolicy = WhenEmpty` 의 "비었다" 조건이
    # 영원히 안 맞아 **임시 노드가 상시 노드가 된다.** 2026-08-23 에 부하 테스트
    # 뒤 노드 한 대가 그렇게 남았다 — 파드는 정상이고 요금만 계속 나간다.
    #
    # 스케일러가 자기 스케일 대상 노드 위에 있는 것 자체도 곤란하다. 그 노드가
    # 반납되는 순간 스케일링이 멈춘다.
    #
    # 최상위 nodeSelector 하나가 세 파드(operator, metrics-apiserver, webhooks)에
    # 모두 적용된다 — 차트 2.17.2 기준.
    nodeSelector = { role = "general" }

    # ── AZ 이중화 ────────────────────────────────────────
    # 셋이 모두 하나뿐이라 같은 노드에 올라가 있었다. 그 노드를 잃으면
    # order-worker 의 자동 확장이 통째로 멈춘다 — 특가 구간에 큐가 쌓여도
    # 아무도 파드를 늘리지 않는다. cue-warmer 가 미리 올려둔 바닥값은
    # 남지만, 그것으로 모자랄 때 더 올리는 쪽이 KEDA 다(D-041 층 구조).
    #
    # 세 컴포넌트가 다중화되는 방식이 서로 다르다.
    #   operator       리더 선출(lease operator.keda.sh). 하나만 일하고
    #                  나머지는 대기하다 리더가 죽으면 넘겨받는다
    #   metricsServer  외부 지표 APIService. 무상태라 요청이 분산된다
    #   webhooks       검증 웹훅. 무상태. 이쪽이 죽어 있으면 ScaledObject
    #                  변경 자체가 거부되므로 오히려 다중화 이득이 크다
    #
    # 셋 다 ScheduleAnyway 다. DoNotSchedule 이면 한쪽 AZ 에 자리가 없을 때
    # 뜨지 못하는데, 오토스케일링이 아예 없는 것보다 한쪽에 몰리는 편이 낫다.
    operator      = { replicaCount = 2 }
    metricsServer = { replicaCount = 2 }
    webhooks      = { replicaCount = 2 }

    topologySpreadConstraints = {
      for c, label in {
        operator      = "keda-operator"
        metricsServer = "keda-operator-metrics-apiserver"
        webhooks      = "keda-admission-webhooks"
        } : c => [{
          maxSkew           = 1
          topologyKey       = "topology.kubernetes.io/zone"
          whenUnsatisfiable = "ScheduleAnyway"
          labelSelector     = { matchLabels = { "app.kubernetes.io/name" = label } }
      }]
    }
  })]

  depends_on = [aws_eks_access_policy_association.admin]
}

###############################################################################
# ScaledObject 는 여기에 두지 않는다
#
# `order-worker` 를 SQS 큐 길이로 늘리려면 두 가지가 먼저 있어야 한다.
#
# 1. **파드당 안전 처리량 실측.** D-041 이 계산식을 정해 뒀다.
#
#        desired_pods = ceil(expected_peak / safe_capacity_per_pod * safety_factor)
#
#    `safe_capacity_per_pod` 를 추정값으로 채우지 않는다. 주문 경로는 아직 부하
#    테스트를 안 했다 — measurements.md 에 api(M-009)와 chat-gateway(M-010)만 있다.
#
# 2. **매니페스트에서 `replicas` 제거.** KEDA 가 scale 을 소유하면 O2-live-deploy 의
#    `replicas` 를 지워야 한다. 안 지우면 KEDA 가 늘리고 Argo CD selfHeal 이
#    되돌리기를 무한 반복한다 — **에러가 안 나서 알아채기 늦다** (D-041, D-004).
#    `order-worker-deployment.yaml` 과 `chat-gateway-deployment.yaml` 에 이미
#    그 경고 주석이 달려 있다.
#
# 또 ScaledObject 는 애플리케이션 배포물이라 Argo CD 가 보는 O2-live-deploy 쪽이
# 자리로는 더 맞다. 여기는 컨트롤러 설치까지만 한다.
###############################################################################

###############################################################################
# KEDA 가 큐 길이를 읽을 자격증명
#
# SQS 스케일러는 `GetQueueAttributes` 로 큐 길이를 읽는다. 권한이 없으면
# **파드는 정상적으로 뜨고 스케일링만 안 된다** — ScaledObject 도 Ready 로
# 보이므로 알아채기 늦다.
#
# 워커의 역할을 빌려 쓰는 길(`identityOwner: workload`)은 택하지 않았다.
# 이 클러스터는 IRSA 가 아니라 EKS Pod Identity 라 KEDA 가 남의 association 을
# 대신 쓰는 경로가 확실하지 않고, 틀리면 위와 같은 방식으로 조용히 실패한다.
#
# 권한은 큐 길이 조회 하나뿐이다. KEDA 는 메시지를 읽지도 지우지도 않는다.
###############################################################################

data "aws_iam_policy_document" "keda_queue_depth" {
  count = local.keda_identity ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sqs:GetQueueAttributes"]
    # 주문 큐 하나다. Chat Signal 큐는 Lambda 가 소비하므로 KEDA 가 스케일할
    # 대상이 아니다 (D-048).
    resources = [local.datastore.order_queue_arn]
  }
}

resource "aws_iam_role" "keda" {
  count = local.keda_identity ? 1 : 0

  name = "${var.project}-${var.environment}-keda"
  # 앱 셋과 같은 신뢰 정책이다 (pods.eks.amazonaws.com).
  assume_role_policy = data.aws_iam_policy_document.app_assume[0].json
}

resource "aws_iam_role_policy" "keda_queue_depth" {
  count = local.keda_identity ? 1 : 0

  name   = "read-queue-depth"
  role   = aws_iam_role.keda[0].id
  policy = data.aws_iam_policy_document.keda_queue_depth[0].json
}

# ServiceAccount 는 Helm 차트가 만든다. association 은 이름 문자열로만 걸므로
# 여기서 따로 만들지 않는다 — 앱 셋(app_data_access.tf)과 다른 점이다.
resource "aws_eks_pod_identity_association" "keda" {
  count = local.keda_identity ? 1 : 0

  cluster_name    = local.cluster_name
  namespace       = var.keda_namespace
  service_account = "keda-operator"
  role_arn        = aws_iam_role.keda[0].arn

  depends_on = [
    aws_iam_role_policy.keda_queue_depth,
    helm_release.keda,
  ]
}

###############################################################################
# apply 뒤에 한 번 해야 하는 것
#
#   kubectl rollout restart deploy/keda-operator -n keda
#
# Pod Identity 자격증명은 파드가 **생성될 때** 주입된다. 이미 떠 있는 파드는
# association 을 걸어도 그대로 자격증명이 없다.
###############################################################################
