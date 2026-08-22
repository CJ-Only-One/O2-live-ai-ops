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
      # us5 조직의 intake endpoint. 기본값(US1)을 쓰면 데이터가 전송되지 않는다.
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

      # 로그는 계속 끈다. 데이터량이 곧 요금이고, 지금 필요한 것은 로그 본문이
      # 아니라 "어느 구간이 느린가" 다.
      logs = {
        enabled = false
      }

      # APM. 파드 지표는 "api 가 느리다" 까지만 말해주고 그 안에서 Valkey 냐
      # MySQL 이냐를 가르지 못한다. 장애 감별이 목적이므로 구간별 시간이 필요하다.
      apm = {
        # UDS 대신 hostPort 로 받는다. 소켓 방식은 애플리케이션 파드마다
        # hostPath 볼륨을 마운트해야 하는데, 그러면 매니페스트 셋을 모두 고치고
        # 파드에 노드 파일시스템 접근을 주게 된다. hostPort 는 DD_AGENT_HOST 를
        # status.hostIP 로 주입하는 것으로 끝난다.
        portEnabled   = true
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

        # trace-agent 에 값을 주지 않으면 request·limit 이 모두 비어 QoS 가
        # BestEffort 가 된다. 노드 메모리가 모자랄 때 가장 먼저 죽는 쪽이고,
        # 상한이 없어 반대로 노드를 다 먹을 수도 있다. APM 은 트래픽에
        # 비례해 커지므로 부하 구간에서 특히 그렇다.
        traceAgent = {
          resources = {
            requests = { cpu = "50m", memory = "64Mi" }
            limits   = { memory = "192Mi" }
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
