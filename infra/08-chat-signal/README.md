# 08-chat-signal

Chat Signal SQS를 소비하고 privacy-safe Candidate를 공통 Agent 진입 계약으로 변환하는
Lambda 실행 계층이다. `03-data`의 remote state에서 전용 SQS·Candidate DynamoDB·Stream을
참조하며, EKS·Dify와 독립적으로 유지한다(D-048, D-050).

## Agent Entry Phase 2 — 배포됨, 실행 비활성

```text
Candidate DynamoDB NEW_IMAGE Stream
  -> disabled Candidate-key event source
  -> Chat Candidate Source Adapter (execution flag false)
  -> Agent Trigger SQS
```

Phase 2에서는 event source와 실행 플래그를 모두 비활성화한다. 추가로
`NOT_BEFORE_EPOCH=2100-01-01`을 넣어, 비활성 기간에 Stream에 쌓인 Candidate가 Phase 3
활성화 시 테스트 입력으로 흘러가지 못하게 한다. Phase 3에서는 합성 테스트 시작 직전
cutover epoch를 명시해야 한다.

Event source filter는 `CANDIDATE#* + META` 키만 통과시킨다. Adapter 코드가
`INSERT` 여부와 Candidate 계약을 다시 검증해
`agent.trigger.v1`을 만든다. 원문·사용자 키·원문 해시는 입력 Candidate와 출력 envelope
모두 금지한다. Stream 재전달은 같은 `trigger_id`와 `idempotency_key`를 만들며, SQS
중복은 Phase 1B Worker ledger가 최종 차단한다.

전용 Adapter DLQ는 원문이 없는 Stream record 실패 메타데이터만 14일 보관한다. bounded
retry는 3회·최대 300초이며, DLQ와 Lambda Error 알람은 기존 Agent 알람 SNS를 재사용한다.
Adapter IAM에는 Candidate Stream read, Agent Trigger SQS send, DLQ send, log write만 있다.
Datadog·Dify·Bedrock·Candidate table write 권한은 없다.

적용은 `03-data` Stream 활성화 후 `08-chat-signal` 순서로만 한다. Stream output이 remote
state에 생기기 전에는 Adapter plan을 만들 수 없다. 세부 gate와 검증 상태는
`docs/agent-entrypoint.md` 6.3을 따른다.

2026-08-23 순차 적용 결과 `03-data`는 `0 add, 1 change, 0 destroy`, 이 스택은
`8 add, 0 change, 0 destroy`였고, 적용 후 두 stack 모두 `No changes`다. Adapter event
source와 실행 플래그는 모두 비활성이고, Agent Trigger Queue·Adapter DLQ·Adapter 로그
스트림은 모두 0이다. Phase 3 합성 Shadow E2E 전까지 이 상태를 유지한다.

Phase 3에서는 D-053의 합성 `broadcast_id` 정확히 1개와 명시 cutover가 있어야 event source와
실행 플래그를 함께 켤 수 있다. 허용되지 않은 운영 broadcast는 Queue로 보내지 않고 정상
제외하며, 빈 값·복수 값·형식 오류는 fail-closed한다. 기본값은 두 게이트 `false`, 빈
allowlist, 2100-01-01 cutoff다.

2026-08-23 현재 `03-data`의 SQS·DynamoDB와 이 스택의 Lambda·IAM은 적용됐다.
최초 외부 E2E는 Worker 5초 timeout과 SQS in-flight 지연으로 Candidate를 만들지 못했고,
생산자 `off`와 event source Disabled로 롤백했다(T-020, M-011). 수정 적용 후 생산자
`shadow`와 event source를 다시 활성화했고, 같은 고정 15초 window의 AC-004 E2E에서
Candidate 1건 생성을 확인했다.

## Phase 4 Shadow 운영 상태

| 항목 | 상태 |
|---|---|
| Lambda와 실행 IAM | Active; timeout 10초, 예약 동시성 2 |
| SQS event source mapping | Enabled; 최대 동시성 2 |
| 결정론적 분류·15초 집계 | 구현·로컬 테스트·AWS same-window 통합 확인 |
| Candidate 처리 로직 | same-window·strong·dedup·cooldown AWS E2E 통과 |
| 전용 SQS·DynamoDB | 적용 완료; 보존 60초·SSE·빈 backlog·TTL 검증 |
| Datadog·Dify·Bedrock 호출 | 권한·코드 모두 없음 |
| 원문 로그·DynamoDB·Candidate 저장 | 없음, 테스트로 검증 |

적용값은 timeout 10초, 예약 동시성 2, event source 최대 동시성 2다. Queue visibility
30초와 원문 보존 60초는 유지한다. 런타임 수정 apply는 `0 add, 2 change, 0 destroy`,
생산자 재활성화 apply는 `0 add, 1 change, 0 destroy`였고, 적용 후 두 스택 plan은 모두
`No changes`다.

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

- Python 테스트 28개: 기존 Worker 20개와 Phase 2 Source Adapter 8개
- Chat Gateway 테스트 20개: `AC-008` fail-open 포함
- Lambda Python 3.13 컨테이너: runtime 모듈과 기본 제공 `boto3` import
- Terraform: `fmt -check`, `validate`
- Chat Gateway: TypeScript build와 Docker image build

로컬 검증은 DynamoDB Local이나 실제 AWS SQS-DynamoDB 통합 테스트가 아니다. 최초 AWS
E2E에서 이 경계 때문에 T-020을 발견했고, 수정 후 외부 E2E를 반복해 Candidate 생성과
Queue drain, 원문 비기록을 검증했다. 고정 tumbling-window 경계의 미탐 가능성은 T-021과
canonical spec의 `VERIFY-CHAT-WINDOW-001`에 남아 있다.

## Shadow 관찰 suite

`apps/chat-gateway/scripts/shadow-observe.mjs`는 외부 WebSocket부터 실제 SQS-Lambda-
DynamoDB 경로를 반복 검증한다. 실환경 주소는 저장하지 않으며 명시적 허용값이 없으면
실행을 거부한다.

```bash
ALLOW_LIVE_SHADOW_TEST=1 \
CHAT_TEST_WS_BASE=ws://<dev-ingress-host> \
CHAT_TEST_ID_BASE=<unused-numeric-base> \
node apps/chat-gateway/scripts/shadow-observe.mjs
```

`CHAT_TEST_ID_BASE + 1`부터 `+ 5`까지가 broadcast ID로 사용된다. 실행 전 DynamoDB에
해당 5개 ID의 상태가 없는지 확인하고 매번 새 범위를 사용한다. 이 스크립트는 합성 원문
24건을 실제 전용 SQS에 넣으므로 dev Shadow에서만 실행한다.

2026-08-23 실행 결과:

| 시나리오 | 결과 |
|---|---|
| 일반 채팅 4건 | 모두 `UNRELATED`, Candidate 없음 |
| 한 사용자 약한 신호 4건 | 1표만 반영, duplicate-user 3, Candidate 없음 |
| strong 3 + weak 1 | `MEDIUM/READ_PATH` Candidate 1건 |
| 경계 offset 13.200초 3건 + 다음 window 0.399초 1건 | window 3+1, Candidate 없음 |
| 두 연속 window 약한 신호 4+4 | Candidate 1건 유지, version 2, matched 8 |

전체 24건은 모두 Worker status로 확인됐고 Queue는 visible/in-flight 0으로 비었다.
Lambda는 13회, duration 67-288ms, Errors 0, Throttles 0, 동시성 최대 2였다. DynamoDB와
CloudWatch에서 합성 원문은 0건이었다(M-011).

경계 시나리오는 현 tumbling window의 미탐을 재현하기 위한 것이다. 스크립트 성공을
rolling-window 보장이나 실제 운영 오탐률 측정으로 해석하지 않는다.

## Chat 입력 → 전용 Dify Workflow E2E

`apps/chat-gateway/scripts/chat-to-dify-e2e.mjs`는 현재 상시 활성인 Chat Gateway·Chat
Signal Worker 뒤의 비활성 실행 게이트를 합성 식별자 한 개로만 순차 활성화한다.

```text
external WebSocket chat
  -> Chat Gateway -> Chat Signal SQS -> Worker -> Candidate
  -> Chat Source Adapter -> Signal Queue -> Correlator
  -> Invocation Queue -> Generic Worker -> dedicated contract-test Dify Workflow
```

실행기는 시작 전 세 작업 Queue가 모두 비어 있는지, Chat Gateway가 `shadow`인지, Chat Signal
Worker consumer가 활성인지 확인한다. 기존 DLQ 메시지는 장애 증거이므로 삭제하거나 테스트
입력과 섞지 않는다. Signal·Invocation DLQ는 시작 baseline 증가 여부를 검사하고, Stream
Adapter DLQ는 비활성 기간의 5분 초과 record가 재활성화 시 이동할 수 있으므로 이번 합성
`broadcast_id`가 들어갔는지를 본문 비출력 방식으로 검사한다. Candidate ID와 Incident ID를
미리 추측하지 않고 앞 단계의 authoritative DynamoDB 상태에서 읽은 뒤 다음 단계 allowlist를
연다. 성공은 Candidate privacy 계약, `agent.incident.v1` revision 1, Worker ledger `SUCCEEDED`,
`attempt_count=1`, Dify `workflow_run_id` 존재를 모두 만족해야 한다.

```bash
cd apps/chat-gateway

ALLOW_LIVE_CHAT_TO_DIFY_E2E=1 \
CHAT_TEST_WS_BASE=ws://<dev-ingress-host> \
CHAT_E2E_BROADCAST_ID=bc_<unused-numeric-id> \
node scripts/chat-to-dify-e2e.mjs
```

이 테스트는 dev AWS 리소스와 전용 테스트 Workflow를 실제로 호출한다. 매번 사용하지 않은
`broadcast_id`를 써야 하며, 실행 중에는 Terraform targeted apply가 Adapter, Correlator,
Generic Worker와 각 event source만 변경한다. 종료 시 성공·실패와 무관하게 세 실행 게이트를
기본 비활성값으로 복귀시키고, 실행 중 발견한 합성 Candidate·Incident·ledger 키만 삭제한다.
원문은 결과와 로그에 출력하지 않는다. 원복 실패가 하나라도 있으면 테스트는 실패한다.

2026-08-24 최초 자동화 실행은 합성 채팅 4건·고유 사용자 4명, 네 WebSocket client의 fanout
수신 16건, `READ_PATH` Candidate와 `raw_chat_included=false`, Chat-only Incident revision 1,
전용 Dify Worker ledger `SUCCEEDED/attempt_count=1`을 확인했다. 종료 후 세 작업 Queue는 0,
Signal·Invocation DLQ는 0을 유지했고 기존 Adapter DLQ 2건은 삭제하지 않았다. 이번 합성
broadcast는 Adapter DLQ에 없었으며, 실행기가 변경한 Terraform 대상의 재-plan은 모두
`No changes`였다.

## Phase 4 적용 순서

적용 순서를 바꾸지 않는다.

1. `03-data` plan에서 Chat Signal SQS·DynamoDB 외 기존 데이터 리소스 변경이 없는지 본다. **완료**
2. `03-data`를 적용하고 Queue 보존 60초·SSE·DynamoDB TTL을 확인한다. **완료**
3. `08-chat-signal` plan/apply로 Lambda와 event source mapping을 만든다. **수정 재적용 및 Enabled 확인 완료**
4. `04-platform`은 Karpenter·KEDA 및 기존 IAM 변경과 섞이지 않는지 plan으로 먼저 분리 확인한다. **완료**
5. Chat Gateway IAM·ConfigMap을 반영하고 `CHAT_SIGNAL_MODE=shadow`로 Pod를 재시작한다. **재활성화 완료**
6. 외부 WebSocket에서 AC 시나리오를 보내 SQS 소비·Candidate·원문 비기록을 확인한다. **AC-004 same-window 통과**

Phase 4에서도 Datadog·Dify·Bedrock 호출과 자동 조치는 금지다.

2026-08-23 apply에서 Karpenter·KEDA 변경은 0건이었다. 함께 잡힌 서비스별 IAM 분리
`7 add, 3 change, 1 destroy`도 적용했다. destroy 1건은 기존 공유 SQS inline policy였고,
Chat Gateway·Order Worker는 각각 전용 Pod Identity 역할로 전환됐다.

## 롤백 순서

1. `CHAT_SIGNAL_MODE=off`를 반영하고 Chat Gateway를 재시작해 신규 원문 전송을 먼저 멈춘다.
2. `enable_event_source=false`를 적용해 Worker 소비를 멈춘다.
3. SQS·DynamoDB·Lambda 리소스는 조사 증거와 Terraform state를 위해 유지한다.

리소스 삭제를 롤백으로 사용하지 않는다. Queue 원문은 최대 60초 뒤 자동 소멸한다.
