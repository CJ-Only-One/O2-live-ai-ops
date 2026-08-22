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
  worker_name              = "${var.project}-${var.environment}-chat-signal-worker"
}
