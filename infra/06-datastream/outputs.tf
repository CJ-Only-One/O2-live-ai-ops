output "data_lake_bucket_name" {
  description = "S3 데이터 레이크 버킷 이름"
  value       = aws_s3_bucket.data_lake.id
}

output "data_lake_bucket_arn" {
  description = "S3 데이터 레이크 버킷 ARN"
  value       = aws_s3_bucket.data_lake.arn
}

output "business_stream_name" {
  description = "비즈니스 이벤트 Kinesis 스트림 이름"
  value       = aws_kinesis_stream.business.name
}

output "business_stream_arn" {
  description = "비즈니스 이벤트 Kinesis 스트림 ARN"
  value       = aws_kinesis_stream.business.arn
}

output "client_stream_name" {
  description = "클라이언트 이벤트 Kinesis 스트림 이름"
  value       = aws_kinesis_stream.client.name
}

output "client_stream_arn" {
  description = "클라이언트 이벤트 Kinesis 스트림 ARN"
  value       = aws_kinesis_stream.client.arn
}

output "agent_context_table_name" {
  description = "Agent 판단 재료 DynamoDB 테이블 이름"
  value       = aws_dynamodb_table.agent_context.name
}

output "agent_context_table_arn" {
  description = "Agent 판단 재료 DynamoDB 테이블 ARN"
  value       = aws_dynamodb_table.agent_context.arn
}

output "business_firehose_name" {
  description = "비즈니스 Kinesis-S3 Firehose 이름"
  value       = aws_kinesis_firehose_delivery_stream.business.name
}

output "client_firehose_name" {
  description = "클라이언트 Kinesis-S3 Firehose 이름"
  value       = aws_kinesis_firehose_delivery_stream.client.name
}

output "firehose_role_arn" {
  description = "Firehose 서비스 IAM 역할 ARN"
  value       = aws_iam_role.firehose.arn
}

output "aggregate_lambda_name" {
  description = "Kinesis 집계 Lambda 함수 이름"
  value       = aws_lambda_function.aggregate.function_name
}

output "aggregate_lambda_arn" {
  description = "Kinesis 집계 Lambda 함수 ARN"
  value       = aws_lambda_function.aggregate.arn
}

output "producer_role_arn" {
  description = "이벤트 생성기 파드용 IRSA 역할 ARN — ServiceAccount annotation에 사용"
  value       = aws_iam_role.producer.arn
}

output "producer_service_account" {
  description = "IRSA 신뢰 정책에 고정된 네임스페이스/ServiceAccount"
  value       = "${local.producer_namespace}/${local.producer_service_account}"
}
