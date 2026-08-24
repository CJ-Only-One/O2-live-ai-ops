# Argo CD 설치와, 이 클러스터가 무엇을 배포해야 하는지 알려주는 Application.
#
# 릴리스를 둘로 나눈다. 처음에는 argo-cd 차트의 extraObjects에 Application을
# 함께 넣었는데, 헬름이 렌더링한 객체를 적용 전에 클러스터 API와 대조하는
# 시점에는 아직 CRD가 없어 실패했다:
#
#   no matches for kind "Application" in version "argoproj.io/v1alpha1"
#
# 같은 릴리스에서 CRD를 설치하면서 그 CRD의 인스턴스를 만들 수는 없다.
# argocd-apps 차트가 정확히 이 용도이므로 그것을 두 번째 릴리스로 둔다.
#
# kubectl apply로 처리하면 kubeconfig가 필요해져서
# "사람이 터미널에서 한 번 쳐야 하는 단계"가 다시 생긴다. 그래서 헬름으로 푼다.

resource "helm_release" "argocd" {
  name             = "argocd"
  namespace        = "argocd"
  create_namespace = true

  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argo-cd"
  # 차트 10.2.2 = Argo CD v3.4.6.
  # 버전을 고정하지 않으면 클러스터를 다시 만들 때마다 다른 버전이 깔린다.
  version = var.argocd_chart_version

  # CRD 설치와 파드 기동에 시간이 걸린다.
  timeout = 900
  wait    = true

  values = [yamlencode({
    # ── 리소스 요청량 ──────────────────────────────────────
    # 차트 기본값에는 requests가 없어 파드가 BestEffort QoS가 된다.
    # 그러면 노드 메모리가 압박받을 때 가장 먼저 축출되는데,
    # 배포 시스템이 부하 상황에서 먼저 죽으면 복구 수단을 잃는다.
    # t3.small(할당 가능 ~1.4GiB) 2대 기준으로 잡은 값이다.
    controller = {
      resources = {
        requests = { cpu = "100m", memory = "256Mi" }
        limits   = { memory = "512Mi" }
      }
    }
    repoServer = {
      resources = {
        # 매니페스트를 렌더링할 때 메모리가 튀는 지점이라 여유를 둔다.
        requests = { cpu = "50m", memory = "192Mi" }
        limits   = { memory = "512Mi" }
      }
    }
    server = {
      resources = {
        requests = { cpu = "50m", memory = "128Mi" }
        limits   = { memory = "256Mi" }
      }
    }
    redis = {
      resources = {
        requests = { cpu = "50m", memory = "64Mi" }
        limits   = { memory = "128Mi" }
      }
    }
    applicationSet = {
      # ApplicationSet CR을 쓰지 않는다. 매니페스트 저장소 루트를 통째로 보는
      # Application 하나뿐이라 서비스를 추가해도 Application 수가 늘지 않는다.
      # 서비스별로 Application을 쪼개고 싶어지면 그때 true로 되돌린다.
      #
      # 끈 상태에서도 CRD는 남는다. ApplicationSet을 만들면 apply는 성공하지만
      # 컨트롤러가 없어 아무 일도 일어나지 않으니, 쓸 때 이 값부터 확인할 것.
      enabled = false
      resources = {
        requests = { cpu = "25m", memory = "64Mi" }
        limits   = { memory = "128Mi" }
      }
    }
    notifications = {
      # 알림은 Datadog으로 보낸다. 여기에 또 두면 경로가 둘로 갈린다.
      # cm에 트리거도 구독 애노테이션도 없어 지금은 아무것도 보내지 않는다.
      enabled = false
      resources = {
        requests = { cpu = "25m", memory = "64Mi" }
        limits   = { memory = "128Mi" }
      }
    }
    dex = {
      # SSO를 아직 안 쓴다. 파드 하나와 메모리를 아낀다.
      # GitHub 로그인을 붙일 때 true로 바꾸고 configs.cm에 연동 설정을 넣는다.
      enabled = var.enable_dex
    }

    configs = {
      params = {
        # 외부 노출 전까지는 TLS 종단이 필요 없다. port-forward로 접근한다.
        # Ingress를 붙일 때 이 값을 지우고 ALB에서 TLS를 종단한다.
        "server.insecure" = true
      }
    }

  })]

  # access entry가 먼저 있어야 helm 프로바이더가 클러스터에 인증할 수 있다.
  depends_on = [aws_eks_access_policy_association.admin]
}

# ── 이 클러스터가 배포할 것 ──────────────────────────────────
# Argo CD가 CRD를 설치한 뒤에 적용되어야 하므로 별도 릴리스로 둔다.
resource "helm_release" "argocd_apps" {
  name      = "argocd-apps"
  namespace = "argocd"

  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argocd-apps"
  version    = var.argocd_apps_chart_version

  values = [yamlencode({
    applications = {
      "o2-dev" = {
        namespace = "argocd"
        finalizers = [
          # Application을 지울 때 배포된 리소스도 함께 정리한다.
          "resources-finalizer.argocd.argoproj.io",
        ]
        project = "default"
        source = {
          # 매니페스트 전용 저장소. public이라 자격증명이 필요 없다.
          # 앱 저장소와 나눈 이유는 docs/decisions.md D-006 참고.
          repoURL        = var.manifest_repo_url
          targetRevision = "main"
          path           = "."
          directory = {
            recurse = false
            exclude = "README.md"
          }
        }
        destination = {
          server    = "https://kubernetes.default.svc"
          namespace = "o2-dev"
        }
        # replicas 를 사람 아닌 것이 만지는 Deployment 는 이 목록에 넣는다.
        # 정상 기준값을 Git 에 남겨야 실험 종료 후 되돌릴 기준이 생기므로
        # 필드를 지우지 않고 이 필드만 selfHeal 대상에서 제외한다.
        # (KEDA 가 소유하는 order-worker 는 아예 필드가 없어 해당 없음)
        #
        # 넣지 않으면 늘린 쪽과 Argo 가 서로 되돌리기를 무한 반복한다.
        # 양쪽 다 자기 일을 정상적으로 했다고만 로그를 남겨 알아채기 늦다
        # (D-004, D-041).
        #
        # ★ Git 의 값은 **정상 기준값**이지 조치 직전 값이 아니다. 실험 중에는
        #   둘이 다를 수 있다 — 증설로 3 이 된 뒤 격리가 들어오면 되돌릴 곳은
        #   Git 의 2 가 아니라 관측된 3 이다. 그 값은 06-agent 의 action_state
        #   `record_restore` 가 조치 기록에 남기고 `judge` 응답이 같이 돌려준다
        #   (D-074). 예외만 켜고 그쪽을 배포하지 않으면 원복이 정상 기준값으로
        #   점프해 중간 단계를 건너뛴다.
        ignoreDifferences = [
          {
            # S2 에서 런북이 일시적으로 2 -> 3 -> 2 로 바꾼다.
            # 원복은 상태 머신/Runbook 책임이다(docs/scenario-experiment.md 3절).
            group        = "apps"
            kind         = "Deployment"
            name         = "api"
            namespace    = "o2-dev"
            jsonPointers = ["/spec/replicas"]
          },
          {
            # cue-warmer 가 큐시트의 진입·게스트 세그먼트 앞에서 미리 늘린다
            # (D-041 사전 확장). 방송 중에는 줄이지 않는다 — 축소는 가용성
            # 위험이라 cooldown·backlog·활성 연결을 확인하는 결정론적 단계로만
            # 하고, WebSocket 연결이 끊기는 chat-gateway 는 특히 그렇다.
            group        = "apps"
            kind         = "Deployment"
            name         = "chat-gateway"
            namespace    = "o2-dev"
            jsonPointers = ["/spec/replicas"]
          },
        ]
        syncPolicy = {
          automated = {
            # Git에 없는 리소스를 클러스터에서 지운다.
            prune = true
            # kubectl로 손댄 것을 되돌린다. Git을 유일한 진실로 만드는 스위치.
            selfHeal = true
          }
          # ignoreDifferences를 diff 화면에만 숨기지 않고 실제 sync에도 적용한다.
          syncOptions = ["CreateNamespace=true", "RespectIgnoreDifferences=true"]
          retry = {
            limit = 3
            backoff = {
              duration    = "10s"
              factor      = 2
              maxDuration = "2m"
            }
          }
        }
      }
    }
  })]

  # CRD가 먼저 있어야 Application을 만들 수 있다.
  depends_on = [helm_release.argocd]
}
