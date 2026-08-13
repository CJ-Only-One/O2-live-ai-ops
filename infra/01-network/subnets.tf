# ── Public: ALB/NLB, NAT GW, (필요 시) Bastion ────────────────────
resource "aws_subnet" "public" {
  for_each = local.public_subnets

  vpc_id            = aws_vpc.this.id
  availability_zone = each.key
  cidr_block        = each.value.cidr

  # false로 두는 이유:
  # 워커 노드를 전부 private에 배치하므로 퍼블릭 IP 자동 할당이 필요 없다.
  # 2024-02부터 퍼블릭 IPv4는 개당 $0.005/hr 과금되므로 불필요한 할당을 막는다.
  # 주의: 여기에 EKS Managed Node Group을 직접 붙이려면 true가 필요하다.
  map_public_ip_on_launch = false

  tags = {
    Name = "${local.name}-public-${each.key}"
    Tier = "public"

    # AWS Load Balancer Controller 서브넷 auto-discovery용
    # 인터넷 페이싱 Ingress/Service가 이 서브넷을 자동 선택한다.
    "kubernetes.io/role/elb"                        = "1"
    "kubernetes.io/cluster/${var.eks_cluster_name}" = "shared"
  }
}

# ── Private App: EKS 워커 노드 + Pod ENI ──────────────────────────
resource "aws_subnet" "private_app" {
  for_each = local.private_app_subnets

  vpc_id            = aws_vpc.this.id
  availability_zone = each.key
  cidr_block        = each.value.cidr

  tags = {
    Name = "${local.name}-private-app-${each.key}"
    Tier = "private-app"

    "kubernetes.io/role/internal-elb"               = "1"
    "kubernetes.io/cluster/${var.eks_cluster_name}" = "shared"

    # Karpenter를 쓸 경우 노드 프로비저닝 대상 서브넷 discovery 태그.
    # Cluster Autoscaler만 쓸 거면 무해하게 남아 있어도 된다.
    "karpenter.sh/discovery" = var.eks_cluster_name
  }
}

# ── Private Data: RDS / ElastiCache / (선택) MSK ──────────────────
# 인터넷 경로(0.0.0.0/0)를 아예 부여하지 않는 격리 계층.
resource "aws_subnet" "private_data" {
  for_each = local.private_data_subnets

  vpc_id            = aws_vpc.this.id
  availability_zone = each.key
  cidr_block        = each.value.cidr

  tags = {
    Name = "${local.name}-private-data-${each.key}"
    Tier = "private-data"
  }
}

# RDS/ElastiCache 서브넷 그룹. enable_data_tier = true 일 때만 생성.
resource "aws_db_subnet_group" "data" {
  count = var.enable_data_tier ? 1 : 0

  name       = "${local.name}-db"
  subnet_ids = [for s in aws_subnet.private_data : s.id]

  tags = {
    Name = "${local.name}-db-subnet-group"
  }
}

resource "aws_elasticache_subnet_group" "data" {
  count = var.enable_data_tier ? 1 : 0

  name       = "${local.name}-cache"
  subnet_ids = [for s in aws_subnet.private_data : s.id]
}
