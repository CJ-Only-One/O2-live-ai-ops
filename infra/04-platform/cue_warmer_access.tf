# cue-warmer(apps/cue-warmer) 에게 클러스터 안 스케일 권한을 준다.
#
# action_executor_access.tf 와 같은 권한(deployments/scale get·patch)이지만
# 주체가 다르다. 저쪽은 클러스터 **밖** Lambda 라 IAM Role + EKS access entry
# 로 신원을 만들어야 하고, 이쪽은 클러스터 **안** 파드라 ServiceAccount 하나면
# 끝난다 — 그래서 access entry 도 IAM Role 도 없다.
#
# app_service_accounts(변수)에는 안 넣는다. 그 목록은 Pod Identity 로 AWS
# 자격증명을 받을 ServiceAccount 들이고, cue-warmer 는 AWS API 를 하나도
# 부르지 않는다(MySQL 은 네트워크, api 는 HTTP, 여기 k8s API 는 SA 토큰).
#
# 권한 범위는 o2-dev 의 deployments/scale 서브리소스, get·patch 뿐이다.
# deployments 본체가 아니라 scale 서브리소스라 이미지·env·probe 같은 것은
# 못 만진다 — 파드 수 말고는 바꿀 수 있는 게 없다.

# ServiceAccount 는 토글에 묶지 않는다. 매니페스트가 serviceAccountName 으로
# 이것을 가리키는데, 없으면 쿠버네티스가 **파드 생성 자체를 거부한다** —
# 스케일이 꺼져 있어도 캐시 워밍까지 같이 멈춘다.
#
# 게다가 replicas 1 + 기본 전략이면 maxUnavailable 이 0 이라 옛 파드가 살아남아
# 머지 시점에는 멀쩡해 보인다. Deployment 는 Progressing 에서 막혀 있고, 이후
# 이미지 갱신이 조용히 반영 안 되다가, 노드 교체로 그 파드가 빠지는 순간
# 대체 없이 사라진다.
#
# 아래 Role·RoleBinding 만 토글로 묶는다. 그래야 "꺼도 파드는 뜨고 스케일
# 호출만 403" 이 실제로 참이 된다.
resource "kubectl_manifest" "cue_warmer_service_account" {
  yaml_body = yamlencode({
    apiVersion = "v1"
    kind       = "ServiceAccount"
    metadata = {
      name      = "cue-warmer"
      namespace = var.app_namespace
      labels = {
        "app.kubernetes.io/managed-by" = "terraform"
      }
    }
  })
}

resource "kubectl_manifest" "cue_warmer_role" {
  count = var.enable_cue_warmer_scaling ? 1 : 0

  yaml_body = yamlencode({
    apiVersion = "rbac.authorization.k8s.io/v1"
    kind       = "Role"
    metadata = {
      name      = "o2-cue-warmer"
      namespace = var.app_namespace
      labels = {
        "app.kubernetes.io/managed-by" = "terraform"
      }
    }
    rules = [
      {
        apiGroups = ["apps"]
        resources = ["deployments/scale"]
        verbs     = ["get", "patch"]
      },
      {
        # order-worker 는 Deployment 의 replicas 를 KEDA 가 소유해서 그쪽을
        # patch 하면 다음 조절 주기에 되돌려진다. 워머는 ScaledObject 의
        # minReplicaCount(바닥)만 올리고 KEDA 가 그 위에서 조절하게 둔다.
        #
        # scale 서브리소스처럼 필드를 좁힐 수단이 없어 리소스 단위로 준다 —
        # ScaledObject 는 CRD 라 서브리소스가 없다. 대신 대상이 o2-dev
        # 네임스페이스로 묶여 있고 삭제·생성 권한은 없다.
        apiGroups = ["keda.sh"]
        resources = ["scaledobjects"]
        verbs     = ["get", "patch"]
      },
    ]
  })
}

resource "kubectl_manifest" "cue_warmer_role_binding" {
  count = var.enable_cue_warmer_scaling ? 1 : 0

  yaml_body = yamlencode({
    apiVersion = "rbac.authorization.k8s.io/v1"
    kind       = "RoleBinding"
    metadata = {
      name      = "o2-cue-warmer"
      namespace = var.app_namespace
      labels = {
        "app.kubernetes.io/managed-by" = "terraform"
      }
    }
    subjects = [
      {
        kind      = "ServiceAccount"
        name      = "cue-warmer"
        namespace = var.app_namespace
      },
    ]
    roleRef = {
      kind     = "Role"
      name     = "o2-cue-warmer"
      apiGroup = "rbac.authorization.k8s.io"
    }
  })

  depends_on = [
    kubectl_manifest.cue_warmer_role,
    kubectl_manifest.cue_warmer_service_account,
  ]
}

# RoleBinding 이 참조하는 SA 는 토글과 무관하게 위에서 항상 만들어진다.
# 바인딩만 없으면 그 SA 토큰으로는 scale 을 못 불러 403 이 나고, 캐시 워밍은
# 그대로 돈다 — 그게 이 토글이 의도하는 상태다.
