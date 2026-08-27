# 시나리오 준비 상태 — 요구 대비 현재, 그리고 할 일

시나리오 셋(S1·S2·S3)이 요구하는 것과 세 저장소에 **실제로 있는 것**을 대조한 표다.
시연까지 무엇을 고치고, 무엇을 새로 만들고, 무엇을 빼는지가 3~5절에 있다.

> **이 문서는 규칙도 수치도 소유하지 않는다.** 판정과 링크만 담는다.
> 시나리오 정의·복구 판정 규칙·주입 설정은 [`scenario-experiment.md`](scenario-experiment.md),
> 실측값은 [`measurements.md`](measurements.md), 결정은 [`decisions.md`](decisions.md) 가 원본이다.
> 여기에 같은 내용을 다시 적으면 반드시 한쪽이 낡는다.

기획 원본은 저장소 밖 노션 문서(장애 시나리오 v4)이고, 그중 구현·실험에 필요한 부분이
`scenario-experiment.md` 로 들어와 있다. 아래 "요구" 열은 기획 원본 기준이다.

## 인덱스

| 절 | 무엇 |
|---|---|
| 0 | 이 문서를 갱신하는 규칙 |
| 1 | 판정 어휘 |
| 2 | 대조표 — 공통 기반 · S1 · S2 · S3 · 녹화 |
| 3 | 변경해야 할 것 |
| 4 | 추가해야 할 것 |
| 5 | 뺄 것 |
| 6 | 실행 순서 |
| 7 | 아직 안 잰 값 |

---

## 0. 이 문서를 갱신하는 규칙

대조표는 손대지 않으면 한 주 만에 낡는다. 아래를 지킨다.

- 상태가 바뀌면 **그 행만** 고친다. 표를 다시 쓰지 않는다
- 판정에는 **근거 경로를 반드시 남긴다**(파일·줄·절). 경로가 없으면 다음 사람이 전수 조사를 다시 한다
- 실측이 채워지면 7절의 행을 지우지 말고 **`M-0NN` 참조로 바꾼다.** 안 잰 것과 잰 것의 이력이 같이 남아야 한다
- **시나리오 자체가 바뀌면 이 문서가 아니라 `scenario-experiment.md` 를 먼저 고친다.** 여기는 따라간다
- `git log --oneline -- docs/scenario-readiness.md` 가 곧 진행 이력이 되도록 **한 번에 한 주제만** 커밋한다

## 1. 판정 어휘

자유 서술을 쓰지 않는다. 표현이 갈리면 "무엇이 남았나" 를 셀 수 없다.

| 판정 | 뜻 |
|---|---|
| **있음** | 그대로 쓸 수 있다 |
| **설계만** | 계약·결정 문서는 있고 구현이 없다 |
| **구현됨** | 저장소 코드와 검증은 있고 실환경에는 아직 적용하지 않았다 |
| **비활성** | 구현·배포는 됐고 실행 게이트가 꺼져 있다 |
| **고쳐야** | 있는데 시나리오 조건과 어긋난다 |
| **깨져 있음** | 있다고 보이는데 실제로는 동작하지 않는다 |
| **보류** | 할 수 있는데 지금은 일부러 안 한다. 이유와 재개 조건을 같이 적는다 |
| **없음** | 아무것도 없다 |

---

## 2. 대조표

### 2.1 공통 기반 — 크리티컬 패스

| 요구 | 현재 | 판정 |
|---|---|---|
| 조치 실행기 (파드 수·노브 변경) | S2는 `action_executor.tf` + `scale_deployment.py`, S1은 `/ws/admin/channel-limit`로 구현됐다. S3도 제어면(`/api/admin/pg-stub`·`/api/admin/pg-provider-switch`)과 L3 `switch_pg_provider`가 있다. 2026-08-28 게시 Dify graph는 PG 전환을 `REAL` 특수 타깃으로 라우팅하지만 URL·admin key를 Code 노드에 평문으로 넣은 옛 배포본이다. 저장소 DSL의 환경변수 방식과 다르므로 키 회전 후 환경변수 기반으로 재게시해야 한다. 옛 `/api/admin/read-path-degraded`는 자산만 유지한다 | **있음 · 보안 드리프트** |
| Dify → EKS 권한 (인스턴스 역할 + RBAC) | 직접 권한 대신 S2 실행기 Lambda에 EKS Access Entry와 `deployments/scale` get·patch만 부여했다(`04-platform/action_executor_access.tf`) | **구현됨** |
| `cfg:*` 노브 저장·조회 | chat-gateway의 `cfg:channel_limit:*`, api의 `cfg:read_path_degraded:*`와 S3 목업 PG의 `cfg:pg:*` SET·DEL 및 테스트가 있다 | **구현됨** |
| 노브 카탈로그 (가역성·예산·precondition·검증 지표) | `seed_runbook.py`의 `KNOBS`, `runbook_lookup.py` 조회와 단위 테스트가 있다. 시간·예산 수치는 미측정이라 `None`. 형식과 live 대조는 `runbook-catalog.md` | **구현됨** |
| 게이트 진입 결정론적 판정 | 판정 입력인 노브 카탈로그 조회는 구현됐지만, 상태 머신/Dify가 이 값으로 분기하는 경로는 없다. 현재 Guardrail은 ACTION `risk_level`만 읽는다 | **설계만** |
| Runbook 위험도 척도 | ACTION의 L1/L2는 AUTO, L3는 APPROVAL로 라우팅되지만 등급 부여 기준은 없다. ACTION-KNOB 중복값도 일치 검사가 없다(D-079) | **없음** |
| 상태 머신 · 검증 대기 타이머 · 재분석 1회 분기 | 별도 서비스가 아니라 Dify 워크플로 안에 있다 — `dify/o2-aiops-workflow.yml`의 상태 dict(`diagnosis_retry`·`remediation_retry`·`excluded_actions`·`skip_diagnosis`), `stabilization` 노드, `GLOBAL_LOOP_MAX_10` 한도. 멱등 키는 Correlator 쪽 signal claim(`09-incident/incident_correlation.tf`)에 있다. **재진단 한도가 2회라 `scenario-experiment.md` 0.4의 "재분석 1회"와 어긋난다** | **고쳐야** |
| `Deduped` 병합 (Incident Correlator) | `infra/09-incident/terraform.tfvars` 에서 실행·event source 게이트 둘 다 `true`, `incident_shadow_mode=false`, 병합 window 420초와 Datadog monitor mapping(S1 셋 + READ_PATH)이 적용됐다. 채팅·Datadog 양방향 live E2E 도 한 인시던트로 병합돼 Dify 를 한 번만 깨웠다(`agent-entrypoint.md` `phase4c_live_source_to_dify_e2e`). 오병합률·복구 실측은 실제 인시던트 표본 뒤로 남았다 | **있음** |
| Datadog Monitor → Correlator 진입 라우팅 | S3 두 Monitor 실제 ID `22078625`·`22078627`을 `@webhook-o2-incident-entry`로 전환하고 map·allowlist에 등록했다. PG 지연은 `CORROBORATING`, 실패율은 `CONTEXT`이며 Chat `READ_PATH` PRIMARY와 같은 correlation tuple을 쓴다. 2026-08-28 대상 plan/apply는 Datadog `0 add / 2 change / 0 destroy`, Incident `0 add / 2 change / 0 destroy`였고, 적용 뒤 Lambda live 환경변수와 Incident 전체 no-change plan을 확인했다. 남은 것은 Chat→두 Monitor가 한 `incident_id`로 합쳐지는 live E2E다 | **있음 · E2E 미검증** |
| Slack 승인 왕복 | `infra/06-agent/slack_approval.tf` — Lambda 둘 + DynamoDB | **있음** |
| 런북 카탈로그 + 조회 | `runbook.tf` + `runbook_lookup.tf` (Lambda + Function URL, `x-api-key`) | **있음** |
| Runbook source-live 일치 | 2026-08-25 scan에서 source에 없는 구형 DEF 4개가 status 없이 남아 Lookup fallback상 active였다. live active ACTION에는 KNOB가 없다 | **고쳐야** |
| 인시던트 히스토리 (S3 + S3 Vectors) | `history.tf`, `history_o2.tf`. O2 전용 분리까지 완료 | **있음** |
| Agent 공통 진입점 | `agent_entry_transport.tf` SQS + Worker. 실행 게이트가 켜졌고 Invocation Queue consumer 도 동작한다(`agent-entrypoint.md` `implementation_state.agent_invocation_queue`·`production_agent_handoff`) | **있음** |
| 저장소 Dify DSL | 시연이 쓰는 워크플로는 `dify/o2-aiops-workflow.yml` 로 저장소에 있다(노드 153개, 최신 반영 9683e19). `alert-triage.yml` 3노드는 옛 자산이다. 남은 드리프트는 팀 운영 워크플로 쪽이고(`agent-entrypoint.md` `production_migration_blockers: DEPLOYED_TEAM_WORKFLOW_DSL_NOT_EXPORTED_TO_REPOSITORY`, T-022) 시연 경로의 blocker 는 아니다 | **있음** |

### 2.2 S1 — 채팅 총량 / 대가 게이트

| 요구 | 현재 | 판정 |
|---|---|---|
| 채널 총량 제한 노브 | `main.ts`의 `overChannelLimit()`과 `/ws/admin/channel-limit`, `cfg:channel_limit:*`이 구현되고 테스트됐다(D-061) | **구현됨** |
| 전파 지연 지표 (서버측) | `o2.chat.propagation` distribution 을 등록하고 S1 p95 Monitor(`[O2][S1] Chat 전파 p95 지연`, 22076983)를 운영 생성했다. `by {broadcast_id}` multi-alert 로 방송축까지 실린다(D-086). 다만 알림 문구가 옛 `@webhook-o2-dify` 라 Correlator 가 아니라 옛 직결 경로로 간다 — 아래 라우팅 행 참조 | **고쳐야** |
| 정상 사용자 차단률 | `o2.warm.channel_limited_rate` 를 S1 차단률 Monitor(`[O2][S1] Chat 정상 사용자 차단률`, 22076982)로 운영 생성했다. `incident_datadog_monitor_map` 에 CORROBORATING 으로 등록됐지만 알림 문구에 webhook 이 하나도 없어 Source Adapter 까지 갈 길이 없다 | **고쳐야** |
| 채팅 전파 계약 기준값 | 없다. `architecture.md` 12.1 의 `p95 < 800ms` 는 읽기 경로용이다 | **없음** |
| 넓은 발화자 분포 | `broadcast.js`의 `PROFILE=s1`은 `SENDERS`를 필수로 받고 발화자당 분당 한도 이상이면 시작 전에 실패한다 | **구현됨** |
| 파형 (첫 파동 → 지속 고원) | `SPIKE_RPS`·`SPIKE_S`·`PLATEAU_RPS`를 모두 필수 입력으로 받아 두 구간을 만든다 | **구현됨** |
| 인입 급증 알림 | S1 진입은 `scenario_alerts.tf` 의 `s1_chat_fanout_volume`(`[O2][S1] 채팅 팬아웃 총량`, 22078626, `last_1m`, `role:entry`)이다. 발화 수만 보던 옛 `chat_ingest_surge` 는 webhook 을 떼고 사람용 `[O2][보류]` 로 남겼다(D-088) | **있음** |

### 2.3 S2 — 느린 파드 / 자기 교정 게이트

| 요구 | 현재 | 판정 |
|---|---|---|
| canary Deployment (같은 Service, CPU 상한만 다름) | `loadtest/s2-canary.sh`가 클러스터의 현재 main Deployment를 원본으로 읽고 실측 CPU/probe 입력을 강제한다. 2026-08-25 로컬 Git base의 이미지 드리프트를 수정한 뒤 server-side dry-run과 200 RPS 실부하 재검증을 완료했다 | **구현·실측됨** |
| 정상 파드 복수 | `api-deployment.yaml`은 `replicas: 2`; main/canary는 서로 다른 Deployment selector와 `o2.cj.io/api-service-member` Service 멤버십을 쓴다 | **구현됨** |
| 파드별 지연 (`latency_by_pod`) | 2026-08-24 PR #133 으로 들어왔다 — warm 의 `o2warm/metrics.py:370` `latency_p95_by_pod`, `sketch.py` 의 `pod_name` 축 집계, `datadog.py` 가 `pod_name` 태그로 전송한다 | **있음** |
| 파드 단위 이상치 모니터 | `monitor.tf:465` `[O2][S2] 파드 단위 응답 지연 이상치 — 2차 재진단 재료` — `outliers(… latency_p95 … by {pod_name}, 'DBSCAN', …)`. 진입이 아니라 재진단 재료라 webhook 을 일부러 뺐다. 캐시 히트율 이상치(`monitor.tf:379`)와 별개다 | **있음** |
| 범용 런북 `RB-API-LATENCY-001` | `status=draft` 로 시딩되지만 S2 실험 게이트(`06-agent/terraform.tfvars` `s2_experiment_*`)가 켜져 있어 Lookup 이 `runbook_status=experiment` 로 반환한다. 복구 판정은 2026-08-27 에 `p99_ms <= 50` 축으로 옮겼다. **게이트에 만료 epoch 가 있어 지나면 조용히 draft 로 빠지고 1차 조치가 사라진다** — 실행 전에 만료를 확인한다 | **있음** |
| 후보 런북 분리·승격 게이트 | `RB-API-POD-RESOURCE-SKEW` 도 `status=draft` 이고 같은 실험 게이트로만 노출된다(`runbook_lookup.py` `S2_EXPERIMENT_RUNBOOKS`, D-077). DynamoDB status 는 안 바꾸므로 실험이 끝나면 승격 상태가 남지 않는다. 반복 재현·오적용·롤백 검증과 운영자 승인 뒤에만 active 로 올린다 | **있음** |
| 자원 요청 현실화 | `api-deployment.yaml:238` `cpu: 100m` (M-009 는 300 RPS 에서 664m). **지금은 올리지 않는다** — 3절 참조 | **보류** |
| replicas 동기화 예외 | `argocd.tf`에 api `/spec/replicas` ignore와 `RespectIgnoreDifferences=true`가 있다. 실험 종료 시 2로 명시 원복 | **구현됨** |
| api 에 HPA·KEDA 없을 것 | ScaledObject 는 `order-worker` 에만 붙어 있다 | **있음** |
| 진입 알림 본문 | 원인 해설을 뺐다. Monitor message 는 진단 프롬프트로 그대로 들어가므로 거기 쓴 설명이 Agent 에게는 정답이 된다 — 2026-08-27 실측에서 1차 진단부터 `pod_load_skew` 로 직행했다. 지금은 관측 사실 한 줄만 싣는다 | **고쳐짐** |
| 재조치·재진단 루프 | 라이브 `main_loop.loop_count` 가 **1** 이었다(git 기록본·노드 제목은 10). 상태 머신이 `stop_flag=false` 로 "재조치하라"를 내놔도 1회차에서 끝났다. 2026-08-27 에 10 으로 고쳐 재진단 라운드가 처음 열렸다. **라이브 값이 git 과 갈릴 수 있으므로 실행 전에 확인한다** | **고쳐짐** |
| 재진단이 `pod_load_skew` 로 정정 | 아직 안 된다. 1·2차 진단이 모두 `traffic_spike_overload`(confidence 둘 다 0.65)라 `ACTIONS_EXHAUSTED_SAME_RCA` 로 끝난다. 데이터는 두 프롬프트에 다 있다(canary 202.54ms 대 정상 5.35·6.15ms). 1차와 2차가 같은 입력을 받는 것이 원인 — 노드 7 을 회차별로 나눠야 한다(`measurements.md` 해당 절) | **고쳐야** |
| `pod_load_skew` 복구 판정 | `overall_failure_rate <= 0.01` 이 Warm 의 `null` 을 만나 구조적으로 통과 불가였다. 조건을 빼고 `p99_ms <= 50` 으로 바꿨다. 격리 전 미달 · 격리 후 통과로 갈린다 | **고쳐짐** |
| 실험 중 `cue-warmer` 정지 | 워머가 `api` 의 `spec.replicas` 를 10초마다 기준값으로 되돌려 Agent 조치를 3~5초 만에 무효화한다(T-043). 실행 절차에 정지·복구를 넣었다(`scenario-experiment.md` 4.3·4.5) | **고쳐짐 · 절차** |

### 2.4 S3 — 외부 결제 PG 장애 / 1차 실패 → 지식화 → 2차 해결

| 요구 | 현재 | 판정 |
|---|---|---|
| 채팅 파생 신호 → Candidate 생성 | `infra/08-chat-signal/lambda/runtime/processor.py`·`repository.py`. `CANDIDATE_CREATED` 가 구현됐고 `infra/08-chat-signal/terraform.tfvars` 에서 실행·DynamoDB Stream 게이트 둘 다 `true` 다 | **있음** |
| Candidate → Agent 호출 handoff | `chat_source_adapter_operational_handoff_approved=true` 이고 `agent-entrypoint.md` `implementation_state.production_agent_handoff=ENABLED` 다. 0절 표의 `agent_handoff_status=NOT_CONFIGURED` 는 2026-08-23 스냅숏이라 현재 상태가 아니다. 결제 불만 채팅은 `READ_PATH` surface 로 분류돼(`chat-incident-candidate.md` 4절) `incident_chat_surface_map` 에 매핑돼 있다 | **있음** |
| **목업 PG 스텁** | `apps/api/app/services/payment.py`가 주문 예약 뒤 `cfg:pg:*` 지연·결정론적 실패를 적용하고 `payment.process`를 발행한다. PG 실패 시 재고·멱등키를 보상한다(D-078). 아직 배포·실측 전 | **구현됨** |
| **`cfg:pg:*` 노브** | `/api/admin/pg-stub`이 별도 admin key로 `delay_ms`·`fail_rate`를 함께 SET·DEL한다. 단위 테스트가 있고 배포 Secret 값은 별도 주입 필요 | **구현됨** |
| S3 Datadog 후속 증거 Monitor | 실제 state ID `22078625`(PG p95)를 `CORROBORATING`, `22078627`(결제 실패율)을 `CONTEXT`로 map·allowlist에 넣고 둘 다 Incident webhook으로 보냈다. 기존 webhook payload가 `COMPOSITE_CONDITION` 고정이라 mapping도 그 계약을 재사용한다. 원인을 alert 본문에서 가르치지 않도록 관측 사실만 남겼다. validate·대상 plan은 통과했지만 live apply와 Chat→두 Monitor 병합 E2E는 아직이다 | **구현됨 · 미적용** |
| **주문 부하 스크립트** | S3 가 쓰는 것은 `loadtest/s3-payment.js` 다 — 결제 불만 채팅을 `CHAT_LEAD_SECONDS`(최소 17초) 먼저 흘리고 주문 부하를 얹는다. 실제 202 복구 응답 뒤 불만 확률은 기본 60초 동안 선형 감소한다. `CHAT_ONLY=true` 로 채팅만 돌려 Candidate 생성 최소 강도를 따로 잴 수 있다. 주문 축만 있는 `order-path.js` 는 그 하위 자산이다. 시나리오 식별 헤더는 없다(의도) | **구현됨** |
| Dify History 유무 분기 | Worker가 S3 Vectors 검색 결과 중 `verified=true`인 사례만 `past_cases`로 넘기고 DSL이 진단 프롬프트에 포함한다. History 없음/있음 자체를 별도 상태로 표시하는 DSL 분기는 아직 없다 | **부분 구현** |
| 1차 실행: active Runbook 없음 → 실패 보고 | 11-B가 `runbook_status`를 하류로 넘기고, 13-A가 `active`·`experiment`가 아니면 `MANUAL_REQUIRED` + `NO_ACTIVE_RUNBOOK`을 내 `ESCALATED`로 끝낸다. 런북이 있는데 후보만 소진된 경우만 종전대로 재진단한다. `dify/test_no_candidate_action.py`가 DSL 원본에서 코드를 꺼내 확인한다. **저장소 DSL 기준이고 실환경 반영은 3절 2번 드리프트 해소 뒤다** | **구현됨 · 미반영** |
| 사람 해결 사례 → verified History | 입력 경로는 `06-agent/scripts/verify.py` 다 — 미검증 인시던트를 하나씩 보여주고 `human_fixed` 와 `labels.txt` 의 원인을 사람이 확정해야 verified 가 된다. 없는 것은 **반복 시연용 격리** 뿐이다. 공유 append-only History 를 쓰면 1차 재촬영 때 verified 사례를 되돌려야 한다 | **부분 구현** |
| PG Failover Runbook 생명주기 | `pg_external_failure` draft는 PG-A→PG-B 우회 L3만 후보로 둔다. draft는 Lookup에서 제외되며, verified History·실측·원복·운영자 승인 증거가 있어야만 active 승격할 수 있다 | **부분 구현** |
| PG-B 상태·전환·원복 제어면 | `/api/admin/pg-provider-switch`가 PG-B ready 확인 후 PG-A→PG-B 전환하고, PG-A 주입 해제 뒤에만 원복한다. 전환·안전한 원복 재시도는 멱등 처리한다. 로컬 통합 테스트가 PG-A 주입 실패 → PG-B 성공 이벤트 → 주입 중 원복 차단 → 안전 원복을 검증한다. 배포·실측 전 | **구현됨** |
| PG-A→PG-B Action Handler | 새 실행기는 필요 없다 — `switch_pg_provider` 가 `L3` 로 등록돼 Slack 승인 경로를 타고, DSL 실행기 노드가 `$PG_PROVIDER_SWITCH_URL` 특수 타깃으로 api admin 라우트를 직접 부른다(auth 는 `READ_PATH_DEGRADED_ADMIN_KEY` 재사용). 저장소 DSL 의 그 환경변수 값이 빈 문자열이라 live 주입 전에는 mock 으로 떨어진다 | **구현됨 · 미주입** |
| `pg_latency_ratio` 집계 | `o2warm/sketch.py`·`metrics.py` 에 있다. `pg_latency_ms` 가 안 들어와서 지금은 표본이 0 | **있음** |
| `pg_external_failure` 복구 판정 | 런북 `success_criteria` 가 있으면 `recovery_judge` 가 그것을 먼저 쓴다 — `overall_failure_rate <= 0.05` 절대 조건과 기준선 대비 두 조건의 AND(장애 한복판을 기준선으로 잡아 통과하던 문제 때문에 절대 조건을 같이 뒀다). 옛 하드코딩 폴백(`p95<=400`·`error<=0.05`)은 런북이 없을 때만이다. 여전히 **PG-B 성공 이벤트와 채팅 불만 감소는 판정에 안 들어간다** — 그 둘은 사람이 확인한다 | **고쳐야** |
| 병합 키에서 `broadcast_id` 제외 | `incident_correlator.py:524` 의 `correlation_key` 는 `environment#incident_family#symptom_family#service#suspected_surface` 다 — 방송 축이 아예 없다. `broadcast_ids` 는 context 에만 실린다(D-086). S3 전용 분기가 필요 없다 | **있음** |
| ~~읽기 요청당 CPU 감소 노브~~ | `/api/admin/read-path-degraded`(D-062) — **S3 에서 빠졌지만 지우지 않는다**(D-076). 읽기 경로 보호로는 유효 | **있음 · 미사용** |
| ~~사람/자동화 두 패턴 부하~~ | `read-path.js` 의 `human`·`ambiguous` — **S3 에서 빠졌지만 지우지 않는다**(D-076) | **있음 · 미사용** |
| 부하 생성기에 표식 없을 것 | 커스텀 헤더 없음 (`scenario-experiment.md` 2.1) | **있음** |
| 채팅 본문 미저장 | `apps/chat-gateway/src/events.ts` — 길이·해시·중복만 싣는다 | **있음** |
| ~~감별 지표 (`ua_diversity`·`interval_cv`·집중도)~~ | `o2warm/metrics.py` — **S3 에서 빠졌지만 지우지 않는다**(D-076) | **있음 · 미사용** |

### 2.5 녹화 프로필

| 요구 | 현재 | 판정 |
|---|---|---|
| 데모용 `last_1m~2m` 모니터 (S1·S2) | `05-datadog/terraform.tfvars` 의 `scenario_entry_window_minutes` · `scenario_early_window_minutes` 가 둘 다 `1` 이라 S1·S2·S3 진입 Monitor 가 모두 `last_1m` 이다. **S3 까지 1분이라 4절의 "S3 는 `last_5m` 그대로" 와 어긋난다** — 채팅 선행 폭이 그만큼 줄어든다 | **고쳐야** |
| 승인 타임아웃 단축 프로필 | Dify HTTP 노드 600초 벽 그대로 | **없음** |
| 검증 대기 단축과 화면 표시 | 대기 자체는 있다(Action Handler 60초 안정화 계약 + `stabilization` 노드). 단축 프로필과 진행 상태를 화면에 보여주는 경로가 없다 | **없음** |

---

## 3. 변경해야 할 것

완료된 replicas·실패 필드·S1 발화자 분포는 2절로 이동했다. 현재 변경 대상만 남긴다.

1. **S3 Incident 라우팅 E2E** — Datadog·09-incident 적용과 live map 검증은 끝났다.
   `Chat PRIMARY → PG p95 CORROBORATING → 실패율 CONTEXT`가 같은 `incident_id`에
   쌓이는지 실제 2차 실행에서 확인한다. 테스트 전 Queue/DLQ 기존 건수를 기준선으로
   기록하고 새 증가분만 실패로 판정한다.
2. **S3 History 분기 명시** — 저장소 DSL 에 `History 없음 → 실패 보고` 는 들어왔다
   (13-A). `History 있음 → 현재 증거 재검증 → active Runbook` 을 별도 분기로 만드는
   것이 남았다. 지금은 `past_cases` 를 진단 프롬프트에 넣는 것까지다.
3. **S1 전파 p95 를 Agent 가 읽을 경로** — Datadog Monitor 는 서버측
   `o2.chat.propagation` 을 본다. 그런데 Agent 의 `Verifying` 은 warm 스냅샷을 읽고
   **warm 에는 propagation 집계가 없다** — DSL 이 참조하는 `chat_propagation_p95_ms`
   는 항상 `None` 이라 복구 판정이 영원히 미달이다. 차단률은
   `channel_block_rate` 로 이미 있다.
4. **자원 요청 현실화는 보류** — api `cpu: 100m`은 실제 사용량보다 작지만, 지금 올리면
   canary 실험 중 Karpenter 노드가 추가돼 조건이 흔들린다. 노드 여유가 한 파드분 이상
   늘거나 api HPA를 도입할 때 재개한다.
5. **S2 실험 게이트 만료 관리** — `s2_experiment_expires_at_epoch` 가 지나면 두 런북이
   조용히 draft 로 빠져 1차 조치가 사라진다. 실행 직전 만료를 확인하고, 지났으면 새
   실험 id 로 갱신한다.

## 4. 추가해야 할 것

1. **Correlator 오병합·복구 실측** — 설정은 끝났다(2.1). 남은 것은 표본이다.
   실제 인시던트가 쌓인 뒤 오병합률과 병합 후 복구 판정을 재
   `measurements.md` 에 남긴다(`agent-entrypoint.md` `operational_followups`).
2. **상태 머신 두 어긋남** — 구현은 Dify 워크플로 안에 있다(2.1). 남은 것은
   `scenario-experiment.md` 0.4 와의 차이 둘 — 재진단 한도가 2회이고,
   `Judging` 세 갈래가 `diagnostic_contamination` 조회로 갈리지 않는다.
   문서를 구현에 맞출지 구현을 문서에 맞출지 정한다.
3. **런북 생명주기와 S2 범용 런북** — 먼저 `RB-API-LATENCY-001`이
   `scenario-experiment.md` 0.2의 범용 런북 등록 기준을 충족하도록 진입·제외 조건,
   최대 변경량, 검증·중단·원복 기준, 소유자와 검증 증거를 만든다. S2 해결 뒤에는
   `pod_load_skew`를 실행 카탈로그에 바로 넣지 않고 별도 후보 영역에 `draft`로 저장한다.
   같은 원인 재현, 조치 효과, 오적용 부작용, 실패·롤백 검증과 운영자 승인을 통과한
   뒤에만 `active` 전용 런북으로 승격한다. 현재 `seed_runbook.py`와 실테이블의
   `pod_load_skew`는 `draft`로 분리돼 있다. 남은 문제는 `runbook-catalog.md`에 정리한
   status 없는 구형 active 항목과 위험도·KNOB 게이트 drift다.
4. **S3 Dify 비밀값 이관** — 목업 PG·전환 제어면은 배포됐고 게시 graph도 PG 전환을
   `REAL`로 호출한다. 그러나 옛 graph가 URL·admin key를 Code 노드에 평문으로 갖고 있다.
   노출된 키를 회전하고 저장소 DSL처럼 `PG_PROVIDER_SWITCH_URL`·admin key 환경변수를
   참조하도록 재게시한 뒤 `is_real=true`를 다시 확인한다.
5. **S3 주입 세기 확정** — `delay_ms` × 주문 RPS 를 스윕해 **주문은 깨지고 읽기는 사는**
   구간을 찾는다. 파드가 죽으면 `pod_resource_exhaustion` 오진이 된다. 확정값은 1차·2차에
   그대로 쓴다(7절).
6. **S3 지식화 경로** — 사람의 수동 해결 결과를 verified History로 남기고, 별도 검증
   증거를 통과한 Runbook만 active로 승격한다. 반복 시연은 공유 append-only History를
   지우지 않도록 격리 데이터셋·벡터 인덱스를 사용한다.
7. **효과 실측** — S1 강도별 차단률·p95, S2 CPU/probe 창과 최종 원복, S3 동일 주입에서
   PG-A 실패와 PG-B 우회 성공, 주문 실패율·p95·채팅 불만 감소를 `measurements.md`에 남긴다.
8. **데모 전용 모니터 창 결정** — 지금은 S1·S2·S3 가 모두 `last_1m` 이다. S3 만
    `last_5m` 로 되돌릴지 정한다. 되돌리면 채팅 선행 폭이 커져 시나리오 전제가
    선명해지고, 두면 녹화가 짧아진다. 어느 쪽이든 `terraform.tfvars` 한 값이다.

## 5. 뺄 것

1. ~~**시나리오 셋 밖 모니터의 `@webhook-o2-dify`**~~ — D-088 로 뗐다. 지금 남은 부착은
   셋 안의 셋뿐이다(전파 p95 · S2 꼬리 지연 · S3 결제 지연). 그 셋이 **옛 경로로 간다는
   문제**는 여기가 아니라 2.1 라우팅 행이 다룬다.
2. **ALB 액세스 로그** — 파드별 지연 후보에서 제외한다. S3 전달 지연이 커서 반복 실험·녹화와 상극이다.
3. **api 에 HPA·KEDA 부착** — 되돌리는 주체가 늘어난다(`scenario-experiment.md` 3절 "파드 수를 조치 수단으로 쓸 때").
4. **FIS · Chaos Mesh** — 주입 원칙 첫째(부하 아니면 설정, 둘 중 하나)가 이미 배제했다(`scenario-experiment.md` 2.1).
5. **`seed_runbook.py` 의 TODO 를 전부 채우는 것** — 현재 시나리오가 쓰는 S1, S2 범용,
   S2 후보, S3 결제 PG 항목만 관리한다. 나머지는 해당 시나리오가 확정될 때 만든다.
6. **좁은 발화자 프로필을 S1 주입에 쓰는 것** — M-010 재현용으로만 남긴다.
7. **Valkey 구독 Collector 를 운영 소스로 만드는 것** — D-047 이 이미 금지했다.

---

## 6. 실행 순서

| 순서 | 무엇 | 왜 |
|---|---|---|
| 0 | 배포 전 정적 검증 — 두 저장소 테스트·Terraform·Kustomize render | 실행 경로의 구조 오류를 먼저 제거한다 |
| 1 | Service 멤버십 라벨과 Argo replica 예외 배포 | S2 canary와 임시 증설의 전제다 |
| 2 | S3 PG-B 제어면·Failover 실행기와 지식화 경로 구현 | 1차 실패와 2차 성공을 가르는 핵심 전제다 |
| 3 | S2 canary CPU/probe 스윕과 범용 런북 검증 | 주입값·1차 실패·격리·최종 원복을 고정한다 |
| 4 | S1 파형·강도 스윕과 서버측 검증 지표 연결 | p95와 차단률을 Agent가 읽게 만든다 |
| 5 | Correlator 운영 설정 + 상태 머신 + Dify handoff·History 분기 | 세 시나리오를 실제 게이트 흐름으로 연결한다 |
| 6 | S3 동일 장애 1차·2차 E2E와 효과 실측 | 같은 주입에서 History·Runbook 유무만 결과를 바꾸는지 확인한다 |
| 7 | 녹화 프로필과 모니터 표시 이름 | 동작 검증이 끝난 뒤 시연 시간만 줄인다 |

**백업 계획** — 조치 실행기가 제때 안 되면 축소 시연으로 간다. Agent 가 조치 명령을 Slack 에
내고, 사람이 실행하고, Agent 가 검증한다. 주제가 human-in-the-loop 이라 이 축소가 오히려
주제에 가깝다.

---

## 7. 아직 안 잰 값

시나리오가 이미 참조하는 실측은 M-009(읽기 포화점), M-010(채팅 붕괴점),
M-016(파드 축 전제)이다. 아래는 전부 **안 쟀다.** 재면 `measurements.md`의 해당 절 표에 행을 추가하고,
여기는 그 `M-0NN` 을 가리키도록 바꾼다.

| 값 | 쓰이는 곳 |
|---|---|
| 검증 대기 시간 · 개선 판정 기준 · 승인 무응답 타임아웃 | 상태 머신 · 게이트 |
| 노브별 최대 영향 범위 · 최대 적용 시간 · 사전 승인 예산 · 쿨다운 | 노브 카탈로그 |
| ~~correlation window~~ | 420초로 확정·적용됐다(`09-incident/terraform.tfvars`). 남은 것은 오병합률 표본이다 |
| 채팅 전파 기준값 · 총량 제한 강도별 인입 감소량과 차단률 | S1 성공·실패 기준 |
| ~~CPU 상한 창~~ | 2026-08-26 스윕으로 `125m` 확정(`measurements.md` S2 canary CPU 상한 스윕). 15분 연속 부하에서는 재시작 3회라 **60초 부하에서만 성립**한다 |
| 증설 전후 서비스 p50·p95·p99 · 격리 후 복귀 폭 · 반복 재현율 | S2 1차·2차·최종 검증 |
| 결제 PG 주입 강도(`delay_ms` × 주문 RPS)와 읽기 경로 생존 구간 | S3 주입값 · 오진 방지 |
| PG-B 상태 확인·전환·원복 시간과 실패 조건 | S3 Failover Runbook·Guardrail 입력 |
| 동일 PG-A 주입에서 PG-A 실패율과 PG-B 성공 이벤트·주문 p95·채팅 불만 감소 | S3 1차 실패·2차 성공 Go/No-Go |
| 게이트별 사람 대기 시간과 Agent 순수 처리 시간 | MTTR 분해 |
| 서비스별 부하 시 실제 CPU·MEM | 자원 요청 현실화. api 만 M-009 에 있고 M-008 은 무부하값이다 |
