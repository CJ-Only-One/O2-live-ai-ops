team        = "o2"
project     = "o2"
environment = "dev"
region      = "ap-northeast-2"

cluster_name = "o2-eks"

network_state_bucket = "o2-tfstate-066107819912"
network_state_key    = "network/terraform.tfstate"

# ── RDS ──────────────────────────────────────────────────────────
# 사이징은 전부 Phase 6 부하 테스트 뒤에 정한다 (설계 문서 10.2).
# 지금 정한 것은 나중에 못 바꾸는 것들뿐이다 — 암호화, 문자셋, 콜레이션.
db_name = "o2"

# 8.0 은 표준 지원이 끝나 확장 지원 요금이 붙는다. 실측 $5.47/day 로
# 인스턴스 요금($0.57/day)의 10배였고, 인스턴스를 정지해도 계속 과금된다.
# 8.4 는 LTS 라 해당 요금이 없다.
db_engine_version    = "8.4"
db_instance_class    = "db.t4g.micro"
db_allocated_storage = 20

db_multi_az              = false
db_backup_retention_days = 1
db_deletion_protection   = false
db_skip_final_snapshot   = true

# micro·small 버스터블 클래스는 Performance Insights 를 지원하지 않는다.
# 인스턴스 등급을 올리는 Phase 6 에서 함께 켠다.
db_performance_insights_enabled = false

# 리플리카는 Phase 6 에서 켠다. 그 전에는 인스턴스 하나가 통째로 노는 비용이다.
enable_read_replica = false

# ── ElastiCache (Valkey) ─────────────────────────────────────────
# apply 전 버전 확인:
#   aws elasticache describe-cache-engine-versions --engine valkey \
#     --region ap-northeast-2 --query 'CacheEngineVersions[].EngineVersion'
cache_engine_version = "8.0"
cache_node_type      = "cache.t4g.micro"

# 1 = 단일 노드. 자동 페일오버 없음.
# Phase 6 에서 2 로 올려 R-02(Valkey 단일 장애) 시나리오를 검증한다.
cache_num_nodes = 1

# ── SQS ──────────────────────────────────────────────────────────
order_queue_visibility_timeout = 60
order_queue_max_receive_count  = 5
