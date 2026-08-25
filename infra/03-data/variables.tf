variable "team" {
  description = "팀 식별자. 태그로만 사용"
  type        = string
  default     = "o2"
}

variable "project" {
  description = "리소스 prefix. 소문자/하이픈만"
  type        = string
  default     = "o2"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", var.project))
    error_message = "소문자, 숫자, 하이픈만 허용."
  }
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "cluster_name" {
  description = <<-EOT
    EKS 클러스터 이름. 노드가 붙어 있는 보안 그룹을 찾는 데만 쓴다.

    02-eks 의 remote state 대신 data source 로 조회한다.
    02-eks 가 cluster_security_group_id 를 출력하지 않아서인데,
    그것만을 위해 EKS 스택을 다시 apply 하는 것보다 읽기 조회가 싸다.
  EOT
  type        = string
  default     = "o2-eks"
}

variable "network_state_bucket" {
  description = "network 스택의 S3 backend 버킷"
  type        = string
}

variable "network_state_key" {
  type    = string
  default = "network/terraform.tfstate"
}

# ── RDS ──────────────────────────────────────────────────────────

variable "db_name" {
  type    = string
  default = "o2"
}

variable "db_engine_version" {
  description = <<-EOT
    메이저 버전만 적으면 AWS가 그 안의 최신 마이너를 고른다.
    설계 문서 4장은 InnoDB 버퍼 풀과 REPEATABLE READ 기준으로 쓰여 있고,
    8.4 도 이 둘은 동일하다.

    8.0 으로 되돌리지 말 것. 표준 지원이 끝나 확장 지원 요금이 붙는다
    (실측 $5.47/day, 인스턴스 요금의 10배). 8.4 는 LTS 라 해당 요금이 없다.
  EOT
  type        = string
  default     = "8.4"
}

variable "db_instance_class" {
  description = <<-EOT
    개발 환경 최소 사양. 사이징은 Phase 6 부하 테스트 뒤에 정한다
    (설계 문서 10.2 — 인스턴스 클래스는 나중에 정할 것).

    캐싱이 제대로 되면 MySQL 이 받는 읽기는 전체의 1% 미만이라
    (설계 문서 3.10) 개발 중에는 이 등급으로 충분하다.
  EOT
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "GiB. gp3 최소치"
  type        = number
  default     = 20
}

variable "db_multi_az" {
  description = <<-EOT
    개발 환경은 끈다. 나중에 무중단으로 켤 수 있다
    (설계 문서 4.6 — 개발환경에서 실제로 미뤄도 되는 항목).
  EOT
  type        = bool
  default     = false
}

variable "db_backup_retention_days" {
  description = "개발 환경 1일. 0 으로 두면 리드 리플리카를 만들 수 없다"
  type        = number
  default     = 1
}

variable "db_deletion_protection" {
  description = "개발 중에는 끈다. 실험 비용 통제를 위해 destroy 가 가능해야 한다"
  type        = bool
  default     = false
}

variable "db_skip_final_snapshot" {
  description = <<-EOT
    개발 환경은 true. false 이면 destroy 시 스냅샷 이름을 요구해 실패한다.
    운영으로 갈 때 반드시 false 로 바꾼다.
  EOT
  type        = bool
  default     = true
}

variable "db_performance_insights_enabled" {
  description = <<-EOT
    ★ micro·small 버스터블 클래스는 Performance Insights 를 지원하지 않는다.
    db.t4g.micro 로 켜면 apply 가 이렇게 실패한다:

      InvalidParameterCombination: Performance Insights not supported
      for this configuration.

    그래서 기본값은 false 다. 인스턴스 등급을 올리는 Phase 6 에서 함께 켠다.

    지금 잃는 것은 UI 하나뿐이다. 설계 문서 4.1 의 버퍼 풀 적중률은
    performance_schema.global_status 를 직접 조회하면 그대로 나온다.
  EOT
  type        = bool
  default     = false
}

variable "enable_read_replica" {
  description = <<-EOT
    개발 중에는 끈다. 리플리카는 인스턴스 하나가 통째로 늘어나는 비용이다.

    켜야 하는 시점은 Phase 6 이다. 설계 문서 4.2 의 리플리카 지연(ReplicaLag)과
    "주문 직후 조회는 writer 로" 라우팅을 실제로 검증하려면 그때 필요하다.
    애플리케이션은 처음부터 writer/reader 두 엔드포인트를 쓰도록 만들고,
    리플리카가 없는 동안에는 둘 다 writer 를 가리키게 한다.
  EOT
  type        = bool
  default     = false
}

# ── ElastiCache (Valkey) ─────────────────────────────────────────

variable "cache_engine_version" {
  description = <<-EOT
    apply 전 확인:
      aws elasticache describe-cache-engine-versions --engine valkey \
        --region ap-northeast-2 --query 'CacheEngineVersions[].EngineVersion'
  EOT
  type        = string
  default     = "8.0"
}

variable "cache_node_type" {
  description = "개발 환경 최소 사양. 사이징은 Phase 6 이후"
  type        = string
  default     = "cache.t4g.micro"
}

variable "cache_snapshot_retention_days" {
  description = <<-EOT
    Valkey 자동 스냅샷 보관 일수. 0 이면 백업을 남기지 않는다.

    재고(stock:{sku})의 원본이 Valkey 이고 MySQL 에 사본이 없어(D-07),
    잃으면 되돌릴 곳이 seed 의 초기값뿐이다. cache.t4g.micro 기준 스토리지
    비용이 무시할 수준이라 하루치는 남긴다.
  EOT
  type        = number
  default     = 1
}

variable "cache_num_nodes" {
  description = <<-EOT
    프라이머리 포함 노드 수. 1 이면 단일 노드라 자동 페일오버가 없다.

    개발 중에는 1 로 둔다. 2 이상으로 올려야 하는 시점은 Phase 6 이다 —
    R-02(Valkey 단일 장애 = 재고 판정 불가 = 판매 중단)의 페일오버 시나리오를
    실제로 검증하려면 그때 필요하다.

    클러스터 모드는 켜지 않는다. 핫키가 단일 키라 샤딩의 이득이 없고
    운영 복잡도만 오른다 (설계 문서 D-04).
  EOT
  type        = number
  default     = 1

  validation {
    condition     = var.cache_num_nodes >= 1 && var.cache_num_nodes <= 6
    error_message = "1 이상 6 이하."
  }
}

# ── SQS ──────────────────────────────────────────────────────────

variable "order_queue_visibility_timeout" {
  description = <<-EOT
    워커가 메시지를 잡고 있는 동안 다른 워커에게 안 보이는 시간.
    워커의 최대 처리 시간보다 넉넉해야 한다. 짧으면 처리 중인 메시지가
    다시 배달되어 중복 주문 시도가 생긴다.

    중복 자체는 정상 동작 범위다 — SQS Standard 는 최소 1회 전달이고
    MySQL 의 uk_idem 이 최종 방어선이다 (설계 문서 4.4). 다만 불필요한
    중복은 워커 부하만 늘리므로 여유를 둔다.
  EOT
  type        = number
  default     = 60
}

variable "order_queue_max_receive_count" {
  description = "이 횟수만큼 실패하면 DLQ 로 보낸다"
  type        = number
  default     = 5
}
