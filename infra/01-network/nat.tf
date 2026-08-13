resource "aws_eip" "nat" {
  for_each = toset(local.nat_gateway_azs)

  domain = "vpc"

  tags = {
    Name = "${local.name}-nat-eip-${each.key}"
  }

  # EIP는 IGW가 붙은 뒤에 할당되어야 한다.
  depends_on = [aws_internet_gateway.this]
}

resource "aws_nat_gateway" "this" {
  for_each = toset(local.nat_gateway_azs)

  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = aws_subnet.public[each.key].id

  tags = {
    Name = "${local.name}-nat-${each.key}"
  }

  depends_on = [aws_internet_gateway.this]
}
