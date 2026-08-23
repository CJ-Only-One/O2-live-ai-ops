# AI Agent 공통 진입점 — canonical design

> **Audience:** coding agents and reviewers
> **Status:** Phase 0 contract only; no AWS resource or production routing change
> **Updated:** 2026-08-23
> **Decision:** `decisions.md` D-050
> **Wire contract:** `contracts.md` 5.8 and `contracts/agent-trigger-v1.schema.json`

```yaml
implementation_state:
  runtime_baseline_verified: COMPLETE
  common_contract: COMPLETE_IN_THIS_CHANGE
  agent_trigger_queue: NOT_IMPLEMENTED
  chat_candidate_adapter: NOT_IMPLEMENTED
  generic_dify_worker: NOT_IMPLEMENTED
  datadog_migration: NOT_STARTED
  production_agent_handoff: DISABLED
activation_blockers:
  - EXISTING_O2_DIFY_DLQ_NOT_EMPTY
  - DEPLOYED_DIFY_DSL_NOT_EXPORTED_TO_REPOSITORY
  - GENERIC_ENTRY_WORKER_AND_IDEMPOTENCY_LEDGER_NOT_IMPLEMENTED
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
| 실제 게시 앱 | `O2 Agentic AIOps — Source-Aligned Mock v4` |
| 실제 공통 입력 후보 | `custom_alert_json`, optional paragraph, 최대 30,000자 |
| 게시 graph 사용 여부 | `custom_alert_json` 참조 확인 |
| 채팅 Candidate handoff | 미구현, `agent_handoff_status=NOT_CONFIGURED` |
| 기존 Agent 경로 상태 | 성공 실행도 있으나 Worker 오류와 DLQ backlog가 있어 신규 경로의 무검증 재사용 금지 |

배포된 Dify 앱에는 `behavior`, `custom_alert_json`, Datadog 호환 입력이 있지만 저장소의
DSL과 README에는 Datadog 입력만 남아 있다(T-022). 따라서 런타임 사실은 API의 `/info`,
`/parameters`, 게시 workflow graph로 확인했고, 복구 가능한 소스의 정답은 DSL을 다시
내보낸 뒤에만 회복된다.

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
                                        Dify custom_alert_json -> Bedrock
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

## 4. Dify 입력 매핑

Generic Agent Worker는 envelope 전체를 compact JSON string으로 직렬화해 다음처럼 보낸다.

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
- `custom_alert_json`의 30,000자 제한을 Worker가 호출 전에 검사한다.
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
| 1 | Agent Trigger SQS/DLQ, idempotency ledger, Generic Worker를 비활성 상태로 생성 | Terraform fmt/validate, event source disabled, Dify 호출 0 |
| 2 | Chat Candidate INSERT Source Adapter와 계약 테스트 | synthetic Candidate가 정확히 한 envelope 생성, 원문/사용자 키 0, 중복 Agent 호출 0 |
| 3 | 별도 실험 workflow로 Dify Shadow E2E | `custom_alert_json` 계약 확인, success 상태 확인, 장애 시 Queue/DLQ 격리, 기존 DLQ 원인 정리 |
| 4 | Datadog Source Adapter dual-run 후 전환 | legacy/new 결과 비교, Recovered 의미 보존, rollback 확인 |
| 5 | 운영 hardening | backlog·error·DLQ 알람, replay runbook, concurrency·timeout 실측 근거 |

Phase 1과 2는 Dify를 호출하지 않는 상태로 진행할 수 있다. Phase 3 활성화 전에는 현재 O2
Worker의 DLQ backlog를 분류하고, 저장소 밖에서 변경된 게시 workflow DSL을 다시
내보내야 한다.

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
