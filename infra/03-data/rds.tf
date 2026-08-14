# 파라미터 그룹을 따로 만드는 이유는 문자셋·콜레이션 때문이다.
# 이 둘은 "지금 정할 것" 쪽에 속한다 (설계 문서 10.2). 나중에 바꾸면 이미 만들어진
# 테이블은 그대로 남아 있어, 같은 DB 안에서 테이블마다 콜레이션이 달라진다.
# 그 상태로 JOIN 하면 "Illegal mix of collations" 로 쿼리가 깨진다.
resource "aws_db_parameter_group" "main" {
  name   = "${local.name}-mysql8"
  family = "mysql${var.db_engine_version}"

  parameter {
    name  = "character_set_server"
    value = "utf8mb4"
  }

  parameter {
    name  = "collation_server"
    value = "utf8mb4_0900_ai_ci"
  }

  # 느린 쿼리를 파일이 아니라 테이블로 남긴다. 개발 중에 psql 없이
  # mysql.slow_log 를 바로 조회할 수 있다.
  parameter {
    name  = "slow_query_log"
    value = "1"
  }

  parameter {
    name  = "long_query_time"
    value = "1"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ── 인스턴스 ─────────────────────────────────────────────────────
resource "aws_db_instance" "main" {
  identifier = "${local.name}-mysql"

  engine         = "mysql"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  db_name  = var.db_name
  username = "o2admin"

  # 비밀번호를 Terraform 이 만들지 않는다.
  # random_password 로 만들면 그 값이 state 에 평문으로 남는다 (.gitignore 의 경고,
  # docs/decisions.md D-005). AWS 가 직접 만들어 Secrets Manager 에 넣고 관리하면
  # state 에는 시크릿 ARN 만 남는다.
  manage_master_user_password = true

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_allocated_storage * 5 # 스토리지 오토스케일 상한
  storage_type          = "gp3"

  # ★ 생성 시점에만 설정할 수 있다. (docs/decisions.md 예정 · 설계 문서 D-10)
  #
  # 나중에 켜려면 스냅샷 -> 암호화 복사 -> 복원, 즉 인스턴스 재생성과 커트오버가
  # 필요하다. 미암호화 인스턴스는 암호화 스냅샷을 만들 수도 없고, 암호화
  # 인스턴스에 미암호화 리드 리플리카를 붙일 수도 없다.
  #
  # 관리형 키(aws/rds) 기준 추가 비용이 없고 성능 영향도 없다.
  # 그래서 개발 환경에서도 켠다. 여기서 아끼면 나중에 재생성으로 갚는다.
  storage_encrypted = true
  kms_key_id        = null # null 이면 aws/rds 관리형 키

  db_subnet_group_name   = local.db_subnet_group_name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  multi_az               = var.db_multi_az

  parameter_group_name = aws_db_parameter_group.main.name

  backup_retention_period = var.db_backup_retention_days
  deletion_protection     = var.db_deletion_protection
  skip_final_snapshot     = var.db_skip_final_snapshot
  final_snapshot_identifier = (
    var.db_skip_final_snapshot ? null : "${local.name}-mysql-final-${formatdate("YYYYMMDDhhmmss", timestamp())}"
  )

  # micro·small 버스터블 클래스는 Performance Insights 를 지원하지 않는다.
  # 기본값이 false 인 이유는 variables.tf 참조.
  # 켤 때는 무료 티어 범위(7일)만 쓴다.
  performance_insights_enabled          = var.db_performance_insights_enabled
  performance_insights_retention_period = var.db_performance_insights_enabled ? 7 : null

  # Enhanced Monitoring 은 끈다. CloudWatch 커스텀 메트릭으로 과금되고,
  # 개발 단계에서는 Performance Insights 로 충분하다.
  monitoring_interval = 0

  auto_minor_version_upgrade = true
  apply_immediately          = true # 개발 환경. 운영은 유지보수 창을 기다린다

  lifecycle {
    ignore_changes = [
      # 위 final_snapshot_identifier 의 timestamp() 때문에 매 plan 마다
      # 변경으로 잡히는 것을 막는다.
      final_snapshot_identifier,
    ]
  }

  depends_on = [terraform_data.require_data_tier]
}

# ── 리드 리플리카 ────────────────────────────────────────────────
# 기본은 끔. 켜는 시점과 이유는 variables.tf 의 enable_read_replica 참조.
resource "aws_db_instance" "replica" {
  count = var.enable_read_replica ? 1 : 0

  identifier          = "${local.name}-mysql-replica"
  replicate_source_db = aws_db_instance.main.identifier
  instance_class      = var.db_instance_class

  # 리플리카는 소스의 서브넷 그룹·암호화 설정을 따라간다.
  # 암호화 인스턴스에 미암호화 리플리카를 붙일 수 없으므로 여기서 지정하지 않는다.
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  skip_final_snapshot = true
  apply_immediately   = true

  # 리플리카도 같은 인스턴스 등급이라 같은 제약을 받는다.
  performance_insights_enabled          = var.db_performance_insights_enabled
  performance_insights_retention_period = var.db_performance_insights_enabled ? 7 : null
}
