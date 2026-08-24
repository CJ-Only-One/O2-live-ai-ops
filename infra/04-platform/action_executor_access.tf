# 조치 실행기(infra/06-agent/action_executor.tf) Lambda 에게 클러스터 접근을
# 준다. 그 스택이 아니라 여기인 이유는 "클러스터 안 권한은 04-platform 이
# 코드로 갖는다"(D-008)는 기존 규칙과 같다 — app_data_access.tf 가 03-data
# 를 참조하는 것과 같은 모양으로, 여기서는 06-agent 를 참조한다.
#
# 권한 범위: o2-dev 네임스페이스의 deployments/scale 서브리소스, get·patch
# 뿐이다. cluster_admin_arns(main.tf)와 이름이 비슷해 보이지만 전혀 다른
# 성격이다 — admin 은 이미 AdministratorAccess 를 가진 사람들이라 EKS 권한을
# 좁혀도 보안 경계가 아니라고 그 변수 설명에 적혀 있다. 이 Role 은 사람이
# 아니라 Lambda 실행 역할이고 다른 AWS 권한이 없으므로, 여기서 좁히는 것이
# 실제 보안 경계가 된다.

data "terraform_remote_state" "agent" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = var.agent_state_key
    region = var.region
  }
}

locals {
  scale_executor_role_arn = data.terraform_remote_state.agent.outputs.scale_executor_role_arn
}

# IAM Role 하나를 K8s 그룹 하나에 매핑한다. AWS 관리형 access policy(admin
# access entry 가 쓰는 것)는 네임스페이스나 서브리소스 단위로 못 좁힌다 —
# 그래서 여기는 access policy 를 안 붙이고, 아래 RBAC Role/RoleBinding 으로
# 직접 권한을 준다.
resource "aws_eks_access_entry" "scale_executor" {
  cluster_name      = local.cluster_name
  principal_arn     = local.scale_executor_role_arn
  type              = "STANDARD"
  kubernetes_groups = ["o2-action-executor"]
}

resource "kubectl_manifest" "scale_executor_role" {
  yaml_body = yamlencode({
    apiVersion = "rbac.authorization.k8s.io/v1"
    kind       = "Role"
    metadata = {
      name      = "o2-action-executor"
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
    ]
  })
}

resource "kubectl_manifest" "scale_executor_role_binding" {
  yaml_body = yamlencode({
    apiVersion = "rbac.authorization.k8s.io/v1"
    kind       = "RoleBinding"
    metadata = {
      name      = "o2-action-executor"
      namespace = var.app_namespace
      labels = {
        "app.kubernetes.io/managed-by" = "terraform"
      }
    }
    subjects = [
      {
        kind     = "Group"
        name     = "o2-action-executor"
        apiGroup = "rbac.authorization.k8s.io"
      },
    ]
    roleRef = {
      kind     = "Role"
      name     = "o2-action-executor"
      apiGroup = "rbac.authorization.k8s.io"
    }
  })

  depends_on = [kubectl_manifest.scale_executor_role]
}
