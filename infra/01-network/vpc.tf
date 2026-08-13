resource "aws_vpc" "this" {
  cidr_block = var.vpc_cidr

  # 둘 다 true여야 하는 이유:
  #  1) EKS 노드가 클러스터 엔드포인트를 프라이빗 DNS로 해석해야 한다.
  #  2) Interface VPC Endpoint의 Private DNS 기능이 동작하지 않는다.
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${local.name}-vpc"
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${local.name}-igw"
  }
}

# 기본 SG는 "동일 SG 내 전체 통신 허용" 규칙을 갖고 태어난다.
# 명시적으로 규칙을 비워 두어 실수로 붙었을 때 통신이 열리지 않게 한다.
# (CIS AWS Foundations Benchmark 5.3 대응)
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${local.name}-default-sg-DO-NOT-USE"
  }
}

# 기본 라우팅 테이블도 비워 둔다. 서브넷은 전부 명시적 RT에 연결한다.
resource "aws_default_route_table" "this" {
  default_route_table_id = aws_vpc.this.default_route_table_id

  tags = {
    Name = "${local.name}-default-rt-DO-NOT-USE"
  }
}
