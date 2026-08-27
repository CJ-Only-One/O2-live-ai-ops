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
| 조치 실행기 (파드 수·노브 변경) | S2는 `action_executor.tf` + `scale_deployment.py`, S1은 `/ws/admin/channel-limit`로 구현됐다. S3도 배선은 끝났다 — 제어면(`/api/admin/pg-stub`·`/api/admin/pg-provider-switch`), 런북 L3 조치(`seed_runbook.py` `switch_pg_provider`), DSL 실행기 특수 타깃(`$PG_PROVIDER_SWITCH_URL`). 다만 저장소 DSL의 환경변수 값이 빈 문자열이라(`dify/o2-aiops-workflow.yml` `PG_PROVIDER_SWITCH_URL`) live 주입 전에는 `is_real=false` mock 경로로 떨어진다. 옛 `/api/admin/read-path-degraded`는 자산만 유지한다 | **고쳐야** |
| Dify → EKS 권한 (인스턴스 역할 + RBAC) | 직접 권한 대신 S2 실행기 Lambda에 EKS Access Entry와 `deployments/scale` get·patch만 부여했다(`04-platform/action_executor_access.tf`) | **구현됨** |
| `cfg:*` 노브 저장·조회 | chat-gateway의 `cfg:channel_limit:*`, api의 `cfg:read_path_degraded:*`와 S3 목업 PG의 `cfg:pg:*` SET·DEL 및 테스트가 있다 | **구현됨** |
| 노브 카탈로그 (가역성·예산·precondition·검증 지표) | `seed_runbook.py`의 `KNOBS`, `runbook_lookup.py` 조회와 단위 테스트가 있다. 시간·예산 수치는 미측정이라 `None`. 형식과 live 대조는 `runbook-catalog.md` | **구현됨** |
| 게이트 진입 결정론적 판정 | 판정 입력인 노브 카탈로그 조회는 구현됐지만, 상태 머신/Dify가 이 값으로 분기하는 경로는 없다. 현재 Guardrail은 ACTION `risk_level`만 읽는다 | **설계만** |
| Runbook 위험도 척도 | ACTION의 L1/L2는 AUTO, L3는 APPROVAL로 라우팅되지만 등급 부여 기준은 없다. ACTION-KNOB 중복값도 일치 검사가 없다(D-079) | **없음** |
| 상태 머신 · 검증 대기 타이머 · 재분석 1회 분기 | 별도 서비스가 아니라 Dify 워크플로 안에 있다 — `dify/o2-aiops-workflow.yml`의 상태 dict(`diagnosis_retry`·`remediation_retry`·`excluded_actions`·`skip_diagnosis`), `stabilization` 노드, `GLOBAL_LOOP_MAX_10` 한도. 멱등 키는 Correlator 쪽 signal claim(`09-incident/incident_correlation.tf`)에 있다. **재진단 한도가 2회라 `scenario-experiment.md` 0.4의 "재분석 1회"와 어긋난다** | **고쳐야** |
| `Deduped` 병합 (Incident Correlator) | `infra/09-incident/terraform.tfvars` 에서 실행·event source 게이트 둘 다 `true`, `incident_shadow_mode=false`, 병합 window 420초와 Datadog monitor mapping(S1 셋 + READ_PATH)이 적용됐다. 채팅·Datadog 양방향 live E2E 도 한 인시던트로 병합돼 Dify 를 한 번만 깨웠다(`agent-entrypoint.md` `phase4c_live_source_to_dify_e2e`). 오병합률·복구 실측은 실제 인시던트 표본 뒤로 남았다 | **있음** |
| Datadog Monitor → Correlator 진입 라우팅 | `scenario_alerts.tf` 헤더 규칙과 `incident_datadog_monitor_map` 은 새 경로(`@webhook-o2-incident-entry` → Datadog Source Adapter → Signal Queue → Correlator)를 전제한다. 그런데 **저장소 Terraform 의 어떤 Monitor 문구에도 그 handle 이 없다** — 등록된 다섯 중 셋(팬아웃 총량·차단률·결제 실패율)은 webhook 자체가 없고, 둘(전파 p95·S2 꼬리 지연)과 S3 진입은 옛 `@webhook-o2-dify` 다. live 에서는 M-020·phase4c 가 통과했으므로 콘솔 쪽 설정이 있을 가능성이 크고, 그렇다면 Terraform 드리프트다. 어느 쪽인지 live 확인이 먼저다 | **고쳐야** |
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

### 2.4 S3 — 외부 결제 PG 장애 / 1차 실패 → 지식화 → 2차 해결

| 요구 | 현재 | 판정 |
|---|---|---|
| 채팅 파생 신호 → Candidate 생성 | `infra/08-chat-signal/lambda/runtime/processor.py`·`repository.py`. `CANDIDATE_CREATED` 가 구현됐고 `infra/08-chat-signal/terraform.tfvars` 에서 실행·DynamoDB Stream 게이트 둘 다 `true` 다 | **있음** |
| Candidate → Agent 호출 handoff | `chat_source_adapter_operational_handoff_approved=true` 이고 `agent-entrypoint.md` `implementation_state.production_agent_handoff=ENABLED` 다. 0절 표의 `agent_handoff_status=NOT_CONFIGURED` 는 2026-08-23 스냅숏이라 현재 상태가 아니다. 결제 불만 채팅은 `READ_PATH` surface 로 분류돼(`chat-incident-candidate.md` 4절) `incident_chat_surface_map` 에 매핑돼 있다 | **있음** |
| **목업 PG 스텁** | `apps/api/app/services/payment.py`가 주문 예약 뒤 `cfg:pg:*` 지연·결정론적 실패를 적용하고 `payment.process`를 발행한다. PG 실패 시 재고·멱등키를 보상한다(D-078). 아직 배포·실측 전 | **구현됨** |
| **`cfg:pg:*` 노브** | `/api/admin/pg-stub`이 별도 admin key로 `delay_ms`·`fail_rate`를 함께 SET·DEL한다. 단위 테스트가 있고 배포 Secret 값은 별도 주입 필요 | **구현됨** |
| S3 Datadog 후속 증거 Monitor | `scenario_alerts.tf` 에 진입 `s3_pg_latency_p95`(`last_1m`, `@webhook-o2-dify`)와 증거 `s3_payment_failure_rate`(webhook 없음)가 있다. 그런데 **둘 다 `incident_datadog_monitor_map` 에 없다** — 등록이 없으면 Datadog Source Adapter 가 신호를 만들지 않으므로 0.7 Phase 1 의 "채팅 다음에 Datadog 증거가 병합된다" 가 성립하지 않는다 | **고쳐야** |
| **주문 부하 스크립트** | S3 가 쓰는 것은 `loadtest/s3-payment.js` 다 — 결제 불만 채팅을 `CHAT_LEAD_SECONDS`(최소 17초) 먼저 흘리고 주문 부하를 얹는다. `CHAT_ONLY=true` 로 채팅만 돌려 Candidate 생성 최소 강도를 따로 잴 수 있다. 주문 축만 있는 `order-path.js` 는 그 하위 자산이다. 시나리오 식별 헤더는 없다(의도) | **구현됨** |
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
| 데모용 `last_1m~2m` 모니터 (S1·S2) | 대부분 `min(last_5m)`. `last_2m` 는 채팅 인입 하나뿐 | **없음** |
| 승인 타임아웃 단축 프로필 | Dify HTTP 노드 600초 벽 그대로 | **없음** |
| 검증 대기 단축과 화면 표시 | 상태 머신 자체가 없다 | **없음** |

---

## 3. 변경해야 할 것

완료된 replicas·실패 필드·S1 발화자 분포는 2절로 이동했다. 현재 변경 대상만 남긴다.

1. **Datadog 모니터 이름의 시나리오 번호** — 지금 이름은 옛 번호(시나리오 1·2·4·5·6)이고
   현재 셋은 S1·S2·S3 다. 표시 이름만 정리하고 Terraform 리소스 이름은 건드리지 않는다.
2. **저장소 Dify DSL 드리프트** — 실환경 DSL 을 저장소로 내보낸다. T-022, production
   migration blocker 다. 그 위에서 S3의 `History 없음 → 실패 보고`와
   `History 있음 → 현재 증거 재검증 → active Runbook` 조건 분기를 명시적으로 추가한다.
3. **S1 서버측 검증 지표** — `chat_propagation_p95`는 아직 k6에만 있다. Agent가
   `Verifying`에서 읽을 수 있는 전달 경로와 정상 사용자 차단률 전용 scalar를 정한다.
4. **자원 요청 현실화는 보류** — api `cpu: 100m`은 실제 사용량보다 작지만, 지금 올리면
   canary 실험 중 Karpenter 노드가 추가돼 조건이 흔들린다. 노드 여유가 한 파드분 이상
   늘거나 api HPA를 도입할 때 재개한다.
5. **S3 draft Runbook 교체** — client pool·timeout/retry 후보는 최신 S3의 실행 절차가 아니다.
   자동 조회되지 않게 유지하고, 검증된 PG-A→PG-B Failover 절차로 대체한다.

## 4. 추가해야 할 것

1. **Incident Correlator 운영 설정** — D-055 계약·비활성 배포와 Phase 3C-A
   Signal Queue 직접 합성 E2E, Phase 4B 실제 Adapter 지연 source별 2회 측정까지 끝났다.
   반복 표본 기반 운영 window 확정과 Datadog monitor mapping은 남았다. `agent.trigger.v1` Signal Queue
   → Correlator → Incident State → `agent.incident.v1` Invocation Queue → Generic Worker.
   기존 `agent-trigger` Queue 는 이름만 바꾸려고 교체하지 않는다.
   **Worker mapping 분리를 확인하기 전에는 Correlator event source 를 켜지 않는다** —
   competing consumer 가 되면 입력을 임의로 나눠 가진다.
   S3 의 두 진입점 병합이 여기에 달려 있다.
2. **상태 머신** — `Baseline` 기록·실행 락·멱등 키(`incident:<id>:revision:<n>`) ·
   검증 대기 타이머 · 재분석 1회 분기 · `Judging` 세 갈래.
   정의는 `scenario-experiment.md` 0.4 에 이미 있다.
3. **런북 생명주기와 S2 범용 런북** — 먼저 `RB-API-LATENCY-001`이
   `scenario-experiment.md` 0.2의 범용 런북 등록 기준을 충족하도록 진입·제외 조건,
   최대 변경량, 검증·중단·원복 기준, 소유자와 검증 증거를 만든다. S2 해결 뒤에는
   `pod_load_skew`를 실행 카탈로그에 바로 넣지 않고 별도 후보 영역에 `draft`로 저장한다.
   같은 원인 재현, 조치 효과, 오적용 부작용, 실패·롤백 검증과 운영자 승인을 통과한
   뒤에만 `active` 전용 런북으로 승격한다. 현재 `seed_runbook.py`와 실테이블의
   `pod_load_skew`는 `draft`로 분리돼 있다. 남은 문제는 `runbook-catalog.md`에 정리한
   status 없는 구형 active 항목과 위험도·KNOB 게이트 drift다.
4. **Candidate → Agent handoff** — `agent_handoff_status` 를 실제로 연결한다. 실행 게이트
    둘(`chat_source_adapter_execution_enabled` · `chat_source_adapter_event_source_enabled`)은
    한 줄 실수를 막으려고 일부러 분리해둔 것이므로 순서대로 켠다.
5. **S3 PG-B 제어면과 실행기** — PG-B 상태 확인, PG-A→PG-B 전환, 원복, Provider별
   성공 이벤트, `L3` Action Handler를 추가한다. 전환 전 남은 PG-B 용량과 결제 가능
   상태를 결정론적으로 검사한다.
6. **S3 지식화 경로** — 사람의 수동 해결 결과를 verified History로 남기고, 별도 검증
   증거를 통과한 Runbook만 active로 승격한다. 반복 시연은 공유 append-only History를
   지우지 않도록 격리 데이터셋·벡터 인덱스를 사용한다.
7. **효과 실측** — S1 강도별 차단률·p95, S2 CPU/probe 창과 최종 원복, S3 동일 주입에서
   PG-A 실패와 PG-B 우회 성공, 주문 실패율·p95·채팅 불만 감소를 `measurements.md`에 남긴다.
8. **데모 전용 모니터** — S1·S2 용 `last_1m~2m`. **S3 는 `last_5m` 그대로 둔다** —
    그 지연 자체가 S3 의 주제다.

## 5. 뺄 것

1. **시나리오 셋 밖 모니터의 `@webhook-o2-dify`** — 지금 6개에 붙어 있고 그중 캐시·주문 큐는
   현재 셋에 없다. 부하가 같이 때리면 측정 중 Agent 가 깨어나 무언가 바꾼다.
   webhook 을 떼거나 Downtime 대상 목록에 명시한다(`scenario-experiment.md` 2.1 넷째 원칙).
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
| correlation window | Correlator 자동 병합 (D-055). Phase 3C 양방향 도착 지연 실측 후 확정 |
| 채팅 전파 기준값 · 총량 제한 강도별 인입 감소량과 차단률 | S1 성공·실패 기준 |
| CPU 상한 창 (Ready 는 유지, 요청은 느림) · canary p95 대 정상 파드 p95 중앙값의 비 | S2 주입 · Go/No-Go |
| 증설 전후 서비스 p50·p95·p99 · 격리 후 복귀 폭 · 반복 재현율 | S2 1차·2차·최종 검증 |
| 결제 PG 주입 강도(`delay_ms` × 주문 RPS)와 읽기 경로 생존 구간 | S3 주입값 · 오진 방지 |
| PG-B 상태 확인·전환·원복 시간과 실패 조건 | S3 Failover Runbook·Guardrail 입력 |
| 동일 PG-A 주입에서 PG-A 실패율과 PG-B 성공 이벤트·주문 p95·채팅 불만 감소 | S3 1차 실패·2차 성공 Go/No-Go |
| 게이트별 사람 대기 시간과 Agent 순수 처리 시간 | MTTR 분해 |
| 서비스별 부하 시 실제 CPU·MEM | 자원 요청 현실화. api 만 M-009 에 있고 M-008 은 무부하값이다 |
