# AI Agent 공통 진입점 — canonical design

> **Audience:** coding agents and reviewers
> **Status:** Phase 1A complete; Phase 1B infrastructure not implemented
> **Updated:** 2026-08-23
> **Decision:** `decisions.md` D-050
> **Wire contract:** `contracts.md` 5.8 and `contracts/agent-trigger-v1.schema.json`

```yaml
implementation_state:
  runtime_baseline_verified: COMPLETE
  common_contract: COMPLETE
  agent_trigger_queue: NOT_IMPLEMENTED
  chat_candidate_adapter: NOT_IMPLEMENTED
  generic_dify_worker: NOT_IMPLEMENTED
  dedicated_test_workflow: PUBLISHED_CODE_ONLY
  dedicated_test_workflow_ui_contract_tests: PASS
  dedicated_test_workflow_service_api_tests: PASS
  dedicated_test_workflow_dsl: RECORDED_IN_REPOSITORY
  dedicated_test_workflow_api_key: STORED_IN_SECRETS_MANAGER
  existing_team_workflow_targeted: false
  datadog_migration: NOT_STARTED
  production_agent_handoff: DISABLED
activation_blockers:
  - GENERIC_ENTRY_WORKER_AND_IDEMPOTENCY_LEDGER_NOT_IMPLEMENTED
production_migration_blockers:
  - EXISTING_O2_DIFY_DLQ_NOT_EMPTY
  - DEPLOYED_TEAM_WORKFLOW_DSL_NOT_EXPORTED_TO_REPOSITORY
```

이 문서는 Chat Incident Candidate를 AI Agent 호출로 연결하는 **새 진입점**의 원본이다.
채팅 분류 규칙이나 임계치는 [`chat-incident-candidate.md`](chat-incident-candidate.md)가
소유하며, 이 문서는 Candidate가 생성된 이후만 다룬다.

## 0. 확인된 현재 상태

2026-08-23에 저장소와 실환경을 함께 확인했다.

| 항목 | 확인 결과 |
|---|---|
| Dify 배치 | EKS 밖 private EC2, SSM 접속, Dify 1.16.1 |
| Agent 호출 | Datadog Ingress Lambda가 비동기로 VPC Worker Lambda를 호출하고 Worker가 Dify Workflow API를 blocking 호출 |
| 관찰한 기존 게시 앱 | `O2 Agentic AIOps — Source-Aligned Mock v4`; 팀 구성 중인 앱이며 신규 진입점 대상이 아님 |
| 확인한 Dify 입력 기능 | `custom_alert_json` 형태의 paragraph 입력과 게시 graph 참조가 가능함을 확인 |
| 전용 contract-test 앱 | 별도 앱으로 게시 완료; Start → Code → Output, LLM·Bedrock·자동 조치 없음 |
| 게시 전 UI 계약 테스트 | Chat·Datadog 정상 예시 ACCEPTED, source/schema 불일치 REJECTED, 토큰 0 |
| Service API 계약 테스트 | 전용 API key로 Chat·Datadog succeeded, 불일치 failed, 토큰 0 |
| 전용 key 보관 | Secrets Manager `o2/dev/dify-agent-entry-contract-test`; 소스·Terraform state에 값 없음 |
| 채팅 Candidate handoff | 미구현, `agent_handoff_status=NOT_CONFIGURED` |
| 기존 Agent 경로 상태 | 성공 실행도 있으나 Worker 오류와 DLQ backlog가 있어 신규 경로의 무검증 재사용 금지 |

배포된 기존 앱을 읽은 목적은 Dify 1.16.1에서 필요한 입력 형태를 지원하는지 확인하는
것이었다. 그 앱이나 API key에는 신규 Queue·Worker를 연결하지 않았다. 기존 앱에는
`behavior`, `custom_alert_json`, Datadog 호환 입력이 있지만 저장소 DSL과 README에는
Datadog 입력만 남아 있다(T-022). 이 drift는 production migration blocker이지, 별도
테스트 앱으로 수행할 신규 진입점 실험의 blocker는 아니다.

## 1. 결정

### 1.1 원본 스키마는 달라도 된다

Datadog과 채팅은 의미가 다르므로 source schema를 억지로 같게 만들지 않는다.

| Source | source schema | 의미 |
|---|---|---|
| Datadog | `datadog.alert.v1` | 임계치를 넘은 모니터 알림 |
| Chat | `chat.incident_candidate.v1` | 사용자가 먼저 체감한 증상 집합, 메트릭 미확인 |

두 source schema는 **Source Adapter 앞에서는 달라도 된다.** 하지만 Agent Queue부터는
공통 envelope `agent.trigger.v1`을 사용한다. `source`가 discriminator이고 `evidence`만
source별 구조를 갖는다.

```text
source-specific JSON
  -> Source Adapter
  -> agent.trigger.v1
  -> Agent Trigger SQS
  -> Generic Agent Worker
  -> Dify custom_alert_json
```

이 경계가 없으면 Dify가 `alert_title` 유무로 source를 추측해야 하고, 새 source가 생길
때마다 워크플로 전체가 조건문과 빈 문자열에 의존한다.

### 1.2 채팅은 Candidate 생성 때 한 번만 호출한다

초기 정책은 `CANDIDATE_CREATED`만 Agent 호출 대상으로 삼는다. 쿨다운 중
`CANDIDATE_UPDATED`는 저장만 하고 다시 호출하지 않는다. 채팅 메시지 한 건당 Agent를
호출하거나 동일 Candidate 업데이트마다 호출하는 것은 금지한다.

초기 멱등 키는 다음과 같다.

```text
chat:<candidate_id>
datadog:<cycle_key>:<transition>
```

업데이트 재분석이 필요해지면 `chat:<candidate_id>:<revision>`으로 계약을 올리고,
호출 빈도와 비용을 측정한 뒤 별도로 결정한다.

### 1.3 팀 workflow와 테스트 workflow를 분리한다

신규 진입점은 팀원이 노드를 구성 중인 기존 앱을 호출하지 않는다. Dify에 전용 테스트
앱 `O2 Agent Entry Contract Test v1`을 새로 만들고 다음 경계를 지킨다.

| 소유 대상 | 규칙 |
|---|---|
| 테스트 앱 | `custom_alert_json` 하나를 start contract로 사용 |
| API key | 테스트 앱 전용 key를 별도 Secrets Manager secret으로 관리 |
| DSL | 생성 즉시 export해 `infra/06-agent/dify/`에 커밋 |
| Worker 설정 | 기존 `dify-api-key`와 분리된 secret 이름을 주입 |
| 트래픽 | 합성 Candidate만 허용; 기존 Datadog webhook과 운영 Chat source는 연결 금지 |

첫 게시 버전은 `Start -> Code validation -> deterministic output`만 둬 transport와 계약을
검증한다. 이것이 통과한 뒤 같은 테스트 앱에 Bedrock LLM과 read-only Datadog Pull을
추가한다. 처음부터 팀 workflow 전체를 복제하면 실패 원인이 진입 계약인지 진단 노드인지
분리할 수 없다.

production 전환 시에는 이 안정된 entry workflow가 source 검증·라우팅을 소유하고,
팀의 diagnosis workflow는 그 뒤에서 별도 버전으로 진화하게 한다. 두 workflow 사이의
호출 방식은 테스트 결과와 Dify export 가능 범위를 확인한 뒤 결정한다.

## 2. 목표 흐름

```text
Chat Gateway -> Chat Signal SQS -> Chat Signal Worker -> Candidate DynamoDB
                                                       |
                                                       | INSERT stream only
                                                       v
                                             Chat Source Adapter
                                                       |
Datadog Webhook -> Datadog Source Adapter -------------+
                                                       v
                                               Agent Trigger SQS
                                                       v
                                      Generic Agent Worker in Dify VPC
                                                       v
                                  Dedicated Test Workflow -> later Bedrock
```

Chat Signal Worker에서 Dify를 직접 호출하지 않는다. Candidate 저장 성공과 Agent 호출
성공을 한 Lambda invocation에 묶으면 Dify 지연이 원문 60초 처리 경로를 막고, 재시도 시
Candidate와 LLM 호출의 멱등 경계도 섞인다.

Chat Source Adapter는 Candidate DynamoDB Stream의 **새 Candidate INSERT만** 읽는다.
이 방식은 Candidate 저장과 handoff 사이의 유실 구간을 줄이고, `CANDIDATE_UPDATED` 호출을
초기 정책에서 자연스럽게 제외한다. Adapter는 원문 채팅을 읽을 수 없고 Candidate의
구조화된 집계만 읽는다.

기존 Datadog 경로는 즉시 교체하지 않는다. 공통 Worker가 Shadow 검증을 통과한 뒤 기존
입력과 새 envelope 결과를 비교하고 source adapter를 전환한다.

## 3. 공통 envelope 불변조건

기계 판독 원본은 [`agent-trigger-v1.schema.json`](contracts/agent-trigger-v1.schema.json)이다.

| ID | 불변조건 |
|---|---|
| `INV-AGENT-ENTRY-001` | Queue 이후 모든 요청은 `agent.trigger.v1`이어야 한다. |
| `INV-AGENT-ENTRY-002` | `source`, `source_schema`, `trigger_type` 조합은 Schema가 강제한다. |
| `INV-AGENT-ENTRY-003` | Chat evidence에 원문, 원문 일부, 원문 해시, 사용자 키를 넣지 않는다. |
| `INV-AGENT-ENTRY-004` | Chat root cause는 handoff 시점에도 `UNDETERMINED`다. |
| `INV-AGENT-ENTRY-005` | Agent Worker는 HTTP 2xx가 아니라 Dify `data.status=succeeded`를 성공으로 본다. |
| `INV-AGENT-ENTRY-006` | 현재 진입점은 `READ_ONLY`; 자동 조치 권한을 부여하지 않는다. |
| `INV-AGENT-ENTRY-007` | Dify 장애가 채팅 전송과 Candidate 생성을 실패시키면 안 된다. |
| `INV-AGENT-ENTRY-008` | 같은 `idempotency_key`는 LLM을 두 번 실행하지 않는다. |
| `INV-AGENT-ENTRY-009` | Trigger Queue와 DLQ는 서버 측 암호화하고 Source Adapter와 Worker에만 최소 권한을 준다. |

Chat 예시는 `contracts.md` 5.8에 있다. `evidence`는 Candidate 계약의 허용 필드만 복사하며
`raw_chat_included`는 evidence가 아니라 공통 `guardrails`에서 항상 `false`로 강제한다.

## 4. 전용 테스트 Dify 입력 매핑

Generic Agent Worker는 팀 workflow가 아니라 전용 테스트 앱을 가리킨다. envelope 전체를
compact JSON string으로 직렬화해 다음처럼 보낸다.

```json
{
  "inputs": {
    "custom_alert_json": "<serialized agent.trigger.v1>"
  },
  "response_mode": "blocking",
  "user": "agent-entry:<source>"
}
```

- Chat evidence를 `alert_title`, `alert_body` 같은 Datadog 필드로 위장하지 않는다.
- 테스트 앱의 `custom_alert_json`은 required paragraph로 만들고 최대 길이는 게시 API에서
  다시 읽어 Worker 검증값과 일치시킨다.
- `behavior`는 실험용 선택값이므로 공통 계약에 넣지 않는다.
- Dify의 모르는 입력 키 무시 동작에 기대지 않는다. 호출 전 Schema 검증과 게시 앱
  `/parameters`의 변수 존재 확인을 배포 게이트로 둔다.
- 워크플로는 `source`로 분기하고, Chat이면 먼저 read-only Datadog Pull로 Candidate 시간창
  주변 메트릭을 조회한다. 모니터가 아직 울리지 않았다는 사실만으로 정상 판정하지 않는다.
- organic traffic과 automation을 서버 측 증거로 구분하지 못하면 `UNDETERMINED`를 유지하고
  운영자에게 외부 사실을 묻는다. 운영자도 모르면 원인을 가르지 않는 안전 조치를 제안한다.

## 5. 실패 격리와 상태

| 실패 | 처리 |
|---|---|
| Candidate Stream/Adapter 실패 | Stream 재시도; Candidate와 채팅 경로는 이미 성공 상태 유지 |
| Agent Trigger SQS 중복 | idempotency ledger에서 같은 key를 성공/진행 상태로 차단 |
| Schema 불일치 | Dify 호출 금지, sanitized error code, DLQ |
| Dify HTTP/네트워크 실패 | bounded retry 후 DLQ |
| Dify HTTP 200 + workflow failed | 실패로 간주, bounded retry 후 DLQ |
| Dify 장시간 지연 | Queue backlog로 흡수; Chat Worker를 점유하지 않음 |
| Agent 결과 저장 실패 | 성공한 LLM을 무조건 재실행하지 않도록 invocation 상태를 분리 |

Agent Trigger SQS와 DLQ의 retention, retry 횟수, visibility timeout, Worker concurrency는
실측 전 확정하지 않는다. 단, visibility timeout은 Worker timeout보다 길어야 하고 Dify
동시 처리량보다 Worker 동시성이 커지면 안 된다.

Dify API key는 기존처럼 Secrets Manager에서 실행 시 읽는다. Generic Worker는 private
Dify에 닿는 VPC 경계 안에 두고 새 public ingress를 만들지 않는다.

관측 항목은 source별 accepted/rejected, Queue age/depth, Dify success/failure/elapsed,
idempotency duplicate, DLQ depth다. 로그에는 Chat 원문이 애초에 들어오지 않으며 envelope
전체도 출력하지 않는다.

## 6. 구현 Phase와 완료 게이트

| Phase | 변경 | 완료 게이트 |
|---|---|---|
| 0 | 실환경 baseline, 공통 Schema, 결정 기록 | 문서 index, JSON Schema validation, source별 machine-readable 예시와 불변조건 일치 |
| 1A | 전용 Dify contract-test 앱 생성 | 기존 앱/API key 미사용, `custom_alert_json` required, Code-only 결정론적 응답, 두 source 예시 직접 호출 통과, DSL export |
| 1B | Agent Trigger SQS/DLQ, idempotency ledger, Generic Worker를 비활성 상태로 생성 | Terraform fmt/validate, event source disabled, 자동 Dify 호출 0, 테스트 앱 secret만 참조 |
| 2 | Chat Candidate INSERT Source Adapter와 계약 테스트 | synthetic Candidate가 정확히 한 envelope 생성, 원문/사용자 키 0, 중복 Agent 호출 0 |
| 3 | 전용 테스트 workflow로 Dify Shadow E2E | contract-only Queue E2E 후 Bedrock 추가, 장애 시 Queue/DLQ 격리, 기존 앱 영향 0 |
| 4 | 기존 DLQ·DSL drift 정리 후 Datadog Source Adapter dual-run | legacy/new 결과 비교, Recovered 의미 보존, rollback 확인 |
| 5 | 운영 hardening | backlog·error·DLQ 알람, replay runbook, concurrency·timeout 실측 근거 |

Phase 1A는 전용 테스트 앱 API를 사람이 직접 호출해 계약만 확인하고, 자동 source는
연결하지 않는다. Phase 1B와 2는 Dify event source를 비활성 상태로 구현한다. Phase 3은
전용 테스트 앱과 합성 입력만으로 Queue E2E를 진행하므로 기존 O2 Worker DLQ와 팀
workflow drift를 건드리지 않는다. 두 문제의 정리는 기존 Datadog 경로를 공통 진입점으로
옮기는 Phase 4의 선행 조건이다.

### 6.1 Phase 1A 현재 체크포인트

2026-08-23에 격리 앱을 생성하고 게시했다. Dify 편집기 Test Run으로 저장소의 두 정상
예시와 source/schema 불일치 음성 예시를 실행했다. 정상 예시는 source별 `ACCEPTED`,
불일치는 content-free code `CONTRACT_REJECTED:SOURCE_SCHEMA`로 종료됐고 세 실행 모두
LLM 토큰은 0이었다. DSL 원본은
[`agent-entry-contract-test-v1.yml`](../infra/06-agent/dify/agent-entry-contract-test-v1.yml)에
기록했다.

전용 API key는 Secrets Manager `o2/dev/dify-agent-entry-contract-test`에 저장했고,
터널의 `localhost:17081/v1`을 통해 게시 `/parameters`와 `/workflows/run`을 직접
검증했다. 호출 클라이언트는 Dify 화면의 `http://localhost/v1`을 그대로 사용하지 않고
자신의 SSM local port를 붙여야 한다. Chat·Datadog 정상 입력은 각각 `succeeded`,
source/schema 불일치는 Dify HTTP 응답 본문의 `data.status=failed`와
`CONTRACT_REJECTED:SOURCE_SCHEMA`를 반환했다. 세 호출 모두 `total_tokens=0`이었다.

따라서 Phase 1A 완료 게이트는 충족했다. 다음 구현 범위는 Phase 1B이며, 자동 source는
여전히 연결하지 않는다.

## 7. 각 Phase에서 사람이 확인할 것

사용자가 매 단계마다 AWS 콘솔을 직접 확인할 필요는 없다. 구현자는 CLI와 테스트로 다음
증거를 제공하고, 사용자는 PR에서 범위와 Terraform plan의 변경 대상을 승인한다.

1. `main` 최신 커밋과 작업 브랜치 기준이 같은지
2. Schema·예시·코드 계약 테스트가 모두 통과했는지
3. Terraform plan에 해당 Phase 외 리소스 변경이나 destroy가 없는지
4. 배포 Phase라면 CI, image, Terraform resource, event source, Dify API를 각각 확인했는지
5. Shadow 종료 후 Queue/DLQ, Lambda Errors/Throttles, 원문 비기록을 확인했는지

실제 apply는 D-005에 따라 로컬에서 사람이 plan을 읽고 실행한다. Agent가 plan과 검증을
준비할 수는 있지만, 문서 merge를 배포 완료로 보고하지 않는다.

Phase 0 예시 파일:

- `contracts/examples/agent-trigger-chat-v1.example.json`
- `contracts/examples/agent-trigger-datadog-v1.example.json`
