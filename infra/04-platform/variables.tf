variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "team" {
  type    = string
  default = "o2"
}

variable "project" {
  type    = string
  default = "o2"
}

variable "environment" {
  type    = string
  default = "dev"
}

# ── 02-eks 의 state 위치 ──────────────────────────────────────
variable "state_bucket" {
  description = "팀 공용 Terraform state 버킷"
  type        = string
  default     = "o2-tfstate-066107819912"
}

variable "eks_state_key" {
  type    = string
  default = "eks/terraform.tfstate"
}

# ── 클러스터 접근 ─────────────────────────────────────────────
variable "cluster_admin_arns" {
  description = <<-EOT
    클러스터 관리자 권한을 줄 IAM 주체 목록.
    클러스터를 다시 만들 때마다 access entry가 초기화되므로 코드로 남긴다.

    사람 단위(IAM User)로 나열하는 이유:
    EKS access entry는 **IAM 그룹을 대상으로 잡을 수 없다.** 사용자 또는 역할만 가능하다.
    Only_One 그룹에 붙이는 식으로는 해결되지 않는다.

    팀이 더 커지면 IAM Role 하나를 만들고 그것만 여기 넣은 뒤 팀원이 assume
    하게 바꾸는 편이 낫다. 그러면 팀원 추가가 IAM 그룹 편집으로 끝난다.
    지금은 5명이라 나열이 더 단순하다.

    권한 수준에 대해:
    이 계정의 Only_One 그룹에 AdministratorAccess가 붙어 있어 팀원 전원이
    이미 AWS 관리자다. 따라서 EKS 권한을 좁혀도 보안 경계가 되지는 않는다
    (본인이 직접 access entry를 만들 수 있다). 좁히는 실익은 사고 방지다.
    필요하면 AmazonEKSEditPolicy 나 View로 낮추고 access_scope를 네임스페이스로
    제한할 것.
  EOT
  type        = list(string)
  default = [
    "arn:aws:iam::066107819912:user/LSM",
    "arn:aws:iam::066107819912:user/KDH",
    "arn:aws:iam::066107819912:user/KSY",
    "arn:aws:iam::066107819912:user/STY",
  ]
  # role/o2-live-github-tf 는 뺐다. 이 스택을 plan하려면 클러스터를 읽어야 해서
  # 넣었었는데, 그 결과 PR에서 도는 plan이 클러스터 관리자 권한을 쥐게 됐다.
  # plan은 임의 코드를 실행할 수 있으므로 AWS 권한만 읽기 전용으로 낮춰서는
  # 구멍이 닫히지 않는다. tf.yml 에서 04-platform 을 빼고 로컬에서 plan한다.
  # (docs/decisions.md D-011)
  #
  # 앱 배포용 역할(o2-live-github-app)에는 애초에 주지 않는다. GitOps라
  # 애플리케이션 CD는 클러스터에 접근할 일이 없다. (D-004)
  # user/JYC 는 넣지 않는다. 클러스터를 만든 주체에게는 EKS가 생성 시점에
  # 관리자 access entry를 자동 부여하므로, 여기 넣으면 이미 있는 것을 또
  # 만들려다 ResourceInUseException 으로 실패한다.
  #
  # 주의: 클러스터를 다른 사람이 다시 만들면 자동 부여 대상이 그 사람으로
  # 바뀐다. 그때는 JYC를 이 목록에 넣고 새 생성자를 빼야 한다.
}

# ── Argo CD ───────────────────────────────────────────────────
variable "argocd_chart_version" {
  description = "argo-cd 차트 버전. 10.2.2 = Argo CD v3.4.6"
  type        = string
  default     = "10.2.2"
}

variable "manifest_repo_url" {
  description = "Argo CD가 감시할 매니페스트 저장소"
  type        = string
  default     = "https://github.com/CJ-Only-One/O2-live-deploy"
}

variable "enable_dex" {
  description = "SSO(GitHub 로그인)를 붙일 때 true. 그 전까지는 파드와 메모리를 아낀다"
  type        = bool
  default     = false
}

# ── AWS Load Balancer Controller ──────────────────────────────
variable "enable_lbc" {
  type    = bool
  default = true
}

variable "lbc_chart_version" {
  type    = string
  default = "3.5.0"
}

variable "argocd_apps_chart_version" {
  description = "argocd-apps 차트. Application 리소스만 담는 얇은 차트다"
  type        = string
  default     = "2.0.5"
}

# ── Datadog ────────────────────────────────────────────────────
variable "enable_datadog" {
  description = "Datadog Agent와 External Secrets Operator를 설치할지 여부. Secrets Manager 원본 키를 먼저 만들고 true로 바꿀 것"
  type        = bool
  default     = false
}

variable "datadog_chart_version" {
  description = "Datadog Helm chart. EKS control plane monitoring 지원 최소 버전은 3.152.0"
  type        = string
  default     = "3.152.0"
}

variable "datadog_namespace" {
  description = "Datadog Agent 전용 네임스페이스"
  type        = string
  default     = "datadog"
}

variable "datadog_kubernetes_secret_name" {
  description = "ESO가 생성하고 Datadog Helm chart가 참조하는 Kubernetes Secret 이름"
  type        = string
  default     = "datadog-secret"
}

variable "datadog_secrets_manager_secret_name" {
  description = "api-key와 app-key JSON을 보관하는 AWS Secrets Manager 원본 Secret 이름. 이 리소스는 platform stack이 소유하지 않는다"
  type        = string
  default     = "o2/dev/datadog"
}

variable "datadog_secret_refresh_interval" {
  description = "ESO가 Secrets Manager에서 Datadog 키 변경을 확인하는 주기"
  type        = string
  default     = "1h"
}

variable "datadog_site" {
  description = "Datadog site. 현재 계정은 AP1 사이트를 사용한다"
  type        = string
  default     = "ap1.datadoghq.com"
}

# ── External Secrets Operator ───────────────────────────────────
variable "external_secrets_namespace" {
  description = "External Secrets Operator 전용 네임스페이스"
  type        = string
  default     = "external-secrets"
}

variable "external_secrets_chart_version" {
  description = "External Secrets Operator Helm chart. 보안 패치는 해당 차트의 최신 지원 minor로 올릴 것"
  type        = string
  default     = "2.8.0"
}
