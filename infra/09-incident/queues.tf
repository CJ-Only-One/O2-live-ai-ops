locals {
  agent_entry_queue_name = "${local.name}-agent-trigger"
  agent_entry_dlq_name   = "${local.name}-agent-trigger-dlq"
}

resource "aws_sns_topic" "incident_alarm" {
  name = "${local.name}-incident-alarm"
}

resource "aws_sqs_queue" "agent_entry_dlq" {
  name = local.agent_entry_dlq_name

  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "agent_entry" {
  name = local.agent_entry_queue_name

  visibility_timeout_seconds = 360
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.agent_entry_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "agent_entry" {
  queue_url = aws_sqs_queue.agent_entry_dlq.url

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.agent_entry.arn]
  })
}

resource "aws_cloudwatch_metric_alarm" "agent_entry_queue_age" {
  alarm_name          = "${local.name}-agent-entry-queue-age"
  alarm_description   = "Incident Signal Queue의 가장 오래된 메시지가 5분을 넘겼다."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  dimensions          = { QueueName = aws_sqs_queue.agent_entry.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 300
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.incident_alarm.arn]
  ok_actions          = [aws_sns_topic.incident_alarm.arn]
}

resource "aws_cloudwatch_metric_alarm" "agent_entry_dlq_not_empty" {
  alarm_name          = "${local.name}-agent-entry-dlq-not-empty"
  alarm_description   = "Incident Signal DLQ에 메시지가 있다. 확인 전 재투입하지 않는다."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.agent_entry_dlq.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.incident_alarm.arn]
  ok_actions          = [aws_sns_topic.incident_alarm.arn]
}
