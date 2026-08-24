data "archive_file" "aggregate" {
  type        = "zip"
  output_path = "${path.module}/lambda/aggregate.zip"

  # 함수 본문과 o2warm 패키지를 함께 담습니다.
  # local.warm_root / local.warm_sources 는 warm-path.tf 에 있습니다.
  source {
    content  = file("${local.warm_root}/handlers/aggregate.py")
    filename = "handler.py"
  }

  dynamic "source" {
    for_each = local.warm_sources

    content {
      content  = file("${local.warm_root}/src/${source.value}")
      filename = source.value
    }
  }
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "aggregate_lambda" {
  name               = "o2-agg-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_sqs_queue" "aggregate_dlq" {
  name                      = "o2-agg-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

data "aws_iam_policy_document" "aggregate_lambda" {
  statement {
    sid       = "SendFailedKinesisBatchToDlq"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.aggregate_dlq.arn]
  }

  statement {
    sid = "ReadBusinessStream"

    actions = [
      "kinesis:DescribeStream",
      "kinesis:DescribeStreamSummary",
      "kinesis:GetRecords",
      "kinesis:GetShardIterator",
      "kinesis:ListShards",
    ]

    resources = [aws_kinesis_stream.business.arn]
  }

  statement {
    sid       = "ListKinesisStreams"
    actions   = ["kinesis:ListStreams"]
    resources = ["*"]
  }

  statement {
    sid = "WriteAgentContext"

    actions = [
      "dynamodb:BatchWriteItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
    ]

    resources = [aws_dynamodb_table.agent_context.arn]
  }

  statement {
    sid = "WriteLambdaLogs"

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = ["${aws_cloudwatch_log_group.aggregate.arn}:*"]
  }
}

resource "aws_iam_role_policy" "aggregate_lambda" {
  name   = "o2-agg-lambda-policy"
  role   = aws_iam_role.aggregate_lambda.id
  policy = data.aws_iam_policy_document.aggregate_lambda.json
}

resource "aws_cloudwatch_log_group" "aggregate" {
  name              = "/aws/lambda/o2-agg"
  retention_in_days = 7
}

# Datadog 장애가 집계 Lambda를 실패시키지 않으므로 intake와 독립된 로그 기반
# 지표로 전송 실패를 감시한다.
resource "aws_cloudwatch_log_metric_filter" "datadog_submit_failure" {
  name           = "o2-datadog-submit-failure"
  log_group_name = aws_cloudwatch_log_group.aggregate.name
  pattern        = "DATADOG_SUBMIT_FAILED"

  metric_transformation {
    name      = "DatadogSubmitFailure"
    namespace = "O2/Warm"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "datadog_submit_failure" {
  alarm_name          = "o2-warm-datadog-submit-failure"
  alarm_description   = "Warm aggregate Lambda failed to submit metrics to Datadog; aggregation remains fail-open."
  namespace           = "O2/Warm"
  metric_name         = "DatadogSubmitFailure"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "aggregate_near_timeout" {
  alarm_name          = "o2-warm-aggregate-near-timeout"
  alarm_description   = "o2-agg maximum duration exceeded 90 percent of its configured timeout."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  dimensions          = { FunctionName = aws_lambda_function.aggregate.function_name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = aws_lambda_function.aggregate.timeout * 1000 * 0.9
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "aggregate_discarded_events" {
  for_each = toset(["DuplicateDiscarded", "LateArrival", "DecodeErrors"])

  alarm_name          = "o2-warm-${lower(each.value)}"
  alarm_description   = "o2-agg emitted ${each.value}; inspect stream ordering and event contracts."
  namespace           = "O2/Warm"
  metric_name         = each.value
  dimensions          = { FunctionName = "o2-agg", Environment = var.environment }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "business_source_aggregate_count_mismatch" {
  alarm_name          = "o2-warm-business-source-aggregate-count-mismatch"
  alarm_description   = "Business Kinesis source records and decoded aggregate events differ in the same 5-minute window."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 0
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "difference"
    expression  = "ABS(source_records - aggregate_events)"
    label       = "Business source/aggregate count difference"
    return_data = true
  }

  metric_query {
    id          = "source_records"
    return_data = false
    metric {
      namespace   = "O2/Warm"
      metric_name = "SourceRecordCount"
      period      = 300
      stat        = "Sum"
      dimensions = {
        FunctionName = "o2-agg"
        Environment  = var.environment
        Source       = aws_kinesis_stream.business.name
      }
    }
  }

  metric_query {
    id          = "aggregate_events"
    return_data = false
    metric {
      namespace   = "O2/Warm"
      metric_name = "AggregateEventCount"
      period      = 300
      stat        = "Sum"
      dimensions = {
        FunctionName = "o2-agg"
        Environment  = var.environment
        Source       = aws_kinesis_stream.business.name
      }
    }
  }
}

resource "aws_lambda_function" "aggregate" {
  function_name = "o2-agg"
  role          = aws_iam_role.aggregate_lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  architectures = ["arm64"]

  # 배관만 하던 때는 128MiB/30초로 충분했지만, 이제 부분 집계를 메모리에
  # 만들고 DynamoDB 병합을 재시도합니다.
  timeout     = 60
  memory_size = 512

  filename         = data.archive_file.aggregate.output_path
  source_code_hash = data.archive_file.aggregate.output_base64sha256

  environment {
    variables = local.warm_env
  }

  depends_on = [aws_iam_role_policy.aggregate_lambda]
}

resource "aws_lambda_event_source_mapping" "business" {
  event_source_arn  = aws_kinesis_stream.business.arn
  function_name     = aws_lambda_function.aggregate.arn
  starting_position = "LATEST"
  batch_size        = 100
  enabled           = true

  # 클릭과 서버 요청이 같은 10초 창 안에서 만나야 click_ratio 가 나옵니다.
  # 배치 창이 길면 늦게 도착한 쪽이 다음 윈도우로 밀려납니다.
  maximum_batching_window_in_seconds = 2

  # ---------------------------------------------------------------------------
  # parallelization_factor 를 설정하지 않습니다. 기본값 1 이 **의도한 값**입니다.
  #
  # 집계기가 밀릴 때(M-015 에서 IteratorAge 102초를 봤습니다) 이 값을 올리는
  # 것이 가장 먼저 떠오르는 손잡이인데, **이 파이프라인에서는 데이터가 조용히
  # 줄어듭니다.**
  #
  # 이유 — 집계기의 이중 집계 가드(`WindowSketch.already_applied`)가 샤드별
  # sequence number 를 **최댓값 하나**로만 들고 있습니다. 같은 샤드를 여러
  # 배치가 동시에 처리하면 늦게 시작한 배치가 먼저 끝날 수 있고, 그러면 앞선
  # 배치가 재시도로 오인돼 통째로 버려집니다. 예외도 오류도 없습니다.
  #
  # 실측: 같은 샤드에서 배치 둘(각 10건)이 뒤바뀌어 도착하면 20건이 아니라
  # **10건**이 남습니다. `warm/tests/test_sequence_guard.py` 가 고정해 뒀습니다.
  #
  # **밀리는 것은 샤드 수로 풉니다.** 샤드가 다르면 `source` 키가 갈려
  # (`aggregate._source_of()` 가 스트림+샤드로 만듭니다) 번호를 독립적으로
  # 비교하므로 안전합니다. 근거와 대안 비교는 D-063.
  # ---------------------------------------------------------------------------

  maximum_retry_attempts         = 3
  bisect_batch_on_function_error = true

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.aggregate_dlq.arn
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "aggregate_dlq_not_empty" {
  alarm_name          = "o2-agg-dlq-not-empty"
  alarm_description   = "A Kinesis batch exhausted o2-agg retries and reached its DLQ."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.aggregate_dlq.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}
