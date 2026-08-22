# 08-chat-signal

Chat Signal SQS를 소비할 Lambda 실행 계층이다. `03-data`의 remote state에서 전용
SQS와 Candidate DynamoDB를 참조하며, EKS·Dify와 독립적으로 유지한다(D-048).

## Phase 1B 상태

| 항목 | 상태 |
|---|---|
| Lambda와 실행 IAM | 코드 존재, 미적용 |
| SQS event source mapping | 코드 존재, `enabled = false`, 미적용 |
| Candidate 처리 로직 | 없음 |
| 원문 로그·저장 | 없음 |

현재 handler는 SQS body를 읽지 않고 모든 `messageId`를 `batchItemFailures`로
반환한다. 실수로 직접 호출되더라도 메시지를 성공 처리하지 않는 안전 골격이다.

## IAM 경계

| 대상 | 허용 작업 |
|---|---|
| Chat Signal SQS | `ReceiveMessage`, `DeleteMessage`, `GetQueueAttributes` |
| Candidate DynamoDB | `GetItem`, `PutItem`, `UpdateItem`, `TransactWriteItems` |
| 전용 Log Group | `CreateLogStream`, `PutLogEvents` |

다른 큐·테이블, Datadog, Dify, Bedrock 권한은 없다.

## 검증

```bash
python3 -m unittest discover -s lambda -p 'test_*.py'
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
```

## 적용 금지

Phase 1B의 완료 조건은 코드 검증까지다. 이 스택을 아직 `apply`하지 않는다.
다음 단계는 Chat Gateway publisher를 `off/shadow` 플래그 뒤에 추가하는 것이다.
실제 Candidate 처리기와 AC-001~AC-010이 준비되기 전에는 event source mapping을
활성화하지 않는다.
