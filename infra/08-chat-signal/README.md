# 08-chat-signal

Chat Signal SQS를 소비할 Lambda 실행 계층이다. `03-data`의 remote state에서 전용
SQS와 Candidate DynamoDB를 참조하며, EKS·Dify와 독립적으로 유지한다(D-048).

## Phase 3 상태

| 항목 | 상태 |
|---|---|
| Lambda와 실행 IAM | 코드 존재, 미적용 |
| SQS event source mapping | 코드 존재, `enabled = false`, 미적용 |
| 결정론적 분류·15초 집계 | 구현 및 로컬 테스트 통과, 미적용 |
| Candidate 처리 로직 | 구현 및 로컬 테스트 통과, 미적용 |
| Datadog·Dify·Bedrock 호출 | 권한·코드 모두 없음 |
| 원문 로그·DynamoDB·Candidate 저장 | 없음, 테스트로 검증 |

Worker는 `chat.signal.v1`을 메모리에서만 읽고 다음 순서로 처리한다.

```text
스키마 검증
  -> EVENT PENDING 멱등 상태
  -> 제외/회복 규칙
  -> strong/weak 분류
  -> broadcast + candidate type + event-time window 집계
  -> 사용자별 1표 조건부 기록
  -> 임계치 판정
  -> 60초 Candidate 조건부 생성/병합
  -> EVENT COMPLETED
```

`PENDING` 이벤트는 중간 DynamoDB 실패 후 재시도할 수 있다. 집계 투표와 Candidate
스냅샷은 조건부·멱등 갱신하므로, 재시도 과정에서 집계나 Candidate가 중복되지 않는다.

## IAM 경계

| 대상 | 허용 작업 |
|---|---|
| Chat Signal SQS | `ReceiveMessage`, `DeleteMessage`, `GetQueueAttributes` |
| Candidate DynamoDB | `GetItem`, `PutItem`, `UpdateItem`, `TransactWriteItems` |
| 전용 Log Group | `CreateLogStream`, `PutLogEvents` |

다른 큐·테이블, Datadog, Dify, Bedrock 권한은 없다.

## 검증

```bash
python3 -m unittest discover -s lambda/tests -p 'test_*.py'
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
```

로컬 검증 범위:

- Python Worker 테스트 20개: `AC-001`-`AC-007`, `AC-009`-`AC-010`, late arrival,
  중간 실패 복구, DynamoDB 조건부 쓰기 구조
- Chat Gateway 테스트 20개: `AC-008` fail-open 포함
- Lambda Python 3.13 컨테이너: runtime 모듈과 기본 제공 `boto3` import
- Terraform: `fmt -check`, `validate`
- Chat Gateway: TypeScript build와 Docker image build

이 검증은 DynamoDB Local이나 실제 AWS SQS-DynamoDB 통합 테스트가 아니다. 실제 AWS
동작은 Phase 4 Shadow 배포 전 별도 확인이 필요하다.

## 적용 금지

Phase 3의 완료 조건은 코드와 로컬 계약 검증까지다. 이 스택을 아직 `apply`하지
않으며 event source mapping은 계속 `enabled = false`로 고정한다. Phase 4는 Phase 2와
Phase 3 리뷰·병합 후 별도 승인으로 Shadow 배포하고, 실제 SQS IAM·DynamoDB 조건부
쓰기·Candidate 생성·외부 WebSocket fail-open을 각각 검증한다.
