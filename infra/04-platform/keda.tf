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
