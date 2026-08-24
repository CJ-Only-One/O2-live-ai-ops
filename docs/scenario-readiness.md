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
| **비활성** | 구현·배포는 됐고 실행 게이트가 꺼져 있다 |
| **고쳐야** | 있는데 시나리오 조건과 어긋난다 |
| **깨져 있음** | 있다고 보이는데 실제로는 동작하지 않는다 |
| **없음** | 아무것도 없다 |

---

## 2. 대조표

### 2.1 공통 기반 — 크리티컬 패스

| 요구 | 현재 | 판정 |
|---|---|---|
| 조치 실행기 (파드 수·노브 변경) | `infra/06-agent/hot-proxy/openapi.yaml` 에 도구 둘뿐 — `query_datadog_metrics`, `hot_api_health` | **없음** |
| Dify → EKS 권한 (인스턴스 역할 + RBAC) | Dify 는 EKS 밖 private EC2. 경로 없음 | **없음** |
| `cfg:*` 노브 저장·조회 | 세 저장소 grep 0건. api·chat-gateway 어디에도 런타임 노브가 없다 | **없음** |
| 노브 카탈로그 (가역성·예산·precondition·검증 지표) | `infra/06-agent/runbook.tf` 는 `rca_type` 축의 런북 스키마다. 노브 카탈로그는 별개 축 | **없음** |
| 게이트 진입 결정론적 판정 | LLM 자유 서술. 테이크마다 달라진다 | **없음** |
| 상태 머신 · 검증 대기 타이머 · 재분석 1회 분기 | 없음. 정의는 `scenario-experiment.md` 0.4 에 있다 | **없음** |
| `Deduped` 병합 (Incident Correlator) | 계약·설계 완료 — D-055, `contracts.md` 5.9, `contracts/agent-incident-v1.schema.json` + 예제 둘. `agent-entrypoint.md` 는 `incident_correlator: NOT_STARTED`, `agent_invocation_queue: NOT_STARTED` | **설계만** |
| Slack 승인 왕복 | `infra/06-agent/slack_approval.tf` — Lambda 둘 + DynamoDB | **있음** |
| 런북 카탈로그 + 조회 | `runbook.tf` + `runbook_lookup.tf` (Lambda + Function URL, `x-api-key`) | **있음** |
| 인시던트 히스토리 (S3 + S3 Vectors) | `history.tf`, `history_o2.tf`. O2 전용 분리까지 완료 | **있음** |
| Agent 공통 진입점 | `agent_entry_transport.tf` SQS + Worker. 실행 게이트 둘 다 기본 `false` | **비활성** |
| 저장소 Dify DSL | `infra/06-agent/dify/alert-triage.yml` 은 시작→LLM→출력 3노드. 실환경과 드리프트(T-022) | **고쳐야** |

### 2.2 S1 — 채팅 총량 / 대가 게이트

| 요구 | 현재 | 판정 |
|---|---|---|
| 채널 총량 제한 노브 | `apps/chat-gateway/src/main.ts:103` `overRateLimit()` 은 **사용자별**(`CHAT_RATE_PER_MIN` 기본 20). 채널 단위 카운터가 없다 | **없음** |
| 전파 지연 지표 (서버측) | M-010 의 전파 p95 는 **k6 클라이언트 Trend** 다. `chat.send` 페이로드에 `latency_ms` 가 없어 warm path 가 지연을 만들지 못한다 | **없음** |
| 정상 사용자 차단률 | 게이트웨이는 `rejected_code: 'RATE_LIMITED'` 를 싣는데(`apps/chat-gateway/src/chat-ingress.ts:40`) warm 은 `failure_code` 를 읽는다(`o2warm/contract.py:50`). **필드 이름이 달라 집계에 안 잡힌다** | **깨져 있음** |
| 채팅 전파 계약 기준값 | 없다. `architecture.md` 12.1 의 `p95 < 800ms` 는 읽기 경로용이다 | **없음** |
| 넓은 발화자 분포 | `loadtest/broadcast.js:72` `SENDERS = CHAT_RPS × 6`. 발화자가 좁아 **1인 도배로 보인다** — S1 전제(전원이 한도 안인데 총량이 넘음)와 반대다 | **고쳐야** |
| 파형 (첫 파동 → 지속 고원) | 고정 발화율뿐 | **없음** |
| 인입 급증 알림 | `infra/05-datadog/monitor.tf:73` `rps_ratio{service:chat-gateway}`, `min(last_2m)` | **있음** |

### 2.3 S2 — 느린 파드 / 자기 교정 게이트

| 요구 | 현재 | 판정 |
|---|---|---|
| canary Deployment (같은 Service 셀렉터, CPU 상한만 다름) | `O2-live-deploy` 에 매니페스트가 없다 | **없음** |
| 정상 파드 복수 | `O2-live-deploy/api-deployment.yaml:9` **`replicas: 1`**. "정상 파드 중앙값" 도 "한 단계 증설" 도 성립하지 않는다 | **고쳐야** |
| 파드별 지연 (`latency_by_pod`) | `o2warm/sketch.py` 에 `cache_hit_by_pod`/`cache_miss_by_pod` 만 있다. `latency` 는 같은 함수에서 `pod_name` 을 인자로 받으면서 파드별로만 안 나뉜다 | **없음** |
| 파드 단위 이상치 모니터 | `monitor.tf:293-314` 에 `outliers(… by {pod_name}, 'DBSCAN', …)` 가 이미 있다. 다만 **지표가 `cache_hit_rate`** 다 | **고쳐야** |
| 범용 런북 `RB-API-LATENCY-001` | `infra/06-agent/scripts/seed_runbook.py` 에 `cache_invalidation_storm` 하나뿐. `pod_load_skew` 는 TODO 주석이다 | **없음** |
| 자원 요청 현실화 | `api-deployment.yaml:160` `cpu: 100m`. M-009 실측은 300 RPS 에서 664m | **고쳐야** |
| replicas 동기화 예외 | Argo CD `ignoreDifferences` 가 없다 | **없음** |
| api 에 HPA·KEDA 없을 것 | ScaledObject 는 `order-worker` 에만 붙어 있다 | **있음** |

### 2.4 S3 — 사람/봇 미확정 / 정보 게이트

| 요구 | 현재 | 판정 |
|---|---|---|
| 채팅 파생 신호 → Candidate 생성 | `infra/08-chat-signal/lambda/runtime/processor.py`·`repository.py`. `CANDIDATE_CREATED` 구현됨. 실행 게이트는 꺼져 있다 | **비활성** |
| Candidate → Agent 호출 handoff | `agent-entrypoint.md` 0절 `agent_handoff_status=NOT_CONFIGURED` | **없음** |
| 읽기 요청당 CPU 감소 노브 | 없음. S3 의 유일한 조치다 | **없음** |
| 사람/자동화 두 패턴 부하 | `loadtest/read-path.js` 의 `__ENV` 는 `BASE_URL`·`BROADCAST_ID`·`RATE`·`DURATION` 넷뿐. 세션 키·UA·지터·클릭 이벤트 분기가 없다 | **없음** |
| 부하 생성기에 표식 없을 것 | 커스텀 헤더 없음 (`scenario-experiment.md` 3.1) | **있음** |
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

1. **api 자원 요청** — `api-deployment.yaml:160` `cpu: 100m` → 500m 수준. M-009 가
   300 RPS 에서 664m 을 쟀다. **HPA 를 붙이기 전에 고쳐야 한다.**
2. **api replicas 1 → 2 이상** — S2 의 "정상 파드 중앙값 대비 canary" 와 "한 단계 증설" 이
   replicas 1 에서는 성립하지 않는다. M-009 의 재측정 트리거에 해당하므로 바꾸면 다시 잰다.
3. **파드 이상치 모니터의 지표** — `monitor.tf:293-314` 의 `cache_hit_rate` → `latency_p95`.
   쿼리 구조(`outliers … by {pod_name}, 'DBSCAN'`)는 그대로 둔다. 새로 발명하지 않는다.
4. **`rejected_code` → `failure_code`** — `apps/chat-gateway/src/events.ts` 의
   `ChatSendPayload` 가 warm 의 `F_FAILURE_CODE` 와 이름이 달라 차단 건수가 집계에서 사라진다.
   S1 은 정상 사용자 차단률이 성공 판정의 필수 축이라, 이걸 안 고치면 **판정 자체가 성립하지 않는다.**
   이벤트 스키마 변경이므로 `contracts.md` 5.3 을 먼저 고치고 코드를 맞춘다(`AGENTS.md` "계약이 구현보다 우선한다").
5. **`loadtest/broadcast.js` 발화자 분포** — `SENDERS` 를 환경변수로 분리하고, 발화자를 크게
   늘려 1인당 발화율이 `CHAT_RATE_PER_MIN` 아래가 되게 배치한다. M-010 재현 조건은
   비교 가능성을 위해 그대로 남긴다.
6. **Datadog 모니터 이름의 시나리오 번호** — 지금 이름은 옛 번호(시나리오 1·2·4·5·6)이고
   현재 셋은 S1·S2·S3 다. 표시 이름만 정리하고 Terraform 리소스 이름은 건드리지 않는다.
7. **저장소 Dify DSL 드리프트** — 실환경 DSL 을 저장소로 내보낸다. T-022, production
   migration blocker 다.

## 4. 추가해야 할 것

1~3 이 없으면 세 장면 모두 조치 직전에서 멈춘다.

1. **조치 실행기 + Dify → EKS 권한** — `hot-proxy/openapi.yaml` 에 조치 도구를 추가하고
   (파드 수 변경 · 노브 설정 · 격리), EC2 인스턴스 역할 + EKS RBAC 을 뚫는다.
   보안 경계 작업이라 짧지 않다. **단일 최대 크리티컬 패스.**
2. **`cfg:*` 노브 기반** — Valkey 키로 두고 api·chat-gateway 가 읽는다.
   채널 총량 카운터를 **파드 로컬로 만들지 않는다** — chat-gateway 가 2 replicas 라
   로컬 카운터면 실제 상한이 두 배가 된다. `main.ts` 의 `overRateLimit()` 이 쓰는
   Valkey `INCR` + `EXPIRE` 패턴을 그대로 쓴다.
3. **노브 카탈로그** — 가역성 두 축 · `preapproved_budget` · `preconditions` ·
   `verification_metrics` · `diagnostic_contamination` · `rollback_method` 등.
   **게이트 진입을 LLM 이 아니라 이 조회로 판정한다** — 녹화 성공률을 가장 크게 올리는 항목이다.
   `runbook.tf` 의 DynamoDB 패턴을 그대로 재사용한다.
4. **Incident Correlator + Agent Invocation Queue** — 계약과 설계는 D-055 로 끝났고 구현이
   `NOT_STARTED` 다. `agent.trigger.v1` Signal Queue → Correlator → Incident State →
   `agent.incident.v1` Invocation Queue → Generic Worker.
   기존 `agent-trigger` Queue 는 이름만 바꾸려고 교체하지 않는다.
   **Worker mapping 분리를 확인하기 전에는 Correlator event source 를 켜지 않는다** —
   competing consumer 가 되면 입력을 임의로 나눠 가진다.
   S3 의 두 진입점 병합이 여기에 달려 있다.
5. **상태 머신** — `Baseline` 기록·실행 락·멱등 키(`incident:<id>:revision:<n>`) ·
   검증 대기 타이머 · 재분석 1회 분기 · `Judging` 세 갈래.
   정의는 `scenario-experiment.md` 0.4 에 이미 있다.
6. **`latency_by_pod`** — `sketch.py` 의 `cache_hit_by_pod` 패턴을 그대로 복제한다.
   `_add_business` 가 이미 `pod_name` 을 인자로 받고 있어 수십 줄이다.
   `metrics.py` 의 `cache_hit_rate_by_pod` 와 `datadog.py` 의 태그 부착 경로도 같이 따라간다.
7. **canary Deployment 매니페스트** (`O2-live-deploy`) — main 과 같은 이미지·같은 Service
   셀렉터, **CPU 상한만** 낮게. `readinessProbe` 의 `timeoutSeconds`·`failureThreshold` 는
   **canary 에만** 올린다. 안 그러면 파드가 Service 에서 빠져 저절로 회복되거나 들락날락한다.
8. **`RB-API-LATENCY-001`** (증상 기반 범용 런북) + `pod_load_skew` 전용 런북 —
   `seed_runbook.py` 에 항목 추가. `labels.txt` 에 `pod_load_skew` 는 이미 있다.
9. **Argo CD replicas 동기화 예외** — 대상 Deployment 의 `replicas` 를 `ignoreDifferences` 로.
   지금 없어서 조치 후 GitOps 가 되돌린다.
10. **Candidate → Agent handoff** — `agent_handoff_status` 를 실제로 연결한다. 실행 게이트
    둘(`chat_source_adapter_execution_enabled` · `chat_source_adapter_event_source_enabled`)은
    한 줄 실수를 막으려고 일부러 분리해둔 것이므로 순서대로 켠다.
11. **읽기 요청당 CPU 감소 노브** — S3 의 유일한 조치다. **먼저 재고 만든다** — 포화점을
    미는 폭이 0 이면 S3 마지막 장면이 통째로 빈다. 읽기 병목이 왕복이 아니라 api 프로세스
    CPU 천장이므로(M-009 해석), 줄일 대상이 CPU 인지부터 확인한다.
12. **`read-path.js` 두 패턴 분기** — 요청마다 새 세션 키 · 클릭 이벤트 동반 발행 ·
    간격 지터 · UA 혼합. **커스텀 헤더는 넣지 않는다** — Agent 입장에서 정답 라벨이 된다.
13. **`broadcast.js` 파형** — 첫 파동(스파이크) → 지속 고원. 이게 있어야 "첫 파동은
    반응형 조치로 못 막는다" 와 "조치는 고원을 낮춘다" 가 분리되어 보인다.
14. **데모 전용 모니터** — S1·S2 용 `last_1m~2m`. **S3 는 `last_5m` 그대로 둔다** —
    그 지연 자체가 S3 의 주제다.
15. **채팅 전파 지연 지표** — 봉투에 실을지 별도 커스텀 메트릭으로 낼지 결정이 필요하다.
    지금은 k6 안에만 있어 Agent 가 검증에 쓸 수 없다.

## 5. 뺄 것

1. **시나리오 셋 밖 모니터의 `@webhook-o2-dify`** — 지금 6개에 붙어 있고 그중 캐시·주문 큐는
   현재 셋에 없다. 부하가 같이 때리면 측정 중 Agent 가 깨어나 무언가 바꾼다.
   webhook 을 떼거나 Downtime 대상 목록에 명시한다(`scenario-experiment.md` 3절 원칙 ④).
2. **ALB 액세스 로그** — 파드별 지연 후보에서 제외한다. S3 전달 지연이 커서 반복 실험·녹화와 상극이다.
3. **api 에 HPA·KEDA 부착** — 되돌리는 주체가 늘어난다(`scenario-experiment.md` 6절).
4. **FIS · Chaos Mesh** — 주입 원칙 ①(부하 아니면 설정, 둘 중 하나)이 이미 배제했다.
5. **`seed_runbook.py` 의 TODO 를 전부 채우는 것** — 지금 필요한 것은 범용 지연 런북과
   `pod_load_skew` 둘뿐이다. 나머지는 만들지 않는다.
6. **좁은 발화자 프로필을 S1 주입에 쓰는 것** — M-010 재현용으로만 남긴다.
7. **Valkey 구독 Collector 를 운영 소스로 만드는 것** — D-047 이 이미 금지했다.

---

## 6. 실행 순서

| 순서 | 무엇 | 왜 |
|---|---|---|
| 0 | 3절 1·2·4 (자원 요청 · replicas · `failure_code`) | 작고, 뒤 단계 전부가 이 위에 선다 |
| 1 | 4절 1 (조치 실행기 + EKS 권한) | 단일 최대 크리티컬 패스 |
| 2 | 4절 2·3·4·5 (`cfg:*` · 노브 카탈로그 · Correlator · 상태 머신) | 없으면 어떤 시나리오도 화면에 못 올린다 |
| 3 | S3 — 4절 10·11·12 | 검증 루프도 원복도 재분석도 안 쓴다. 기반 점검용 |
| 4 | S2 — 4절 6·7·8·9, 3절 3 | 신규 인프라가 가장 적다 |
| 5 | S1 — 4절 2(채널 노브)·13·15, 3절 5 | 노브와 채팅 지표를 새로 만들어야 한다 |
| 6 | 녹화 프로필 — 4절 14, 3절 6·7 | 시연 직전 |

**백업 계획** — 조치 실행기가 제때 안 되면 축소 시연으로 간다. Agent 가 조치 명령을 Slack 에
내고, 사람이 실행하고, Agent 가 검증한다. 주제가 human-in-the-loop 이라 이 축소가 오히려
주제에 가깝다.

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
| 읽기 조치가 api 포화점을 미는 폭 | S3 성공 기준. **0 이면 S3 마지막 장면이 빈다** |
| 두 패턴의 분류기 구분 가능성 | S3 Go/No-Go |
| 게이트별 사람 대기 시간과 Agent 순수 처리 시간 | MTTR 분해 |
| 서비스별 부하 시 실제 CPU·MEM | 자원 요청 현실화. api 만 M-009 에 있고 M-008 은 무부하값이다 |
