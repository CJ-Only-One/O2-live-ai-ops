output "db_writer_endpoint" {
  description = "쓰기와 '주문 직후 조회'가 가는 곳 (설계 문서 4.2)"
  value       = aws_db_instance.main.address
}

output "db_reader_endpoint" {
  description = <<-EOT
    읽기 전용 조회 대상. 리플리카가 없으면 writer 를 가리킨다.

    애플리케이션은 리플리카 유무와 무관하게 항상 이 두 값을 받도록 만든다.
    나중에 enable_read_replica 를 켜는 것만으로 읽기가 분산되고,
    코드는 손대지 않는다.
  EOT
  value       = try(aws_db_instance.replica[0].address, aws_db_instance.main.address)
}

output "db_port" {
  value = aws_db_instance.main.port
}

output "db_name" {
  value = aws_db_instance.main.db_name
}

output "db_master_secret_arn" {
  description = <<-EOT
    AWS 가 만들어 관리하는 마스터 비밀번호 시크릿.
    ESO 의 ExternalSecret 이 이 ARN 을 참조해 파드에 주입한다
    (04-platform 의 datadog 시크릿과 같은 경로).

    이 출력은 ARN 일 뿐 비밀번호 값이 아니다. 값은 state 에 남지 않는다.
  EOT
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
}

output "valkey_primary_endpoint" {
  description = "쓰기(DECR 등)와 Pub/Sub 발행 대상"
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "valkey_reader_endpoint" {
  description = <<-EOT
    읽기 분산용. 노드가 1개면 프라이머리와 같은 곳을 가리킨다.

    설계 문서 3.8(2)의 "읽기 분산은 Replica 증설 + reader endpoint 가
    샤드 추가보다 효과적" 이 이 엔드포인트를 말한다.
  EOT
  value       = aws_elasticache_replication_group.main.reader_endpoint_address
}

output "valkey_port" {
  value = aws_elasticache_replication_group.main.port
}

output "valkey_tls_required" {
  description = "transit 암호화가 켜져 있으므로 클라이언트는 TLS 로 접속해야 한다"
  value       = aws_elasticache_replication_group.main.transit_encryption_enabled
}

output "order_queue_url" {
  value = aws_sqs_queue.order.id
}

output "order_queue_arn" {
  description = "Phase 3 에서 파드 IAM 역할의 리소스 조건에 쓴다"
  value       = aws_sqs_queue.order.arn
}

output "order_dlq_url" {
  value = aws_sqs_queue.order_dlq.id
}

output "chat_signal_queue_url" {
  value = aws_sqs_queue.chat_signal.id
}

output "chat_signal_queue_arn" {
  value = aws_sqs_queue.chat_signal.arn
}

output "chat_incident_table_name" {
  value = aws_dynamodb_table.chat_incident_state.name
}

output "chat_incident_table_arn" {
  value = aws_dynamodb_table.chat_incident_state.arn
}

output "rds_security_group_id" {
  value = aws_security_group.rds.id
}

output "valkey_security_group_id" {
  value = aws_security_group.valkey.id
}
