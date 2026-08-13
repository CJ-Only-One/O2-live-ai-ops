data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# ── S3 Gateway Endpoint: 무조건 켠다 ─────────────────────────────
# 시간당 요금 0원, 데이터 처리 요금 0원.
# 효과:
#  1) ECR 이미지 레이어 실체는 S3에 있다 → 이미지 pull 바이트의 대부분이 NAT를 우회
#  2) Loki/Thanos/Mimir 등 S3 백엔드 관측 스택의 chunk 업로드가 NAT를 우회
#  3) VPC Flow Logs → S3 전달 경로도 NAT를 타지 않음
# 안 켜면 위 트래픽 전부가 NAT 데이터 처리료 대상이 된다.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.region}.s3"
  vpc_endpoint_type = "Gateway"

  route_table_ids = concat(
    [for rt in aws_route_table.private_app : rt.id],
    [for rt in aws_route_table.private_data : rt.id],
  )

  tags = {
    Name = "${local.name}-vpce-s3"
  }
}

# ── Interface Endpoint용 SG ──────────────────────────────────────
resource "aws_security_group" "vpc_endpoints" {
  count = var.enable_ecr_interface_endpoints ? 1 : 0

  name        = "${local.name}-vpce-sg"
  description = "Allow HTTPS from VPC to interface endpoints"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name = "${local.name}-vpce-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "vpce_https" {
  count = var.enable_ecr_interface_endpoints ? 1 : 0

  security_group_id = aws_security_group.vpc_endpoints[0].id
  description       = "HTTPS from within VPC"
  cidr_ipv4         = var.vpc_cidr
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

# ── ECR Interface Endpoints: 기본 off ────────────────────────────
# 손익분기 계산(README 참조) 결과 3주 프로젝트에서는 NAT 경유가 더 싸다.
# 향후 인터넷 egress를 완전히 차단하는 요건이 생기면 true로 전환한다.
locals {
  interface_endpoint_services = var.enable_ecr_interface_endpoints ? [
    "ecr.api",
    "ecr.dkr",
  ] : []
}

resource "aws_vpc_endpoint" "interface" {
  for_each = toset(local.interface_endpoint_services)

  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [for s in aws_subnet.private_app : s.id]
  security_group_ids  = [aws_security_group.vpc_endpoints[0].id]
  private_dns_enabled = true

  tags = {
    Name = "${local.name}-vpce-${replace(each.key, ".", "-")}"
  }
}
