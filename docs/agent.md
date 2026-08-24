# Dify 워크플로 — O2 Agentic AIOps (진단·조치)

> 이 문서는 다이어그램이 아니라 **Postgres 안 실제 워크플로 그래프(65 노드, 앱
> `O2 Agentic AIOps — Source-Aligned Mock v4`, 2026-08-24 기준)를 직접 조회해
> 대조한 결과**다. DSL export 는 아직 없다 — 다음에 워크플로를 고치면 Export DSL 을
> 먼저 하고, 이 문서는 그 DSL 대조본으로 낮춘다.

## 이 워크플로가 하는 일

Datadog에서 알람 하나가 날아오면, Lambda가 알람을 정규화하고 과거 유사
인시던트를 S3 Vectors에서 검색해 `past_cases`로 묶은 뒤 Dify를 호출한다.
**이 검색은 Dify 노드가 아니라 Lambda 안에서 끝난다** — Dify는 `past_cases`를
텍스트 변수로 받을 뿐이다(`../infra/06-agent/dify/README.md` 1.1.1).

Dify는 이 입력으로 진단·조치 루프에 들어간다. 루프 안에서는 먼저 Observability
스냅샷(Warm Path API 1회 + Hot Path CPU/Memory 조회 2회, 총 3건)을 가져와
원인을 진단하고, 확보한 런북 후보 중 하나를 골라 실행한다. 위험도가 낮으면
바로 실행하고, 높으면 Slack으로 사람 승인을 먼저 받는다. 실행 후 일정 시간을
기다렸다가 지표를 다시 확인해 실제로 나아졌는지 판정한다.

나아지지 않았으면, 같은 진단으로 다른 조치를 최대 2번까지 다시 시도하고,
그래도 안 되면 진단 자체를 최대 2번까지 다시 한다. 이 전체 사이클은
**최대 10번까지** 돈다(`main_loop.loop_count = 10`) 끝내 해결되지 않거나 사람이 조치를 거부하면 Slack으로
에스컬레이션하고 종료한다.

---

## 1. 전체 흐름

```
[Lambda] 과거 유사 인시던트 검색(S3 Vectors) → past_cases 텍스트로 조립
   │        ※ Dify 노드가 아니다. Dify start 노드의 입력 변수 하나일 뿐
   ▼
START (Datadog Alert Payload + past_cases)
   │
   ▼
CODE — Incident Normalize            payload → incident_context
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│  진단·조치 루프  (main_loop, loop_count = 10)                  │
│                                                               │
│  Diagnosis Router ──skip_diagnosis──▶ Runbook Lookup 로 직행   │
│       │ false                                                │
│       ▼                                                      │
│  [진단 단계]  →  [Runbook 준비]  →  [조치 결정]  →  [승인 분기]  │
│       →  [실행: PRE 스냅샷→라우팅→실행→결과병합]                 │
│       →  [검증: POST 스냅샷→비교→판정]  →  [Retry Router]        │
│                                                               │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
Post-Loop Router  (resolved 여부)
   │
   ▼
Finalize Output (결과 조립, 공통)
   │
   ▼
Slack Final Notify? ──아니오(resolved)──▶ END
   │ 예(미해결/manual_required)
   ▼
Slack Final Notify (HTTP) → END
```

---

## 2. 노드별 역할

### 2.1 진입 (루프 밖)

| # | 노드 | 타입 | 역할 |
|---|---|---|---|
| 1 | START | 시작 | Datadog Alert Payload + `past_cases` 수신. 입력 계약은 `../infra/06-agent/dify/README.md` 1절과 동일 계열 |
| 2 | Incident Normalize | CODE | payload → `incident_context` 로 정규화. 이후 모든 노드가 이 형태를 기준으로 참조 |

> **다이어그램에 있던 "3. Knowledge Retrieval — Incident History" 는 실제
> 워크플로에 존재하지 않는다.** 65개 노드 전체를 확인했지만 이력 검색 노드가
> 없다. **원래는 Dify 안에 이 노드가 있었으나, 이후 검색을 Lambda 쪽으로
> 옮기는 방향으로 로직이 바뀌었다** — 지금은 Lambda(`../infra/06-agent/lambda/worker.py`)가
> Dify 호출 **전에** 검색을 끝내고 `past_cases` 하나로 시작 시점에 넘겨줄
> 뿐이다. Dify는 벡터도, S3도 모른다.

### 2.2 진단 단계

| # | 노드 | 타입 | 역할 |
|---|---|---|---|
| 5 | Diagnosis Router | 분기(if-else) | `skip_diagnosis == false` 면 진단 수행(6번으로), `true` 면 **진단을 건너뛰고 Runbook Lookup(11번)으로 직행** |
| 6 | Observability Snapshot | HTTP | `warm_snapshot` — Warm Path API 스냅샷 1회 |
| 6-B/6-C | Hot Path — CPU/Memory | HTTP ×2 | `hot_cpu_snapshot`/`hot_mem_snapshot` — Datadog 직접 조회. 6번과 합쳐 **총 3건이 동시에 조회됨** |
| 7 | Context Enrichment | CODE | `warm_snapshot.body` + `hot_cpu_snapshot.body`/`hot_mem_snapshot.body`(CPU·Memory 최댓값 계산) + `incident_context` 를 `context_json` 하나로 병합. Warm Path 응답이 비거나 실패해도(dry-run 등) 예외 처리로 안전하게 degrade |
| 8 | Diagnosis Prompt | Template | Context + `attempt_log`(이전 시도 기록)를 반영해 프롬프트 조립 |
| 9 | Diagnosis Agent | Dify Agent 노드 (`type: agent`, v2, inline_agent 바인딩) | RCA 후보를 비교하고 근거와 confidence 를 산출. **query_athena tool 연결되어 있음** — snapshot 지표만으로 부족할 때 원시 로그 SQL 조회용. 모델은 Bedrock이 아니라 **GPT** — Bedrock + Dify Agent 노드 + 커스텀 tool 조합에서 `toolSpec.description null` 버그(langgenius/dify 확인된 버그)가 있어 이 노드만 GPT로 운용(제목·`desc` 필드에 명시, 2026-08-24 확인) |
| 10 | Diagnosis Output Parser | CODE | Agent 응답 → `parsed_diagnosis` 구조화 |

### 2.3 Runbook 준비

| # | 노드 | 타입 | 역할 |
|---|---|---|---|
| 11-A | Runbook Request Build | CODE | `parsed_diagnosis` 에서 `rca_category` 추출 |
| 11 | Runbook Lookup | HTTP POST (`RUNBOOK_LOOKUP_URL`) | rca_category 로 Runbook API 조회 — 내부적으로 DynamoDB(rca_type 6종: `cache_invalidation_storm` · `deploy_defect` · `pg_external_failure` · `pod_resource_exhaustion` · `queue_backlog` · `traffic_spike_overload`) 를 조회하는 것으로 확인(2026-08-24 테이블 스캔). **Dify는 DynamoDB를 직접 두드리지 않는다 — HTTP API 뒤에 숨어 있다** |
| 11-B | Runbook Response Shape | CODE | HTTP 응답에서 `actions` / `success_criteria` 추출 |
| 12 | Excluded Filter | CODE | `available_actions = runbook_actions − excluded_actions` |
| 13 | Candidate Guard | 분기 | `len(available_actions) > 0` 이면 조치 결정(14번)으로. 0 이면 13-A |
| 13-A | Event — Candidates Exhausted | CODE | `REDIAGNOSE` 이벤트 발행. 실제 재진단 허가/조기 종료 판정은 `state_reducer`가 한다 — 상세는 2.7절 |

**HTTP 노드가 3갈래(build → HTTP → shape)로 나뉘는 이유** — Dify HTTP 노드는
`{{#node.field#}}` 단순 변수 치환만 가능하고, JSON 파싱·중첩 필드 추출·기본값
처리 같은 로직은 못 한다. 그래서 요청 전에 CODE로 필요한 값을 미리 계산하고,
응답 후 CODE로 안전하게 파싱해 재포장하는 패턴이 이 워크플로 전체의 컨벤션이다
(`action_http`(19-D)도 동일하게 `resolve_target`/`param_resolver` CODE 노드를 거친다).

### 2.4 조치 결정

| # | 노드 | 타입 | 역할 |
|---|---|---|---|
| 14 | Remediation Planner | LLM (Bedrock Claude Sonnet 5) | 액션 후보를 비교해 trade-off 를 따져 하나를 선택. 현재는 tool 호출 없이 프롬프트 정보만으로 판단(`tools: null`) — **Agent 노드로 전환해 `history_lookup` 을 tool 로 호출하도록 변경 예정** |
| 15 | Guardrail Judge | CODE (결정론적 정책) | 액션의 `risk_level` 기준으로 verdict 산출: **L1/L2 → `AUTO`, L3 → `APPROVAL`** |
| 16 | Verdict Router | 분기 | `AUTO` → 바로 실행(19번). `APPROVAL` → Slack 승인 요청(17번) |
| 17 | Slack Approval Request | HTTP | 승인 대기. 데모 기준 타임아웃 600초 |
| 17-B | Slack Response Parser | CODE | Slack 응답 파싱 |
| 17-E | Event — Slack Approval Transport Failed | CODE | **Slack HTTP 호출 자체가 실패**했을 때(전송 실패, 타임아웃 등)의 별도 처리 — 사람이 거부한 것과는 다른 경로 |
| 18 | Slack Decision Router | 분기 | 사람의 응답을 분기 |
| 18-A | Event — Manual Required | CODE | [거부] → `MANUAL_REQUIRED` 이벤트 → `manual_required = true` 로 **루프 종료(Loop Break)** |
| 18-B | Event — Reconsider / Re-diagnose | CODE | [재판단] → `RECONSIDER` 이벤트. **이름과 달리 14번으로 바로 돌아가지 않는다** — 20-B(실행 실패)와 완전히 같은 공유 재시도 로직을 탄다: `remediation_retry` 남아있으면 12번, 소진되면 5번 (2.7절) |

### 2.5 실행

다이어그램의 "Action Executor" 하나는 실제로 **PRE 스냅샷 + 실행 라우팅 3갈래 +
결과 병합**으로 이루어져 있다.

| # | 노드 | 타입 | 역할 |
|---|---|---|---|
| 20-PRE | Warm Snapshot — Before Action | HTTP | 조치 실행 직전 상태 스냅샷. 사후 비교(22-C)의 PRE 기준점 |
| 19-A | Resolve Execution Target | CODE | 실행 대상 URL 계산 |
| 19-B | Execution Route | 분기 | **admin-key / api-key / Mock 3갈래**로 라우팅 |
| 19-C | Action Executor — Mock Fallback | CODE | **[TEMP JSON]** — 대상 미확정 시 임시 목업 결과 |
| 19-D | Action Executor (x-api-key) | HTTP | api-key 경로 실행 |
| 19-D2 | Action Executor (x-admin-key) | HTTP | admin-key 경로 실행 |
| 19-E | Shape HTTP Result | CODE | HTTP 실행 결과 정리 |
| 19-F | Action Result Merge | CODE | 19-D/19-D2/19-C 결과를 하나로 병합 |
| 20 | Execution Check | 분기 | 성공 여부 확인. 실패 시 20-B |
| 20-B | Event — Execution Failed | CODE | `excluded_actions += current_action`, `remediation_retry++`, `skip_diagnosis = true` 로 **12번(Excluded Filter)까지만 되돌아감**. (※ 이전 버전 문서에서 "20-A"로 표기했던 것과 동일 노드 — 실제 명칭은 20-B) |
| 21 | Stabilization Gate | CODE | 조치 적용 후 지표 반영을 위한 대기 |

### 2.6 검증과 재시도 판단

다이어그램의 "Verify Metrics" 하나도 실제로는 **POST 스냅샷 3종 + 비교 + 정리**로
나뉜다.

| # | 노드 | 타입 | 역할 |
|---|---|---|---|
| 22-A | Warm Snapshot — After Action | HTTP | 조치 후 Warm Path 스냅샷 |
| 22-B | Warm Metrics — Current Window | HTTP | 현재 윈도우 지표 조회 |
| 22-C | Warm Compare — PRE vs POST | HTTP | 20-PRE 스냅샷과 비교 |
| 22-D | Verification Shaper | CODE | 위 결과들을 정리 |
| 22-E/22-F | Hot Path — CPU/Memory After Action | HTTP ×2 | Datadog에서 조치 후 CPU/Memory 재조회 |
| 23 | Recovery Judge | CODE (결정론적 SLO 비교) | RCA가 지목한 지표를 SLO/정상 범위와 비교해 `resolved` 산출 |
| 24 | Retry Router | 분기 | `resolved`, `remediation_retry`, `diagnosis_retry` 조합으로 분기 |

### 2.7 Retry Router 이후 — 이벤트 병합 + 단일 리듀서

`recovery_judge`/`recovery_router`(23·24)를 포함해 이 루프 전체의 재시도
로직은 **여러 노드가 각자 상태를 갱신하는 게 아니라, "이벤트"를 만들기만
하고 `state_reducer` 하나가 전부 판정**하는 구조다. `event_agg`(병합) →
`state_reducer`(코드) → `apply_state`(할당) 순으로 흐른다. `state_reducer`
전체 코드를 직접 읽고 확인했다(2026-08-24).

**이벤트 타입 → 처리 (확정)**

| 이벤트 타입 | 발생 노드 | state_reducer 처리 |
|---|---|---|
| `RESOLVED` | `ev_resolved`(24-A) | `resolved=true`, `final_status='RESOLVED'`, `terminal_reason='SLO_RECOVERED'` → Loop Break |
| `MANUAL_REQUIRED` | `ev_approval_reject`(18-A) 등 | `manual_required=true`, `final_status='ESCALATED'` → Loop Break |
| `REDIAGNOSE` | `ev_candidates_exhausted`(13-A) | 아래 "13-A 전용 로직" 참고 |
| `EXECUTION_FAILED` / `NO_RECOVERY` / `RECONSIDER` | 20-B / `ev_no_recovery`(24) / `ev_approval_reconsider`(18-B) | **셋이 완전히 동일한 로직을 공유** — 아래 "공유 재시도 로직" 참고 |

(`ACTION_DENIED`(16-A) 도 코드상 같은 공유 버킷에 속하지만, 이 노드는 문서
반영 대상에서 제외하기로 했다 — 6절 참고.)

**공유 재시도 로직 — EXECUTION_FAILED / NO_RECOVERY / RECONSIDER**

```python
if action_id: excluded_actions.append(action_id)   # 실패/미회복/재판단 액션 제외
if remediation_retry < 2:
    remediation_retry += 1; skip_diagnosis = True    # 12번(Excluded Filter)부터 재시도
elif diagnosis_retry < 2:
    grant_rediagnosis()                              # 5번부터 재진단 (아래 참고)
else:
    final_status = 'RETRY_LIMIT_EXCEEDED'
    terminal_reason = 'REMEDIATION_AND_DIAGNOSIS_LIMIT'  # Loop Break
```

**18-B(재판단)는 20-B(실행 실패)와 완전히 같은 카운터를 공유한다** — "14번으로
돌아가 다른 후보를 고른다"가 아니라, `remediation_retry`가 남아있으면 12번,
소진됐으면 5번으로 간다. `ev_no_recovery`도 마찬가지로 이 공유 로직을 타고,
**REGRESSION(악화됨)인지 NO_RECOVERY(그냥 안 나아짐)인지는 로그·표시용
구분일 뿐 라우팅에는 영향을 주지 않는다.**

**13-A 전용 로직 (`REDIAGNOSE`) — 조기 종료 안전장치 포함**

```python
same_rca_no_new_info = (
    reason == 'CANDIDATES_EXHAUSTED'
    and current_rca == pending_rediagnosis_rca   # 직전에 재진단을 "허가"했을 때의 rca와 비교
)
if same_rca_no_new_info:
    final_status = 'RETRY_LIMIT_EXCEEDED'
    terminal_reason = 'ACTIONS_EXHAUSTED_SAME_RCA'   # 재진단해도 같은 원인 → 조기 종료
elif diagnosis_retry < 2:
    grant_rediagnosis()   # diagnosis_retry++, remediation_retry=0, skip_diagnosis=false,
                           # pending_rediagnosis_rca = 이번 rca
else:
    final_status = 'RETRY_LIMIT_EXCEEDED'
    terminal_reason = 'DIAGNOSIS_RETRY_LIMIT'
```

이 조기 종료(`same_rca_no_new_info`)는 코드 주석에 따르면 **실제 운영
인시던트(2026-08-23, 큐 적체 건)에서 재진단이 같은 원인을 반복해서
`diagnosis_retry` 2회를 전부 허비한 사례가 있어서 나중에 추가된 것**이다 —
설계 당시엔 없었고 실전에서 배선이 바뀐 부분이다.

`mock_revert`(24-D, **[TEMP JSON]**)는 아직 실제 연동 전 목업이라 위 흐름
어디서 호출되는지는 이 코드만으로 확정할 수 없다.

### 2.8 루프 종료 후

다이어그램에 있던 **"DynamoDB 쓰기(27-A/27-B)"는 실재하지 않는다.** 65개 노드
전체에 DynamoDB에 쓰는 노드가 하나도 없다. 27-A/27-B의 실제 정체는 Slack
최종 알림이다.

| # | 노드 | 타입 | 역할 |
|---|---|---|---|
| 25 | Post-Loop State Parser | CODE | 루프 종료 시점 state 파싱 |
| 25 | Post-Loop Router | 분기 | `resolved` 여부로 분기 |
| 26 | Finalize Output | CODE | 최종 결과 객체 조립 — **성공/실패 공통 경로**, "26-A/26-B"로 나뉘어 있지 않다 |
| 27-A | Slack Final Notify? | 분기 | 미해결/`manual_required` 케이스에서만 Slack 알림 여부 판단 |
| 27-B | Slack Final Notify (HTTP) | HTTP | Slack으로 최종 알림 전송 |
| END | END: FINAL RESULT | 종료 | 워크플로 출력 반환 |

**27-A/27-B는 Slack 알림 전용이고, Lambda나 S3는 전혀 관여하지 않는다.**
`final_slack_http`(27-B)의 실제 URL을 확인해보면
`https://hooks.slack.com/services/...` — **Slack Incoming Webhook 을 직접
호출**한다(2026-08-24 확인). 앞의 `finalize_output`(26) 코드도 `slack_text`/
`slack_payload_json`만 조립할 뿐 S3나 Lambda 호출 로직이 없다.

이력(S3 원본 JSON + S3 Vectors)은 `../infra/06-agent/README.md` "이력 저장소" 절에 문서화된
대로 **Dify 워크플로 밖에서, Dify를 호출하는 `lambda/worker.py`가** Triggered/
Recovered 시점에 담당한다. 즉 흐름은:

```
Datadog → Lambda(worker.py) ─┬─▶ Dify 호출 (이 워크플로 전체)
                              └─▶ S3 원본 JSON + S3 Vectors 적재 (Dify와 별도)
```

Dify 안에는 이력을 적재하는 노드가 없고, 27-A/27-B가 하는 일은 Slack 알림
하나뿐이다. `worker.py`가 Dify 실행 전후 정확히 어느 시점에 무엇을 트리거로
S3에 쓰는지는 이 그래프만으로 확인할 수 없다 — `../infra/06-agent/lambda/worker.py` 코드
확인 필요(6절).

---

## 3. State 변수

| 변수 | 초기값 | 갱신 위치 | 의미 |
|---|---|---|---|
| `remediation_retry` | 0 | 20-B, `ev_no_recovery` 에서 갱신. 13-A 에서 리셋 | 같은 진단 결과 안에서 조치를 재시도한 횟수. **최대 2** |
| `diagnosis_retry` | 0 | 13-A, `ev_no_recovery` 에서 갱신 | 진단 자체를 다시 시도한 횟수. **최대 2** |
| `skip_diagnosis` | false | 20-B 에서 `true`. 13-A 에서 `false` | true 면 5번 진단 단계를 건너뛰고 11번(Runbook Lookup)부터 시작 |
| `excluded_actions` | `[]` | 20-B 에서 `+=` 실패 액션. 13-A 에서 `[]` 로 리셋 | 이번 진단 사이클 안에서 이미 실패했거나 소진된 액션 |
| `attempt_log` | `[]` | `ev_resolved`, `mock_revert`, 20-B 등에서 누적 | 모든 시도(성공·실패 포함) 기록 |
| `manual_required` | false | 18-A 에서 `true` | true 가 되면 그 즉시 Loop Break, 27-A 로 Slack 최종 알림 |
| `stop_flag` | false | `main_loop` 의 break 조건이 참조하는 변수(`apply_state`가 설정하는 것으로 추정) | true 가 되면 루프 즉시 종료 |

State 갱신은 위 표에 적힌 개별 노드가 아니라 **`state_reducer`(단일 리듀서) →
`apply_state`(할당)** 를 거쳐 실제 반영되는 것으로 보인다. 정확한 리듀서 로직은
코드 미확인(6절).

## 4. 한도 정리

| 한도 | 값 | 근거 |
|---|---|---|
| Outer Loop (main_loop) | **최대 10회** | `main_loop.loop_count = 10` (설정값 직접 확인, 2026-08-24) |
| `remediation_retry` (조치 재시도) | 2 | 재진단으로 전환 |
| `diagnosis_retry` (재진단) | 2 | 한도 초과 종료 |
| Slack 승인 대기 | 600초 (데모 기준) | 타임아웃 시 동작은 `17-E`(전송 실패)로 처리되는 것으로 보이나, 정확히 타임아웃과 전송 실패가 같은 경로인지는 미확인 |

## 5. 되돌아가는 지점 정리 (헷갈리기 쉬운 부분)

| 무엇이 실패했나 | 되돌아가는 지점 | 왜 |
|---|---|---|
| Runbook 후보가 애초에 0개 (13-A) | `remediation_retry` 와 무관하게 5번, 진단부터 다시(단, "같은 원인 반복" 이면 조기 종료 — 2.7절) | 후보가 없다는 것 자체가 진단이 쓸모없었다는 신호 |
| 액션 실행이 기술적으로 실패 (20-B) | `remediation_retry < 2` 면 12번, 소진되면 5번 | 진단은 맞을 수 있다. 방금 액션만 빼고 남은 후보로 재시도 |
| 액션은 실행됐지만 지표가 안 나아짐 (`ev_no_recovery`) | 20-B와 **동일한 공유 로직** — `remediation_retry < 2` 면 12번, 소진되면 5번 | 진단은 맞을 수 있다. 다른 후보를 시도 |
| Slack에서 [재판단] 선택 (`ev_approval_reconsider`, 18-B) | 20-B/`ev_no_recovery`와 **동일한 공유 로직** — 14번이 아니라 12번 또는 5번 | "재판단"이라는 이름과 달리 실제로는 실행 실패·미회복과 완전히 같은 카운터를 공유한다(2.7절) |

**"실행 실패"·"지표 미회복"·"재판단"은 세 가지 다른 이름이지만 코드에서는
완전히 같은 재시도 로직(공유 버킷)을 탄다.** `remediation_retry` 값이 남아
있으면 12번, 소진됐으면 5번으로 가는 게 전부다 — 무엇이 트리거였는지는
`terminal_reason`/로그에만 남고 라우팅 자체는 갈리지 않는다.

## 6. 아직 안 정한 것 / 미확인

- **Slack 승인 타임아웃(600초) 이후 동작.** `17-E`(전송 실패 이벤트)와 관계가
  있는지, 타임아웃 자체가 별도로 처리되는지 코드 확인 필요
- **16-A(Guardrail Deny) / `ACTION_DENIED` 이벤트.** 코드상으로는 확인됐지만
  (`guardrail`(15)이 카탈로그에 없는 action_id에 DENY를 내리고, `state_reducer`에서
  다른 공유 이벤트와 같은 재시도 버킷을 탐) **이 부분은 문서에 반영하지 않기로
  했다.** 필요해지면 이 README의 과거 대화 기록이나 `state_reducer`/`guardrail`
  코드를 다시 확인할 것
- **`worker.py`가 Dify 실행 전후 정확히 언제 S3/S3 Vectors 에 쓰는지.** 27-A/27-B는
  Slack 알림 전용(Webhook 직접 호출)으로 확인됐고 Dify 안에 이력 쓰기 노드는
  없다 — 적재는 `../infra/06-agent/lambda/worker.py` 쪽이지만 정확한 트리거 시점은 그 코드를
  봐야 확정된다
- **`mock_action_fallback`(19-C), `mock_revert`(24-D) 등 "[TEMP JSON]" 표시된
  노드들.** 아직 실제 연동 전 임시 목업 — 실제 연동되면 이 문서도 갱신
- **Remediation Planner(14번)의 tool 미연결.** `type: llm` 노드라 `tools: null`
  확인됨(9번과 달리 옛 LLM 노드 스키마라 이 필드 체크가 유효하다). Agent 노드로
  전환해 `history_lookup` 을 tool 화할 예정(2.4절)
- **Diagnosis Agent(9번) `agent_binding.agent_id` 의 정확한 tool 스펙.**
  query_athena 연결 자체는 `desc` 필드로 확인됐지만, 파라미터 스키마 등
  상세는 별도 Dify `agents` 테이블을 더 조회해야 확정된다
- **DSL export.** 아직 없다. 다음 워크플로 수정 시 Export DSL 을 먼저 하고
  이 문서를 DSL 대조본으로 낮춘다
- **`agent_backend` 컨테이너와의 관계.** 호스트에 Dify 표준 compose에 없는
  `docker-agent_backend-1` 등 커스텀 컨테이너가 떠 있다(2026-08-24 확인).
  어느 노드가 이를 호출하는지 미확인 — `resolve_target`/`execution_route`
  (19-A/19-B)의 라우팅 대상 중 하나일 가능성이 있으나 코드 확인 전까지는 추정

## 7. 이 문서를 고쳐야 하는 시점

- Dify 콘솔에서 이 워크플로의 노드를 추가·제거·재배선할 때 → 해당 절 표를 같이 고친다
- 한도(`remediation_retry`, `diagnosis_retry`, `loop_count`, Slack 타임아웃)를 바꿀 때 → 4절
- State 변수 이름이나 갱신 위치를 바꿀 때 → 3절
- 6절의 미확인 항목을 코드로 확인했을 때 → 해당 항목을 지우고 본문에 확정 반영
- **DSL 을 처음 export 하는 날** → 상단 안내 문구를 지우고 `../infra/06-agent/dify/README.md` "파일" 표에
  실제 DSL 파일명을 추가한다
