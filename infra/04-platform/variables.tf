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

    # tf.yml 이 쓰는 역할. 이 스택이 헬름 릴리스(Argo CD, LBC)를 관리하므로
    # plan 단계에서도 클러스터 상태를 읽어야 한다. 없으면 CI가
    # "Kubernetes cluster unreachable" 로 실패한다.
    #
    # 앱 배포용 역할(o2-live-github-app)에는 주지 않는다. GitOps라
    # 애플리케이션 CD는 클러스터에 접근할 일이 없다. (docs/decisions.md D-004)
    "arn:aws:iam::066107819912:role/o2-live-github-tf",
  ]
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
