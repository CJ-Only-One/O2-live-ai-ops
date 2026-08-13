# Argo CD 설치와, 이 클러스터가 무엇을 배포해야 하는지 알려주는 Application.
#
# 둘을 한 릴리스에 담는다. 차트가 CRD를 먼저 설치(crds.install=true)한 뒤
# extraObjects를 적용하므로, Application CRD가 없어서 실패하는 일이 없다.
# 별도로 kubectl apply를 돌리면 kubeconfig가 필요해지는데, 그러면
# "터미널에서 사람이 한 번 쳐야 하는 단계"가 다시 생긴다.

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
      resources = {
        requests = { cpu = "25m", memory = "64Mi" }
        limits   = { memory = "128Mi" }
      }
    }
    notifications = {
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

    # ── 이 클러스터가 배포할 것 ────────────────────────────
    extraObjects = [
      {
        apiVersion = "argoproj.io/v1alpha1"
        kind       = "Application"
        metadata = {
          name      = "o2-dev"
          namespace = "argocd"
          finalizers = [
            # Application을 지울 때 배포된 리소스도 함께 정리한다.
            "resources-finalizer.argocd.argoproj.io",
          ]
        }
        spec = {
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
          syncPolicy = {
            automated = {
              # Git에 없는 리소스를 클러스터에서 지운다.
              prune = true
              # kubectl로 손댄 것을 되돌린다. Git을 유일한 진실로 만드는 스위치.
              selfHeal = true
            }
            syncOptions = ["CreateNamespace=true"]
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
      },
    ]
  })]

  # access entry가 먼저 있어야 helm 프로바이더가 클러스터에 인증할 수 있다.
  depends_on = [aws_eks_access_policy_association.admin]
}
