output "signal_queue_url" {
  value = aws_sqs_queue.agent_entry.url
}

output "incident_alarm_topic_arn" {
  value = aws_sns_topic.incident_alarm.arn
}

output "signal_queue_name" {
  value = aws_sqs_queue.agent_entry.name
}

output "incident_state_table" {
  value = aws_dynamodb_table.incident_state.name
}

output "incident_correlator_function_name" {
  value = aws_lambda_function.incident_correlator.function_name
}

output "incident_correlator_event_source_enabled" {
  value = aws_lambda_event_source_mapping.incident_correlator.enabled
}

output "incident_correlator_execution_enabled" {
  value = var.incident_correlator_execution_enabled
}

output "agent_invocation_queue_url" {
  value = aws_sqs_queue.agent_invocation.url
}

output "agent_invocation_queue_name" {
  value = aws_sqs_queue.agent_invocation.name
}

output "datadog_source_adapter_function_name" {
  value = aws_lambda_function.datadog_source_adapter.function_name
}

output "datadog_source_adapter_function_url" {
  value     = aws_lambda_function_url.datadog_source_adapter.function_url
  sensitive = true
}
