# 장애 시나리오 실험 — 복구 기준과 주입 설정

세 시나리오(채팅 총량 · 느린 파드 · 외부 결제 PG 장애)의 **흐름과, 재현 가능하게
돌리고 판정하기 위한 규칙**이다. S3는 한 인시던트 안에서 조치를 반복하는 시나리오가
아니라, **첫 실행 실패 → 사람의 해결·지식화 → 동일 장애 2차 실행 성공**을 한 세트로
검증한다. 0절이 시나리오가 무엇인지, 1~3절이 어떻게 판정하고 무엇을 주입하는지다.

> 발표 구성·시연 순서·슬랙 메시지 문안은 저장소 밖 기획 문서에 있다.
> **여기에는 구현과 실험에 필요한 것만 둔다.**

> **수치는 여기에 확정하지 않는다.** 실측값은 전부 `docs/measurements.md` 가
> 원본이고 이 문서는 참조만 한다. 안 잰 값은 "안 쟀다" 로 남긴다 (`AGENTS.md`
> "숫자를 지어내지 않는다").

## 인덱스

| 절 | 무엇 |
|---|---|
| 0 | 시나리오 셋과 게이트 셋 — 정의, 공통 상태 머신, 시나리오별 흐름 |
| 1 | 복구 판정 — 규칙 둘, 시나리오별 기준 |
| 2 | 장애 주입 — 지켜야 할 것 넷, 시나리오별 설정 |
| 3 | 실행 사이 초기화 |
| 4 | 실행 Runbook — 주입·원복 명령과 입력값 안전장치 |

---

## 0. 시나리오 셋과 게이트 셋

### 0.1 세 갈래 — 시나리오가 보여주는 세 운영 판단

S1·S2는 한 번의 Agent 실행으로 끝난다. S3만 두 번의 별도 실행을 비교한다.
S3의 2차 실행은 1차 실행의 내부 재시도나 같은 조치 반복이 아니라, 사람이 검증된
History와 Runbook을 만든 뒤 **동일 장애를 다시 주입해 새 인시던트로 호출**하는 것이다.

| 경로 | 종착 | 사람이 나오나 | 시나리오 |
|---|---|---|---|
| **승인 → 해결** | `RESOLVED` | 실행 **전에** 승인 1회 | S1 |
| **재진단 → 해결** | `RESOLVED` | **안 나옴** | S2 |
| **지식 없음 → 실패 / 지식화 후 재실행 → 해결** | 1차 `ESCALATED`<br>2차 `RESOLVED` | 1차 뒤 수동 해결·검증<br>2차 실행 전 승인 | S3 |

**조치 실행 전에 승인을 받는 지점은 Guardrail 하나뿐이다.** 카탈로그 등급을 조회해 결정론적으로 정한다 —
`L1`/`L2` 는 `AUTO`, `L3` 는 `APPROVAL`, 카탈로그에 없으면 `DENY`.
**"물어봐야 하나" 를 LLM 이 판단하지 않는다.** 다만 이것은 현재 승인 라우팅
규칙이고 L1/L2/L3 부여 척도와 KNOB precondition 집행은 아직 없다. 실제 상태는
`runbook-catalog.md`와 D-079를 본다.

S3 1차의 `ESCALATED`는 승인 요청이 아니라, 실행 가능한 active Runbook이 없어서
종료한 뒤 사람에게 넘기는 **실패 인계**다.

| 버튼 | 그 다음 | 사람이 기여한 것 |
|---|---|---|
| 승인 | 조치 실행 → 검증 | 가치판단 |
| 다시 보기 | 그 조치가 `excluded_actions` 로. 코멘트가 다음 진단·계획 입력 | 정보 |
| 거부 | 재시도 없이 `ESCALATED` | 권한 회수 |

### 0.2 분류와 런북은 다른 축이다

| 축 | 값 | 기준 |
|---|---|---|
| 분류 | 알려진 장애 / 처음 보는 장애 | **과거에 같은 원인의 사례가 있는가** (S3 Vectors 유사도 임계) |
| 런북 | 전용(원인 기반) / 범용(증상 기반) / 없음 | 절차가 원인에 붙었나 증상에 붙었나 |

**런북을 썼다고 알려진 장애가 되는 것이 아니다.** 범용 런북은 원인을 몰라도 쓴다.
S2 가 그 경우다 — 처음 보는 장애인데 증상 기반 런북으로 시작한다.

#### 런북의 종류와 운영 상태도 다른 축이다

장애가 해결됐다고 그 해결 절차가 곧바로 전용 런북이 되지는 않는다.
**원인 확인**과 **절차 검증**은 별도 판정이다.

| 운영 상태 | 무엇을 담나 | Agent 조회·실행 |
|---|---|---|
| 해결 사례 | 이번 장애의 관측·가설·조치·검증·원복 결과 | 재분석 근거로만 사용. 실행 절차로 취급하지 않음 |
| 후보 런북 (`draft`) | 해결 사례에서 일반화한 적용 조건·조치·검증·롤백 초안 | 운영 런북 조회와 자동 실행에서 제외 |
| 전용 런북 (`active`) | 재현성·안전성·실패·롤백 검증과 사람 승인을 통과한 원인 기반 절차 | 조건이 맞을 때만 조회·실행 가능 |

후보 런북은 별도 영역에 둔다. 최소한 다음을 통과한 뒤에만 전용 런북으로
승격한다.

1. 같은 원인으로 장애를 반복 재현하고, 같은 조치로 복구되는가
2. 진입 조건과 제외 조건이 관측 가능한 지표로 판정되는가
3. 정상 상태에 잘못 적용했을 때의 부작용과 최대 영향 범위를 확인했는가
4. 성공·실패·중단 기준과 안정화 대기 시간이 고정돼 있는가
5. 원복 절차가 실제로 동작하고 원복 후 기준선이 회복되는가
6. 소유자·버전·검증 증거·검토일을 남기고 운영자가 승인했는가

한 번의 복구는 **후보를 만들 근거**이지, 자동 실행 가능한 전용 런북의 증거가 아니다.
승격 전 같은 원인의 장애가 재발하면, 원인 사례의 사람 검증 여부에 따라
`알려진 장애`로 분류될 수는 있어도 **검증된 전용 런북은 없는 상태**다. 후보 절차를
자동 실행하지 않고 범용 런북 또는 분석에서 시작한다.

#### 범용 런북 등록 기준

범용 런북은 단순히 "자주 하는 조치"가 아니다. 원인을 모르는 상태에서도
안전하게 실행하면서 가설을 좁힐 수 있어야 한다.

| 기준 | 필수 내용 |
|---|---|
| 선택 가능성 | 원인이 아니라 관측 가능한 증상·진입 임계값으로 선택할 수 있음 |
| 제한된 조치 | 가역적이며 대상·최대 변경량·유지 시간·비용 예산이 고정됨 |
| 사전 검사 | 적용 금지 조건·용량 여유·장애 격리 범위를 결정론적으로 확인함 |
| 검증 가능성 | 실행 전 Baseline과 성공·실패·즉시 중단 지표가 미리 정해져 있음 |
| 반복 방지 | 같은 인시던트에서 최대 실행 횟수가 1회이며 실패 후 같은 조치를 반복하지 않음 |
| 원복 가능성 | 원복 방법과 원복 후 재검증 기준이 실제로 검증돼 있음 |
| 운영 책임 | 소유자·버전·검토일·만료일·변경 이력이 있음 |

하나라도 빠지면 범용 런북이 아니라 **분석 중 참고 절차**다. 자동 실행 대상으로
등록하지 않는다. S2의 `RB-API-LATENCY-001`도 이 기준을 충족했다는 검증 증거가
있어야 범용 런북으로 사용할 수 있다.

### 0.3 시나리오 셋

| # | 진입 | `rca_category` | 장애 | 조치 | 종착 |
|---|---|---|---|---|---|
| **S1** | Datadog | `chat_channel_overload` | 채팅 총량이 채널 감당 선 초과 → 전파 지연 | 채널 총량 제한 (`L3`) | **승인 → 해결** |
| **S2** | Datadog | `pod_resource_exhaustion`<br>→ `pod_load_skew` | Service 에 붙은 파드 하나만 CPU 조임 → 서비스 꼬리 지연 | 증설 → 미달 → 격리 (둘 다 `L1`/`L2`) | **재진단 → 해결** |
| **S3** | **채팅** | `pg_external_failure` | 외부 PG-A 지연 → 주문 타임아웃 | 1차: 실행 안 함<br>2차: PG-A → PG-B 전환 (`L3`) | **1차 실패 → 지식화 → 2차 해결** |

**인시던트 단위가 셋 다 다르다.** 이것이 곧 `Deduped` 병합 키다.

| | 단위 | 근거 |
|---|---|---|
| S1 | `service` + **`broadcast_id`** | 채널 총량은 방송마다 별개다. 다른 방송의 폭주는 다른 인시던트이고 조치도 그 방송에만 건다 |
| S2 | `service` + **`deployment`** | 파드가 여럿 이상해도 원인이 하나의 Deployment 설정이면 한 인시던트다 |
| S3 | **`service` 만** (방송 무관) | 외부 의존이라 모든 방송에 동시에 영향한다. **`broadcast_id` 를 병합 키에서 뺀다** — 안 그러면 같은 사건이 방송 수만큼 늘어난다 |

### 0.4 공통 상태 머신

세 시나리오가 모두 이 위에서 돈다. 시나리오별 차이는 **어느 분기를 타는가**뿐이다.

```mermaid
stateDiagram-v2
    [*] --> Detected: Datadog 알림 또는 채팅 Candidate
    Detected --> Deduped: 진행 중 사건과 병합 확인
    Deduped --> Analyzing
    Analyzing --> InfoGate: 가설이 상충
    Analyzing --> Planned: 가설 하나
    Analyzing --> Escalated: 원인 확인 · 실행 가능한 active Runbook 없음

    InfoGate --> Analyzing: 실험 결과 · 운영자 답변
    InfoGate --> HoldAction: 모르겠다 → 양쪽에 안전한 조치

    Planned --> Precheck: 결정론적 검사
    Precheck --> CostGate: 검사 실패 또는 예산 초과
    Precheck --> Baseline: 통과 · 예산 이내
    CostGate --> Baseline: 승인
    CostGate --> Closed: 거부
    CostGate --> Expired: 만료 · 무응답

    Expired --> HoldAction: 가장 약한 단계만
    HoldAction --> Baseline

    Baseline --> Acting: 기준값 기록 · 실행 락
    Acting --> Verifying: 대기 타이머
    Verifying --> Resolved: 기준 충족
    Verifying --> Judging: 미달

    Judging --> RollbackNow: 악화 또는 기준선 오염
    Judging --> KeepAndReanalyze: 무해하고 다음 조치에 도움
    RollbackNow --> Reanalyzing
    KeepAndReanalyze --> Reanalyzing

    Reanalyzing --> Planned: 재분석 1회
    Reanalyzing --> Escalated: 이미 1회 썼음

    Resolved --> Cleanup: 임시 조치 정리
    Cleanup --> Recorded
    Escalated --> Recorded
    Closed --> Recorded
    Recorded --> [*]
```

지켜야 하는 것 넷.

| 상태 | 불변조건 |
|---|---|
| `Deduped` | 진입점이 둘이라 **같은 장애가 두 번 들어온다.** D-055의 결정론적 조건으로 같은 진행 중 사건에 붙이고, 모호하면 강제 병합하지 않는다 |
| `Baseline` | 기준값 기록 · 실행 락 · 멱등 키. **이것 없이 `Acting` 으로 가지 않는다** |
| `Verifying` | `verification_metrics` 로만 판정. **런북으로 시작했으면 그 런북이 지정한 지표로** |
| 런북 반복 금지 | 런북 조치가 검증 실패하면 **같은 절차를 다시 실행하지 않는다** |

`Judging` 의 세 갈래는 `diagnostic_contamination` 을 조회해 정한다.
**무조건 되돌리는 것이 규칙이 아니다** — 틀린 조치와 불완전한 조치는 다르다.

### 0.5 S1 흐름 — 승인 → 해결

**Phase 1. 장애 탐지**

- 다수 시청자가 개인 Rate Limit 아래에서 동시에 발화한다.
- 방송 전체 처리량이 채널 용량을 넘어 Datadog 채팅 전파 p95 알림으로 Agent가 진입한다.
- `service + broadcast_id` 범위에서 `chat_channel_overload`를 진단한다.

**Phase 2. Runbook 조회와 사전 검사**

- 유사 History와 active 전용 Runbook을 조회한다.
- 대상 방송·적용할 고정 제한값·정상 사용자 영향·원복 방법을 확인한다.
- 정상 사용자 메시지도 일부 제한될 수 있으므로 `L3`로 결정론적으로 분류한다.

**Phase 3. 승인과 실행**

- 운영자에게 방치 시 피해와 제한 시 피해를 함께 제시한다.
- 승인받은 뒤 해당 `broadcast_id`의 채널 총량만 제한한다.
- 최초 Spike는 이미 지났으므로 이후 지속 Plateau를 완화 대상으로 삼는다.

**Phase 4. 복구 검증과 정리**

- 적용 시각 이후 채팅 전파 p95 회복과 정상 사용자 차단률 상한을 함께 확인한다.
- 안정화 후 채널 제한을 해제하고, 해제 후 지연이 재발하지 않는지 다시 확인한다.
- 실행값·승인자·사용자 영향·복구 결과를 History에 기록한다.

```mermaid
flowchart TB
    A["Datadog 채팅 전파 p95 알림"] --> B{"유사 과거 사례"}
    B -->|"있음 · 알려진 장애"| C["전용 런북 조회<br/>조치 = 채널 총량 제한"]
    C --> D{"Precheck<br/>user_effect_reversible"}
    D -->|"아니오 · 예산 밖"| E["대가 게이트<br/>조치 시 피해 · 방치 시 피해"]
    E -->|"강도 선택"| F["채널 총량 노브 하향"]
    E -->|"거부"| X["종료 · 기록"]
    E -->|"무응답 · 만료"| G["가장 약한 단계만 적용<br/>후 재질의"]
    G --> F
    F --> H["검증 — 적용 시각 이후만"]
    H -->|"전파 p95 회복<br/>AND 차단률 상한 내"| I["안착 · 기록"]
    H -->|"미달"| J["자기 교정으로"]
```

**첫 파동은 어떤 조치로도 못 막는다** — 알림→분석→승인→적용 사이에 단발 스파이크는
끝나 있다. 조치가 낮추는 것은 **지속 고원**이다. 그래서 검증도 적용 시각 이후만 센다.

### 0.6 S2 흐름 — 재진단 → 해결 (사람 없음)

**Phase 1. 장애 탐지와 1차 진단**

- CPU limit만 낮은 `api-canary`가 정상 API Service에 붙은 상태에서 읽기 부하를 건다.
- Datadog 서비스 꼬리 지연 알림(`[O2][S2] API 꼬리 지연 — p99 조기 감지`)으로 Agent가 진입하고,
  동일 History가 없어 처음 보는 장애로 분류한다.
- 서비스 전체 지표만 보고 API 처리 용량 부족을 1차 가설로 세운다.

**Phase 2. 범용 Runbook 1회 실행**

- `RB-API-LATENCY-001`의 가역성·변경 상한·노드 여유를 사전 검사한다.
- 정상 API Deployment를 한 단계 증설하고 조치 직전 Baseline을 저장한다.

**Phase 3. 검증 실패와 재진단**

- p50은 개선되지만 꼬리(p99)는 미달인 것을 확인한다. 파드 하나만 느린 상황에서 그 파드의
  몫이 5% 미만이면 p95는 아예 움직이지 않는다.
- 같은 Scale-out을 반복하지 않고, 무해한 증설분은 재진단 동안만 유지한다.
- 파드별 지연·CPU 사용량·resource 설정을 비교해 `api-canary`만 이상치임을 찾는다.
- 진단을 전체 용량 부족에서 `pod_load_skew`로 수정한다.

**Phase 4. 격리와 최종 검증**

- Canary를 빼도 정상 Pod 용량이 안전 최소 이상인지 검사한 뒤 `api-canary`를 격리한다.
- 서비스 꼬리 지연이 canary 투입 전으로 돌아오는지 확인하고, 1차 증설분을 원복한다.
- 원복 후에도 유지돼야 `RESOLVED`로 종료한다.

**Phase 5. 운영 지식화**

- 원인·1차 조치·검증 실패·격리·원복 증거를 해결 사례로 기록한다.
- `RB-API-POD-RESOURCE-SKEW`는 `draft` 후보로만 만들고 별도 검증·승인 전에는 실행하지 않는다.

```mermaid
flowchart TB
    A["Datadog 서비스 지연 알림<br/>서비스 단위 지표만"] --> B{"유사 과거 사례"}
    B -->|"없음 · 처음 보는 장애"| C["범용 런북 RB-API-LATENCY-001<br/>증상 기반"]
    C --> D{"Precheck<br/>가역 · 예산 내 · 노드 여유"}
    D -->|"통과"| E["자동 실행<br/>정상 Deployment 한 단계 증설"]
    E --> F["Baseline 기록 → 검증"]
    F -->|"p50 개선 · p99 미달"| G["자기 교정 게이트<br/>런북 반복 금지"]
    G --> H{"되돌릴 것인가"}
    H -->|"무해 + 다음 조치에 도움"| I["그대로 두고 재분석"]
    I --> J["파드별 분해<br/>지연 · CPU 조임 · 자원 프로필 비교"]
    J --> K["수정 가설<br/>용량 부족이 아니라 파드 하나"]
    K --> L{"격리 Precheck<br/>정상 용량 안전 최소 이상"}
    L -->|"통과"| M["canary 격리"]
    L -->|"실패"| N["대가 게이트로"]
    M --> O["검증 → 증설분 원복"]
    O --> P["최종 재검증"]
    P --> Q["장애 해결 사례 기록<br/>원인·조치·검증·원복 증거"]
    Q --> R["후보 런북 영역에 Draft 등록<br/>RB-API-POD-RESOURCE-SKEW"]
    R --> S["별도 재현·안전성·실패·롤백 검증"]
    S -->|"운영자 승인"| T["전용 런북으로 승격<br/>active 카탈로그 등록"]
    S -->|"미달"| U["후보 유지 또는 폐기<br/>자동 조회·실행 금지"]
```

**재분석은 1회다.** 초과하면 `Escalated` 로 사람에게 넘긴다.
**최종 재검증까지가 조치의 끝이다** — 2.2 참조.
그 뒤의 후보 런북 검증과 승격은 인시던트 처리와 분리된 사후 절차다.
따라서 S2 시연에서 확정할 수 있는 것은 **복구와 후보 런북 등록까지**이며,
전용 런북의 활성화만 별도 검증 완료 후에 가능하다. 다음 재발의 `알려진 장애`
분류는 전용 런북 유무가 아니라 과거 원인 사례의 사람 검증 결과로 독립 판정한다.

### 0.7 S3 흐름 — 1차 실패 → 지식화 → 동일 장애 2차 실행 성공 (채팅 진입)

**Phase 1. 최초 장애 탐지와 진단**

- 시청자 결제 불만의 파생 신호로 Datadog보다 먼저 Agent가 진입한다.
- Athena에서 `payment.process` 원시 이벤트를 조회한다.
- `pg_provider=PG-A`, `failure_code=PG_TIMEOUT`, `failure_stage=PG_CALL`,
  `pg_latency_ms` 증가와 정상 클러스터 자원을 근거로 `pg_external_failure`를 진단한다.

**Phase 2. 1차 Agent 실행 실패**

- 유사한 verified History와 active PG Failover Runbook이 없다.
- PG-B 안전성·전환 조건·멱등성·원복 방법을 검증하지 않았으므로 임의 전환하지 않는다.
- 원인과 필요한 후속 조치를 보고하고 `ESCALATED`로 종료한다.
- 이것은 조치 실패 후 같은 절차를 반복하는 `재시도`가 아니라 **실행 가능한 지식이 없어 멈춘 것**이다.

**Phase 3. 사람 해결과 운영 지식화**

- 운영자가 PG-A에서 PG-B로 수동 전환하고 결제 정상화를 확인한다.
- 해결 사례를 verified History로 기록한다.
- PG 전환·원복·주문 멱등성·정상 상태 오적용·실패 처리를 별도 검증한다.
- 검증을 통과한 PG Failover Runbook만 운영자 승인 후 `draft → active`로 승격한다.

**Phase 4. 동일 장애 재현과 Agent 2차 실행**

- 환경을 초기화한 뒤 같은 PG-A 장애 조건을 다시 주입해 새 인시던트로 Agent를 호출한다.
- Dify의 History 유무 분기에서 verified PG-A 장애 사례를 찾는다.
- 이는 1차 인시던트의 내부 retry가 아니라 **지식 개입 전후를 비교하는 별도 실행**이다.

**Phase 5. 현재 증거 재검증**

- 과거 History를 현재 장애의 사실이나 실행 권한으로 그대로 믿지 않는다.
- 현재 이벤트에서도 `PG-A + PG_TIMEOUT + PG_CALL + pg_latency_ms 증가`가 일치하는지 다시 확인한다.
- 증거가 다르면 과거 Runbook을 실행하지 않고 일반 진단으로 돌아간다.

**Phase 6. 승인과 PG Failover 실행**

- History에 연결된 active PG Failover Runbook과 PG-B 상태·전환 조건을 조회한다.
- 결제 경로 전환은 blast radius가 큰 `L3` 조치이므로 사람 승인을 받는다.
- Agent가 결제 경로를 PG-A에서 PG-B로 전환한다. PG-A 장애 자체는 유지한다.

**Phase 7. 2차 실행 복구 검증**

- PG-B 결제 성공 이벤트, 주문 실패율 감소, 결제 p95 회복을 확인한다.
- 채팅 결제 불만 감소까지 확인해 사용자 영향도 함께 회복됐는지 판정한다.
- 지표와 사용자 영향이 모두 회복되면 2차 실행을 `RESOLVED`로 종료한다.

```mermaid
flowchart TB
    A["채팅 파생 신호<br/>본문 없음"] --> B["Incident Correlator<br/>Datadog 후속 증거 병합"]
    B --> C["Dify History 분기"]
    C -->|"1차 · verified History 없음"| D["Athena 현재 이벤트 조회"]
    D --> E["PG-A 외부 장애 진단"]
    E --> F["active Failover Runbook 없음"]
    F --> G["ESCALATED<br/>진단·필요 조치 보고"]
    G --> H["운영자 PG-B 수동 전환"]
    H --> I["History verified<br/>Runbook 검증 · active 승격"]
    I --> J["환경 초기화<br/>동일 PG-A 장애 재주입"]
    J --> K["Agent 2차 실행"]
    K --> L["Dify History 분기<br/>verified 사례 있음"]
    L --> M["현재 증거 재검증"]
    M -->|"불일치"| N["일반 진단으로"]
    M -->|"일치"| O["active PG Failover Runbook"]
    O --> P["L3 사람 승인"]
    P --> Q["PG-A → PG-B 전환"]
    Q --> R["지표 + PG-B 성공 이벤트<br/>+ 채팅 불만 감소"]
    R --> S["RESOLVED"]
```

S3가 증명해야 하는 것은 **같은 장애, 같은 Agent라도 검증된 운영 지식 유무에 따라
결과가 달라진다**는 점이다. History는 유사 사례를 찾는 근거이고 실행 권한이 아니다.
실제 실행 절차와 권한은 별도 검증을 통과한 `active` Runbook과 Guardrail이 제공한다.

**장애 주입은 목업 PG 스텁으로 하고 실제 결제 인프라는 만들지 않는다.**
현재 API 주문 접수 경로에는 PG-A 지연·실패 주입과 `payment.process` 이벤트 발행이
구현돼 있다. SDK에 `pg_latency_ms`·`failure_code`(`PG_TIMEOUT` 등)가 정의돼 있고,
warm은 `pg_latency_ratio`를 집계하며, `pg_external_failure`는 진단 enum과 복구 판정
폴백에 있다. PG-B ready 확인·전환·원복과 Provider별 성공 이벤트는 API 목업에
구현됐지만, 이를 L3 승인 Action Handler와 active Runbook으로 연결한 경로는 아직 없다.

```python
# apps/api/app/services/payment.py — 목업 PG
delay_ms  = int(valkey.get("cfg:pg:delay_ms")  or 0)
fail_rate = float(valkey.get("cfg:pg:fail_rate") or 0)
time.sleep(delay_ms / 1000)
# 같은 Idempotency-Key는 같은 표본을 써 재시도 결과가 뒤집히지 않는다.
failed = deterministic_sample(idempotency_key) < fail_rate
emit.payment_process(..., result="FAILED" if failed else "SUCCESS",
                     failure_code="PG_TIMEOUT" if failed else None,
                     failure_stage="PG_CALL" if failed else None,
                     pg_latency_ms=pg_ms, total_latency_ms=pg_ms)
```

| | |
|---|---|
| 주입 · 해제 | `SET cfg:pg:delay_ms` · `cfg:pg:fail_rate` / 해제는 `DEL`. 재배포 없이 켜고 끈다 |
| **어디에 넣나** | **`order-worker` 가 아니라 `api` 주문 접수 경로.** worker 에 넣으면 SQS 백로그가 쌓여 `queue_backlog` 로 오진한다 — 이 시나리오는 "정확히 진단했는데 못 고친다" 가 핵심이라 오진이 방해된다 |
| 세기 | 동기 라우트라 uvicorn 스레드풀이 마르고 api p95 가 전면 상승한다(알림이 뜨니 좋다). 너무 세면 api 가 죽어 `pod_resource_exhaustion` 처럼 보인다 — **주문은 깨지는데 읽기는 사는 구간**을 찾는다 |
| PG-B | `/api/admin/pg-provider-switch`에서 PG-B ready를 확인한 뒤 전환한다. PG-A 주입값은 유지되고 PG-B 요청은 이를 무시하므로, `pg_provider=PG-B`·`result=SUCCESS` 이벤트가 우회 효과를 증명한다. 이 작업은 Action Handler 배선을 변경하지 않는다 |
| Runbook | 1차에는 active 항목이 없어야 한다. 사람의 별도 검증 뒤에만 PG Failover Runbook을 active로 올리고 2차 실행에서 조회한다 |

**채팅 본문을 Agent 에게 주지 않는다.** 시청자가 자유롭게 타이핑하는 유일한 입력이라
본문을 저장하면 프롬프트 인젝션 경로가 된다. 파생값만 쓴다.

| 무엇 | 어디 |
|---|---|
| 본문을 싣지 않는 근거 | `contracts.md` 5.3 "본문은 싣지 않는다" (설계 8.5 프롬프트 인젝션) |
| 파생 신호 스키마 | `contracts.md` 5.6 `chat.signal.v1` |
| Candidate 스키마 | `contracts.md` 5.7 `chat.incident_candidate.v1` |
| Candidate 생성·Incident 호출 정책 | `docs/chat-incident-candidate.md`, `docs/agent-entrypoint.md` 1.2, D-055 |

**Chat trigger 생성은 `CANDIDATE_CREATED`에서 한 번만이다**(D-050, D-055).
쿨다운 중 `CANDIDATE_UPDATED`는 저장만 한다.

**진입점이 둘이 되면 Agent 호출 전에 병합 계층이 반드시 필요해진다**(0.4 `Deduped`, D-055).
채팅으로 하나, 알림으로 하나 들어오므로 합치지 않으면 같은 사건을 두 번 조사한다.
**S3 는 병합 키에서 `broadcast_id` 를 뺀다**(0.3) — 외부 의존이라 모든 방송에 동시에 영향하기 때문이다.

---

## 1. 복구 판정

### 1.1 규칙 둘

**① 계약 SLO 복귀 _AND_ 조치 직전 기준선 대비 개선, 둘 다 만족해야 한다.**

- SLO 만 보면 **부하가 저절로 빠져도 통과**한다. 자연 회복이 조치 효과로 기록된다.
- 기준선 개선만 보면 **여전히 계약 위반인데 "해결"** 이 된다.

`Baseline` 상태가 조치 직전 값을 찍는 이유가 이것이다.

**② 빨라졌나 + 안 망가뜨렸나, 둘 다 본다.**

지연만 보면 **"정상 사용자 절반을 차단해서 빨라진 것"** 이 성공이 된다.
그래서 **정상 사용자 차단률**을 항상 같이 판정한다.

> 검증 대기는 **60초 이상**. warm path 집계 창이 10초라 그보다 짧으면
> 창 하나가 튄 것으로 판정이 뒤집힌다.

### 1.2 시나리오별

| | 성공 | 놓치면 안 되는 것 |
|---|---|---|
| **S1** | 전파 p95 가 붕괴 전 구간으로 복귀 **AND** 정상 사용자 차단률이 상한 이내 | **효과는 조치 적용 시각 이후만 센다.** 첫 파동은 이미 지나가 있다.<br>채팅 전파 계약 기준이 저장소에 없다 — M-010 실측 형상을 기준선으로 쓴다 |
| **S2** | 격리 후 꼬리 지연이 **canary 붙이기 전** 값으로 복귀. 판정 축은 **p99** 이고 두 용량 런북의 기준은 `p99_ms <= 50` 이다(2026-08-27) | **증설분을 원복한 뒤에도 유지되어야 끝이다.** 남긴 채 회복하면 "결국 파드를 늘려서 나은 것" 을 배제할 수 없다.<br>1차 증설은 **실패해야 정상**이다 — p50 만 개선되고 꼬리는 그대로.<br>**p95 로 판정하지 않는다** — 장애 중 서버측 p95 가 28.63ms 라 `<= 350`·`<= 800` 같은 기준은 장애 한복판에서도 통과한다 |
| **S3** | **1차:** 현재 PG-A 원인 진단 성공 + active Runbook 부재로 임의 조치 없이 `ESCALATED`<br>**2차:** PG-B 성공 이벤트 확인 + 주문 실패율·p95 회복 + 채팅 불만 감소 | 두 실행을 모두 통과해야 성공이다. 1차가 임의 Failover로 해결돼도 실패이고, 2차가 History만 믿고 현재 증거를 재검증하지 않아도 실패다.<br>PG-A 장애는 유지해 자연 회복이 아니라 PG-B 우회 효과임을 증명한다 |

---

## 2. 장애 주입

### 2.1 지켜야 할 것 넷

| | |
|---|---|
| **부하 아니면 설정, 둘 중 하나로만** | 프로세스를 죽이거나 네트워크를 끊지 않는다. S1·S3 는 부하, S2 는 설정. FIS·Chaos Mesh 불필요 |
| **k6 에 식별용 표식을 붙이지 않는다** | 봉투에 실려(T-023) warm path 를 거쳐 **Agent 가 읽는 지표**가 된다. 표식은 곧 정답 라벨이다. `broadcast.js`·`read-path.js`·`order-path.js`에 시나리오 정답을 드러내는 커스텀 헤더를 넣지 않는다 |
| **콜드 캐시에서 시작하되 `stock:*` 은 지우지 않는다** | 재고는 Valkey 가 원본이다(D-07). 지우면 재고가 0 으로 표시되고 다음 주문 측정까지 망가진다. 비우려면 `kubectl rollout restart deploy/api` |
| **측정할 땐 모니터 Downtime, 주입할 땐 해제** | 안 재우면 측정 중에 Agent 가 깨어나 무언가 바꾼다 |

### 2.2 시나리오별

| | 무엇을 주입하나 | 안 하면 실패하는 것 |
|---|---|---|
| **S1** | `broadcast.js` 의 `PROFILE=s1` 로 `아이템/s = 시청자 × 발화율` 을 M-010 붕괴점 위로. **연결 축**으로 올린다 — 같은 총량이면 연결이 많을수록 확실히 무너진다(M-010 해석 2) | **발화자를 넓게 퍼뜨린다.** 전제는 *전원이 한도 안인데 인원이 많아 총량이 넘는다* 이므로 전원이 `CHAT_RATE_PER_MIN` 아래여야 한다 — 스크립트가 `SENDERS` 를 필수로 받고 1인당 한도를 넘으면 시작 전에 실패한다.<br>파형은 **첫 파동 + 지속 고원** — `SPIKE_RPS`·`SPIKE_S`·`PLATEAU_RPS` 로 두 구간을 만든다 |
| **S2** | canary Deployment 를 같은 Service 에 붙인다. main 과 **같은 이미지·같은 셀렉터, CPU 상한만** 낮게. 부하는 `read-path.js` 고정 도착률 | **CPU 상한은 `125m` 으로 정해졌다**(2026-08-26 스윕, 200 RPS·60초). `100m` 은 liveness 를 5초로 넓혀도 재시작이 나고, `150m` 은 장애가 약해진다. **`125m` 의 재시작 0 은 60초 부하에서만 성립한다** — 15분 연속에서는 재시작 3회다. 시연처럼 길게 끌면 `150m` 이나 `failureThreshold` 확대를 다시 재야 한다.<br>판정에는 p95 절대값을 쓰지 않는다 — 실행마다 흔들린다. 쓰는 것은 재시작 0 · 정상 파드 중앙값 16ms 대 · canary 가 정상 파드의 8.1배다 |
| **S3** | **목업 PG-A 스텁**에 `cfg:pg:delay_ms`·`cfg:pg:fail_rate`를 SET하고 k6 주문 부하를 건다. `payment.process` 이벤트가 `pg_provider=PG-A`·`failure_stage=PG_CALL`·`failure_code=PG_TIMEOUT`·`pg_latency_ms`를 싣는다. 지식화 후 환경을 초기화하고 같은 값을 다시 주입한다 | **1차와 2차의 장애 조건을 같게 유지한다.** PG 지연을 중간에 풀면 자연 회복이 Failover 효과로 기록된다.<br>**`api` 주문 접수 경로에 넣는다.** `order-worker`에 넣으면 SQS 백로그 때문에 `queue_backlog`로 오진한다.<br>PG-B 전환 뒤에도 PG-A 주입값은 유지하고, Provider별 성공 이벤트로 실제 우회를 확인한다 |

**파드별 지연 지표는 이미 있다.** `p95:o2.apm.request.duration{...} by {pod_name}` 을
`monitor.tf` 의 `latency_p95_pod_outlier` 가 DBSCAN 으로 본다.
**조임 비율(`cfs.*`)은 보지 않는다** — 이 클러스터는 CPU limit 을 일부러 안 걸어서
그 지표가 **영구히 비어 있다**(D-064). 파드별 CPU 는 `kubernetes.cpu.usage.total by {pod_name}`
사용량으로 보되, **조여진 파드는 상한에 막혀 오히려 낮게 나온다**는 점을 기억한다.
**ALB 액세스 로그는 쓰지 않는다** — 전달 지연이 커서 실험 반복에 안 맞는다.

> **은폐와 범위는 다르다.** canary 설정값은 채점자 전용이지만 Agent 는 재분석에서
> `kubectl` 로 조회할 수 있어야 한다. **첫 알림 문맥에만 안 들어가면 된다.**

---

## 3. 실행 사이 초기화

| | |
|---|---|
| 노브 · 카운터 | `cfg:*` 삭제 · `chat:rate:*` · 채널 총량 카운터 |
| 파드 수 | main replicas 복원 · canary 제거 |
| 캐시 | Valkey 는 **메타 키만** — `stock:*` 금지 (2.1) |
| 시나리오 간섭 | S3 전 **canary 제거** 확인 · S2 전 **`cfg:pg:*` 해제** 확인. 지연이 남아 있으면 S2 의 p95 판정이 오염된다 |
| S3 지식 상태 | 1차 실행 전에는 대상 사례가 History 검색에 없어야 하고 PG Failover Runbook은 inactive여야 한다. 2차 실행 전에는 같은 사례가 `verified`, Runbook이 `active`여야 한다. 공유 append-only History를 삭제하지 말고 반복 시연용 격리 데이터셋·인덱스를 사용한다 |
| **Datadog 모니터 상태** | **OK 로 돌아왔는지 확인하고 다음 실행을 시작한다.** ALERT 로 남아 있으면 다음 실행에서 알림이 다시 안 떠서 Agent 가 안 깨어난다 — **반복 실행에서 가장 자주 밟는다** |
| k6 | 누락 반복 수 0 인지 확인. 아니면 부하 생성기가 먼저 막힌 것이다 |
| 노드 | 부하 뒤 Karpenter 임시 노드가 남았는지 본다(D-051) |

### 파드 수를 조치 수단으로 쓸 때

Argo 는 `selfHeal` 이 켜져 있어(`04-platform/argocd.tf`) 매니페스트와 다르면 되돌린다.
넘기는 방법이 둘인데 **경우에 따라 다르다.**

| 경우 | 방법 | 왜 |
|---|---|---|
| 파드 수를 **다른 컨트롤러가 상시 소유**한다 | 매니페스트에서 `replicas` 를 **뺀다** | `order-worker` 가 이렇게 한다 — KEDA 가 소유하므로 선언할 기준값이 없다 |
| 파드 수를 **평소엔 선언해두고 실험 중에만 바꾼다** | `replicas` 를 적고 Argo 의 **`ignoreDifferences`** 로 그 필드만 제외한다 | S2 의 api 가 이 경우다. **정상 파드 수가 기준값이라 git 에 남아야** 하고, 조치는 그 위에서 일시적으로 움직인다 |

`ignoreDifferences` 는 Argo 가 **되돌려주지도 않는다**는 뜻이므로,
실험 종료 시 **복원은 초기화 절차가 책임진다**(위 표의 "파드 수" 행).

대상에 **HPA·KEDA 를 붙이지 않는다** — 되돌리는 주체가 하나 더 늘어난다.
지금 ScaledObject 는 `order-worker` 에만 있고 api 에는 없다.

**되돌리는 주체는 HPA·KEDA 만이 아니다.** `cue-warmer` 가 큐시트 사전 확장을 위해
`api` 의 `spec.replicas` 를 폴링해서 기준값으로 되돌린다 — 그래서 S2 는 실행 전에
워머를 세운다(4.3, T-043). **파드 수를 조치 수단으로 쓰는 시나리오를 만들 때는 그
필드를 쓰는 컨트롤러를 먼저 세어본다.**

> Agent 가 replica 수를 **자유롭게 만들어 적용하지 않는다**(D-041).
> 증설은 런북이 지정한 **한 단계**이고, 상한과 예산은 노브 카탈로그 조회로 정해진다.

---

## 4. 실행 Runbook

아래 명령은 저장소 루트 `O2-live-ai-ops`에서 실행한다. `<M-0NN 값>`은
`docs/measurements.md`에 기록된 값으로만 바꾼다. 자리표시자를 그대로 두거나 값이
없으면 실행하지 않는다.

### 4.1 공통 사전 검사

```bash
kubectl config current-context
kubectl get deploy api chat-gateway -n o2-dev -o wide
kubectl get endpointslice -n o2-dev -l kubernetes.io/service-name=api -o wide
kubectl top nodes
```

측정 단계에서는 관련 Datadog 모니터를 Downtime으로 두고, 장애 주입 직전에
Downtime을 해제한다. API 키나 모니터 ID를 저장소 스크립트에 넣지 않는다.

### 4.2 S1 — 첫 파동과 지속 고원

```bash
PROFILE=s1 \
WS_URL='wss://<현재-ALB>' \
VIEWERS='<측정 프로필>' \
SENDERS='<개인 한도 미만이 되는 발화자 수>' \
SPIKE_RPS='<M-010 기반 첫 파동 RPS>' \
SPIKE_S='<첫 파동 지속 초>' \
PLATEAU_RPS='<M-010 붕괴점 위 지속 RPS>' \
CHAT_P95_MAX_MS='<실측 복구 기준>' \
k6 run -e PROFILE -e WS_URL -e VIEWERS -e SENDERS -e SPIKE_RPS -e SPIKE_S \
  -e PLATEAU_RPS -e CHAT_P95_MAX_MS loadtest/broadcast.js
```

스크립트는 `SENDERS`, 파형, p95 기준을 생략하거나 발화자별 분당 발화가
`CHAT_RATE_PER_MIN` 이상이면 시작 전에 실패한다. 채널 제한 원복은 다음과 같다.

```bash
curl -fsS -X POST "$CHAT_GATEWAY_ADMIN_URL" \
  -H "x-admin-key: $CHANNEL_LIMIT_ADMIN_KEY" \
  -H 'content-type: application/json' \
  -d '{"broadcast_id":"bc_1042","action":"clear"}'
```

### 4.3 S2 — CPU 제한 canary

**시작 전에 `cue-warmer` 를 먼저 세운다.** 이걸 빼먹으면 실험이 조용히 무의미해진다 —
Agent 가 `api` 를 증설해도 워머가 3~5초 만에 기준값으로 되돌리고, 조치 실행기는 그
사실을 모른 채 200 을 돌려준다. 검증은 증설 전 상태를 보고 "효과 없음"으로 판정한다
(T-043). 워머는 `api` 의 `spec.replicas` 를 10초마다 폴링해서 기준값과 다르면
되돌리는데, **누가 바꿨는지는 구분하지 않는다.**

`cue-warmer` 는 Argo 의 `ignoreDifferences` 목록에 없어서 그냥 `kubectl scale` 만
하면 selfHeal 이 같은 초에 되살린다. **selfHeal 을 먼저 끄고 내린다.**

```bash
kubectl patch application o2-dev -n argocd --type merge \
  -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":false,"prune":true}}}}'
kubectl scale deploy/cue-warmer -n o2-dev --replicas=0

# 파드가 실제로 사라졌는지 확인하고 나서 진행한다.
kubectl get deploy cue-warmer -n o2-dev
```

`ignoreDifferences` 에 `cue-warmer` 를 추가하는 방법은 쓰지 않는다 — 그 값의 주인이
Git 이 아니라 사람 손이 되어, 실험 뒤 0 인 채로 잊히면 사전 확장이 조용히 죽는다.
selfHeal 토글은 되돌리는 일이 눈에 보인다는 점에서 낫다. **근본 해결은 워머가 자기가
설정한 값일 때만 되돌리게 고치는 것이고, 그러면 이 절차 자체가 없어진다.**

측정 결과를 남길 때 **"cue-warmer 정지 상태에서 측정"을 함께 적는다.** 운영에서는
워머가 켜져 있으므로 이 조건을 빼면 결과가 운영을 대표하지 못한다.

canary는 **클러스터에 배포된 현재 main Deployment**를 원본으로 읽으므로 이미지·
환경변수·ServiceAccount가 main과 같다. 로컬 `O2-live-deploy` 파일은 Argo가 먼저
새 버전을 배포하면 뒤처질 수 있어 실행 원본으로 쓰지 않는다. CPU와 probe 값은
실측 입력이 없으면 렌더링조차 막는다.

```bash
# 2026-08-26 스윕에서 확정한 값이다(measurements.md "S2 canary CPU 상한 스윕").
CANARY_CPU_LIMIT='125m' \
CANARY_READINESS_TIMEOUT_SECONDS='5' \
CANARY_READINESS_FAILURE_THRESHOLD='6' \
CANARY_LIVENESS_TIMEOUT_SECONDS='5' \
loadtest/s2-canary.sh render > /tmp/o2-s2-api-canary.yaml

kubectl diff -f /tmp/o2-s2-api-canary.yaml
kubectl apply -f /tmp/o2-s2-api-canary.yaml
kubectl rollout status deploy/api-canary -n o2-dev --timeout=180s
```

원복은 canary 제거와 main 기준값 복원 둘 다 수행한다. Argo CD는 api의
`/spec/replicas`를 무시하므로 자동 원복하지 않는다.

```bash
loadtest/s2-canary.sh remove
kubectl scale deploy/api -n o2-dev --replicas=2
kubectl rollout status deploy/api -n o2-dev --timeout=180s

kubectl scale deploy/cue-warmer -n o2-dev --replicas=1
kubectl patch application o2-dev -n argocd --type merge \
  -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":true,"prune":true}}}}'
```

### 4.4 S3 — 외부 결제 PG 지연, 지식화 전후 두 번 실행

1차와 2차에 **같은 주입값과 주문 부하 프로필**을 사용한다. 아래 자리표시자는
실측값으로 확정하기 전에는 실행하지 않는다.

```bash
# 공통 입력 — 1차와 2차에 바꾸지 않는다.
PG_DELAY_MS='<실측 후 확정>'
PG_FAIL_RATE='<실측 후 확정>'
ORDER_RATE='<주문 RPS>'
ORDER_DURATION='<알림 창보다 길게>'
ORDER_PRE_ALLOCATED_VUS='<실측값>'
ORDER_MAX_VUS='<실측값>'
CHAT_BASE_RPS='<타임세일 전 일반 채팅 RPS>'
CHAT_SALE_RPS='<타임세일 후 증가한 일반 채팅 RPS>'
CHAT_INCIDENT_RPS='<타임세일 후 결제 장애 채팅 RPS>'
CHAT_PRE_ALLOCATED_VUS='<채팅 실측값>'
CHAT_MAX_VUS='<채팅 실측값>'

# 1차 장애 주입
curl -fsS -X POST "$PG_STUB_ADMIN_URL" \
  -H "x-admin-key: $PG_STUB_ADMIN_KEY" \
  -H 'content-type: application/json' \
  -d "{\"action\":\"set\",\"delay_ms\":${PG_DELAY_MS},\"fail_rate\":${PG_FAIL_RATE}}"

# 1차 주문 부하
BASE_URL='https://<현재-ALB>' WS_URL='wss://<현재-ALB>' \
RATE="$ORDER_RATE" DURATION="$ORDER_DURATION" \
PRE_ALLOCATED_VUS="$ORDER_PRE_ALLOCATED_VUS" MAX_VUS="$ORDER_MAX_VUS" \
CHAT_BASE_RPS="$CHAT_BASE_RPS" CHAT_SALE_RPS="$CHAT_SALE_RPS" \
CHAT_INCIDENT_RPS="$CHAT_INCIDENT_RPS" \
CHAT_PRE_ALLOCATED_VUS="$CHAT_PRE_ALLOCATED_VUS" CHAT_MAX_VUS="$CHAT_MAX_VUS" \
k6 run -e BASE_URL -e WS_URL -e RATE -e DURATION -e PRE_ALLOCATED_VUS \
  -e MAX_VUS -e CHAT_BASE_RPS -e CHAT_SALE_RPS -e CHAT_INCIDENT_RPS \
  -e CHAT_PRE_ALLOCATED_VUS -e CHAT_MAX_VUS loadtest/s3-payment.js

# 사람 해결·History/Runbook 검증이 끝난 뒤 실험 환경 초기화
curl -fsS -X POST "$PG_STUB_ADMIN_URL" \
  -H "x-admin-key: $PG_STUB_ADMIN_KEY" \
  -H 'content-type: application/json' \
  -d '{"action":"clear"}'

# Datadog Monitor가 OK로 복귀하고 2차 실행 지식 상태를 확인한 뒤 같은 장애 재주입
curl -fsS -X POST "$PG_STUB_ADMIN_URL" \
  -H "x-admin-key: $PG_STUB_ADMIN_KEY" \
  -H 'content-type: application/json' \
  -d "{\"action\":\"set\",\"delay_ms\":${PG_DELAY_MS},\"fail_rate\":${PG_FAIL_RATE}}"

# 2차 주문 부하 — 1차와 같은 프로필
BASE_URL='https://<현재-ALB>' WS_URL='wss://<현재-ALB>' \
RATE="$ORDER_RATE" DURATION="$ORDER_DURATION" \
PRE_ALLOCATED_VUS="$ORDER_PRE_ALLOCATED_VUS" MAX_VUS="$ORDER_MAX_VUS" \
CHAT_BASE_RPS="$CHAT_BASE_RPS" CHAT_SALE_RPS="$CHAT_SALE_RPS" \
CHAT_INCIDENT_RPS="$CHAT_INCIDENT_RPS" \
CHAT_PRE_ALLOCATED_VUS="$CHAT_PRE_ALLOCATED_VUS" CHAT_MAX_VUS="$CHAT_MAX_VUS" \
k6 run -e BASE_URL -e WS_URL -e RATE -e DURATION -e PRE_ALLOCATED_VUS \
  -e MAX_VUS -e CHAT_BASE_RPS -e CHAT_SALE_RPS -e CHAT_INCIDENT_RPS \
  -e CHAT_PRE_ALLOCATED_VUS -e CHAT_MAX_VUS loadtest/s3-payment.js

# 2차 검증까지 끝난 뒤 주입 해제
curl -fsS -X POST "$PG_STUB_ADMIN_URL" \
  -H "x-admin-key: $PG_STUB_ADMIN_KEY" \
  -H 'content-type: application/json' \
  -d '{"action":"clear"}'
```

**세기는 "주문은 깨지는데 읽기는 사는 구간" 이다.** 동기 라우트라 uvicorn 스레드풀이
마르면서 api p95 가 전면 상승하는 것까지는 의도한 것이다(알림이 떠야 병합을 보여준다).
너무 세면 api 자체가 죽어 `pod_resource_exhaustion` 으로 오진된다 — `delay_ms` × 주문 RPS 를
스윕해 하한을 잡는다.

**확인할 것**

| 무엇 | 어떻게 |
|---|---|
| 채팅이 알림보다 **먼저** 왔는가 | Candidate 생성 시각과 Datadog 알림 시각의 차 — 0 이면 이 시나리오의 전제가 없다 |
| 두 진입이 **한 인시던트로 병합**됐는가 | 같은 `incident_id` 의 revision 증가 |
| `pg_latency_ratio` 가 1.0 에 가까운가 | 이 값이 "우리가 아니라 PG" 의 유일한 증거다 |
| 1차가 임의 조치 없이 멈췄는가 | 현재 증거·원인·active Runbook 부재·필요한 사람 조치를 보고하고 `ESCALATED`로 끝난다 |
| 지식화가 인시던트 해결과 분리됐는가 | 수동 해결 1회만으로 active 승격하지 않고 전환·원복·멱등성·오적용·실패를 별도 검증한다 |
| 2차가 History 분기를 탔는가 | 검색된 History ID와 `verified` 상태를 실행 기록에 남긴다 |
| 현재 증거를 다시 확인했는가 | 2차 Athena 결과에도 `PG-A`·`PG_TIMEOUT`·`PG_CALL`·`pg_latency_ms` 증가가 있어야 한다 |
| 실제 PG-B로 우회했는가 | `pg_provider=PG-B`, `result=SUCCESS`인 `payment.process` 이벤트를 확인한다 |
| 사용자 영향도 회복했는가 | 주문 실패율·p95와 채팅 결제 불만 파생 신호가 함께 감소해야 한다 |
| 2차 종료 사유 | `final_status: RESOLVED`. PG-A 주입은 검증이 끝날 때까지 유지한다 |

> **현재 구현 경계:** PG-A 장애 주입·이벤트와 PG-B ready·전환·원복 제어면은
> 구현돼 있다. L3 승인 배선·Runbook active 승격·History 분기와 실제 Agent E2E는
> 별도 검증 대상이며, 이 항목을 확인하기 전에는 위 2차 실행을 E2E 완료로
> 표시하지 않는다.

### 4.6 발표 도입부 클립 (라이브 화면만)

발표 맨 앞에 아키텍처 설명 없이 **사용자 화면만으로** "불만이 올라왔다가 멎는" 그림을
보여주려면 4.4 와 다른 부하 프로필이 필요하다. 4.4 의 불만 채팅은 `CHAT_INCIDENT_RPS`
고정 발화라 PG-B 우회 뒤에도 그대로 쏟아진다 — 측정에는 그게 맞지만(1차·2차 조건을
같게 유지해야 한다) 회복 장면은 안 나온다.

```bash
BASE_URL='https://<현재-ALB>' WS_URL='wss://<현재-ALB>' \
PG_STUB_ADMIN_URL='https://<현재-ALB>/api/admin/pg-stub' PG_STUB_ADMIN_KEY='<주입>' \
PG_DELAY_MS='<실측 후 확정>' PG_FAIL_RATE='<실측 후 확정>' \
ORDER_RATE='<주문 RPS>' ORDER_PRE_ALLOCATED_VUS='<실측값>' ORDER_MAX_VUS='<실측값>' \
CHAT_BASE_RPS='<타임세일 전>' CHAT_SALE_RPS='<타임세일 후>' \
CHAT_PRE_ALLOCATED_VUS='<실측값>' CHAT_MAX_VUS='<실측값>' \
RUN_DURATION='<Agent 한 바퀴보다 길게>' loadtest/s3-coldopen.sh
```

러너가 하는 일은 셋뿐이다 — **타임세일을 열고, 장애를 넣고, 끝나면 원복한다.**
PG-B 전환은 하지 않는다. 그것을 러너가 대신하면 녹화물이 연극이 된다.

| 무엇 | 어떻게 |
|---|---|
| 불만이 멎는 근거 | `COMPLAINT_ON_FAILURE_RATIO` — 실제 502를 본 VU가 불만을 쓰고, 202 복구 응답 뒤 `RECOVERY_COMPLAINT_DECAY_SECONDS`(기본 60초) 동안 발화 확률이 선형 감소한다 |
| 진입 시드 4건 | `INCIDENT_SEED_DELAY_SECONDS` 로 장애 주입 뒤로 민다. 주입 전에 시드가 나가면 아무도 실패하지 않았는데 불만이 먼저 오는 그림이 된다 |
| 타임세일 오픈 | `PENDING` 상품 하나를 `ON_SALE` 로 바꾼다. 화면의 "아직 특가가 시작되지 않았습니다" 가 구매 가능으로 바뀌는 순간이 오픈 장면이다 |
| 품절 방지 | 재고를 크게 올려 둔다. 녹화 중 `SOLD_OUT` 이 나면 결제 실패가 아니라 품절로 화면이 갈린다 |
| 원복 | 종료·중단 어느 쪽이든 PG 주입 해제와 상품 상태·재고 원복이 돌아간다. **PG-B 로 전환된 상태는 러너가 안 되돌린다** — `/api/admin/pg-provider-switch` 로 사람이 되돌린다 |

**시작 전에 사람이 확인한다.** 이 클립은 **2차 실행**을 찍는 것이다 — verified History 와
active 런북이 있어야 하고, Dify 워크플로의 `PG_PROVIDER_SWITCH_URL` 값이 채워져 있어야
하며, L3 승인을 누를 사람이 대기해야 한다. 셋 중 하나라도 없으면 1차 실행이 되어
`ESCALATED` 로 끝나고 결제는 낫지 않는다.

**실제 소요는 12~18분이다**(채팅 선행 + 알림 창 + 진단 + 승인 + 전환 + 검증 대기).
클립은 그중 도배 고원 구간을 배속으로 압축해 만든다.

### 4.5 다음 실행 전 확인

```bash
test "$(kubectl get deploy api -n o2-dev -o jsonpath='{.spec.replicas}')" = '2'
test -z "$(kubectl get deploy api-canary -n o2-dev --ignore-not-found -o name)"
kubectl get endpointslice -n o2-dev -l kubernetes.io/service-name=api -o wide

# S2 를 돌렸으면 여기서 반드시 확인한다 (4.3).
test "$(kubectl get deploy cue-warmer -n o2-dev -o jsonpath='{.spec.replicas}')" = '1'
test "$(kubectl get application o2-dev -n argocd -o jsonpath='{.spec.syncPolicy.automated.selfHeal}')" = 'true'
```

마지막으로 Datadog 모니터가 `OK`인지, k6 `dropped_iterations`가 허용 범위인지,
Karpenter 임시 노드가 남지 않았는지 확인한 뒤 다음 시나리오로 넘어간다.
