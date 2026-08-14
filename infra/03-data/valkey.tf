# ★ 이 스택에서 가장 중요한 한 줄은 maxmemory-policy 다.
#
# Valkey 는 재고의 "캐시"가 아니라 "원본"이다 (설계 문서 D-07).
# stock:{sku} 에는 TTL 을 걸지 않는다 — 만료되는 순간 재고가 소실되기 때문이다
# (docs/contracts.md 4장).
#
# 그런데 기본 정책이 allkeys-lru 면 메모리가 차는 순간 TTL 이 없는 키도 축출 대상이
# 된다. 방송 중에 재고 키가 조용히 사라지고, 다음 주문에서 Lua 스크립트가 -2
# (미초기화)를 반환한다. 로그에는 "재고 없음"만 남아 원인을 찾기 어렵다.
#
# volatile-lru 는 TTL 이 있는 키만 축출한다. 세션·상품 상세는 지워져도
# 다시 채우면 되지만 재고는 그렇지 않다. 이 구분이 정책 하나로 표현된다.
resource "aws_elasticache_parameter_group" "main" {
  name = "${local.name}-valkey"

  # 패밀리 이름은 메이저 버전까지만 쓴다 (예: valkey8).
  family = "valkey${split(".", var.cache_engine_version)[0]}"

  parameter {
    name  = "maxmemory-policy"
    value = "volatile-lru"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${local.name}-valkey"
  description          = "Valkey. session, stock counter, room mapping, pub/sub"

  engine         = "valkey"
  engine_version = var.cache_engine_version
  node_type      = var.cache_node_type
  port           = 6379

  parameter_group_name = aws_elasticache_parameter_group.main.name
  subnet_group_name    = local.cache_subnet_group_name
  security_group_ids   = [aws_security_group.valkey.id]

  # 클러스터 모드 비활성. 핫키가 단일 키라 샤딩의 이득이 없다 (설계 문서 D-04).
  # num_cache_clusters 는 프라이머리 포함 노드 수다.
  num_cache_clusters = var.cache_num_nodes

  # 노드가 1개면 페일오버할 대상이 없어 둘 다 false 여야 한다.
  automatic_failover_enabled = var.cache_num_nodes > 1
  multi_az_enabled           = var.cache_num_nodes > 1

  # 암호화는 RDS 와 같은 이유로 처음부터 켠다 — 나중에 켜는 것이 비싸다.
  # transit 암호화를 켜면 클라이언트가 TLS 로 접속해야 한다.
  # (redis-py: ssl=True / ioredis: tls: {})
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  # AUTH 토큰은 쓰지 않는다. 토큰을 두면 관리 대상이 하나 늘고 state 에 남는데,
  # 접근 통제는 이미 보안 그룹이 EKS 노드로 좁히고 있다. VPC 안에서 노드 SG 를
  # 단 워크로드만 닿을 수 있다.
  # 멀티테넌시가 생기면 그때 Valkey RBAC(user group)으로 간다.

  # 스냅샷을 남기지 않는다. 이 안의 데이터는 세션과 재고 카운터인데,
  # 세션은 복구할 가치가 없고 재고는 방송 종료 배치가 MySQL 에 반영한다
  # (설계 문서 3.9). 복구 원본은 언제나 MySQL 이다.
  snapshot_retention_limit = 0

  auto_minor_version_upgrade = true
  apply_immediately          = true # 개발 환경

  depends_on = [terraform_data.require_data_tier]
}
