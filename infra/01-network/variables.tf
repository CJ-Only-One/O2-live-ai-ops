variable "team" {
  description = "팀 식별자. 태그로만 사용"
  type        = string
  default     = "o2"
}

variable "project" {
  description = <<-EOT
    프로젝트 식별자. 모든 리소스 이름/태그 prefix로 사용.
    소문자/하이픈만 사용할 것 (S3 버킷명, ECR 저장소명, k8s 라벨 제약).
    "O2" 나 "o 2" 처럼 공백이 들어가면 apply가 실패한다.
  EOT
  type        = string
  default     = "o2"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", var.project))
    error_message = "소문자, 숫자, 하이픈만 허용. 공백/대문자/언더스코어 불가."
  }
}

variable "environment" {
  description = "환경 구분 (dev/stg/prod). 3주 프로젝트는 dev 단일 환경 권장"
  type        = string
  default     = "dev"
}

variable "region" {
  description = "AWS 리전"
  type        = string
  default     = "ap-northeast-2"
}

variable "availability_zones" {
  description = <<-EOT
    사용할 AZ 목록. EKS 컨트롤플레인은 최소 2개 AZ의 서브넷을 요구한다.
    주의: AZ 이름(ap-northeast-2a)은 계정마다 물리 AZ(AZ ID, apne2-az1 등)에 다르게 매핑된다.
    다른 팀원 계정과 물리 AZ를 맞춰야 하면 az_id 기준으로 재검증할 것.
  EOT
  type        = list(string)
  default     = ["ap-northeast-2a", "ap-northeast-2c"]

  validation {
    condition     = length(var.availability_zones) >= 2 && length(var.availability_zones) <= 3
    error_message = "CIDR 분할 계획이 2~3 AZ 기준이다. 4 AZ 이상은 locals.tf의 cidrsubnet 인덱스를 재설계해야 한다."
  }
}

variable "vpc_cidr" {
  description = <<-EOT
    VPC CIDR. /16 고정 권장.
    근거: AWS VPC CNI는 Pod마다 VPC IP를 소비하므로 일반 EC2 워크로드보다 IP 소모량이 10~50배다.
    또한 향후 온프렘/타 VPC 피어링 시 RFC1918 대역 충돌을 피하려고 10.0.0.0/16을 팀 전용으로 예약한다.
  EOT
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = tonumber(split("/", var.vpc_cidr)[1]) <= 16
    error_message = "VPC CNI IP 소모량 때문에 /16 이상(더 큰) 대역을 사용해야 한다."
  }
}

variable "single_nat_gateway" {
  description = <<-EOT
    true  : NAT GW 1개를 전 AZ가 공유 (비용 절감, AZ 장애 시 전체 egress 중단)
    false : AZ당 1개 (HA, 비용 2배 + cross-AZ 전송료 제거)
    3주 테스트 환경 기본값은 true.
  EOT
  type        = bool
  default     = true
}

variable "enable_nat_gateway" {
  description = "NAT GW 자체를 끌 수 있는 킬 스위치. 야간/주말에 destroy 없이 비용을 0으로 만들 때 사용"
  type        = bool
  default     = true
}

variable "enable_ecr_interface_endpoints" {
  description = <<-EOT
    ECR API/DKR Interface Endpoint 생성 여부. 기본 false.
    근거: 이미지 레이어 실체는 S3에서 내려오므로 무료인 S3 Gateway Endpoint만으로 대부분의 바이트가 커버된다.
    Interface Endpoint는 $0.01/hr/AZ/endpoint 고정비가 붙어 3주 기준 손익분기 트래픽에 도달하기 어렵다.
    (자세한 계산은 README 참조)
  EOT
  type        = bool
  default     = false
}

variable "enable_data_tier" {
  description = <<-EOT
    private-data 서브넷 + DB/Cache 서브넷 그룹 생성 여부. 기본 false.
    지금은 RDS/Redis를 쓰지 않으므로 끈다.
    나중에 true로 바꿔도 CIDR 인덱스가 고정(12,13)이라 기존 서브넷에 영향이 없다.
    비용은 어차피 0이므로 켜 두어도 손해는 없고, plan 출력이 짧아지는 것이 유일한 이득이다.
  EOT
  type        = bool
  default     = false
}

variable "enable_flow_logs" {
  description = "VPC Flow Logs(S3 저장) 생성 여부. 보안/데이터파이프라인 트랙 입력 데이터로 사용"
  type        = bool
  default     = true
}

variable "flow_logs_traffic_type" {
  description = "ALL | ACCEPT | REJECT. 부하테스트 기간에는 볼륨이 커지므로 REJECT로 낮추는 것도 선택지"
  type        = string
  default     = "ALL"

  validation {
    condition     = contains(["ALL", "ACCEPT", "REJECT"], var.flow_logs_traffic_type)
    error_message = "ALL, ACCEPT, REJECT 중 하나여야 한다."
  }
}

variable "flow_logs_retention_days" {
  description = "Flow Logs S3 객체 만료일. 프로젝트 종료(8/28) 이후 잔여 비용 차단용"
  type        = number
  default     = 14
}

variable "eks_cluster_name" {
  description = <<-EOT
    아직 클러스터를 만들지 않았더라도 이름을 먼저 확정해야 한다.
    AWS Load Balancer Controller의 서브넷 auto-discovery가
    kubernetes.io/cluster/<name> 태그를 참조하기 때문이다.
  EOT
  type        = string
  default     = "o2-eks"
}

variable "owner" {
  description = "리소스 소유 담당자 태그"
  type        = string
  default     = "o2"
}
