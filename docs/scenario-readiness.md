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
| 조치 실행기 (파드 수·노브 변경) | 조치별로 셋이 붙었다 — S2 격리·원복은 `infra/06-agent/action_executor.tf` + `lambda/scale_deployment.py`(Deployment replicas patch, D-059), S1 채널 노브는 chat-gateway 라우트(`main.ts:147`), S3 읽기 노브는 `apps/api/app/api/routes/admin.py`. `hot-proxy` 는 조회 전용 그대로다 | **있음** |
| Dify → EKS 권한 (인스턴스 역할 + RBAC) | `infra/04-platform/action_executor_access.tf` — EKS Access Entry 로 `o2-dev` 의 `deployments/scale` 에 `get`·`patch` 만 (D-059) | **있음** |
| `cfg:*` 노브 저장·조회 | 둘이 있다 — `cfg:channel_limit:{broadcastId}`(chat-gateway `main.ts:122`), `cfg:read_path_degraded:{broadcast_id}`(api `routes/admin.py`). 둘 다 Valkey 원본이라 파드 로컬이 아니다 | **있음** |
| 노브 카탈로그 (가역성·예산·precondition·검증 지표) | `infra/06-agent/runbook.tf` 는 `rca_type` 축의 런북 스키마다. 노브 카탈로그는 별개 축 | **없음** |
| 게이트 진입 결정론적 판정 | LLM 자유 서술. 테이크마다 달라진다 | **없음** |
| 상태 머신 · 검증 대기 타이머 · 재분석 1회 분기 | 없음. 정의는 `scenario-experiment.md` 0.4 에 있다 | **없음** |
| `Deduped` 병합 (Incident Correlator) | Signal Queue 직접 합성 E2E에서 양방향 모두 같은 Incident revision 2로 병합. 실제 Adapter 지연도 source별 2회 측정했지만 운영 window·Datadog monitor mapping은 미설정이고 실행 gate는 다시 껐다 | **비활성** |
| Slack 승인 왕복 | `infra/06-agent/slack_approval.tf` — Lambda 둘 + DynamoDB | **있음** |
| 런북 카탈로그 + 조회 | `runbook.tf` + `runbook_lookup.tf` (Lambda + Function URL, `x-api-key`) | **있음** |
| 인시던트 히스토리 (S3 + S3 Vectors) | `history.tf`, `history_o2.tf`. O2 전용 분리까지 완료 | **있음** |
| Agent 공통 진입점 | `agent_entry_transport.tf` SQS + Worker. 실행 게이트 둘 다 기본 `false` | **비활성** |
| 저장소 Dify DSL | `infra/06-agent/dify/alert-triage.yml` 은 시작→LLM→출력 3노드. 실환경과 드리프트(T-022) | **고쳐야** |

### 2.2 S1 — 채팅 총량 / 대가 게이트

| 요구 | 현재 | 판정 |
|---|---|---|
| 채널 총량 제한 노브 | `main.ts:120` `overChannelLimit()` — `cfg:channel_limit:{broadcastId}` 를 읽고 `chat:total:{broadcastId}` 를 Valkey `INCR`+`EXPIRE` 로 센다. **파드 로컬이 아니라 2 replicas 에서도 상한이 배가되지 않는다.** 사용자별 `overRateLimit()` 은 보조로 남는다 | **있음** |
| 전파 지연 지표 (서버측) | M-010 의 전파 p95 는 **k6 클라이언트 Trend** 다. `chat.send` 페이로드에 `latency_ms` 가 없어 warm path 가 지연을 만들지 못한다 | **없음** |
| 정상 사용자 차단률 | D-060 으로 고쳤다 — `chat-ingress.ts` 가 `result` 를 항상 싣고 거부 셋(`TOO_LONG`·`RATE_LIMITED`·`CHANNEL_LIMITED`)에 `failure_code` 를 붙인다. warm 은 한 줄도 안 고쳤고 `failure_rate{event:chat.send}` 가 그대로 나온다 | **있음** |
| 채팅 전파 계약 기준값 | 없다. `architecture.md` 12.1 의 `p95 < 800ms` 는 읽기 경로용이다 | **없음** |
| 넓은 발화자 분포 | `loadtest/broadcast.js:72` `SENDERS = CHAT_RPS × 6`. 발화자가 좁아 **1인 도배로 보인다** — S1 전제(전원이 한도 안인데 총량이 넘음)와 반대다 | **고쳐야** |
| 파형 (첫 파동 → 지속 고원) | 고정 발화율뿐 | **없음** |
| 인입 급증 알림 | `infra/05-datadog/monitor.tf:73` `rps_ratio{service:chat-gateway}`, `min(last_2m)` | **있음** |

### 2.3 S2 — 느린 파드 / 자기 교정 게이트

| 요구 | 현재 | 판정 |
|---|---|---|
| canary Deployment (같은 Service 셀렉터, CPU 상한만 다름) | `O2-live-deploy` 에 매니페스트가 없다 | **없음** |
| 정상 파드 복수 | `O2-live-deploy/api-deployment.yaml:15` **`replicas: 2`**. `maxSurge: 0` 블록도 같이 지웠다(기본값 25% 복귀). 기존 `topologySpreadConstraints` 의 `DoNotSchedule` 이 두 파드를 다른 노드로 가른다. **자원 요청은 안 올렸다** — 아래 행 | **있음** |
| 파드별 지연 (`latency_by_pod`) | 2026-08-24 PR #133 으로 들어왔다 — `o2warm/sketch.py:514·609`, `metrics.py:328` `latency_p95_by_pod`, `datadog.py:131` 이 `pod_name` 태그로 전송한다 | **있음** |
| 파드 단위 이상치 모니터 | `monitor.tf:420` `[O2][시나리오 5] 파드 단위 응답 지연 이상치` — `outliers(… latency_p95 … by {pod_name}, 'DBSCAN', …)`. 캐시 히트율 이상치(`monitor.tf:331`)와 별개로 붙었다 | **있음** |
| 범용 런북 `RB-API-LATENCY-001` | 증상·진입 임계값·최대 변경량·실패/중단·원복·소유자 기준은 `scenario-experiment.md` 0.2에 정의했다. 그러나 `seed_runbook.py` 에 이 항목과 검증 증거는 없다 | **없음** |
| 후보 런북 분리·승격 게이트 | `seed_runbook.py` 의 `pod_load_skew` 가 상태 구분 없이 실행 카탈로그 `RUNBOOKS` 에 들어가 있다. `draft/active` 상태, 후보 전용 저장 영역, 재현·안전성·롤백 검증, 운영자 승인 게이트가 없다 | **고쳐야** |
| 자원 요청 현실화 | `api-deployment.yaml:160` `cpu: 100m` (M-009 는 300 RPS 에서 664m). **지금은 올리지 않는다** — 3절 1 참조 | **보류** |
| replicas 동기화 예외 | Argo CD `ignoreDifferences` 가 없다 | **없음** |
| api 에 HPA·KEDA 없을 것 | ScaledObject 는 `order-worker` 에만 붙어 있다 | **있음** |

### 2.4 S3 — 사람/봇 미확정 / 정보 게이트

| 요구 | 현재 | 판정 |
|---|---|---|
| 채팅 파생 신호 → Candidate 생성 | `infra/08-chat-signal/lambda/runtime/processor.py`·`repository.py`. `CANDIDATE_CREATED` 구현됨. 실행 게이트는 꺼져 있다 | **비활성** |
| Candidate → Agent 호출 handoff | Correlator·Invocation Queue·Phase 3D Worker 까지 배포됐고 shadow E2E 는 PASS 다. **실행 게이트는 전부 꺼져 있다** — `incident_correlator: DEPLOYED_EXECUTION_DISABLED`, `agent_invocation_queue: DEPLOYED_DISABLED_CONSUMER` | **비활성** |
| 읽기 요청당 CPU 감소 노브 | `apps/api/app/api/routes/admin.py` 가 `cfg:read_path_degraded:{broadcast_id}` 를 SET(조치)·DEL(원복) 한다. **포화점을 미는 폭은 아직 안 쟀다**(7절) | **있음** |
| 사람/자동화 두 패턴 부하 | `loadtest/read-path.js` 의 `__ENV` 는 `BASE_URL`·`BROADCAST_ID`·`RATE`·`DURATION` 넷뿐. 세션 키·UA·지터·클릭 이벤트 분기가 없다 | **없음** |
| 부하 생성기에 표식 없을 것 | 커스텀 헤더 없음 (`scenario-experiment.md` 2.1) | **있음** |
| 채팅 본문 미저장 | `apps/chat-gateway/src/events.ts` — 길이·해시·중복만 싣는다 | **있음** |
| 감별 지표 (`ua_diversity`·`interval_cv`·집중도) | `o2warm/metrics.py` 에 있다 | **있음** |

### 2.5 녹화 프로필

| 요구 | 현재 | 판정 |
|---|---|---|
| 데모용 `last_1m~2m` 모니터 (S1·S2) | 대부분 `min(last_5m)`. `last_2m` 는 채팅 인입 하나뿐 | **없음** |
| 승인 타임아웃 단축 프로필 | Dify HTTP 노드 600초 벽 그대로 | **없음** |
| 검증 대기 단축과 화면 표시 | 상태 머신 자체가 없다 | **없음** |

---

## 3. 변경해야 할 것

1. **`loadtest/broadcast.js` 발화자 분포** — `SENDERS` 를 환경변수로 분리하고, 발화자를 크게
   늘려 1인당 발화율이 `CHAT_RATE_PER_MIN` 아래가 되게 배치한다. M-010 재현 조건은
   비교 가능성을 위해 그대로 남긴다.
2. **Datadog 모니터 이름의 시나리오 번호** — 지금 이름은 옛 번호(시나리오 1·2·4·5·6)이고
   현재 셋은 S1·S2·S3 다. 표시 이름만 정리하고 Terraform 리소스 이름은 건드리지 않는다.
3. **저장소 Dify DSL 드리프트** — 실환경 DSL 을 저장소로 내보낸다. T-022, production
   migration blocker 다.

### 보류 — api 자원 요청 상향

`api-deployment.yaml` 의 `cpu: 100m` 은 M-009 실측(300 RPS 에서 664m)의 1/6 이지만
**지금 올리지 않는다.** 올려야 할 이유였던 "HPA 를 붙이기 전에" 가 이 시나리오에서는
성립하지 않는다 — api 에 HPA 를 붙이지 않기로 이미 정했다(5절 3).

반대로 500m 으로 올리면 자리가 없어진다. 2026-08-24 실측으로 노드 여유가
730m·550m(c6i.large 2대, 1,930m 중)이라 api 2파드 × 500m = 1,000m 을 넣으면
canary 를 얹을 때 Karpenter 가 노드를 새로 띄운다. 실험 중 노드가 늘면 타이밍이
매번 달라진다(D-051).

**재개 조건** — api 에 HPA 를 붙이기로 하거나, 노드 여유가 1파드분 이상 늘어나면 그때 올린다.

## 4. 추가해야 할 것

조치 실행기와 노브가 들어오면서 "조치 직전에서 멈춘다" 는 상태는 지났다.
남은 크리티컬 패스는 **게이트 진입 판정과 상태 머신**이다.

1. **노브 카탈로그** — 가역성 두 축 · `preapproved_budget` · `preconditions` ·
   `verification_metrics` · `diagnostic_contamination` · `rollback_method` 등.
   **게이트 진입을 LLM 이 아니라 이 조회로 판정한다** — 녹화 성공률을 가장 크게 올리는 항목이다.
   `runbook.tf` 의 DynamoDB 패턴을 그대로 재사용한다. 노브 셋(채널 총량 · 읽기 저하 ·
   Deployment replicas)은 이미 실행 가능하므로 **남은 것은 그 셋을 서술하는 메타데이터**다.
2. **상태 머신** — `Baseline` 기록·실행 락·멱등 키(`incident:<id>:revision:<n>`) ·
   검증 대기 타이머 · 재분석 1회 분기 · `Judging` 세 갈래.
   정의는 `scenario-experiment.md` 0.4 에 이미 있다.
3. **Correlator·Worker 실행 게이트 활성화** — 배포와 shadow E2E 는 끝났다(2.1·2.4).
   남은 것은 반복 표본 기반 correlation window 확정, Datadog monitor mapping,
   그리고 게이트를 켜는 것이다.
   **Worker mapping 분리를 확인하기 전에는 Correlator event source 를 켜지 않는다** —
   competing consumer 가 되면 입력을 임의로 나눠 가진다.
4. **canary Deployment 매니페스트** (`O2-live-deploy`) — main 과 같은 이미지·같은 Service
   셀렉터, **CPU 상한만** 낮게. `readinessProbe` 의 `timeoutSeconds`·`failureThreshold` 는
   **canary 에만** 올린다. 안 그러면 파드가 Service 에서 빠져 저절로 회복되거나 들락날락한다.
5. **런북 생명주기와 S2 런북** — 먼저 `RB-API-LATENCY-001`이
   `scenario-experiment.md` 0.2의 범용 런북 등록 기준을 충족하도록 진입·제외 조건,
   최대 변경량, 검증·중단·원복 기준, 소유자와 검증 증거를 만든다. S2 해결 뒤에는
   `pod_load_skew`를 실행 카탈로그에 바로 넣지 않고 별도 후보 영역에 `draft`로 저장한다.
   같은 원인 재현, 조치 효과, 오적용 부작용, 실패·롤백 검증과 운영자 승인을 통과한
   뒤에만 `active` 전용 런북으로 승격한다. 현재 `seed_runbook.py`의 `pod_load_skew`는
   이 상태와 게이트 없이 활성 카탈로그 모양으로 들어가 있으므로 승격 전 분리해야 한다.
6. **Argo CD replicas 동기화 예외** — 대상 Deployment 의 `replicas` 를 `ignoreDifferences` 로.
   지금 없어서 조치 후 GitOps 가 되돌린다. **replicas 2 가 들어갔으므로 이제 실제로 물린다** —
   격리 조치가 replicas 를 건드리는 순간 Argo 가 되돌린다.
   두 방법 중 왜 `ignoreDifferences` 인지는 `scenario-experiment.md` 3절 "파드 수를 조치
   수단으로 쓸 때" 에 있다 — api 는 정상 파드 수가 기준값이라 git 에 남아야 하므로
   `order-worker` 처럼 필드를 빼는 방식을 쓸 수 없다.
7. **`read-path.js` 두 패턴 분기** — 요청마다 새 세션 키 · 클릭 이벤트 동반 발행 ·
   간격 지터 · UA 혼합. **커스텀 헤더는 넣지 않는다** — Agent 입장에서 정답 라벨이 된다.
8. **`broadcast.js` 파형** — 첫 파동(스파이크) → 지속 고원. 이게 있어야 "첫 파동은
   반응형 조치로 못 막는다" 와 "조치는 고원을 낮춘다" 가 분리되어 보인다.
9. **데모 전용 모니터** — S1·S2 용 `last_1m~2m`. **S3 는 `last_5m` 그대로 둔다** —
   그 지연 자체가 S3 의 주제다.
10. **채팅 전파 지연 지표** — 봉투에 실을지 별도 커스텀 메트릭으로 낼지 결정이 필요하다.
    지금은 k6 안에만 있어 Agent 가 검증에 쓸 수 없다.

## 5. 뺄 것

1. **시나리오 셋 밖 모니터의 `@webhook-o2-dify`** — 지금 6개에 붙어 있고 그중 캐시·주문 큐는
   현재 셋에 없다. 부하가 같이 때리면 측정 중 Agent 가 깨어나 무언가 바꾼다.
   webhook 을 떼거나 Downtime 대상 목록에 명시한다(`scenario-experiment.md` 2.1 넷째 원칙).
2. **ALB 액세스 로그** — 파드별 지연 후보에서 제외한다. S3 전달 지연이 커서 반복 실험·녹화와 상극이다.
3. **api 에 HPA·KEDA 부착** — 되돌리는 주체가 늘어난다(`scenario-experiment.md` 3절 "파드 수를 조치 수단으로 쓸 때").
4. **FIS · Chaos Mesh** — 주입 원칙 첫째(부하 아니면 설정, 둘 중 하나)가 이미 배제했다(`scenario-experiment.md` 2.1).
5. **`seed_runbook.py` 의 TODO 를 전부 채우는 것** — 지금 필요한 것은 범용 지연 런북과
   `pod_load_skew` 둘뿐이다. 나머지는 만들지 않는다.
6. **좁은 발화자 프로필을 S1 주입에 쓰는 것** — M-010 재현용으로만 남긴다.
7. **Valkey 구독 Collector 를 운영 소스로 만드는 것** — D-047 이 이미 금지했다.

---

## 6. 실행 순서

| 순서 | 무엇 | 왜 |
|---|---|---|
| 1 | 4절 1·2 (노브 카탈로그 · 상태 머신) | 남은 단일 크리티컬 패스. 게이트 진입이 LLM 자유 서술이면 테이크마다 달라진다 |
| 2 | 4절 3 (Correlator·Worker 게이트 활성화) | 배포는 끝났고 켜는 일만 남았다. S3 두 진입점 병합이 여기 달렸다 |
| 3 | S2 — 4절 4·5·6 | 관측 축도 조치 실행기도 끝났다. 남은 것은 canary · 런북 · Argo 예외 |
| 4 | S3 — 4절 7 + 7절의 읽기 노브 실측 | 노브는 있고 **효과를 아직 안 쟀다** |
| 5 | S1 — 4절 8·10, 3절 1 | 노브는 있고 부하 프로필과 전파 지표가 남았다 |
| 6 | 녹화 프로필 — 4절 9, 3절 2·3 | 시연 직전 |

**백업 계획** — 상태 머신이 제때 안 되면 축소 시연으로 간다. Agent 가 조치 명령을 Slack 에
내고, 사람이 실행하고, Agent 가 검증한다. 주제가 human-in-the-loop 이라 이 축소가 오히려
주제에 가깝다. 조치 실행기는 이미 있으므로 이 축소는 예전보다 덜 아프다.

---

## 7. 아직 안 잰 값

`measurements.md` 에 있는 것은 M-009(읽기 포화점)와 M-010(채팅 붕괴점)뿐이다.
아래는 전부 **안 쟀다.** 재면 `measurements.md` 의 해당 절 표에 행을 추가하고,
여기는 그 `M-0NN` 을 가리키도록 바꾼다.

| 값 | 쓰이는 곳 |
|---|---|
| 검증 대기 시간 · 개선 판정 기준 · 승인 무응답 타임아웃 | 상태 머신 · 게이트 |
| 노브별 최대 영향 범위 · 최대 적용 시간 · 사전 승인 예산 · 쿨다운 | 노브 카탈로그 |
| correlation window | Correlator 자동 병합 (D-055). Phase 3C 양방향 도착 지연 실측 후 확정 |
| 채팅 전파 기준값 · 총량 제한 강도별 인입 감소량과 차단률 | S1 성공·실패 기준 |
| CPU 상한 창 (Ready 는 유지, 요청은 느림) · canary p95 대 정상 파드 p95 중앙값의 비 | S2 주입 · Go/No-Go |
| 증설 전후 서비스 p50·p95·p99 · 격리 후 복귀 폭 · 반복 재현율 | S2 1차·2차·최종 검증 |
| 읽기 조치가 api 포화점을 미는 폭 | S3 성공 기준. **노브는 이미 있다(2.4). 효과를 안 쟀을 뿐이고, 0 이면 S3 마지막 장면이 빈다** |
| 두 패턴의 분류기 구분 가능성 | S3 Go/No-Go |
| 게이트별 사람 대기 시간과 Agent 순수 처리 시간 | MTTR 분해 |
| 서비스별 부하 시 실제 CPU·MEM | 자원 요청 현실화. api 만 M-009 에 있고 M-008 은 무부하값이다 |
