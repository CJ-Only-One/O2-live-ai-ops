# ── Public RT: 전 AZ 공유 (경로가 동일하므로 분리 이득 없음) ─────
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${local.name}-rt-public"
  }
}

resource "aws_route" "public_default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

# ── Private App RT: AZ별 분리 ────────────────────────────────────
# AZ별로 나누는 이유: single_nat_gateway=false로 전환할 때
# 코드 변경 없이 각 AZ가 자기 AZ의 NAT를 바라보게 하기 위함.
resource "aws_route_table" "private_app" {
  for_each = local.private_app_subnets

  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${local.name}-rt-private-app-${each.key}"
  }
}

resource "aws_route" "private_app_default" {
  for_each = var.enable_nat_gateway ? local.private_app_subnets : {}

  route_table_id         = aws_route_table.private_app[each.key].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[local.nat_az_for[each.key]].id
}

resource "aws_route_table_association" "private_app" {
  for_each = aws_subnet.private_app

  subnet_id      = each.value.id
  route_table_id = aws_route_table.private_app[each.key].id
}

# ── Private Data RT: 기본 경로 없음 (완전 격리) ──────────────────
# 0.0.0.0/0 라우트를 만들지 않는다. DB가 인터넷으로 나갈 이유가 없고,
# 데이터 유출 경로를 라우팅 레벨에서 제거하는 것이 SG보다 강한 통제다.
resource "aws_route_table" "private_data" {
  for_each = local.private_data_subnets

  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${local.name}-rt-private-data-${each.key}"
  }
}

resource "aws_route_table_association" "private_data" {
  for_each = aws_subnet.private_data

  subnet_id      = each.value.id
  route_table_id = aws_route_table.private_data[each.key].id
}
