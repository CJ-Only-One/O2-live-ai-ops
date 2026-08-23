# 채팅 기반 Incident Candidate의 짧은 분석 버퍼와 파생 상태.
# 처리 계약은 docs/chat-incident-candidate.md, wire schema는 contracts.md 5.6·5.7.

resource "aws_sqs_queue" "chat_signal" {
  name = "${local.name}-chat-signal"

  # PRIV-002. AWS SQS의 최소 보존값이다. Worker 장애가 이를 넘으면 신호 유실을
  # 수용한다 — 고객 트랜잭션이 아니라 조기 탐지 보조 신호다(D-047).
  message_retention_seconds = 60

  sqs_managed_sse_enabled = true

  tags = {
    Name = "${local.name}-chat-signal"
  }
}

# 원문 DLQ는 만들지 않는다. 실패 메타데이터는 Lambda가 원문 없이 기록해야 한다.

resource "aws_dynamodb_table" "chat_incident_state" {
  name         = "${local.name}-chat-incident-state"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  # Phase 2 Agent Entry Source Adapter는 새 Candidate INSERT만 비동기로 읽는다.
  # KEYS_ONLY로는 privacy-safe Candidate payload를 만들 수 없고, NEW_AND_OLD_IMAGES는
  # UPDATE의 이전 payload까지 불필요하게 복제하므로 NEW_IMAGE만 사용한다.
  stream_enabled   = true
  stream_view_type = "NEW_IMAGE"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name = "${local.name}-chat-incident-state"
  }
}
