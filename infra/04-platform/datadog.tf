# Datadog Agent for EKS.
#
# API/App key는 Terraform 변수나 Helm values에 직접 넣지 않는다. 키 원문은
# Secrets Manager에만 있고, ESO가 Kubernetes Secret으로 동기화한다. Terraform은
# Secret ARN/이름 같은 메타데이터만 state에 기록한다.
resource "helm_release" "datadog" {
  count = var.enable_datadog ? 1 : 0

  name             = "datadog"
  namespace        = var.datadog_namespace
  create_namespace = false

  repository = "https://helm.datadoghq.com"
  chart      = "datadog"
  # EKS control plane monitoring 지원 최소 차트 버전(3.152.0)으로 고정한다.
  # 업그레이드는 릴리스 노트와 Datadog 비용 변화를 검토한 PR에서만 수행한다.
  version = var.datadog_chart_version

  timeout = 900
  wait    = true

  values = [yamlencode({
    datadog = {
      # ap1 조직의 intake endpoint. US site 기본값을 쓰면 데이터가 전송되지 않는다.
      site                 = var.datadog_site
      clusterName          = local.cluster_name
      apiKeyExistingSecret = var.datadog_kubernetes_secret_name
      appKeyExistingSecret = var.datadog_kubernetes_secret_name

      # 모든 telemetry에 붙는 저카디널리티 태그. 비용 분석과 환경 분리에 사용한다.
      tags = [
        "env:${var.environment}",
        "project:${var.project}",
        "team:${var.team}",
      ]

      # Node Agent: kubelet/cAdvisor에서 노드, 파드, 컨테이너의 CPU·메모리·네트워크
      # 메트릭을 수집한다. Cluster Agent: Kubernetes API의 상태 메트릭을 중앙 수집한다.
      kubeStateMetricsEnabled = false
      kubeStateMetricsCore = {
        enabled                   = true
        ignoreLegacyKSMCheck      = true
        collectConfigMaps         = false
        collectSecretMetrics      = false
        collectCrdMetrics         = false
        collectApiServicesMetrics = false
      }

      # Container Explorer에는 Process Agent가 필요하지만, 지금은 프로세스 목록까지
      # 보내지 않는다. 메트릭 전용 범위를 유지하고 필요할 때만 별도로 활성화한다.
      processAgent = {
        enabled           = true
        processCollection = false
      }

      # 이번 범위는 메트릭과 Kubernetes 이벤트다. 로그/APM은 데이터량과 과금 모델이
      # 달라 명시적으로 끈다.
      logs = {
        enabled = false
      }
      apm = {
        socketEnabled = false
      }

      collectEvents = true
      kubernetesEvents = {
        # 실패·스케줄링·노드 이상 이벤트만 모아 이벤트 폭주를 피한다.
        filteringEnabled = true
      }

      # 애플리케이션 이름만 태그로 승격한다. 요청 ID 같은 고카디널리티 라벨은 넣지 않는다.
      podLabelsAsTags = {
        "app.kubernetes.io/name"    = "kube_app"
        "app.kubernetes.io/part-of" = "kube_part_of"
      }
    }

    clusterAgent = {
      enabled      = true
      replicaCount = 1
      resources = {
        requests = { cpu = "100m", memory = "256Mi" }
        limits   = { memory = "384Mi" }
      }
    }

    agents = {
      containers = {
        agent = {
          resources = {
            requests = { cpu = "100m", memory = "256Mi" }
            limits   = { memory = "512Mi" }
          }
        }
      }
    }

    # EKS API Server, Controller Manager, Scheduler 메트릭을 Cluster Check로 수집한다.
    # 이 기능은 Datadog App Key가 있어야 하며 Helm chart 3.152.0 이상이 필요하다.
    providers = {
      eks = {
        controlPlaneMonitoring = true
      }
    }
  })]

  # ExternalSecret이 먼저 Kubernetes Secret을 만들도록 순서를 강제한다.
  depends_on = [kubectl_manifest.datadog_external_secret]
}
