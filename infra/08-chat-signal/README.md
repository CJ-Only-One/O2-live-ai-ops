# 08-chat-signal

Chat Signal SQS를 소비할 Lambda 실행 계층이다. `03-data`의 remote state에서 전용
SQS와 Candidate DynamoDB를 참조하며, EKS·Dify와 독립적으로 유지한다(D-048).

2026-08-23 현재 `03-data`의 SQS·DynamoDB와 이 스택의 Lambda·IAM은 적용됐다.
최초 외부 E2E는 Worker 5초 timeout과 SQS in-flight 지연으로 Candidate를 만들지 못했고,
생산자 `off`와 event source Disabled로 롤백했다(T-020, M-011).

## Phase 4 Shadow 준비 상태

| 항목 | 상태 |
|---|---|
| Lambda와 실행 IAM | 적용 완료; runtime limit 수정 전 source disabled |
| SQS event source mapping | 롤백으로 Disabled; 수정 병합 후 다시 활성화 |
| 결정론적 분류·15초 집계 | 구현 및 로컬 테스트 통과, AWS 통합 확인 필요 |
| Candidate 처리 로직 | 구현 및 로컬 테스트 통과, AWS 통합 확인 필요 |
| 전용 SQS·DynamoDB | 적용 완료; 보존 60초·SSE·빈 backlog·TTL 검증 |
| Datadog·Dify·Bedrock 호출 | 권한·코드 모두 없음 |
| 원문 로그·DynamoDB·Candidate 저장 | 없음, 테스트로 검증 |

수정 의도값은 timeout 10초, 예약 동시성 2, event source 최대 동시성 2다. Queue
visibility 30초와 원문 보존 60초는 유지한다. 현재 롤백 state 기준 plan은 이 함수와
event source mapping만 `0 add, 2 change, 0 destroy`다.

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

이 검증은 DynamoDB Local이나 실제 AWS SQS-DynamoDB 통합 테스트가 아니다. 최초 AWS
E2E에서 이 경계 때문에 T-020을 발견했다. runtime-limit 수정 후 반드시 외부 E2E를 반복한다.

## Phase 4 적용 순서

적용 순서를 바꾸지 않는다.

1. `03-data` plan에서 Chat Signal SQS·DynamoDB 외 기존 데이터 리소스 변경이 없는지 본다. **완료**
2. `03-data`를 적용하고 Queue 보존 60초·SSE·DynamoDB TTL을 확인한다. **완료**
3. `08-chat-signal` plan/apply로 Lambda와 event source mapping을 만든다. **완료 후 Disabled 롤백**
4. `04-platform`은 Karpenter·KEDA 및 기존 IAM 변경과 섞이지 않는지 plan으로 먼저 분리 확인한다. **완료**
5. Chat Gateway IAM·ConfigMap을 반영하고 `CHAT_SIGNAL_MODE=shadow`로 Pod를 재시작한다. **완료 후 `off` 롤백**
6. 외부 WebSocket에서 AC 시나리오를 보내 SQS 소비·Candidate·원문 비기록을 확인한다. **최초 실패, 수정 후 재실행 필요**

Phase 4에서도 Datadog·Dify·Bedrock 호출과 자동 조치는 금지다.

2026-08-23 apply에서 Karpenter·KEDA 변경은 0건이었다. 함께 잡힌 서비스별 IAM 분리
`7 add, 3 change, 1 destroy`도 적용했다. destroy 1건은 기존 공유 SQS inline policy였고,
Chat Gateway·Order Worker는 각각 전용 Pod Identity 역할로 전환됐다.

## 롤백 순서

1. `CHAT_SIGNAL_MODE=off`를 반영하고 Chat Gateway를 재시작해 신규 원문 전송을 먼저 멈춘다.
2. `enable_event_source=false`를 적용해 Worker 소비를 멈춘다.
3. SQS·DynamoDB·Lambda 리소스는 조사 증거와 Terraform state를 위해 유지한다.

리소스 삭제를 롤백으로 사용하지 않는다. Queue 원문은 최대 60초 뒤 자동 소멸한다.
