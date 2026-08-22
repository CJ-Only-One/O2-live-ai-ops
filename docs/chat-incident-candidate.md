# Chat Incident Candidate — canonical implementation spec

> **Audience:** coding agents and reviewers
> **Status:** approved design, Phase 2 implemented and locally verified, default off, not deployed
> **Updated:** 2026-08-22
> **Decision:** `decisions.md` D-047
> **Wire contracts:** `contracts.md` 5.6-5.7

This file is normative for processing behavior. `contracts.md` is normative for JSON field names,
types, and enums. D-047 is normative for the reason behind the design.

```yaml
implementation_state:
  canonical_docs: COMPLETE
  data_terraform: CODE_VALIDATED_NOT_APPLIED
  service_iam_terraform: CODE_VALIDATED_NOT_APPLIED
  lambda_processor: SKELETON_CODE_VALIDATED_NOT_APPLIED
  event_source_mapping: CODE_VALIDATED_DISABLED_NOT_APPLIED
  chat_gateway_publisher: CODE_VALIDATED_DEFAULT_OFF_NOT_DEPLOYED
  candidate_logic: NOT_IMPLEMENTED
  deployed_feature: false
next_action:
  phase: 3
  goal: ADD_DETERMINISTIC_CLASSIFICATION_AND_AGGREGATION
  apply_allowed: false
code_refs:
  data_terraform: infra/03-data/chat_signal.tf
  service_iam_terraform: infra/04-platform/app_data_access.tf
  worker_terraform: infra/08-chat-signal/worker.tf
  worker_skeleton: infra/08-chat-signal/lambda/handler.py
  chat_gateway_publisher: apps/chat-gateway/src/chat-signal.ts
  chat_ingress_fork: apps/chat-gateway/src/chat-ingress.ts
verification:
  chat_gateway_npm_ci: PASS
  chat_gateway_tests: PASS_20
  chat_gateway_typescript_build: PASS
  chat_gateway_docker_build: NOT_RUN_DOCKER_DAEMON_UNAVAILABLE
  platform_terraform_validate: PASS
  aws_sqs_iam_integration: NOT_RUN
  eks_runtime_verification: NOT_RUN
```

`CODE_VALIDATED_NOT_APPLIED` means `terraform fmt` and `terraform validate` succeeded locally. It
MUST NOT be interpreted as an AWS resource, deployment, or runtime verification.
`SKELETON_CODE_VALIDATED_NOT_APPLIED` additionally means fail-safe handler unit tests passed.
`CODE_VALIDATED_DISABLED_NOT_APPLIED` means the event source is hard-coded disabled and was not
created in AWS.
`CODE_VALIDATED_DEFAULT_OFF_NOT_DEPLOYED` means unit tests and TypeScript build passed while the
runtime mode remains fail-safe `off`; it does not mean an image or Pod was deployed.

## 0. Agent execution rules

Before changing this feature, an agent MUST read:

1. this file;
2. `contracts.md` 3.7-3.8 and 5.3-5.7;
3. `decisions.md` D-047;
4. the target stack README before editing Terraform.

Precedence when documents conflict:

1. newer three-digit decision in `decisions.md`;
2. wire schema in `contracts.md`;
3. processing rules in this file;
4. older two-digit design in `architecture.md`.

An implementation MUST NOT infer missing values. Items marked `VERIFY` remain undecided until
measured or explicitly approved.

## 1. Scope

### 1.1 In scope

- branch accepted chat input from Chat Gateway to a dedicated SQS Standard queue;
- classify deterministic latency signals;
- aggregate by broadcast, candidate type, and event-time window;
- deduplicate SQS delivery and users;
- persist derived state in DynamoDB;
- create one structured Incident Candidate.

### 1.2 Out of scope

- Datadog API calls;
- Dify workflow calls;
- Bedrock calls;
- root-cause selection;
- human-versus-bot classification;
- infrastructure mutation or automatic remediation;
- per-message ML or LLM classification.

The terminal output of this scope is:

```text
metric_status=NOT_CHECKED
root_cause=UNDETERMINED
agent_handoff_status=NOT_CONFIGURED
```

## 2. Required data flow and invariants

```text
accepted WebSocket chat
  └─ Chat Gateway
       ├─ Valkey Pub/Sub -> existing WebSocket fanout
       └─ dedicated Chat Signal SQS -> Lambda -> DynamoDB -> Incident Candidate
```

The two branches are independent.

| ID | Invariant |
|---|---|
| `INV-CHAT-001` | Valkey Pub/Sub MUST remain the real-time fanout path. |
| `INV-CHAT-002` | Analysis MUST originate at Chat Gateway ingress, not from a Valkey subscriber. |
| `INV-CHAT-003` | SQS failure MUST NOT reject or delay accepted chat beyond a bounded attempt. |
| `INV-CHAT-004` | Chat Gateway MUST NOT classify, aggregate, call Datadog, or call an Agent. |
| `INV-CHAT-005` | One chat message MUST NOT cause one Agent call. |
| `INV-CHAT-006` | Candidate creation MUST NOT assert a root cause. |
| `INV-CHAT-007` | Dify placement changes MUST NOT require changes to chat ingestion. |

## 3. Implementation status boundary

| Component | Status on 2026-08-22 |
|---|---|
| Chat Gateway WebSocket ingress | implemented |
| Valkey Pub/Sub fanout | implemented and previously live-verified |
| `chat.send` Kinesis telemetry | implemented; separate from this feature |
| dedicated Chat Signal SQS | Terraform code validated; not applied |
| Chat Signal Lambda | fail-safe skeleton code validated; not applied |
| SQS event source mapping | Terraform code validated; hard-disabled; not applied |
| DynamoDB aggregation state | Terraform code validated; not applied |
| service-specific SQS IAM | Terraform code validated; not applied |
| Chat Gateway SQS publisher | code locally verified; default `off`; not deployed |
| Incident Candidate creation | not implemented |
| Datadog Pull and Dify handoff | out of scope / not implemented |

Do not report a Terraform validation, image build, or document merge as a deployed feature.

## 4. Signal taxonomy

The PoC candidate type is fixed:

```text
USER_PERCEIVED_LATENCY
```

`suspected_surface` is evidence scope, not root cause:

| Value | Evidence required |
|---|---|
| `READ_PATH` | page, product data, image, loading, refresh, button, order, or payment context |
| `PLAYBACK` | playback, buffering, frozen video, or stream context |
| `CHAT` | chat connection, send, receive, or chat lag context |
| `UNKNOWN` | latency expression without a target surface |

Rules MUST run in this order:

```text
1. exclusion, negation, and recovery
2. strong signal
3. weak signal
4. unrelated chat
```

Strong signal: service surface/action plus a latency/failure expression. Examples:
`상품 정보가 늦게 떠요`, `새로고침해도 계속 로딩돼요`.

Weak signal: latency expression without a target. Examples: `느리네`, `나만 느림?`,
`렉 걸린 것 같은데`.

Excluded signal: explicit non-service context or non-active symptom. Examples: delivery speed,
presenter speed, broadcast pacing, `이제 정상이에요`.

Signal strength is evidence specificity, not severity or sentiment.

## 5. Approved PoC thresholds

These values are initial hypotheses, not measured capacity, SLOs, or universal production values.

| Parameter | Initial value | Rationale |
|---|---:|---|
| event-time window | 15 seconds | allow independent users to react while retaining early detection |
| minimum matched messages | 4 | require a repeated symptom rather than one utterance |
| minimum unique users | 3 | reject one-user spam and reduce two-person conversation noise |
| user contribution | 1 per window and candidate type | prevent repeats from filling the threshold |
| candidate cooldown | 60 seconds | merge continuing evidence instead of creating candidate floods |
| accepted late arrival | 5 seconds | tolerate short delay and Standard Queue reordering |

Creation rule A:

```text
strong_signal_count >= 1
AND matched_messages >= 4
AND unique_users >= 3
```

Creation rule B:

```text
strong_signal_count == 0
AND weak_signal_count >= 4
AND unique_users >= 4
=> confidence=LOW, suspected_surface=UNKNOWN
```

During cooldown, the processor MUST update the existing Candidate and MUST NOT create another for
the same `broadcast_id + candidate_type`.

Threshold changes require replay evidence. Compare at least:

| Profile | Window | Messages | Users |
|---|---:|---:|---:|
| sensitive | 10s | 3 | 3 |
| approved initial | 15s | 4 | 3 |
| conservative | 20s | 5 | 4 |

## 6. Privacy and retention

| ID | Requirement |
|---|---|
| `PRIV-001` | Raw chat MAY exist only in the encrypted analysis SQS message. |
| `PRIV-002` | Queue message retention MUST be 60 seconds. |
| `PRIV-003` | A successfully processed message MUST be deleted immediately. |
| `PRIV-004` | Raw chat MUST NOT be written to logs, Datadog, DynamoDB, or Candidate output. |
| `PRIV-005` | Raw chat hashes MUST NOT be written to new analysis state or Candidate output. |
| `PRIV-006` | Failure records MUST contain identifiers and error codes only, never the SQS body. |
| `PRIV-007` | A raw-message DLQ MUST NOT be created for this PoC. |

Accepted trade-off: an analysis signal may be lost when processing is unavailable longer than the
60-second retention. This feature is advisory and does not protect a customer transaction.

The existing `chat.send.msg_hash` telemetry contract is not input to this feature. Its separate
retention/privacy review is not part of this implementation.

## 7. Worker and state ownership

Initial processor: AWS Lambda triggered by SQS.

- traffic is unknown and expected to be low during the PoC;
- no idle Pod is required;
- retries and bounded concurrency are native;
- detector failure remains isolated from EKS and Dify;
- Dify can move from EC2 to EKS without changing the detector.

DynamoDB MUST own idempotency, window aggregation, unique-user votes, cooldown, and Candidate
state. Dify MUST NOT own this concurrent authoritative state.

Initial table requirements:

```text
billing_mode=PAY_PER_REQUEST
PITR=false
Streams=false
GlobalTable=false
```

Conceptual item families:

```text
EVENT#{event_id}                                      TTL 10m
WINDOW#{broadcast_id}#{candidate_type}#{window_start} / AGG
WINDOW#{broadcast_id}#{candidate_type}#{window_start} / USER#{user_key}
CANDIDATE#{candidate_id}                              TTL 7d
```

Candidate creation MUST use conditional writes or an equivalent atomic guard.

## 8. Failure semantics

| Failure | Required behavior |
|---|---|
| SQS send failure | continue chat; emit sanitized failure metric |
| duplicate delivery | apply once by `event_id` |
| out-of-order delivery | place by `event_ts`, not receive time |
| arrival up to 5s late | update the original window |
| arrival over 5s late | discard; increment sanitized counter |
| transient Lambda failure | retry within message retention |
| invalid schema | emit sanitized metadata; delete message |
| DynamoDB conditional conflict | re-read; do not duplicate Candidate |
| outage over 60s | signal loss is accepted and observable |
| Dify unavailable | no effect; Dify is outside this scope |

## 9. Observability without content

- Chat Gateway SQS attempt, success, failure, and duration;
- SQS visible messages and oldest-message age;
- Lambda invocation, duration, error, throttle, schema rejection, and late-event count;
- DynamoDB request, throttle, and conditional-conflict count;
- rule ID match counts;
- Candidate counts by `suspected_surface` and `confidence`;
- first matching signal to Candidate duration;
- duplicate Candidate count.

Do not define an operational SLO before measurement. The PoC functional target is Candidate
creation within `15s window + 5s late allowance = 20s`.

## 10. Acceptance cases

| ID | Input | Expected result |
|---|---|---|
| `AC-001` | unrelated chat only | no Candidate |
| `AC-002` | one user repeats `느려요` | no Candidate |
| `AC-003` | 3 strong users and 1 weak user within 15s | one `READ_PATH` Candidate |
| `AC-004` | 4 distinct weak users within 15s | one `LOW/UNKNOWN` Candidate |
| `AC-005` | delivery/presenter/pacing slowness | no Candidate |
| `AC-006` | duplicate SQS delivery | counts increase once |
| `AC-007` | same evidence during cooldown | existing Candidate updated, no new Candidate |
| `AC-008` | SQS unavailable | WebSocket chat still succeeds |
| `AC-009` | processing exception | no raw chat in logs or failure record |
| `AC-010` | Candidate persisted | `root_cause=UNDETERMINED`, no raw chat/hash |

## 11. Future handoff boundary

Future flow, not part of this implementation:

```text
Incident Candidate -> adapter -> Dify -> read-only Datadog Pull -> Bedrock analysis
```

Candidate generation MUST NOT wait for a Datadog monitor or metrics query. Later investigation
SHOULD query timeseries around `window_start/window_end`; monitor status alone can lag user signal.

The future Agent MUST return `UNDETERMINED` when server-side evidence cannot distinguish organic
traffic from automation. Client-generated session identifiers are insufficient evidence.

## 12. Implementation order and gates

| Phase | Work | Exit gate |
|---|---|---|
| 0 | canonical spec, decision, wire contract | docs index passes; no document conflict |
| 1A | split IAM and add SQS/DynamoDB | Terraform fmt/validate; no apply |
| 1B | add disabled Lambda skeleton and least-privilege worker IAM | Terraform fmt/validate; event source remains disabled |
| 2 | Chat Gateway publisher behind `off/shadow` flag | tests pass; SQS failure cannot fail chat |
| 3 | deterministic classification and aggregation | `AC-001` through `AC-010` pass |
| 4 | deploy Shadow Mode | CI, image, manifest, EKS, and external chat verified separately |
| 5 | replay and threshold review | evidence recorded before default changes |
| later | Datadog Pull and Dify handoff | separate contract and approval |

No phase may be described as deployed until its exit gate is satisfied.
