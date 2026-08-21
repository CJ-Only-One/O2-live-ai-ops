# 인시던트 이력 저장소. 두 종류를 한 파일에 둔다.
#
#   S3 버킷        원본 JSON. 진실은 여기 하나뿐이고 append-only 다
#   S3 Vectors     "비슷한 인시던트 찾기" 용 벡터 인덱스
#
# 왜 Dify 번들 weaviate 가 아닌가. weaviate 는 EC2 루트 볼륨에만 있고
# `delete_on_termination = true` 라 인스턴스가 한 번 교체되면 전멸한다
# (README 의 "함정" 표). 이력은 이 프로젝트의 산출물이므로 EC2 밖에 둔다.
#
# ★ 이름에 "agent" 를 쓰지 않는다. versions.tf 의 state 키 주석과 같은 이유다 —
#   그 이름은 AI 에이전트 백데이터 파트(06-datastream)가 쓸 가능성이 있고,
#   `o2-agent-context` 처럼 이미 쓰고 있는 것도 있다. 이 스택 것은 dify 접두사로 둔다.

locals {
  # ★ 이 값과 위 인덱스의 dimension 은 한 몸이다. 모델을 바꾸면 차원이
  #   바뀌고, 차원이 바뀌면 인덱스를 새로 만들어야 한다. 한쪽만 고치지 마라.
  #   IAM 도 이 ID 로 좁혀져 있다 (lambda.tf).
  embed_model_id = "amazon.titan-embed-text-v2:0"
}

# ── 원본 ─────────────────────────────────────────────────────────

# 버킷 이름은 전역 유일이라 계정 번호를 붙인다 (tfstate 버킷과 같은 방식).
resource "aws_s3_bucket" "history" {
  bucket = "${local.name}-history-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "history" {
  bucket = aws_s3_bucket.history.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 키가 cycle_key 라 덮어쓸 일이 없지만, 이 데이터가 이 작업의 산출물 전부다.
# 버그 하나로 날아가는 경로를 남기지 않는다. 300MB/년 규모라 비용은 없다시피 하다.
resource "aws_s3_bucket_versioning" "history" {
  bucket = aws_s3_bucket.history.id

  versioning_configuration {
    status = "Enabled"
  }
}

# ★ 암호화 리소스를 두지 않는다. 2023년부터 신규 버킷은 SSE-S3 가 기본이다.
#   KMS 로 올리면 요청마다 KMS 호출료가 붙는데, 여기 들어가는 것은 이미
#   Datadog 과 CloudWatch 에 있는 알림 본문이라 등급을 올릴 이유가 없다.
#
# ★ 수명주기 규칙도 두지 않는다. 객체가 건당 수 KB 라 IA 로 옮기면
#   최소 과금 단위(128KB)와 전환 요청비 때문에 **오히려 비싸진다.**

# ── 벡터 ─────────────────────────────────────────────────────────

resource "aws_s3vectors_vector_bucket" "history" {
  vector_bucket_name = "${local.name}-history-vectors"
}

resource "aws_s3vectors_index" "incidents" {
  vector_bucket_name = aws_s3vectors_vector_bucket.history.vector_bucket_name
  index_name         = "incidents"

  # titan-embed-text-v2 의 기본 출력 차원. 임베딩 모델을 바꾸면 이 값도
  # 바뀌고, **차원이 다르면 인덱스를 새로 만들어야 한다.** 기존 벡터를
  # 이어 쓸 수 없으므로 모델 교체는 곧 전체 재색인이다.
  data_type       = "float32"
  dimension       = 1024
  distance_metric = "cosine"

  metadata_configuration {
    # summary 는 프롬프트에 그대로 넣을 문장이라 길다. 필터에 쓸 일이
    # 없는 큰 텍스트를 필터 가능으로 두면 인덱스만 무거워진다.
    non_filterable_metadata_keys = ["summary"]
  }
}
