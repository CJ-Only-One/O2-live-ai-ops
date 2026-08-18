# 03-data 와 같은 이유로 규칙을 인라인 블록이 아니라 별도 리소스로 둔다
# (순환 의존 회피, 설계 문서 10.3).

resource "aws_security_group" "dify" {
  name        = local.name
  description = "Dify host. EKS node SG inbound only"
  vpc_id      = local.vpc_id

  tags = {
    Name = local.name
  }
}

# Dify 는 nginx 컨테이너가 80 하나로 콘솔·API·웹을 전부 앞단에서 받는다.
# 개별 컨테이너 포트(5001 등)는 열지 않는다.
resource "aws_vpc_security_group_ingress_rule" "dify_from_nodes" {
  security_group_id = aws_security_group.dify.id
  description       = "HTTP from EKS nodes"

  referenced_security_group_id = local.node_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
}

# RDS/Valkey 와 달리 이그레스가 필요하다 —
# 이미지 pull(NAT), SSM 폴링, LLM API 호출.
resource "aws_vpc_security_group_egress_rule" "dify_all" {
  security_group_id = aws_security_group.dify.id
  description       = "Image pull, SSM, LLM API"

  cidr_ipv4   = "0.0.0.0/0"
  ip_protocol = "-1"
}
