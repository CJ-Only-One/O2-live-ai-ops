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

    지금은 사람 단위(IAM User)로 나열하지만, 팀이 커지면
    IAM Role 하나를 만들고 그것만 여기 넣은 뒤 팀원이 assume 하게 바꾸는 편이 낫다.
    그러면 팀원 추가가 IAM 그룹 편집으로 끝나고 이 파일을 안 건드려도 된다.
  EOT
  type        = list(string)
  default = [
    "arn:aws:iam::066107819912:user/LSM",
  ]
  # 클러스터를 만든 주체(현재 user/JYC)는 EKS가 생성 시점에 자동으로
  # 관리자 access entry를 부여한다. 여기 넣으면 이미 있는 것을 또 만들려다
  # ResourceInUseException 으로 실패한다. EKS가 관리하는 것은 건드리지 않는다.
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
