# O2 파이프라인 전용 인시던트 이력 저장소.
#
# history.tf 의 원본(alert-triage)과 완전히 분리해서 만든다. 같은 버킷/인덱스를
# 공유하면 두 파이프라인이 같은 Datadog 모니터를 받을 때 cycle_key 가 겹쳐
# 서로의 인시던트를 덮어쓴다 (lambda_o2.tf 상단 주석 참고). 버킷을 나누면
# 코드(worker.py/ingress.py) 수정 없이 환경변수만으로 완전히 격리된다.

resource "aws_s3_bucket" "history_o2" {
  bucket = "${local.name}-history-o2-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "history_o2" {
  bucket = aws_s3_bucket.history_o2.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "history_o2" {
  bucket = aws_s3_bucket.history_o2.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3vectors_vector_bucket" "history_o2" {
  vector_bucket_name = "${local.name}-history-vectors-o2"
}

resource "aws_s3vectors_index" "incidents_o2" {
  vector_bucket_name = aws_s3vectors_vector_bucket.history_o2.vector_bucket_name
  index_name         = "incidents"

  # history.tf 의 embed_model_id(local, 원본과 공유)와 짝이 맞아야 한다.
  # 모델을 바꾸면 이 차원도 바꾸고 인덱스를 새로 만들어야 한다.
  data_type       = "float32"
  dimension       = 1024
  distance_metric = "cosine"

  metadata_configuration {
    non_filterable_metadata_keys = ["summary"]
  }
}
