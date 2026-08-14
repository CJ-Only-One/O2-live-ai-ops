# 규칙을 security group 리소스 안의 인라인 블록이 아니라 별도 리소스로 둔다.
# 인라인으로 쓰면 노드 SG 와 서로를 참조하게 될 때 Terraform 순환 의존이 생긴다
# (설계 문서 10.3). 지금은 단방향이라 문제가 없지만, 나중에 반대 방향 규칙이
# 필요해질 때 리소스 구조를 갈아엎지 않으려면 처음부터 이렇게 두는 편이 낫다.

# ── RDS ──────────────────────────────────────────────────────────

resource "aws_security_group" "rds" {
  name        = "${local.name}-rds"
  description = "RDS MySQL. EKS node SG only"
  vpc_id      = local.vpc_id

  tags = {
    Name = "${local.name}-rds"
  }
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_nodes" {
  security_group_id = aws_security_group.rds.id
  description       = "MySQL from EKS nodes"

  referenced_security_group_id = local.node_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 3306
  to_port                      = 3306
}

# ── ElastiCache (Valkey) ─────────────────────────────────────────

resource "aws_security_group" "valkey" {
  name        = "${local.name}-valkey"
  description = "ElastiCache Valkey. EKS node SG only"
  vpc_id      = local.vpc_id

  tags = {
    Name = "${local.name}-valkey"
  }
}

resource "aws_vpc_security_group_ingress_rule" "valkey_from_nodes" {
  security_group_id = aws_security_group.valkey.id
  description       = "Valkey from EKS nodes"

  referenced_security_group_id = local.node_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
}

# 이그레스는 두 SG 모두 만들지 않는다.
# aws_security_group 을 인라인 블록 없이 선언하면 기본 allow-all 이그레스가
# 생성되지 않고, RDS·ElastiCache 는 스스로 바깥으로 연결할 일이 없다.
