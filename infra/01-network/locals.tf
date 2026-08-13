locals {
  # 리소스 이름에 환경을 넣지 않는다. 환경 구분은 Environment 태그가 맡는다.
  # 주의: 같은 계정에 다른 환경을 올리면 이름이 충돌한다.
  #       환경을 나눌 때는 계정을 분리하거나 이 접두사를 되돌려야 한다.
  name = var.project
  azs  = var.availability_zones

  common_tags = {
    Team        = var.team
    Project     = var.project
    Environment = var.environment
    Owner       = var.owner
    ManagedBy   = "terraform"
    CostCenter  = var.project # Billing 콘솔에서 Cost Allocation Tag로 활성화 필요
  }

  # ─────────────────────────────────────────────────────────────
  # CIDR 분할 계획 (vpc_cidr = 10.0.0.0/16 기준)
  #
  #   10.0.0.0/18   (0.0   - 63.255)  : Public + Data 전용 예약
  #     ├ public-a  10.0.0.0/20   (4,091 usable)
  #     ├ public-c  10.0.16.0/20
  #     ├ public-d  10.0.32.0/20   (3 AZ 확장 시)
  #     ├ data-a    10.0.48.0/22  (1,019 usable)
  #     ├ data-c    10.0.52.0/22
  #     ├ data-d    10.0.56.0/22   (3 AZ 확장 시)
  #     └ 10.0.60.0/22 : 예약(미사용)
  #
  #   10.0.64.0/18  : private-app-a (16,379 usable)
  #   10.0.128.0/18 : private-app-c
  #   10.0.192.0/18 : private-app-d (3 AZ 확장 시)
  #
  # Public이 /20인 이유: ALB/NLB ENI + NAT GW만 들어가므로 실제 소모는 수십 개.
  #   다만 ALB는 서브넷당 최소 /27(8개 여유 IP)을 요구하고, LB 스케일아웃 시
  #   ENI가 늘어나므로 /24 이상은 확보한다. /20은 여유분.
  #
  # Private-app이 /18인 이유: VPC CNI 기본 모드에서 Pod 1개 = VPC IP 1개.
  #   m5.large 기준 max-pods 29, prefix delegation 사용 시 노드당 /28 단위로
  #   16 IP씩 선점된다. 노드 50대 × prefix 7개 × 16 IP = 5,600 IP 수준까지
  #   부하테스트 중 순간 소모될 수 있으므로 AZ당 16,379개를 확보한다.
  #
  # Data가 /22인 이유: RDS/ElastiCache는 인스턴스 수가 한 자릿수. 과대 할당 불필요.
  # ─────────────────────────────────────────────────────────────

  public_subnets = {
    for idx, az in local.azs : az => {
      cidr = cidrsubnet(var.vpc_cidr, 4, idx) # /20
    }
  }

  private_app_subnets = {
    for idx, az in local.azs : az => {
      cidr = cidrsubnet(var.vpc_cidr, 2, idx + 1) # /18
    }
  }

  private_data_subnets = var.enable_data_tier ? {
    for idx, az in local.azs : az => {
      cidr = cidrsubnet(var.vpc_cidr, 6, idx + 12) # /22
    }
  } : {}

  # single_nat_gateway = true  → 첫 번째 AZ에만 NAT GW 1개
  # single_nat_gateway = false → AZ마다 NAT GW
  nat_gateway_azs = var.enable_nat_gateway ? (
    var.single_nat_gateway ? [local.azs[0]] : local.azs
  ) : []

  # 각 private 서브넷이 어느 AZ의 NAT를 쓸지 결정
  nat_az_for = {
    for az in local.azs : az => var.single_nat_gateway ? local.azs[0] : az
  }
}
