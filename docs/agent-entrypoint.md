# AI Agent 공통 진입점 — canonical design

> **Audience:** coding agents and reviewers
> **Status:** Operational READ_PATH Incident handoff enabled; waiting for the first real correlated Incident
> **Updated:** 2026-08-25
> **Decision:** `decisions.md` D-050, D-055, D-066, D-070, D-072, and D-073
> **Wire contracts:** `contracts.md` 5.8-5.9 and `contracts/agent-*.schema.json`

```yaml
implementation_state:
  runtime_baseline_verified: COMPLETE
  common_contract: COMPLETE
  agent_trigger_queue: DEPLOYED_EMPTY
  chat_candidate_adapter: DEPLOYED_OPERATIONAL
  generic_dify_worker_runtime: DEPLOYED_OPERATIONAL_EXISTING_DIFY_AND_HISTORY_PRESERVED
  phase3d_incident_worker_repository: APPLIED_EXECUTION_DISABLED
  phase3d_targeted_plan: APPLIED_1_ADD_2_CHANGE_0_DESTROY
  phase3_synthetic_guard: DEPLOYED_EXECUTION_DISABLED
  incident_correlation_contract: COMPLETE
  incident_correlator: DEPLOYED_OPERATIONAL
  agent_invocation_queue: DEPLOYED_ENABLED_CONSUMER
  phase3c_signal_queue_correlation_e2e: PASS
  phase3c_source_pipeline_delay_measurement: PASS_PHASE4B_TWO_ORDER_RUNS
  phase3d_dify_incident_contract_dsl: PUBLISHED
  phase3d_shadow_e2e: PASS
  idempotency_ledger: DEPLOYED_EMPTY
  dedicated_test_workflow: PUBLISHED_INCIDENT_CODE_ONLY
  dedicated_test_workflow_ui_contract_tests: PASS
  dedicated_test_workflow_service_api_tests: PASS
  dedicated_test_workflow_dsl: RECORDED_IN_REPOSITORY
  dedicated_test_workflow_api_key: STORED_IN_SECRETS_MANAGER
  existing_team_workflow_targeted: false
  datadog_source_adapter: DEPLOYED_OPERATIONAL_MONITOR_21940250
  phase4a_targeted_plan: APPLIED_8_ADD_0_CHANGE_0_DESTROY
  datadog_shadow_webhook: CONFIGURED_PRODUCTION_PAYLOAD_NOT_ATTACHED
  phase4b_synthetic_monitor: DELETED_AFTER_TEST
  phase4b_source_delay_samples: CHAT_7995_8743MS_DATADOG_TRIGGERED_68400_63611MS
  phase4b_legacy_new_dual_run: NOT_RUN_LEGACY_DIFY_INTENTIONALLY_EXCLUDED
  datadog_monitor_id_guard: APPLIED_EXECUTION_DISABLED
  phase4c_live_source_to_dify_e2e: PASS_CHAT_DATADOG_CORRELATED_DIFY_ONCE
  phase4c_datadog_cycle_substitution: PASS_TRIGGERED_RECOVERED_SAME_CYCLE
  phase4d_environment_contract: APPLIED_EXECUTION_DISABLED
  phase4d_targeted_plan: APPLIED_0_ADD_2_CHANGE_0_DESTROY_CODE_HASH_ONLY
  phase4d_environment_mismatch_shadow: PASS_AMBIGUOUS_NO_AUTO_MERGE
  phase4e_datadog_monitor_mapping: APPLIED_EXECUTION_DISABLED
  phase4e_targeted_plan: APPLIED_0_ADD_1_CHANGE_0_DESTROY_MAPPING_ONLY
  phase4f_initial_correlation_window: IMPLEMENTED_NOT_APPLIED_420_SECONDS
  phase4f_window_evidence_validation: PASS
  phase4f_targeted_plan: PASS_0_ADD_1_CHANGE_0_DESTROY_WINDOW_ONLY
  datadog_migration: PHASE4C_SHADOW_E2E_ONLY
  production_agent_handoff: ENABLED_WAITING_FOR_REAL_VERIFIED_INCIDENT
activation_blockers:
  - NONE
operational_followups:
  - MEASURE_FALSE_MERGE_AND_RECOVERY_AFTER_REAL_INCIDENTS
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
| 채팅 Candidate handoff | Source Adapter 배포·실행 비활성, `agent_handoff_status=NOT_CONFIGURED` |
| Datadog 신규 handoff | 기존 ingress와 분리된 Source Adapter 배포·실행 비활성; Shadow webhook은 구성됐지만 monitor에 미부착 |
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
| `INV-AGENT-ENTRY-012` | `VERIFIED`는 `primary`와 `corroborating` trigger가 모두 있고 ambiguity가 없어야 한다. source 제품명 조합을 하드코딩하지 않는다. |
| `INV-AGENT-ENTRY-013` | 자동 병합은 환경·증상군·대상 범위·시간이 맞는 진행 중 사건이 정확히 하나일 때만 허용한다. |
| `INV-AGENT-ENTRY-014` | 후보가 둘 이상이거나 비교 차원이 부족하면 강제 병합하지 않고 `AMBIGUOUS`로 남긴다. |
| `INV-AGENT-ENTRY-015` | 같은 Incident의 Agent 실행과 조치 락은 하나이며 revision별 실행은 직렬화한다. |
| `INV-AGENT-ENTRY-016` | Worker는 Incident State의 최신 revision보다 오래된 Invocation을 `SUPERSEDED` 처리하고 Dify를 호출하지 않는다. |
| `INV-AGENT-ENTRY-017` | 만료된 Incident lock은 자동 탈취하지 않는다. Dify 도달 여부를 확인한 운영자만 ledger와 DLQ를 복구한다. |

Chat 예시는 `contracts.md` 5.8에 있다. `evidence`는 Candidate 계약의 허용 필드만 복사하며
`raw_chat_included`는 evidence가 아니라 공통 `guardrails`에서 항상 `false`로 강제한다.

## 4. 전용 테스트 Dify 입력 매핑

Generic Agent Worker는 팀 workflow가 아니라 전용 테스트 앱을 가리킨다. Incident snapshot
전체를
compact JSON string으로 직렬화해 다음처럼 보낸다.

```json
{
  "inputs": {
    "custom_alert_json": "<serialized agent.incident.v1>"
  },
  "response_mode": "blocking",
  "user": "agent-entry:incident"
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
| 같은 Incident revision 동시 도착 | DynamoDB Incident lock으로 하나만 실행; 나머지는 SQS 재전달 |
| 대기 중 더 최신 revision 도착 | Incident State 최신 revision보다 오래된 메시지는 `SUPERSEDED`; Dify 호출 0 |
| lock lease 만료 | Dify 도달 여부가 불명확하므로 자동 탈취하지 않고 fail-closed, DLQ에서 운영자 확인 |

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
| 3C | 상관관계 전용 합성 E2E와 source 전달 지연 측정 | Signal Queue 직접 입력에서 Chat→Datadog과 Datadog→Chat 모두 같은 `incident_id`, revision 증가, 모호한 후보 강제 병합 0, Dify 실행 0. 이후 실제 Adapter 양쪽 전달 지연을 재서 운영 window 확정 |
| 3D | 병합된 Incident를 전용 테스트 workflow로 Shadow E2E | revision 멱등, Incident별 실행 직렬화, 장애 시 Queue/DLQ 격리, 기존 앱 영향 0 |
| 4A | 기존 ingress와 분리된 Datadog Source Adapter를 비활성 상태로 생성 | 기존 경로 변경 0, 신규 URL·Lambda·최소 IAM만 생성, 실행 false·allowlist empty·2100 cutoff |
| 4B | 합성 monitor에서 기존/new webhook dual-run과 양쪽 source 지연 측정 | legacy/new 수신 확인, Recovered 보존, Chat/Datadog event·Queue 도착 시각 기록, Dify 실행 0 |
| 4C | 운영 전환 전 기존 DLQ·DSL drift 정리 | 기존 오류 원인 제거, 게시 DSL export, rollback 확인 |
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
`AMBIGUOUS`로 기록해 강제 병합하지 않는다. 두 상태는 Incident State에만 남기고 Agent
Invocation Queue에는 보내지 않는다. 명시 mapping의 `primary`와 `corroborating` 역할이
모두 채워져 `evidence_assessment.verification_state=VERIFIED`가 된 material revision만
Queue로 보낸다. 같은 source라도 서로 다른 역할이면 결합할 수 있다. LLM은 이 결정을
소유하지 않는다. 운영
correlation window 값은 아직 측정하지 않았으므로 Phase 3C의 양방향 도착 지연 실측 전에는
확정하지 않는다.

현재 물리 이름이 `agent-trigger`인 Queue는 Phase 3B에서 논리적 Signal Queue 역할을 한다.
별도 Agent Invocation Queue를 만들고 Generic Worker를 그쪽으로 옮긴다. Correlator와 기존
Worker가 같은 SQS의 competing consumer가 되는 순간 신호가 임의 소비되므로, 기존 Worker
mapping을 비활성·분리했다고 확인하기 전에는 Correlator event source를 켜지 않는다.

Phase 3B 구현은 현재 모니터링 팀 소유의 `infra/09-incident/incident_correlation.tf`과
`lambda/incident_correlator.py`에 있다(D-078). 구성은 다음과 같다.

| 구성 | Phase 3B 상태 |
|---|---|
| 기존 `agent-trigger` Queue | 물리 교체 없이 Signal Queue로 유지 |
| Incident State DynamoDB | Incident snapshot, correlation pointer, source signal claim 저장 |
| Incident Correlator | 실행 플래그 `false`, event source `false` |
| correlation window | `0`; 0인 동안 활성화 precondition 실패 |
| Chat mapping | S3 범위의 `READ_PATH → LATENCY/api`만 명시 |
| Datadog monitor mapping | 빈 map; monitor ID를 명시하기 전 추측하지 않음 |
| Agent Invocation Queue | 배포됨; Phase 3B consumer 없음 |
| Generic Worker / Dify | 기존 비활성 경로 그대로, 신규 Queue 미연결 |

source signal claim과 Incident revision 갱신은 한 DynamoDB transaction으로 묶는다.
`PROVISIONAL`·`AMBIGUOUS` claim은 `NOT_REQUIRED`, Queue 전송 대상인 `CORRELATED` revision은
전송 전 `PENDING`, 성공 후 `EMITTED`가 된다. 전송이 실패하면 같은 snapshot을 재전송하고
새 revision을 만들지 않는다. 전송 성공 후 claim 확정만 실패해 중복 전송되는 경우는
Phase 3D Worker의 revision 멱등 키가 막는다.

같은 correlation key의 첫 Chat·Datadog이 동시에 `0 matches`를 읽는 경쟁은 correlation
pointer의 조건부 transaction으로 직렬화한다. 한쪽만 신규 Incident를 만들고 패자는 재시도한다.
GSI에 `AMBIGUOUS` Incident가 남아 있어도 자동 병합 후보에서는 제외한다.

단위 테스트는 Chat→Datadog, Datadog→Chat, window 밖 분리, 복수 후보 ambiguity, mapping
부족, 중복, pending replay, 비물질적 same-source update, 원문 필드 거부, 비활성 gate,
DynamoDB transaction 3항목 구성을 포함한다. 로컬 Python과 Lambda Python 3.12에서 통과했고,
생성된 provisional/correlated snapshot은 `agent.incident.v1` Schema를 통과했다.

2026-08-24 병합본에서 Phase 3B 신규 리소스만 제한한 저장 plan을 적용했다. 적용 전
계획은 `13 add, 0 change, 0 destroy`였고, 실행 플래그 `false`, event source `false`,
correlation window `0`, 빈 합성 allowlist, 빈 Datadog monitor mapping, Agent Invocation
Queue consumer 0개를 기계적으로 확인했다. 기존 `06-agent` Lambda와 IAM 변경은 이
저장 plan에 포함하지 않았다.

적용 후 실환경 확인 결과는 다음과 같다.

| 검증 항목 | 결과 |
|---|---|
| 대상 apply | `13 added, 0 changed, 0 destroyed` |
| Incident Correlator | `Active`, Python 3.12, reserved concurrency 2 |
| Correlator 실행 플래그 | `false`; window `0`, allowlist empty, Datadog mapping `{}` |
| Correlator event source | `Disabled`, batch size 1, 처리 결과 없음 |
| 기존 Generic Worker event source | `Disabled`, 처리 결과 없음 |
| Agent Invocation Queue consumer | 0개 |
| Signal Queue/DLQ · Invocation Queue/DLQ | visible, in-flight, delayed 모두 0 |
| Incident State | `ACTIVE`, `PAY_PER_REQUEST`, SSE·TTL·PITR enabled, GSI `ACTIVE`, item 0 |
| Correlator 실행 흔적 | CloudWatch Log Stream 0개 |
| 신규 경로의 Dify 호출 가능성 | Correlator 미실행, 두 Queue consumer 없음으로 차단 |
| 전체 `06-agent` 재-plan | `0 add, 5 change, 0 destroy`; 기존 Lambda 4개와 연관 IAM 변경만 남음 |

따라서 Phase 3B는 `DEPLOYED_EXECUTION_DISABLED`다. Queue age 알람은 신규·무트래픽
Queue라 최초 확인 시 `INSUFFICIENT_DATA`였고, DLQ·Lambda Error 알람은 `OK`였다.
Phase 3C 합성 E2E 전에는 어떤 event source나 실행 플래그도 변경하지 않는다.

### 6.6 Phase 3C-A Signal Queue 합성 상관관계 E2E

2026-08-24에 운영 Adapter를 켜지 않고 Signal Queue에 계약을 통과한 합성 trigger만 직접
넣었다. 테스트 전용 correlation window는 **300초**였다. 이 값은 두 source의 event time을
같게 고정한 기능 검증용 상한이며 운영값의 근거가 아니다. allowlist는 각 실행의 Chat key와
Datadog cycle key 두 개만 허용했다.

| 순서 | revision 1 | revision 2 | 결과 |
|---|---|---|---|
| Chat → Datadog | `PROVISIONAL`, `CHAT_FIRST_NO_METRIC` | 같은 Incident, `CORRELATED`, `CROSS_SOURCE_EVIDENCE_ADDED` | PASS |
| Datadog → Chat | `PROVISIONAL`, `DATADOG_FIRST_NO_CHAT` | 같은 Incident, `CORRELATED`, `CROSS_SOURCE_EVIDENCE_ADDED` | PASS |

두 실행 모두 revision 1·2만 Agent Invocation Queue에 생성했다. 이 Queue의 event source
consumer는 0개여서 Generic Worker와 Dify는 실행되지 않았다. Correlator warm 처리시간은
각각 204.28ms, 212.93ms였다. 첫 실행은 Lambda cold start와 최초 AWS SDK credential
초기화를 포함해 각각 6,535.02ms, 6,447.42ms였다(M-017).

종료는 다음 순서로 수행했다.

1. Correlator event source와 실행 플래그를 `false`, window를 `0`, allowlist를 empty,
   Datadog mapping을 `{}`로 복귀
2. 각 합성 Incident의 pointer·snapshot·signal claim만 정확한 PK로 조건부 삭제
3. 각 Invocation body의 합성 `trace_id`를 확인한 뒤 ReceiptHandle로 개별 삭제
4. 대상 Terraform 재-plan `No changes`, Incident State item 0, 네 Queue의 visible·in-flight·
   delayed 0, 두 DLQ 0, Invocation consumer 0, Lambda Error 알람 `OK` 확인

Phase 3C-A의 **상관관계 기능 게이트는 통과**했다. 이 시점의 입력은 두 Adapter를 거치지
않았으므로 source 전달 지연 분포는 아직 측정하지 못했다. 이후 Phase 4B에서 실제 Adapter
지연 표본을 M-017에 추가했지만 source별 2개뿐이므로 운영 correlation window는 계속
미확정이다.

### 6.7 Phase 3D 저장소 구현 체크포인트

2026-08-24에 Generic Worker의 입력 경계를 Signal Queue의 `agent.trigger.v1`에서 Agent
Invocation Queue의 `agent.incident.v1`로 옮겼다. Terraform 기본값은 계속 event source
`false`, 실행 플래그 `false`, 합성 Incident allowlist empty라 병합이나 apply만으로 Dify가
호출되지 않는다. 실환경에는 이 비활성 상태로 적용했고 전용 Dify 앱도 Incident 계약으로
게시했다. 기존 팀 앱은 변경하지 않았다.

Worker 처리 순서는 다음으로 고정했다.

1. `agent.incident.v1`과 포함된 모든 source trigger를 exact-field 방식으로 검증
2. allowlist의 합성 `incident_id` 정확히 한 개인지 확인
3. Incident State의 authoritative 최신 revision을 consistent read
4. 오래된 revision이면 execution ledger에 `SUPERSEDED` 기록 후 종료
5. 현재 revision이면 revision 멱등 항목과 Incident lock을 한 DynamoDB transaction으로 획득
6. 전용 contract-test Dify 앱을 blocking 호출하고 `data.status=succeeded`와 sanitized output 검증
7. execution 상태 확정과 Incident lock 해제를 한 transaction으로 완료

Standard SQS의 중복·역순 전달은 유지하되 FIFO 교체 없이 DynamoDB가 Incident별 직렬화를
소유한다. 실행 중 새 revision이 생기면 현재 실행은 중단하지 않고 완료하며, 대기 중인 오래된
revision은 다음 수신에서 최신 상태와 비교해 건너뛴다. 네트워크 단절이나 Lambda 종료로 lock이
만료된 경우 자동 탈취하지 않는다. 요청이 Dify에 도달했을 수 있으므로 DLQ에서 실행 이력을
확인하기 전 재호출하면 안 된다.

Phase 1B의 Signal Queue Worker mapping은 Terraform destroy 없이 `enabled=false`로 보존하고
해당 Queue 소비 IAM을 제거했다. Phase 3D는 별도 Invocation Queue mapping을 추가한다. 따라서
apply plan은 비활성 mapping 1개 추가와 Worker/IAM 제자리 변경만 포함해야 하며, 기존 mapping
삭제나 Queue 교체는 포함하면 안 된다.

병합본 targeted plan은 Invocation mapping 1개 생성, Worker Lambda와 최소 IAM 2개 제자리
변경, 삭제 0개였다. 새 mapping은 `enabled=false`, Worker 실행 플래그도 `false`, allowlist는
empty인 상태로 적용했고 대상 재-plan은 `No changes`였다. 전체 stack의 별도 변경 4개는
적용하지 않았다. 별도 음성 plan에서 allowlist 없이 event source와 실행 플래그만 `true`로
주자 resource precondition이 의도대로 plan을 거부했다.

로컬 검증은 Worker 20개, Correlator 15개(로컬 boto3 부재 1개 skip), JSON Schema 정상 2개·
거부 4개, Dify 초안·게시 Service API의 정상 Incident와 raw chat 거부를 통과했다. Terraform
`fmt`와 `validate`도 통과했다.

첫 Shadow E2E에서 합성 Incident 한 건은 Dify에서 `succeeded`까지 갔지만 Worker가 성공
ledger와 Incident lock 해제를 확정하는 transaction에서 `dynamodb:DeleteItem` 권한이 없어
`IDEMPOTENCY_FINALIZE`로 실패했다. ledger와 lock은 `IN_PROGRESS`로 남아 재호출을 막았고,
event source와 실행 플래그는 즉시 `false`, allowlist는 empty로 복귀했다. 수정 후보는
`UseIdempotencyLedger`에 `DeleteItem` 하나만 추가하며 targeted plan은 `0 add, 1 change,
0 destroy`다. 실패 메시지는 Message ID·body·attribute의 합성 Incident ID를 확인한 뒤
개별 삭제했고, revision ledger·lock·Incident State도 한 조건부 transaction으로 정리했다.
Queue·DLQ와 세 DynamoDB key는 모두 비어 있는 상태로 복구했다.

IAM 수정 병합 후 `DeleteItem` 한 개만 추가되는 plan(`0 add, 1 change, 0 destroy`)을 적용했고,
대상 재-plan은 `No changes`였다. 새 합성 Incident ID와 revision 2를 사용한 재측정에서 첫
메시지는 Worker ledger `SUCCEEDED`, attempt 1로 완료됐고 Dify run도 정확히 한 건만
`succeeded`였다. Incident lock은 정상 삭제됐다. 동일 revision의 같은 메시지를 다시 넣자
Worker는 `DUPLICATE`로 종료했고 ledger의 attempt와 Dify run ID는 바뀌지 않았다. 첫 실행은
cold start를 포함해 6,176.10ms, 중복 차단 실행은 143.43ms였다.

재측정 직후 event source를 `Disabled`, 실행 플래그를 `false`, allowlist를 empty로 복귀했고,
Queue·DLQ 0건, Worker/DLQ alarm `OK`, 합성 ledger·lock·Incident State 삭제를 확인했다. 최종
대상 재-plan도 `No changes`였다. 따라서 Phase 3D Shadow 기능 게이트는 통과했지만 production
Agent handoff는 계속 비활성이다. 당시 남은 blocker 중 실제 source 전달 지연은 Phase 4B에서
두 표본씩 측정했다. 현재 blocker는 반복 표본 기반 운영 correlation window 결정, Datadog
monitor mapping, 실제 `$ALERT_CYCLE_KEY` 치환 검증이다.

### 6.8 Phase 4A 격리 Datadog Source Adapter

기존 `o2-dify-ingress`를 수정해 한 요청에서 두 경로로 분기하지 않는다. 신규 Adapter는
별도 Function URL을 가지며 Datadog의 별도 Shadow webhook이 선택한 합성 monitor에만 붙는다.
기존 webhook은 기존 Worker/Dify 경로를 그대로 사용하므로 신규 Adapter의 인증·계약·SQS
오류가 운영 알림 분석을 막지 않는다.

신규 Adapter는 기존 15필드 `datadog.alert.v1` 입력을 exact-field 방식으로 검증한다. 현재
Datadog `$DATE_POSIX` 값과 RFC 3339를 모두 받아 Queue envelope에서는 RFC 3339 UTC로
정규화한다. 같은 `cycle_key + transition + event_id`는 같은 ULID trigger와
`datadog:<cycle_key>:<transition>` 멱등 키를 만든다. `Recovered`도 버리지 않고 전달해
Correlator가 기존 Incident에 복구 revision을 추가할 수 있게 한다. alert 본문은 Queue
evidence에는 포함되지만 로그에는 request ID·상태·content-free error code만 남는다.

안전 경계는 다음과 같다.

| 경계 | 기본값·권한 |
|---|---|
| 실행 플래그 | `false` |
| 합성 monitor ID allowlist | empty; 활성화 시 정확히 1개 |
| cutover | 2100-01-01; 활성화 시 명시한 epoch |
| 인증 | 기존 O2 webhook secret을 Secrets Manager에서 실행 시 읽고 `x-dd-secret` 비교 |
| IAM | 해당 secret read, Signal Queue send, 로그 쓰기만 허용 |
| 금지 | 기존 ingress/Worker invoke, Dify·Bedrock 호출, Incident State write |
| 실패 관측 | payload 없는 `status=FAILED` 로그를 CloudWatch metric/alarm으로 변환 |

로컬 06-agent suite는 48개가 통과했고 Lambda-runtime `boto3`가 필요한 기존 Correlator
transaction 1개만 로컬에서 skip됐다. Terraform `fmt`·`validate`가 통과했으며 신규 대상
plan은 `8 add, 0 change, 0 destroy`였다. 실행 플래그만 `true`로 바꾸고 allowlist와 cutover를
두지 않은 음성 plan은 resource precondition에서 거부됐다. 병합 후 이 저장 plan만 적용했고
Lambda `Active`·update `Successful`, 실행 `false`, allowlist empty, 2100 cutover, Queue/DLQ 0을
확인했다. 전체 stack의 별도 4개 update는 적용하지 않았다.

Phase 4A 병합 후 순서는 다음으로 고정한다.

1. 신규 8개 리소스만 포함한 저장 plan을 다시 만들고 기존 `alert_relay` IAM·Lambda 3개
   update와 모든 destroy가 제외됐는지 확인한 뒤 비활성 상태로 apply
2. Function URL은 공유 문서에 남기지 않고, 기존 O2 webhook과 같은 secret header를 쓰는
   별도 Datadog Shadow webhook으로 등록
3. 합성 monitor 하나에만 기존 webhook과 Shadow webhook을 함께 붙임
4. Correlator·Generic Worker는 계속 disabled로 두고, Datadog Adapter는 합성 monitor ID 1개,
   Chat Adapter는 합성 broadcast 1개와 명시 cutover로만 일시 활성화
5. Signal Queue 메시지의 envelope `occurred_at`과 SQS `SentTimestamp`를 source별로 기록
6. Chat source-to-Queue, Datadog source-to-Queue, 두 source event-time 차이, 두 Queue 도착
   시각 차이를 Chat-first·Datadog-first 반복 실행에서 측정해 M-017에 추가
7. `Recovered`가 같은 cycle의 별도 trigger로 도착하는지 확인
8. 두 Adapter를 기본 비활성값으로 복귀하고 Shadow webhook을 합성 monitor에서 제거한 뒤,
   정확한 합성 메시지만 개별 삭제하고 Queue·DLQ 0과 대상 재-plan `No changes` 확인

운영 correlation window는 위 측정값이 생긴 뒤에만 결정한다. Phase 4A apply 성공이나 단일
샘플만으로 값을 정하지 않으며, 이 과정에서는 Agent Invocation Queue와 Dify를 열지 않는다.

2026-08-24 Phase 4B에서 위 절차를 실제로 수행했다. Datadog API로 별도 Shadow webhook을
등록했고 URL·`x-dd-secret`·15필드 payload·JSON encoding을 값 노출 없이 재조회 검증했다.
운영 monitor는 건드리지 않고 전용 custom metric monitor를 일시 생성했으며 기존
`@webhook-o2-dify`는 붙이지 않았다. 테스트 동안만 두 Adapter의 실행 gate를 열었고
Correlator·Invocation Worker는 계속 disabled였다.

| 실행 순서 | Chat source-to-Queue | Datadog Triggered source-to-Queue | Recovered 확인 |
|---|---:|---:|---|
| Chat-first | 7,995ms | 68,400ms | 63,400ms |
| Datadog-first | 8,743ms | 63,611ms | 62,828ms |

두 순서는 사람이 다음 source를 넣기 전에 앞 source의 Queue 도착을 확인한 제어 실험이다.
따라서 source 간 event-time 간격 자체는 운영 correlation window 근거가 아니다. 확인된 것은
Chat Candidate Stream 경로가 약 8-9초, Datadog monitor 평가·webhook 경로가 약 63-68초였고,
이번 두 표본에서 source transport 차이가 약 55-60초였다는 점이다. 운영 window는 반복 자동화
표본과 실제 장애의 source 발생 간격을 더 측정한 뒤 결정한다.

합성 allowlist 값을 Datadog alert 생성 전에 알 수 없으므로 테스트 동안 webhook payload의
`cycle_key`만 고정 합성값으로 바꿨고 종료 후 `$ALERT_CYCLE_KEY`로 복원했다. 따라서 Triggered와
Recovered가 같은 고정 cycle로 도착하는 것은 검증했지만 Datadog의 `$ALERT_CYCLE_KEY` 변수
치환 자체는 아직 별도 검증 항목이다. 신규 custom metric은 값이 먼저 보이고 tag-filter
index가 늦게 반영돼 초기 `run:` 쿼리가 빈 series였다. 테스트는 격리 전용 metric name의
`{*}`만 감시했고, 후속 조회에서 세 tag와 filtered series가 모두 나타난 것을 확인했다.
운영 monitor에서는 `{*}`로 우회하지 않고 tag-filter 조회가 가능해질 때까지 prewarm한다.

D-066 후속 구현은 이 사전 미확정 문제를 제거하기 위해 guard를 합성 monitor ID 하나로
바꿨다. 실제 `cycle_key`는 payload와 멱등 키에 그대로 남는다. 비활성 targeted apply는
`0 add / 1 update / 0 destroy`로 수행했고, Phase 4C에서 원래 `$ALERT_CYCLE_KEY` payload의
Triggered와 Recovered가 같은 cycle로 들어오는 것을 확인했다. 이에 따라
`DATADOG_ALERT_CYCLE_KEY_SUBSTITUTION_NOT_VERIFIED` blocker는 제거했다. 전체 plan의 기존 별도
IAM 1개·Lambda 4개 update는 targeted apply 대상에서 제외했고 적용하지 않았다.

종료 후 두 Adapter는 실행 `false`, allowlist empty, 2100 cutover로 복귀했고 Chat event source는
`Disabled`다. 합성 monitor는 삭제 후 GET 404를 확인했고 Shadow webhook은 운영형 15필드
payload로 남겨 두되 어떤 monitor에도 붙이지 않았다. Signal Queue·두 Adapter DLQ·Invocation
Queue/DLQ는 모두 visible/in-flight/delayed 0, 합성 Candidate 0, Adapter 실패 로그 0이었다.
두 Adapter 대상 재-plan은 `No changes`였고 06-agent 전체 plan의 별도 기존 update 4개는 계속
적용하지 않았다. 상세 측정 근거는 M-017에 있다.

### 6.9 Phase 4C 실제 source → 동일 Incident → Dify Shadow E2E

2026-08-24에 실제 외부 WebSocket Chat Candidate와 Datadog custom metric monitor를 같은
테스트 Incident로 연결했다. 300초는 기능 검증용 window이며 운영값이 아니다. 기존 팀 앱과
기존 Datadog webhook은 대상으로 삼지 않았고, 전용 contract-test Dify 앱만 호출했다.

첫 실행은 Chat의 환경 `dev`와 Datadog tag `env:o2-dev`가 달라 같은 symptom·service·surface와
시간창이어도 Incident 두 개로 분리됐다. Correlator가 환경을 exact match하는 계약대로
fail-safe한 결과다. Worker는 disabled라 Dify 호출은 0이었고 두 Invocation, Incident State와
합성 monitor를 개별 정리한 뒤 새 식별자로 재실행했다(T-026).

재실행에서는 Datadog tag를 `env:dev`로 맞췄다. 실제 Chat Candidate는 `READ_PATH/MEDIUM`,
4 messages, 4 unique users, `raw_chat_included=false`였고, Datadog은 원래 15필드 payload의
`$ALERT_CYCLE_KEY`와 `$ALERT_ID`를 그대로 사용했다.

| 검증 지점 | 결과 |
|---|---|
| source event-time 차이 | 57,840ms; 300초 test window 안 |
| Incident | revision 2, `CORRELATED/HIGH`, Chat+Datadog 두 source |
| normalized scope | `dev/LATENCY/api/READ_PATH` |
| Invocation revision 1 | Worker `SUPERSEDED`, Dify 미호출 |
| Invocation revision 2 | Worker `SUCCEEDED`, 전용 Dify run 정확히 1건 |
| Dify API 상태 | `succeeded`, error null, 3 steps, 0 tokens, elapsed 0.177606s |
| 실제 cycle 치환 | Triggered와 Recovered가 같은 cycle key, transition만 다름 |

성공 확인 즉시 Chat Adapter, Datadog Adapter, Correlator, Generic Worker와 세 event source를
모두 기본 비활성값으로 복귀했다. 합성 monitor는 삭제 후 GET 404, Signal/Invocation Queue와
모든 관련 DLQ는 visible/in-flight/delayed 0, Incident State·execution ledger·Candidate·window
state는 0이다. 이번에 건드린 06-agent/08-chat-signal 대상 plan은 모두 `No changes`다.
06-agent 전체 plan의 별도 기존 IAM 1개·Lambda 4개 update는 적용하지 않았다.

이 E2E로 새 Chat 진입점의 기능 게이트는 통과했지만 production 자동 호출을 연 것은 아니다.
운영 전에는 source별 반복 지연으로 correlation window를 정하고, 운영 Datadog monitor mapping과
`environment` canonicalization 정책을 확정해야 한다.

### 6.10 Phase 4D source environment 계약

D-070에 따라 Incident의 canonical environment는 배포 stack의 `var.environment`로 고정한다.
현재 `dev`가 environment이고 `o2-dev`는 Kubernetes namespace다. Chat은 Adapter의 배포값을
사용하고 Datadog은 webhook의 `env` tag가 Correlator 배포값과 exact match해야 한다.

Datadog 값이 다르면 정상 correlation key나 별도 provisional Incident를 만들지 않는다.
`AMBIGUOUS/SOURCE_ENVIRONMENT_MISMATCH`로 격리하고 운영자 확인을 요구한다. 접두사를 지우거나
namespace를 environment로 추측하는 alias 변환은 하지 않는다. 원래 Datadog 값은 signal에
남고 normalized context는 현재 배포 environment를 유지한다.

Phase 4D 구현은 schema·Correlator·단위 테스트·결정 기록까지 포함하지만 아직 Lambda에
적용하지 않았다. 병합 후 event source와 실행 gate가 disabled인지 먼저 확인하고 Correlator와
Generic Worker Lambda를 같은 비활성 targeted apply로 갱신한다. 새 reason code의 생산자와
소비자 계약이므로 둘을 나눠 배포하지 않는다. 적용 후 `env:o2-dev` 합성 신호가 mismatch reason으로
격리되고 기존 `dev` Incident에 자동 병합되지 않는지 확인한 뒤 blocker를 제거한다. Worker가
활성화된 운영 단계에서는 이 `AMBIGUOUS` snapshot도 read-only 분석 대상이 될 수 있지만
operator confirmation 없이 자동 조치로 넘어갈 수 없다.

병합 전 실제 state 기반 targeted plan은 `0 add / 2 change / 0 destroy`였고 두 Lambda의
`source_code_hash`만 바뀐다. IAM·환경변수·Queue·event source 변경은 없다. 이 저장 plan은
병합 전 커밋 기준이므로 apply에 재사용하지 않고 병합 후 같은 두 target으로 다시 만든다.

2026-08-24 병합 후 새 plan으로 두 Lambda를 함께 적용했다. Correlator·Worker의 code hash만
바뀌었고 실행 플래그와 event source는 계속 disabled였다. 이어 합성 idempotency key 한 개,
300초 test window, 합성 monitor mapping 한 개로 Correlator만 잠시 열어 `env:o2-dev` 신호를
넣었다. 생성된 revision 1은 다음 계약을 만족했다.

| 필드 | 실제 결과 |
|---|---|
| correlation | `AMBIGUOUS/LOW` |
| reason | `SOURCE_ENVIRONMENT_MISMATCH` |
| normalized environment | `dev` |
| source evidence env | `o2-dev` |
| operator confirmation | `true` |
| Worker/Dify | Worker disabled, 호출 0 |

검증 직후 Correlator를 `false`, allowlist empty, window `0`, mapping `{}`, event source
`Disabled`로 복귀했다. Signal·Invocation Queue와 두 DLQ, Incident State·execution ledger는
모두 0이고 Phase 4D 대상 plan은 `No changes`다.

### 6.11 Phase 4E 운영 Datadog monitor mapping

D-072에 따라 시나리오 4의 `role:page` 캐시 흡수 실패 composite monitor 한 개만
`LATENCY/READ_PATH/api`로 매핑한다. 이 monitor는 cache hit 저하와 API p95 상승을 동시에
요구한다. 같은 조건의 두 `role:sub` monitor는 중복 신호를 막기 위해 제외하고, 주문 응답 p95
monitor는 READ_PATH가 아니므로 제외한다.

mapping은 `infra/06-agent/terraform.tfvars`가 환경별 실제 monitor ID를 소유한다. 숫자 ID와
통제된 symptom/surface, 1~128자 service만 허용하도록 Terraform validation도 추가했다.
Phase 4E는 2026-08-24 병합 후 Correlator가 disabled인 상태에서 targeted apply했다.
실제 결과는 `0 add / 1 change / 0 destroy`였고
`INCIDENT_DATADOG_MONITOR_MAP_JSON`만 바뀌었다. 적용 후 update `Successful`, 실행 `false`,
allowlist empty, window `0`, event source `Disabled`를 확인했다. Signal·Invocation Queue와 두
DLQ, Incident State·ledger는 모두 0이고 대상 재-plan은 `No changes`였다. 전체 plan에 남은
기존 IAM 1개·Lambda 3개 update는 적용하지 않았다. Shadow webhook은 운영 monitor에 붙이지
않았고 Agent/Dify 호출도 0건이다.

### 6.12 Phase 4F 초기 correlation window

D-073에 따라 초기 Shadow correlation window를 420초로 준비한다. 값은 소수 표본의 p95가
아니라 실제 매핑한 Datadog monitor의 5분 full window 300초와, 관측된 Datadog Triggered
source-to-Queue 최대 69.474초를 60초 단위로 올린 120초를 합한 보수적 상한이다.

기계 판독 근거는 `infra/09-incident/correlation-window-evidence.json`이고
`scripts/validate-incident-correlation-window.py`가 다음 drift를 CI에서 막는다.

- Chat Worker 고정 window가 15초인지
- Datadog 시나리오 진입 monitor 기본 full window가 5분인지
- 관측값에서 계산한 tail guard가 120초인지
- `infra/06-agent/terraform.tfvars` 값이 계산 결과 420초와 같은지
- scope가 `SHADOW_ONLY`이고 production Agent handoff가 false인지

비활성 상태에서도 측정된 window를 미리 구성할 수 있도록 Terraform precondition을
`disabled + empty allowlist`로 바꾼다. 실행 `false`와 event source `false`는 그대로 강제한다.
병합 전 실제 state plan은 Correlator 환경변수 `INCIDENT_CORRELATION_WINDOW_SECONDS`만
`0 → 420`인 `0 add / 1 change / 0 destroy`다. 421초는 variable validation이 거부했고,
`enabled + empty allowlist`는 resource precondition이 거부했다. 전체 plan의 기존 IAM 1개·Lambda
3개 update는 대상 plan에서 제외했으며 적용하지 않는다. 병합 후 같은 target으로 새 plan을 만든다.
420초는 Shadow 초기값이며 p95·SLO가 아니다. 서로 다른 READ_PATH 장애의 오병합률을 Shadow에서
확인한 뒤 production handoff 전에 유지·축소 또는 구분 차원 추가를 결정한다.

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
- `contracts/examples/agent-incident-chat-first-v1.example.json`
- `contracts/examples/agent-incident-correlated-v1.example.json`
- `contracts/examples/agent-incident-environment-mismatch-v1.example.json`
