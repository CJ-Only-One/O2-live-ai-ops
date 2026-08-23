variable "team" {
  description = "팀 식별자. 태그로만 사용"
  type        = string
  default     = "o2"
}

variable "project" {
  description = "리소스 prefix. 소문자/하이픈만"
  type        = string
  default     = "o2"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", var.project))
    error_message = "소문자, 숫자, 하이픈만 허용."
  }
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "cluster_name" {
  description = "network 스택의 eks_cluster_name과 반드시 동일해야 한다 (서브넷 discovery 태그)"
  type        = string
  default     = "o2-eks"
}

variable "kubernetes_version" {
  description = <<-EOT
    표준 지원 버전만 사용할 것.
    확장 지원 버전은 $0.10/hr -> $0.60/hr 로 6배가 된다.
    2026-08 기준 표준 지원: 1.34, 1.35, 1.36 / 1.33은 2026-07-29 종료됨.
    apply 전 확인: aws eks describe-cluster-versions --region ap-northeast-2
  EOT
  type        = string
  default     = "1.35"
}

variable "network_state_bucket" {
  description = "network 스택의 S3 backend 버킷"
  type        = string
}

variable "network_state_key" {
  type    = string
  default = "network/terraform.tfstate"
}

variable "node_instance_types" {
  description = <<-EOT
    현재 워크로드: 테스트 페이지 2 Pod + LBC + CoreDNS + DaemonSet 2종.
    노드당 실제 Pod 수는 5개 내외다.

    t3.small (2vCPU burst / 2GiB, max-pods 11)  <- 현재 기본값
      allocatable 약 1.4GiB. coredns 70Mi + lbc 200Mi + nginx 64Mi 로 충분하다.
    t3.medium (2vCPU / 4GiB, max-pods 17)
      테스트 페이지 외에 뭐라도 하나 더 올리는 순간 이쪽으로 올려야 한다.

    t3.small 선택 근거: 3주 기준 t3.medium 대비 약 $27 절감.

    부족해지면 instance_types만 바꾸면 되지만 **롤링 교체가 아니다.**
    이 값은 ForceNew라 plan에 `must be replaced`가 뜨고, node_group_name이
    "default"로 고정돼 있어 create_before_destroy도 못 건다. 즉 노드그룹을
    지운 뒤 새로 만든다 — 그동안 노드가 0대이고 모든 Pod가 Pending이다.
    서비스가 뜬 상태에서 바꾸려면 중단 창을 잡고 해라.
  EOT
  type        = list(string)
  default     = ["t3.small"]
}

variable "node_capacity_type" {
  description = <<-EOT
    ON_DEMAND | SPOT
    Phase 1은 ON_DEMAND 권장. 파이프라인 디버깅 중 Spot 회수가 발생하면
    "CI/CD가 실패한 것인지 노드가 사라진 것인지" 원인 분리가 어려워진다.
    Phase 3 부하테스트에서는 SPOT으로 전환해 비용을 3분의 1로 낮춘다.
  EOT
  type        = string
  default     = "ON_DEMAND"
}

variable "node_desired_size" {
  type    = number
  default = 2
}

variable "node_min_size" {
  type    = number
  default = 2
}

variable "node_max_size" {
  type    = number
  default = 4
}

variable "node_disk_size" {
  description = "GiB. 컨테이너 이미지 캐시 여유분 포함"
  type        = number
  default     = 30
}

variable "cluster_public_access_cidrs" {
  description = <<-EOT
    퍼블릭 엔드포인트 접근 허용 대역.
    GitHub Actions 러너 IP는 고정할 수 없어 기본값이 0.0.0.0/0 이다.
    인증은 IAM(access entry)이 담당하므로 무인증 접근은 불가하나,
    엔드포인트가 인터넷에 노출되는 것 자체가 싫다면
    self-hosted runner를 VPC 안에 두고 이 값을 사무실 IP로 좁혀야 한다.
  EOT
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "control_plane_log_types" {
  description = <<-EOT
    CloudWatch Logs 과금 대상.
    Phase 1은 api/authenticator만. audit은 볼륨이 크고 Phase 2 보안 트랙에서 켠다.
  EOT
  type        = list(string)
  default     = ["api", "authenticator"]
}

variable "control_plane_log_retention_days" {
  type    = number
  default = 7
}

variable "enable_karpenter" {
  description = <<-EOT
    Karpenter 용 IAM·SQS·EventBridge 를 만든다. Helm 설치는 04-platform 이 한다.

    **4차 안전망이지 주력이 아니다.** 노드 확보에 최소 26초(2026-08-21 실측) +
    이미지 pull 이 걸리는데 방송 시작 스파이크는 30초 안에 끝난다. 주력은 큐시트
    기반 사전 확장이고(D-041), Karpenter 는 예상 밖 Pending Pod 와 노드 장애를 받는다.

    끄면 IAM 역할과 큐가 지워진다. Helm 릴리스를 먼저 내린 뒤 끌 것 —
    순서를 바꾸면 컨트롤러가 권한을 잃은 채로 남아 노드를 정리하지 못한다.
  EOT
  type        = bool
  default     = false
}
