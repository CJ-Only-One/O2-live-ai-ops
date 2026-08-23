# Chat Incident Candidate — canonical implementation spec

> **Audience:** coding agents and reviewers
> **Status:** Phase 4 Shadow active; observation matrix passed; fixed-window boundary limitation reproduced
> **Updated:** 2026-08-23
> **Decision:** `decisions.md` D-047
> **Wire contracts:** `contracts.md` 5.6-5.7

This file is normative for processing behavior. `contracts.md` is normative for JSON field names,
types, and enums. D-047 is normative for the reason behind the design.

```yaml
implementation_state:
  canonical_docs: COMPLETE
  data_terraform: AWS_VERIFIED_APPLIED
  service_iam_terraform: AWS_VERIFIED_APPLIED
  lambda_processor: AWS_VERIFIED_SHADOW_ACTIVE
  event_source_mapping: AWS_VERIFIED_ENABLED
  chat_gateway_publisher: AWS_VERIFIED_SHADOW_ACTIVE
  candidate_logic: AWS_E2E_VERIFIED_AC_004_SAME_WINDOW
  shadow_observation: AWS_E2E_PASS_WITH_KNOWN_BOUNDARY_FALSE_NEGATIVE
  deployed_feature: true
next_action:
  phase: 5_WINDOW_POLICY_EVALUATION
  goal: COMPARE_BOUNDARY_SAFE_WINDOW_OPTIONS_WITH_PRIVACY_SAFE_LABELED_INPUTS
  apply_allowed: NO_WINDOW_CHANGE_UNTIL_DECISION
code_refs:
  data_terraform: infra/03-data/chat_signal.tf
  service_iam_terraform: infra/04-platform/app_data_access.tf
  worker_terraform: infra/08-chat-signal/worker.tf
  worker_runtime: infra/08-chat-signal/lambda/runtime/
  worker_tests: infra/08-chat-signal/lambda/tests/
  shadow_observation: apps/chat-gateway/scripts/shadow-observe.mjs
  chat_gateway_publisher: apps/chat-gateway/src/chat-signal.ts
  chat_ingress_fork: apps/chat-gateway/src/chat-ingress.ts
verification:
  chat_gateway_npm_ci: PASS
  chat_gateway_tests: PASS_20
  chat_gateway_typescript_build: PASS
  chat_gateway_docker_build: PASS_LOCAL_IMAGE
  worker_python_tests: PASS_20
  worker_lambda_python_3_13_import: PASS
  worker_terraform_validate: PASS
  acceptance_cases_local: PASS_AC_001_THROUGH_AC_010
  platform_terraform_validate: PASS
  chat_gateway_main_image_build: PASS
  chat_gateway_gitops_tag_update: PASS
  chat_signal_sqs_and_dynamodb_apply: PASS_2_ADD_0_CHANGE_0_DESTROY
  chat_signal_sqs_retention_sse_empty: PASS
  chat_incident_dynamodb_ttl: PASS
  worker_terraform_plan: PASS_5_ADD_0_CHANGE_0_DESTROY
  platform_terraform_plan: REVIEW_7_ADD_3_CHANGE_1_DESTROY
  platform_scaling_diff: NONE
  service_iam_and_config_apply: PASS_7_ADD_3_CHANGE_1_DESTROY
  external_websocket_fanout: PASS_4_CONNECTIONS_16_ITEMS
  first_shadow_candidate_e2e: FAIL_LAMBDA_TIMEOUT_AND_LATE_DROP
  runtime_fix_terraform_plan: PASS_0_ADD_2_CHANGE_0_DESTROY
  runtime_fix_apply: PASS_0_ADD_2_CHANGE_0_DESTROY
  producer_reenable_apply: PASS_0_ADD_1_CHANGE_0_DESTROY
  post_fix_cold_e2e: PASS_NO_TIMEOUT_BUT_WINDOW_SPLIT_NO_CANDIDATE
  aligned_candidate_e2e: PASS_AC_004
  candidate_contract: PASS_LOW_UNKNOWN_4_MESSAGES_4_USERS_NO_RAW_CHAT
  worker_success_interval: PASS_ERRORS_0_THROTTLES_0_CONCURRENCY_MAX_2
  queue_after_e2e: PASS_VISIBLE_0_IN_FLIGHT_0
  raw_chat_persistence_check: PASS_ZERO_RAW_ATTRIBUTES
  raw_chat_cloudwatch_filter: PASS_ZERO_MATCHES
  post_apply_terraform_drift: PASS_NO_CHANGES_04_AND_08
  aws_sqs_iam_integration: PASS_SEND_AND_CONSUME
  eks_runtime_verification: IMAGE_READY_CONFIG_SHADOW
  shadow_observation_websocket: PASS_24_MESSAGES_ALL_EXPECTED_FANOUT
  shadow_observation_processing: PASS_24_STATUSES_ACCOUNTED
  shadow_unrelated_filter: PASS_4_UNRELATED_NO_CANDIDATE
  shadow_same_user_dedup: PASS_1_VOTE_3_DUPLICATE_NO_CANDIDATE
  shadow_strong_threshold: PASS_MEDIUM_READ_PATH_4_MESSAGES_4_USERS
  shadow_cooldown: PASS_ONE_CANDIDATE_VERSION_2_8_MESSAGES_8_USERS
  shadow_boundary: CONFIRMED_FALSE_NEGATIVE_3_PLUS_1_NO_CANDIDATE
  shadow_worker_runtime: PASS_13_INVOCATIONS_ERRORS_0_THROTTLES_0_MAX_CONCURRENCY_2
  shadow_worker_duration: PASS_MIN_67_MS_MAX_288_MS
  shadow_privacy: PASS_DDB_FORBIDDEN_KEYS_0_DDB_TEXT_0_LOG_TEXT_0
```

`AWS_VERIFIED_APPLIED` means the dedicated SQS and DynamoDB exist in AWS and their 60-second
retention, managed SSE, empty backlog, and TTL were read back after apply.
`AWS_VERIFIED_SHADOW_ACTIVE` means the Lambda is Active with timeout 10 seconds and reserved
concurrency 2, and the live Chat Gateway ConfigMap has `CHAT_SIGNAL_MODE=shadow` after restart.
`AWS_VERIFIED_ENABLED` means the SQS event source mapping is Enabled with maximum concurrency 2.
`AWS_E2E_VERIFIED_AC_004_SAME_WINDOW` means four distinct weak signals placed in the same fixed
15-second event-time window created exactly one Candidate. It does not mean boundary false
negatives are resolved; see 5.1 and T-021.
`AWS_E2E_PASS_WITH_KNOWN_BOUNDARY_FALSE_NEGATIVE` means the controlled Shadow matrix verified
filtering, user deduplication, strong-signal creation, cooldown update, Queue drain, and privacy,
while independently reproducing a boundary false negative without timeout or throttle.

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

| Component | Status on 2026-08-23 |
|---|---|
| Chat Gateway WebSocket ingress | implemented |
| Valkey Pub/Sub fanout | implemented and previously live-verified |
| `chat.send` Kinesis telemetry | implemented; separate from this feature |
| dedicated Chat Signal SQS | applied; 60-second retention, managed SSE, empty backlog verified |
| Chat Signal Lambda | active; timeout 10s, reserved concurrency 2; post-fix E2E verified |
| SQS event source mapping | enabled; maximum concurrency 2; Queue drained after E2E |
| DynamoDB aggregation state | applied; `expires_at` TTL enabled |
| service-specific SQS IAM | applied; Chat Gateway and Order Worker use dedicated Pod Identity roles |
| Chat Gateway SQS publisher | `shadow` active; external send and fanout verified after Pod restart |
| Incident Candidate creation | AC-004 same-window AWS E2E passed; fixed-window boundary limitation remains (T-021) |
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

### 5.1 Known fixed-window boundary limitation

The current processor uses epoch-aligned 15-second tumbling windows. It does not implement an
arbitrary rolling 15-second interval, overlapping windows, or a true sliding window.

Therefore, four qualifying messages that occur within 15 seconds of each other can be split across
a fixed boundary, for example three votes in one window and one vote in the next. Neither window
then satisfies rule B. The post-fix `bc_1043` E2E reproduced this case without a Lambda timeout:
one message remained below threshold and three were dropped as late after cold processing.

`VERIFY-CHAT-WINDOW-001`: use Shadow replay evidence to choose one of the following before changing
the production default:

1. retain fixed tumbling windows and accept/measure boundary false negatives;
2. add bounded overlapping windows with explicit idempotency and cost limits;
3. implement a true sliding window with a revised state and Candidate contract.

Aligning synthetic messages to one window is valid for verifying the existing AC-004
implementation, but it is not a production fix for this limitation.

The controlled Shadow matrix reproduced the limitation without cold start or late drop. Three
weak votes sent at window offset 13.200 seconds and one at offset 0.399 seconds produced adjacent
window counts of 3 and 1 and no Candidate. All four events were processed normally. This proves
the failure mode exists; it does not measure its production frequency or a real false-positive
rate.

Until `VERIFY-CHAT-WINDOW-001` is decided:

- keep the current implementation in Shadow only;
- do not connect Candidate output to Dify or an automatic action;
- do not claim that the 15-second rule is a rolling-window guarantee;
- use privacy-safe labeled synthetic inputs because raw production chat is not retained for replay.

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
| `AC-003` | 3 strong users and 1 weak user in the same 15s event-time window | one `READ_PATH` Candidate |
| `AC-004` | 4 distinct weak users in the same 15s event-time window | one `LOW/UNKNOWN` Candidate |
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
