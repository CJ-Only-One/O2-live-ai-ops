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

data "aws_iam_policy_document" "aggregate_lambda" {
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

  maximum_retry_attempts         = 3
  bisect_batch_on_function_error = true
}
