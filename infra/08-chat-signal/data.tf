data "terraform_remote_state" "datastore" {
  backend = "s3"

  config = {
    bucket = var.state_bucket
    key    = var.datastore_state_key
    region = var.region
  }
}

locals {
  chat_signal_queue_arn    = data.terraform_remote_state.datastore.outputs.chat_signal_queue_arn
  chat_incident_table_name = data.terraform_remote_state.datastore.outputs.chat_incident_table_name
  chat_incident_table_arn  = data.terraform_remote_state.datastore.outputs.chat_incident_table_arn
  chat_incident_stream_arn = data.terraform_remote_state.datastore.outputs.chat_incident_table_stream_arn
  worker_name              = "${var.project}-${var.environment}-chat-signal-worker"
  chat_source_adapter_name = "${var.project}-${var.environment}-chat-candidate-source-adapter"
}

data "aws_sqs_queue" "agent_trigger" {
  name = var.agent_trigger_queue_name
}

data "aws_sns_topic" "agent_alarm" {
  name = var.agent_alarm_topic_name
}
