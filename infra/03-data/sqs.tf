# 주문 확정 큐. API 가 Valkey DECR 로 재고 판정을 끝낸 뒤 여기에 넣고,
# 워커가 꺼내 MySQL 에 기록한다 (설계 문서 3.6).
#
# Standard 를 쓰는 이유는 FIFO 가 필요 없어서다. 주문 사이에 순서 요구가 없고
# 중복은 Idempotency-Key 로 흡수한다. FIFO 는 그룹당 처리량 상한이 있어
# 특가 스파이크(Peak 2,400 RPS)에서 오히려 병목이 된다.

# DLQ 를 먼저 만든다. 메인 큐가 redrive_policy 로 이것을 참조한다.
resource "aws_sqs_queue" "order_dlq" {
  name = "${local.name}-order-dlq"

  # DLQ 는 사람이 열어보기 전까지 보관해야 의미가 있다. 최대치로 둔다.
  message_retention_seconds = 1209600 # 14일

  sqs_managed_sse_enabled = true

  tags = {
    Name = "${local.name}-order-dlq"
  }
}

resource "aws_sqs_queue" "order" {
  name = "${local.name}-order"

  visibility_timeout_seconds = var.order_queue_visibility_timeout
  message_retention_seconds  = 345600 # 4일 (기본값)

  # KMS 대신 SQS 관리형 암호화를 쓴다. 추가 비용이 없고 키 관리도 없다.
  sqs_managed_sse_enabled = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.order_dlq.arn
    maxReceiveCount     = var.order_queue_max_receive_count
  })

  tags = {
    Name = "${local.name}-order"
  }
}

# DLQ 쪽에서도 소스 큐를 명시한다. 콘솔에서 "DLQ 재처리" 버튼이 이 설정을 본다.
resource "aws_sqs_queue_redrive_allow_policy" "order_dlq" {
  queue_url = aws_sqs_queue.order_dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.order.arn]
  })
}

# 큐에 접근할 IAM 역할은 여기서 만들지 않는다.
# 파드의 ServiceAccount 이름과 네임스페이스가 정해져야 Pod Identity association 을
# 걸 수 있는데, 그건 애플리케이션이 생기는 Phase 3 의 일이다.
# 04-platform 이 external-secrets 에 대해 하고 있는 것과 같은 패턴으로 붙인다.
