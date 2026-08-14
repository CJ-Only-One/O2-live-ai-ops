# Glue가 작업 스크립트와 Raw 데이터를 읽고 ML-ready 결과를 쓸 때 사용하는 역할입니다.
data "aws_iam_policy_document" "glue_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ml_data_prep_glue" {
  name               = "o2-ml-data-prep-glue-role"
  assume_role_policy = data.aws_iam_policy_document.glue_assume_role.json
}

data "aws_iam_policy_document" "ml_data_prep_glue" {
  statement {
    sid = "ListDataLake"

    actions = [
      "s3:GetBucketLocation",
      "s3:ListBucket",
    ]

    resources = [aws_s3_bucket.data_lake.arn]
  }

  statement {
    sid = "ReadRawAndJobScript"

    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.data_lake.arn}/raw/business/*",
      "${aws_s3_bucket.data_lake.arn}/raw/client/*",
      "${aws_s3_bucket.data_lake.arn}/glue/scripts/*",
    ]
  }

  statement {
    sid = "WriteMlReadyData"

    actions = [
      "s3:AbortMultipartUpload",
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:PutObject",
    ]

    # EMRFS는 출력 경로 준비 시 ml-ready_$folder$ 마커도 생성/삭제한다.
    resources = ["${aws_s3_bucket.data_lake.arn}/ml-ready*"]
  }

  statement {
    sid = "WriteGlueLogs"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = ["arn:aws:logs:*:${data.aws_caller_identity.current.account_id}:log-group:/aws-glue/*"]
  }
}

resource "aws_iam_role_policy" "ml_data_prep_glue" {
  name   = "o2-ml-data-prep-glue-policy"
  role   = aws_iam_role.ml_data_prep_glue.id
  policy = data.aws_iam_policy_document.ml_data_prep_glue.json
}

# Terraform 적용 시 Glue가 실행할 PySpark 파일을 데이터 레이크에 함께 배포합니다.
resource "aws_s3_object" "ml_data_prep_script" {
  bucket = aws_s3_bucket.data_lake.id
  key    = "glue/scripts/etl_ml_preparation.py"
  source = "${path.module}/glue/etl_ml_preparation.py"
  etag   = filemd5("${path.module}/glue/etl_ml_preparation.py")
}

resource "aws_glue_job" "ml_data_prep" {
  name     = "o2-ml-data-prep-job"
  role_arn = aws_iam_role.ml_data_prep_glue.arn

  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  max_retries       = 1

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${aws_s3_object.ml_data_prep_script.bucket}/${aws_s3_object.ml_data_prep_script.key}"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
  }

  depends_on = [aws_iam_role_policy.ml_data_prep_glue]
}

# Glue 스케줄 트리거가 매일 15:00 UTC(한국 시간 자정)에 작업을 시작합니다.
# EventBridge 규칙은 Glue 워크플로만 타깃으로 지원하고 잡은 지원하지 않아 네이티브 트리거를 사용합니다.
resource "aws_glue_trigger" "ml_data_prep_daily" {
  name        = "o2-ml-data-prep-daily"
  description = "Run the O2 ML data preparation Glue job daily at 00:00 KST"
  type        = "SCHEDULED"
  schedule    = "cron(0 15 * * ? *)"
  enabled     = true

  actions {
    job_name = aws_glue_job.ml_data_prep.name
  }
}
