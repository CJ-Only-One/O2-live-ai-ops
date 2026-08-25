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
| 조치 실행기 (파드 수·노브 변경) | S2는 `action_executor.tf` + `scale_deployment.py`, S1은 `/ws/admin/channel-limit`로 구현됐다. 옛 S3 `/api/admin/read-path-degraded`는 자산만 유지한다. 새 S3 결제 client pool·timeout/retry 실행기는 없다 | **고쳐야** |
| Dify → EKS 권한 (인스턴스 역할 + RBAC) | 직접 권한 대신 S2 실행기 Lambda에 EKS Access Entry와 `deployments/scale` get·patch만 부여했다(`04-platform/action_executor_access.tf`) | **구현됨** |
| `cfg:*` 노브 저장·조회 | chat-gateway의 `cfg:channel_limit:*`, api의 `cfg:read_path_degraded:*`와 S3 목업 PG의 `cfg:pg:*` SET·DEL 및 테스트가 있다 | **구현됨** |
| 노브 카탈로그 (가역성·예산·precondition·검증 지표) | `seed_runbook.py`의 `KNOBS`, `runbook_lookup.py` 조회와 단위 테스트가 있다. 시간·예산 수치는 미측정이라 `None`. 형식과 live 대조는 `runbook-catalog.md` | **구현됨** |
| 게이트 진입 결정론적 판정 | 판정 입력인 노브 카탈로그 조회는 구현됐지만, 상태 머신/Dify가 이 값으로 분기하는 경로는 없다. 현재 Guardrail은 ACTION `risk_level`만 읽는다 | **설계만** |
| Runbook 위험도 척도 | ACTION의 L1/L2는 AUTO, L3는 APPROVAL로 라우팅되지만 등급 부여 기준은 없다. ACTION-KNOB 중복값도 일치 검사가 없다(D-079) | **없음** |
| 상태 머신 · 검증 대기 타이머 · 재분석 1회 분기 | 없음. 정의는 `scenario-experiment.md` 0.4 에 있다 | **없음** |
| `Deduped` 병합 (Incident Correlator) | Signal Queue 직접 합성 E2E에서 양방향 모두 같은 Incident revision 2로 병합. 실제 Adapter 지연도 source별 2회 측정했지만 운영 window·Datadog monitor mapping은 미설정이고 실행 gate는 다시 껐다 | **비활성** |
| Slack 승인 왕복 | `infra/06-agent/slack_approval.tf` — Lambda 둘 + DynamoDB | **있음** |
| 런북 카탈로그 + 조회 | `runbook.tf` + `runbook_lookup.tf` (Lambda + Function URL, `x-api-key`) | **있음** |
| Runbook source-live 일치 | 2026-08-25 scan에서 source에 없는 구형 DEF 4개가 status 없이 남아 Lookup fallback상 active였다. live active ACTION에는 KNOB가 없다 | **고쳐야** |
| 인시던트 히스토리 (S3 + S3 Vectors) | `history.tf`, `history_o2.tf`. O2 전용 분리까지 완료 | **있음** |
| Agent 공통 진입점 | `agent_entry_transport.tf` SQS + Worker. 실행 게이트 둘 다 기본 `false` | **비활성** |
| 저장소 Dify DSL | `infra/06-agent/dify/alert-triage.yml` 은 시작→LLM→출력 3노드. 실환경과 드리프트(T-022) | **고쳐야** |

### 2.2 S1 — 채팅 총량 / 대가 게이트

| 요구 | 현재 | 판정 |
|---|---|---|
| 채널 총량 제한 노브 | `main.ts`의 `overChannelLimit()`과 `/ws/admin/channel-limit`, `cfg:channel_limit:*`이 구현되고 테스트됐다(D-061) | **구현됨** |
| 전파 지연 지표 (서버측) | M-010 의 전파 p95 는 **k6 클라이언트 Trend** 다. `chat.send` 페이로드에 `latency_ms` 가 없어 warm path 가 지연을 만들지 못한다 | **없음** |
| 정상 사용자 차단률 | `chat.send` 전체 시도 대비 `CHANNEL_LIMITED`를 계산한 `channel_limited_rate` scalar를 warm이 Datadog으로 보낸다. 상한 실측은 남음 | **구현됨** |
| 채팅 전파 계약 기준값 | 없다. `architecture.md` 12.1 의 `p95 < 800ms` 는 읽기 경로용이다 | **없음** |
| 넓은 발화자 분포 | `broadcast.js`의 `PROFILE=s1`은 `SENDERS`를 필수로 받고 발화자당 분당 한도 이상이면 시작 전에 실패한다 | **구현됨** |
| 파형 (첫 파동 → 지속 고원) | `SPIKE_RPS`·`SPIKE_S`·`PLATEAU_RPS`를 모두 필수 입력으로 받아 두 구간을 만든다 | **구현됨** |
| 인입 급증 알림 | `infra/05-datadog/monitor.tf:73` `rps_ratio{service:chat-gateway}`, `min(last_2m)` | **있음** |

### 2.3 S2 — 느린 파드 / 자기 교정 게이트

| 요구 | 현재 | 판정 |
|---|---|---|
| canary Deployment (같은 Service, CPU 상한만 다름) | `O2-live-deploy/experiments/s2-api-canary`가 main을 base로 렌더링하고 `loadtest/s2-canary.sh`가 실측 CPU/probe 입력을 강제한다. 자동 배포는 안 됨 | **구현됨** |
| 정상 파드 복수 | `api-deployment.yaml`은 `replicas: 2`; main/canary는 서로 다른 Deployment selector와 `o2.cj.io/api-service-member` Service 멤버십을 쓴다 | **구현됨** |
| 파드별 지연 (`latency_by_pod`) | 2026-08-24 PR #133 으로 들어왔다 — `o2warm/sketch.py:514·609`, `metrics.py:328` `latency_p95_by_pod`, `datadog.py:131` 이 `pod_name` 태그로 전송한다 | **있음** |
| 파드 단위 이상치 모니터 | `monitor.tf:420` `[O2][시나리오 5] 파드 단위 응답 지연 이상치` — `outliers(… latency_p95 … by {pod_name}, 'DBSCAN', …)`. 캐시 히트율 이상치(`monitor.tf:331`)와 별개로 붙었다 | **있음** |
| 범용 런북 `RB-API-LATENCY-001` | `seed_runbook.py`에 한 단계 증설·검증·원복 조건과 `status=draft`로 시딩된다. Lookup은 draft를 반환하지 않는다. 반복 재현·원복·승인 증거가 남음 | **비활성** |
| 후보 런북 분리·승격 게이트 | `RB-API-POD-RESOURCE-SKEW`가 `status=draft`로 시딩되고 Lookup이 자동 조회에서 제외한다(D-077). 재현·오적용·롤백 검증과 운영자 승인 뒤에만 active로 바꾼다 | **비활성** |
| 자원 요청 현실화 | `api-deployment.yaml:160` `cpu: 100m` (M-009 는 300 RPS 에서 664m). **지금은 올리지 않는다** — 3절 1 참조 | **보류** |
| replicas 동기화 예외 | `argocd.tf`에 api `/spec/replicas` ignore와 `RespectIgnoreDifferences=true`가 있다. 실험 종료 시 2로 명시 원복 | **구현됨** |
| api 에 HPA·KEDA 없을 것 | ScaledObject 는 `order-worker` 에만 붙어 있다 | **있음** |

### 2.4 S3 — 외부 결제 PG 장애 / 소진 → 실패 보고

| 요구 | 현재 | 판정 |
|---|---|---|
| 채팅 파생 신호 → Candidate 생성 | `infra/08-chat-signal/lambda/runtime/processor.py`·`repository.py`. `CANDIDATE_CREATED` 구현됨. 실행 게이트는 꺼져 있다 | **비활성** |
| Candidate → Agent 호출 handoff | `agent-entrypoint.md` 0절 `agent_handoff_status=NOT_CONFIGURED` | **없음** |
| **목업 PG 스텁** | `apps/api/app/services/payment.py`가 주문 예약 뒤 `cfg:pg:*` 지연·결정론적 실패를 적용하고 `payment.process`를 발행한다. PG 실패 시 재고·멱등키를 보상한다(D-078). 아직 배포·실측 전 | **구현됨** |
| **`cfg:pg:*` 노브** | `/api/admin/pg-stub`이 별도 admin key로 `delay_ms`·`fail_rate`를 함께 SET·DEL한다. 단위 테스트가 있고 배포 Secret 값은 별도 주입 필요 | **구현됨** |
| **주문 부하 스크립트** | `loadtest/order-path.js`가 고정 도착률 주문을 만들며 RATE·DURATION·VU 수를 필수 입력으로 받는다. 시나리오 식별 헤더는 없다 | **구현됨** |
| `pg_external_failure` 런북 (조치 **둘 이상**) | 결제 client pool 확대와 timeout/retry 조정 두 액션을 `status=draft`로 시딩한다. 옛 PostgreSQL 의미의 네 액션은 삭제하지 않고 retired 처리한다. 실제 Action Handler는 없음 | **설계만** |
| `pg_latency_ratio` 집계 | `o2warm/sketch.py`·`metrics.py` 에 있다. `pg_latency_ms` 가 안 들어와서 지금은 표본이 0 | **있음** |
| `pg_external_failure` 복구 판정 | `recovery_judge` 폴백에 `p95<=400`·`error<=0.05` 가 이미 있다 | **있음** |
| 병합 키에서 `broadcast_id` 제외 | Correlator 가 source·service 로 묶는다. **S3 만 방송 축을 빼는 분기가 없다**(D-076) | **고쳐야** |
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
   migration blocker 다.
3. **S1 서버측 검증 지표** — `chat_propagation_p95`는 아직 k6에만 있다. Agent가
   `Verifying`에서 읽을 수 있는 전달 경로와 정상 사용자 차단률 전용 scalar를 정한다.
4. **자원 요청 현실화는 보류** — api `cpu: 100m`은 실제 사용량보다 작지만, 지금 올리면
   canary 실험 중 Karpenter 노드가 추가돼 조건이 흔들린다. 노드 여유가 한 파드분 이상
   늘거나 api HPA를 도입할 때 재개한다.

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
5. **효과 실측** — S1 강도별 차단률·p95, S2 CPU/probe 창과 최종 원복, S3 결제
   client pool·timeout/retry 조치의 미복구와 원복 결과를 `measurements.md`에 남긴다.
6. **데모 전용 모니터** — S1·S2 용 `last_1m~2m`. **S3 는 `last_5m` 그대로 둔다** —
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
| 2 | S3 효과 실측 | 상태 머신 없이도 조치 효과와 원복을 먼저 확인할 수 있다 |
| 3 | S2 canary CPU/probe 스윕과 범용 런북 검증 | 주입값·1차 실패·격리·최종 원복을 고정한다 |
| 4 | S1 파형·강도 스윕과 서버측 검증 지표 연결 | p95와 차단률을 Agent가 읽게 만든다 |
| 5 | Correlator 운영 설정 + 상태 머신 + Dify handoff | 세 시나리오를 실제 게이트 흐름으로 연결한다 |
| 6 | 녹화 프로필과 모니터 표시 이름 | 동작 검증이 끝난 뒤 시연 시간만 줄인다 |

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
| 결제 client pool·timeout/retry 조치 전후와 원복 결과 | S3 후보 소진·실패 보고 Go/No-Go |
| 게이트별 사람 대기 시간과 Agent 순수 처리 시간 | MTTR 분해 |
| 서비스별 부하 시 실제 CPU·MEM | 자원 요청 현실화. api 만 M-009 에 있고 M-008 은 무부하값이다 |
