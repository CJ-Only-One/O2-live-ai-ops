# D-078 state migration guard.
#
# Incident 생성 runtime은 09-incident로 이동했다. 기존 dev state의 아래 주소를
# 새 backend로 이전하기 전 06-agent가 실제 AWS 객체를 destroy하지 않게 한다.
# state migration 완료 후에도 이력으로 남기며, apply 전에는 반드시
# ../09-incident/README.md 절차와 양쪽 plan을 확인한다.

removed {
  from = aws_sqs_queue.agent_entry_dlq
  lifecycle { destroy = false }
}

removed {
  from = aws_sqs_queue.agent_entry
  lifecycle { destroy = false }
}

removed {
  from = aws_sqs_queue_redrive_allow_policy.agent_entry
  lifecycle { destroy = false }
}

removed {
  from = aws_cloudwatch_metric_alarm.agent_entry_queue_age
  lifecycle { destroy = false }
}

removed {
  from = aws_cloudwatch_metric_alarm.agent_entry_dlq_not_empty
  lifecycle { destroy = false }
}

removed {
  from = aws_sqs_queue.agent_invocation_dlq
  lifecycle { destroy = false }
}

removed {
  from = aws_sqs_queue.agent_invocation
  lifecycle { destroy = false }
}

removed {
  from = aws_sqs_queue_redrive_allow_policy.agent_invocation
  lifecycle { destroy = false }
}

removed {
  from = aws_dynamodb_table.incident_state
  lifecycle { destroy = false }
}

removed {
  from = aws_iam_role.incident_correlator
  lifecycle { destroy = false }
}

removed {
  from = aws_iam_role_policy_attachment.incident_correlator_basic
  lifecycle { destroy = false }
}

removed {
  from = aws_iam_role_policy.incident_correlator
  lifecycle { destroy = false }
}

removed {
  from = aws_cloudwatch_log_group.incident_correlator
  lifecycle { destroy = false }
}

removed {
  from = aws_lambda_function.incident_correlator
  lifecycle { destroy = false }
}

removed {
  from = aws_lambda_event_source_mapping.incident_correlator
  lifecycle { destroy = false }
}

removed {
  from = aws_cloudwatch_metric_alarm.agent_invocation_queue_age
  lifecycle { destroy = false }
}

removed {
  from = aws_cloudwatch_metric_alarm.agent_invocation_dlq_not_empty
  lifecycle { destroy = false }
}

removed {
  from = aws_cloudwatch_metric_alarm.incident_correlator_errors
  lifecycle { destroy = false }
}

removed {
  from = aws_iam_role.datadog_source_adapter
  lifecycle { destroy = false }
}

removed {
  from = aws_iam_role_policy_attachment.datadog_source_adapter_basic
  lifecycle { destroy = false }
}

removed {
  from = aws_iam_role_policy.datadog_source_adapter
  lifecycle { destroy = false }
}

removed {
  from = aws_cloudwatch_log_group.datadog_source_adapter
  lifecycle { destroy = false }
}

removed {
  from = aws_lambda_function.datadog_source_adapter
  lifecycle { destroy = false }
}

removed {
  from = aws_lambda_function_url.datadog_source_adapter
  lifecycle { destroy = false }
}

removed {
  from = aws_cloudwatch_log_metric_filter.datadog_source_adapter_failures
  lifecycle { destroy = false }
}

removed {
  from = aws_cloudwatch_metric_alarm.datadog_source_adapter_failures
  lifecycle { destroy = false }
}
