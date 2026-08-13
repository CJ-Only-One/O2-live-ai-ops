# Flow Logs 목적지를 CloudWatch Logs가 아닌 S3로 잡은 이유:
#  1) CloudWatch Logs 수집 단가가 S3 전달보다 비싸다 (vended logs 기준 약 5배)
#  2) 데이터 파이프라인 트랙(김수연/김도훈)이 Athena/Glue로 바로 질의하기 좋다
#  3) 보안 트랙(이상문)의 매크로/크리덴셜 스터핑 탐지 근거 데이터로 재사용 가능

resource "aws_s3_bucket" "flow_logs" {
  count = var.enable_flow_logs ? 1 : 0

  bucket        = "${local.name}-flowlogs-${data.aws_caller_identity.current.account_id}"
  force_destroy = true # 3주 프로젝트 종료 시 destroy 막히지 않도록. 운영에서는 false.

  tags = {
    Name = "${local.name}-flowlogs"
  }
}

resource "aws_s3_bucket_public_access_block" "flow_logs" {
  count = var.enable_flow_logs ? 1 : 0

  bucket                  = aws_s3_bucket.flow_logs[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "flow_logs" {
  count = var.enable_flow_logs ? 1 : 0

  bucket = aws_s3_bucket.flow_logs[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-KMS는 Flow Logs 전달 시 추가 설정/비용 발생
    }
  }
}

# 부하테스트 기간 로그가 급증하므로 만료 정책은 필수
resource "aws_s3_bucket_lifecycle_configuration" "flow_logs" {
  count = var.enable_flow_logs ? 1 : 0

  bucket = aws_s3_bucket.flow_logs[0].id

  rule {
    id     = "expire"
    status = "Enabled"

    filter {}

    expiration {
      days = var.flow_logs_retention_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

data "aws_iam_policy_document" "flow_logs_bucket" {
  count = var.enable_flow_logs ? 1 : 0

  statement {
    sid    = "AWSLogDeliveryWrite"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["delivery.logs.amazonaws.com"]
    }

    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.flow_logs[0].arn}/*"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    # Confused deputy 방지
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:*"]
    }
  }

  statement {
    sid    = "AWSLogDeliveryAclCheck"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["delivery.logs.amazonaws.com"]
    }

    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.flow_logs[0].arn]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_s3_bucket_policy" "flow_logs" {
  count = var.enable_flow_logs ? 1 : 0

  bucket = aws_s3_bucket.flow_logs[0].id
  policy = data.aws_iam_policy_document.flow_logs_bucket[0].json
}

resource "aws_flow_log" "vpc" {
  count = var.enable_flow_logs ? 1 : 0

  vpc_id               = aws_vpc.this.id
  traffic_type         = var.flow_logs_traffic_type
  log_destination_type = "s3"
  log_destination      = aws_s3_bucket.flow_logs[0].arn

  # 600초(10분) 집계. 기본값 600, 최소 60.
  # 60초로 낮추면 탐지 지연은 줄지만 객체 수와 비용이 10배가 된다.
  # 1차 탐지는 메트릭이 담당하고,
  # Flow Logs는 사후 RCA/보안 분석용이므로 600초로 충분하다.
  max_aggregation_interval = 600

  # pkt-srcaddr / pkt-dstaddr 는 NAT/LB 뒤의 실제 Pod IP를 식별할 때 필요하다.
  # 매크로 공격 시나리오에서 "요청 출처 분포"를 판별하는 핵심 필드.
  log_format = join(" ", [
    "$${version}", "$${account-id}", "$${interface-id}",
    "$${srcaddr}", "$${dstaddr}", "$${srcport}", "$${dstport}",
    "$${protocol}", "$${packets}", "$${bytes}",
    "$${start}", "$${end}", "$${action}", "$${log-status}",
    "$${vpc-id}", "$${subnet-id}", "$${instance-id}", "$${tcp-flags}",
    "$${type}", "$${pkt-srcaddr}", "$${pkt-dstaddr}",
    "$${flow-direction}", "$${traffic-path}",
  ])

  destination_options {
    file_format                = "parquet" # Athena 스캔 비용 절감
    per_hour_partition         = true      # 파티션 프루닝으로 쿼리 비용 절감
    hive_compatible_partitions = true      # Glue Crawler 없이 파티션 인식
  }

  tags = {
    Name = "${local.name}-vpc-flowlog"
  }
}
