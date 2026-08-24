# AI Agent 공통 진입점 — canonical design

> **Audience:** coding agents and reviewers
> **Status:** Phase 3A synthetic guards deployed with execution gates disabled
> **Updated:** 2026-08-24
> **Decision:** `decisions.md` D-050 and D-055
> **Wire contracts:** `contracts.md` 5.8-5.9 and `contracts/agent-*.schema.json`

```yaml
implementation_state:
  runtime_baseline_verified: COMPLETE
  common_contract: COMPLETE
  agent_trigger_queue: DEPLOYED_EMPTY
  chat_candidate_adapter: DEPLOYED_EXECUTION_DISABLED
  generic_dify_worker: DEPLOYED_EXECUTION_DISABLED
  phase3_synthetic_guard: DEPLOYED_EXECUTION_DISABLED
  incident_correlation_contract: COMPLETE
  incident_correlator: IMPLEMENTED_NOT_APPLIED
  agent_invocation_queue: IMPLEMENTED_NOT_APPLIED
  idempotency_ledger: DEPLOYED_EMPTY
  dedicated_test_workflow: PUBLISHED_CODE_ONLY
  dedicated_test_workflow_ui_contract_tests: PASS
  dedicated_test_workflow_service_api_tests: PASS
  dedicated_test_workflow_dsl: RECORDED_IN_REPOSITORY
  dedicated_test_workflow_api_key: STORED_IN_SECRETS_MANAGER
  existing_team_workflow_targeted: false
  datadog_migration: NOT_STARTED
  production_agent_handoff: DISABLED
activation_blockers:
  - PHASE_3B_INFRASTRUCTURE_NOT_APPLIED
  - CORRELATION_WINDOW_NOT_MEASURED
  - DATADOG_MONITOR_MAPPING_NOT_CONFIGURED
  - PHASE_3_CORRELATION_E2E_NOT_RUN
operational_followups:
  - EXISTING_06_AGENT_LAMBDA_CHANGES_MUST_BE_SEPARATED_BEFORE_APPLY
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

두 source schema는 **Source Adapter 앞에서는 달라도 된다.** Source Adapter 뒤의 Signal
Queue에서는 공통 envelope `agent.trigger.v1`을 사용한다. `source`가 discriminator이고
`evidence`만 source별 구조를 갖는다. Correlator가 한 개 이상의 trigger를 진행 중 사건에
붙인 뒤 Agent Invocation Queue에는 `agent.incident.v1`만 보낸다(D-055).

```text
source-specific JSON
  -> Source Adapter
  -> agent.trigger.v1
  -> Signal Queue
  -> Incident Correlator
  -> agent.incident.v1
  -> Agent Invocation Queue
  -> Generic Agent Worker
  -> Dify custom_alert_json
```

이 경계가 없으면 Dify가 `alert_title` 유무로 source를 추측해야 하고, 새 source가 생길
때마다 워크플로 전체가 조건문과 빈 문자열에 의존한다.

### 1.2 채팅 Candidate는 Incident 생성 신호를 한 번만 만든다

초기 정책은 `CANDIDATE_CREATED`만 `agent.trigger.v1`로 만든다. 쿨다운 중
`CANDIDATE_UPDATED`는 저장만 하고 새 trigger를 만들지 않는다. 채팅 메시지 한 건마다
Incident나 Agent 실행을 만드는 것은 금지한다.

Source 멱등 키와 Agent 실행 멱등 키는 서로 다른 경계가 소유한다.

```text
chat:<candidate_id>
datadog:<cycle_key>:<transition>
incident:<incident_id>:revision:<revision>
```

Chat-first Incident revision 1은 즉시 read-only 분석 대상으로 만들 수 있다. 늦게 온
Datadog 신호가 같은 사건에 붙으면 같은 `incident_id`의 revision 2가 된다. 단, 새 신호가
붙을 때마다 실행하지 않고 첫 cross-source 증거, 심각도 변화, 복구 증거처럼
`analysis_reason`에 정의된 material change만 새 Agent 실행을 만든다. 같은 Incident의
실행은 직렬화하고 실행 락은 Incident 단위로 하나만 둔다.

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
                                                       | Candidate-key stream
                                                       v
                                             Chat Source Adapter ----+
                                                                    |
Datadog Webhook -> Datadog Source Adapter --------------------------+
                                                                    v
                                                        agent.trigger.v1 Queue
                                                                    v
                                                         Incident Correlator
                                                                    |
                                                        Incident State DynamoDB
                                                                    |
                                                        agent.incident.v1 Queue
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

## 3. Trigger와 Incident 불변조건

기계 판독 원본은 [`agent-trigger-v1.schema.json`](contracts/agent-trigger-v1.schema.json)이다.

| ID | 불변조건 |
|---|---|
| `INV-AGENT-ENTRY-001` | Source Adapter 뒤 Signal Queue의 모든 요청은 `agent.trigger.v1`이어야 한다. |
| `INV-AGENT-ENTRY-002` | `source`, `source_schema`, `trigger_type` 조합은 Schema가 강제한다. |
| `INV-AGENT-ENTRY-003` | Chat evidence에 원문, 원문 일부, 원문 해시, 사용자 키를 넣지 않는다. |
| `INV-AGENT-ENTRY-004` | Chat root cause는 handoff 시점에도 `UNDETERMINED`다. |
| `INV-AGENT-ENTRY-005` | Agent Worker는 HTTP 2xx가 아니라 Dify `data.status=succeeded`를 성공으로 본다. |
| `INV-AGENT-ENTRY-006` | 현재 진입점은 `READ_ONLY`; 자동 조치 권한을 부여하지 않는다. |
| `INV-AGENT-ENTRY-007` | Dify 장애가 채팅 전송과 Candidate 생성을 실패시키면 안 된다. |
| `INV-AGENT-ENTRY-008` | 같은 `idempotency_key`는 LLM을 두 번 실행하지 않는다. |
| `INV-AGENT-ENTRY-009` | Trigger Queue와 DLQ는 서버 측 암호화하고 Source Adapter와 Worker에만 최소 권한을 준다. |
| `INV-AGENT-ENTRY-010` | Dify에 보낼 최종 직렬화 문자열이 게시 입력 상한 30,000자를 넘으면 외부 호출과 ledger 획득 전에 거부한다. |
| `INV-AGENT-ENTRY-011` | Agent Invocation Queue의 모든 요청은 `agent.incident.v1`이어야 한다. |
| `INV-AGENT-ENTRY-012` | `CORRELATED`는 Chat과 Datadog trigger를 각각 하나 이상 포함해야 한다. |
| `INV-AGENT-ENTRY-013` | 자동 병합은 환경·증상군·대상 범위·시간이 맞는 진행 중 사건이 정확히 하나일 때만 허용한다. |
| `INV-AGENT-ENTRY-014` | 후보가 둘 이상이거나 비교 차원이 부족하면 강제 병합하지 않고 `AMBIGUOUS`로 남긴다. |
| `INV-AGENT-ENTRY-015` | 같은 Incident의 Agent 실행과 조치 락은 하나이며 revision별 실행은 직렬화한다. |

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
| Signal Queue trigger 중복 | Correlator가 source `idempotency_key`로 같은 신호의 중복 귀속을 차단 |
| Agent Invocation Queue revision 중복 | Worker ledger가 Incident revision `idempotency_key`를 성공/진행 상태로 차단 |
| Schema 불일치 | Dify 호출 금지, sanitized error code, DLQ |
| Dify 호출 시작 전 Secret 조회 실패 | ledger를 잡지 않고 SQS가 제한 횟수 재전달 |
| Dify HTTP/네트워크 실패 | 호출 도달 여부가 불명확하므로 ledger를 `FAILED`로 닫고 자동 재호출 금지; DLQ에서 운영 확인 |
| Dify HTTP 200 + workflow failed | 실패로 간주하고 ledger를 `FAILED`로 닫아 자동 재호출 금지; DLQ에서 운영 확인 |
| Dify 장시간 지연 | Queue backlog로 흡수; Chat Worker를 점유하지 않음 |
| Agent 결과 저장 실패 | 성공한 LLM을 무조건 재실행하지 않도록 invocation 상태를 분리 |

Signal Queue·Agent Invocation Queue와 각 DLQ의 retention, retry 횟수, visibility timeout,
Correlator·Worker concurrency는
실측 전 확정하지 않는다. 단, visibility timeout은 Worker timeout보다 길어야 하고 Dify
동시 처리량보다 Worker 동시성이 커지면 안 된다.

Dify API key는 기존처럼 Secrets Manager에서 실행 시 읽는다. Generic Worker는 private
Dify에 닿는 VPC 경계 안에 두고 새 public ingress를 만들지 않는다.

관측 항목은 source별 accepted/rejected, correlation state/reason, ambiguous 수, revision 수,
두 Queue의 age/depth, Dify success/failure/elapsed, idempotency duplicate, DLQ depth다. 로그에는
Chat 원문이 애초에 들어오지 않으며 envelope 전체도 출력하지 않는다.

## 6. 구현 Phase와 완료 게이트

| Phase | 변경 | 완료 게이트 |
|---|---|---|
| 0 | 실환경 baseline, 공통 Schema, 결정 기록 | 문서 index, JSON Schema validation, source별 machine-readable 예시와 불변조건 일치 |
| 1A | 전용 Dify contract-test 앱 생성 | 기존 앱/API key 미사용, `custom_alert_json` required, Code-only 결정론적 응답, 두 source 예시 직접 호출 통과, DSL export |
| 1B | Agent Trigger SQS/DLQ, idempotency ledger, Generic Worker를 비활성 상태로 생성 | Terraform fmt/validate, event source disabled, 자동 Dify 호출 0, 테스트 앱 secret만 참조 |
| 2 | Chat Candidate INSERT Source Adapter와 계약 테스트 | synthetic Candidate가 정확히 한 envelope 생성, 원문/사용자 키 0, 중복 Agent 호출 0 |
| 3A | 합성 입력 guard를 비활성 상태로 적용 | 양쪽 실행·event source false, allowlist empty, Queue/DLQ 0 |
| 3B | `agent.incident.v1`, Incident State, Correlator, Agent Invocation Queue를 비활성 상태로 구현 | 계약 검증, 기존 Worker와 Correlator가 같은 Queue를 동시에 소비하지 않음, Dify 실행 0 |
| 3C | 상관관계 전용 합성 E2E | Chat→Datadog과 Datadog→Chat 모두 같은 `incident_id`, revision 증가, 모호한 후보 강제 병합 0, Dify 실행 0 |
| 3D | 병합된 Incident를 전용 테스트 workflow로 Shadow E2E | revision 멱등, Incident별 실행 직렬화, 장애 시 Queue/DLQ 격리, 기존 앱 영향 0 |
| 4 | 기존 DLQ·DSL drift 정리 후 Datadog Source Adapter dual-run | legacy/new 결과 비교, Recovered 의미 보존, rollback 확인 |
| 5 | 운영 hardening | backlog·error·DLQ 알람, replay runbook, concurrency·timeout 실측 근거 |

Phase 1A는 전용 테스트 앱 API를 사람이 직접 호출해 계약만 확인하고, 자동 source는
연결하지 않는다. Phase 1B와 2는 Dify event source를 비활성 상태로 구현한다. Phase 3은
상관관계 계층과 전용 테스트 앱을 합성 입력만으로 검증하므로 기존 O2 Worker DLQ와 팀
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

따라서 Phase 1A 완료 게이트는 충족했다. Phase 1B도 비활성 상태로 배포했으며, 다음 구현
범위는 Phase 2 Chat Candidate Source Adapter다. 자동 source는 여전히 연결하지 않는다.

### 6.2 Phase 1B 현재 체크포인트

2026-08-23에 `infra/06-agent/agent_entry_transport.tf`과 Generic Worker를 구현했다.
구성은 SSE가 적용된 Agent Trigger SQS/DLQ, `PAY_PER_REQUEST` DynamoDB 멱등 ledger,
private Dify에 연결 가능한 VPC Lambda, Queue age·DLQ·Lambda Error 알람이다. Worker IAM은
전용 테스트 앱 secret 읽기, 전용 Queue 소비, 전용 ledger 읽기·갱신으로 제한했다.

자동 실행은 다음 두 게이트로 차단했다.

1. SQS event source mapping을 `enabled=false`로 생성한다.
2. Worker 환경변수 `AGENT_ENTRY_EXECUTION_ENABLED=false`를 코드에 고정한다.

Worker 단위 테스트는 Chat·Datadog 정상 envelope, source/schema 불일치, Chat 원문 필드
거부, Dify 입력 크기 상한, 비활성 게이트, SQS partial batch failure, 성공 중복, Dify
실패, 기존 `FAILED` ledger의 자동 재획득 금지를 검증한다. `terraform fmt`,
`terraform validate`, Python 단위 테스트는 통과했다.

전체 `06-agent` plan은 Phase 1B의 신규 리소스 14개 외에 기존 Lambda 3개의
`source_code_hash` 변경과 연관 IAM policy 재평가를 함께 표시했다. state 해시와 현재
저장소 archive 해시를 비교한 결과, 공유 source를 쓰는 다른 Lambda는 이미 현재 해시인
반면 이 3개만 이전 해시였다. 즉 Phase 1B 코드가 기존 Lambda를 수정한 것이 아니라,
앞서 병합되고 일부 함수에만 적용된 기존 변경이 같은 stack plan에 섞인 상태다.

따라서 전체 stack apply는 허용하지 않고, Phase 1B 대상만 지정한 저장 plan에서
`14 add, 0 change, 0 destroy`와 두 실행 게이트 `false`를 기계적으로 확인한 뒤 한 번만
target apply했다. 결과는 `14 added, 0 changed, 0 destroyed`였다.

apply 후 실환경 확인 결과는 다음과 같다.

| 검증 항목 | 결과 |
|---|---|
| Phase 1B 대상 재-plan | `No changes` |
| 전체 `06-agent` 재-plan | `0 add, 4 change, 0 destroy`; 기존 Lambda 3개와 연관 IAM 변경만 남음 |
| SQS event source | `Disabled`, 처리 결과 없음, batch size 1 |
| Worker | `Active`, update successful, Python 3.12, timeout 60초, reserved concurrency 2 |
| Worker 실행 플래그 | `AGENT_ENTRY_EXECUTION_ENABLED=false` |
| 배포 코드 | Lambda code SHA와 병합본 archive SHA 일치 |
| Agent Trigger Queue/DLQ | visible 0, in-flight 0, SSE enabled |
| 멱등 ledger | ACTIVE, `PAY_PER_REQUEST`, SSE·TTL·PITR enabled, item 0 |
| Worker 실행 흔적 | CloudWatch Log Stream 0개 |
| 전용 Dify 앱 실행 이력 | 기존 3건 그대로; apply 이후 신규 run 0건 |
| 알람 | action enabled; Queue age·DLQ·Worker error 모두 `OK` |

Phase 1B는 `DEPLOYED_EXECUTION_DISABLED`다. 기존 리소스 4개 plan 변경은 여전히 별도
검토 대상이며, 이후에도 전체 `06-agent` apply에 섞어 실행하지 않는다.

### 6.3 Phase 2 실환경 적용 결과

Candidate DynamoDB의 `NEW_IMAGE` Stream과 `08-chat-signal` 소유 Chat Source Adapter를
구현했다. Candidate 생성 Worker가 Agent Queue를 직접 호출하지 않으므로 Candidate 저장과
handoff 실패가 서로의 재시도·지연 경계를 침범하지 않는다.

Phase 2 실행 경계는 다음과 같다.

| 경계 | Phase 2 값 |
|---|---|
| Candidate Stream view | `NEW_IMAGE` |
| Stream filter | `CANDIDATE#*` + `META`; `INSERT` 여부는 Adapter 코드에서 재검증 |
| Adapter event source | `enabled=false` |
| Adapter 실행 플래그 | `CHAT_SOURCE_ADAPTER_ENABLED=false` |
| 과거 Candidate 차단 | `NOT_BEFORE_EPOCH=2100-01-01`; Phase 3 cutover 시각으로 별도 변경 필요 |
| Adapter 권한 | Candidate Stream read, Agent Trigger SQS send, 전용 DLQ send, 전용 log write |
| 금지 권한 | Datadog·Dify·Bedrock·EKS·Candidate table write |

Adapter는 Candidate payload의 필드를 정확히 검증하고 `raw_chat_included=false`,
`root_cause=UNDETERMINED`, `agent_handoff_status=NOT_CONFIGURED`를 강제한다. 원문·사용자 키·
원문 해시 같은 추가 필드가 있으면 Queue에 보내지 않고 bounded retry 후 Adapter DLQ로
보낸다. `trigger_id`는 Candidate ULID로 결정적으로 만들고 모든 재전달에서 같은
`idempotency_key=chat:<candidate_id>`를 사용한다. SQS Standard의 중복 자체는 허용하되
Phase 1B Worker ledger가 같은 Agent 실행을 차단한다.

로컬 테스트는 기존 Chat Signal 20개와 Source Adapter 8개, 총 28개가 통과했다. Adapter
범위는 정상 INSERT 1건→공통 envelope 1건, 결정적 멱등 키, UPDATE·비Candidate 제외,
활성화 이전 Candidate 제외, 사용자 키 거부, 비활성 게이트, Queue 실패 partial retry다.
Python 컴파일, Terraform fmt·validate도 통과했다.

2026-08-23 병합된 `main`에서 순차 적용했다. `03-data` 저장 plan은 Candidate table의
Stream만 켜는 `0 add, 1 change, 0 destroy`였고, 적용 후 table `ACTIVE`, Stream
`NEW_IMAGE`를 확인했다. 이어 생성한 `08-chat-signal` 저장 plan은 Source Adapter 계층만
추가하는 `8 add, 0 change, 0 destroy`였다.

적용 후 실환경 확인 결과는 다음과 같다.

| 검증 항목 | 결과 |
|---|---|
| `03-data`, `08-chat-signal` 전체 plan | 둘 다 `No changes` |
| Adapter Lambda | `Active`, update `Successful`, Python 3.13 |
| Adapter event source | `Disabled`, processed record 0 |
| Adapter 실행 플래그 | `false` |
| 과거 Candidate 차단 | epoch `4102444800` 유지 |
| Agent Trigger Queue | visible, in-flight, delayed 모두 0 |
| Adapter DLQ | visible, in-flight, delayed 모두 0 |
| Adapter 실행 흔적 | CloudWatch Log Stream 0개 |
| 공통 Agent Worker | Lambda `Active`, 실행 플래그 `false`, event source `Disabled` |

따라서 Phase 2 상태는 `DEPLOYED_EXECUTION_DISABLED`다. Agent/Dify 호출 경로는 열리지
않았으며, Phase 3 합성 Shadow E2E 전에는 어떤 실행 게이트도 변경하지 않는다.

### 6.4 Phase 3 합성 입력 격리 준비

Phase 3은 운영 Candidate나 기존 팀 workflow를 대상으로 하지 않는다. Queue contract-only
E2E와 Chat Candidate E2E 모두 매 실행마다 새 합성 식별자 한 개만 허용한다(D-053).

| 경계 | 합성 입력 제한 |
|---|---|
| Chat Source Adapter | 정확히 한 `broadcast_id`만 Agent Trigger Queue 전송 허용 |
| Generic Agent Worker | 정확히 한 `idempotency_key`만 Secret·ledger·Dify 접근 허용 |
| Terraform 기본값 | 두 계층의 event source와 실행 플래그 모두 `false`, allowlist는 빈 집합 |
| 활성화 plan | 두 게이트 `true`와 allowlist 1개가 함께 있어야 통과 |
| Adapter cutover | 명시한 test epoch 이후 Candidate만 허용; 비활성 기본값은 2100-01-01 |
| 종료 상태 | 두 게이트 `false`, allowlist 빈 집합, Adapter cutoff 2100-01-01로 복귀 |

허용되지 않은 production broadcast는 정상 제외해 재시도·DLQ를 만들지 않는다. 반면 빈 값,
복수 값, 형식 오류 같은 allowlist 구성 오류는 fail-closed하고 Queue 전송이나 Dify 호출을
하지 않는다. Worker의 allowlist 검사는 Secret 조회와 idempotency ledger 획득보다 먼저
실행한다.

2026-08-24 병합본에서 두 Lambda만 제한한 저장 plan을 적용했다. Chat Adapter와 Agent
Worker는 각각 1개 제자리 업데이트였고 생성·삭제는 없었다. 적용 후 두 실행 플래그와 두
event source는 모두 `false`/`Disabled`, allowlist는 빈 값, Agent Queue와 DLQ는 visible과
in-flight 모두 0이었다. 따라서 Phase 3A는 `DEPLOYED_EXECUTION_DISABLED`로 완료했다.

### 6.5 Phase 3B 상관관계 계약

`agent.trigger.v1`은 Incident가 아니라 source 신호다. 같은 장애의 Chat Candidate와
Datadog 알림을 직접 Dify에 보내면 분석과 조치가 둘로 갈라진다. Phase 3B부터는 Correlator가
durable Incident State를 소유하고 Agent Worker에는 `agent.incident.v1` revision만 보낸다.

자동 병합은 다음 조건을 모두 만족할 때만 한다.

1. 같은 environment
2. 같은 normalized symptom family
3. source별 고정 mapping으로 호환되는 affected scope
4. 측정으로 정한 correlation window 안의 event time
5. 위 조건을 만족하는 OPEN Incident가 정확히 하나

0개면 새 provisional Incident를 만들고, 2개 이상이거나 필수 차원이 없으면
`AMBIGUOUS`로 기록해 강제 병합하지 않는다. LLM은 이 결정을 소유하지 않는다. 운영
correlation window 값은 아직 측정하지 않았으므로 Phase 3C의 양방향 도착 지연 실측 전에는
확정하지 않는다.

현재 물리 이름이 `agent-trigger`인 Queue는 Phase 3B에서 논리적 Signal Queue 역할을 한다.
별도 Agent Invocation Queue를 만들고 Generic Worker를 그쪽으로 옮긴다. Correlator와 기존
Worker가 같은 SQS의 competing consumer가 되는 순간 신호가 임의 소비되므로, 기존 Worker
mapping을 비활성·분리했다고 확인하기 전에는 Correlator event source를 켜지 않는다.

Phase 3B 구현은 `infra/06-agent/incident_correlation.tf`과
`lambda/incident_correlator.py`에 있다. 구성은 다음과 같다.

| 구성 | Phase 3B 상태 |
|---|---|
| 기존 `agent-trigger` Queue | 물리 교체 없이 Signal Queue로 유지 |
| Incident State DynamoDB | Incident snapshot, correlation pointer, source signal claim 저장 |
| Incident Correlator | 실행 플래그 `false`, event source `false` |
| correlation window | `0`; 0인 동안 활성화 precondition 실패 |
| Chat mapping | S3 범위의 `READ_PATH → LATENCY/api`만 명시 |
| Datadog monitor mapping | 빈 map; monitor ID를 명시하기 전 추측하지 않음 |
| Agent Invocation Queue | 생성 대상이지만 Phase 3B consumer 없음 |
| Generic Worker / Dify | 기존 비활성 경로 그대로, 신규 Queue 미연결 |

source signal claim과 Incident revision 갱신은 한 DynamoDB transaction으로 묶는다. Queue
전송 전 claim은 `PENDING`, 성공 후 `EMITTED`가 된다. 전송이 실패하면 같은 snapshot을
재전송하고 새 revision을 만들지 않는다. 전송 성공 후 claim 확정만 실패해 중복 전송되는
경우는 Phase 3D Worker의 revision 멱등 키가 막는다.

같은 correlation key의 첫 Chat·Datadog이 동시에 `0 matches`를 읽는 경쟁은 correlation
pointer의 조건부 transaction으로 직렬화한다. 한쪽만 신규 Incident를 만들고 패자는 재시도한다.
GSI에 `AMBIGUOUS` Incident가 남아 있어도 자동 병합 후보에서는 제외한다.

단위 테스트는 Chat→Datadog, Datadog→Chat, window 밖 분리, 복수 후보 ambiguity, mapping
부족, 중복, pending replay, 비물질적 same-source update, 원문 필드 거부, 비활성 gate,
DynamoDB transaction 3항목 구성을 포함한다. 로컬 Python과 Lambda Python 3.12에서 통과했고,
생성된 provisional/correlated snapshot은 `agent.incident.v1` Schema를 통과했다. 아직
Terraform apply와 Phase 3C 합성 E2E는 수행하지 않았다.

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
