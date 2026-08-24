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
  description = "Chat Candidate Stream event source 활성화 여부"
  value       = aws_lambda_event_source_mapping.chat_source_adapter.enabled
}

output "chat_source_adapter_execution_enabled" {
  description = "Chat Source Adapter Queue 전송 실행 게이트"
  value       = var.chat_source_adapter_execution_enabled
}

output "chat_source_adapter_dlq_url" {
  value = aws_sqs_queue.chat_source_adapter_dlq.url
}
