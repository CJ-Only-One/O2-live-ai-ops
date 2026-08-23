output "worker_function_name" {
  value = aws_lambda_function.worker.function_name
}

output "worker_function_arn" {
  value = aws_lambda_function.worker.arn
}

output "event_source_mapping_uuid" {
  value = aws_lambda_event_source_mapping.chat_signal.uuid
}

output "event_source_enabled" {
  description = "SQS event source mapping의 Terraform 의도 상태"
  value       = var.enable_event_source
}

output "chat_source_adapter_function_name" {
  value = aws_lambda_function.chat_source_adapter.function_name
}

output "chat_source_adapter_event_source_uuid" {
  value = aws_lambda_event_source_mapping.chat_source_adapter.uuid
}

output "chat_source_adapter_event_source_enabled" {
  description = "Phase 2 완료 상태는 반드시 false"
  value       = aws_lambda_event_source_mapping.chat_source_adapter.enabled
}

output "chat_source_adapter_dlq_url" {
  value = aws_sqs_queue.chat_source_adapter_dlq.url
}
