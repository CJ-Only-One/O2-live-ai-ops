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
