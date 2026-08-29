# Runbook 실행 카탈로그 형식과 위험도

이 문서는 **Agent가 조회하고 실행 후보를 고르는 기계 판독용 Runbook
카탈로그**를 설명한다. 사람 검증 이력에서 라벨별로 만들기로 한
`infra/06-agent/runbooks/<label>.md`와는 다른 자산이다. 후자는 아직 없다.

> **7절 대조표는 2026-08-25 snapshot 이다.** 그 뒤 코드 원본이 바뀌었다 —
> 갱신분은 7.3 에 있다. 두 절을 함께 읽는다.

2026-08-25 기준으로 다음 둘을 대조했다.

- 코드 원본: `infra/06-agent/scripts/seed_runbook.py`
- 실테이블: Terraform output으로 찾은 DynamoDB Runbook 테이블의 읽기 전용 scan

코드와 실테이블이 다르므로 아래에서는 **코드 원본**, **실테이블**, **실제 조회
동작**을 구분한다. 숫자와 목록은 해당 날짜의 snapshot이며, 실행 원본은 계속
`seed_runbook.py`다.

## 1. 결론

1. 카탈로그는 DynamoDB 한 테이블에 `DEF`, `ACTION`, `KNOB` 세 종류 아이템을
   저장한다.
2. Runbook 상태는 `active`, `draft`, `retired`다. Lookup은 `active`의 조치만
   반환한다. 다만 상태가 없는 구형 아이템은 하위 호환 때문에 `active`로 본다.
3. `risk_level`은 현재 **위험을 계산하는 모델이 아니라 승인 경로를 고르는
   라우팅 값**이다. 저장소에는 L1/L2/L3를 부여하는 판정 척도가 없다.
4. 실제 Guardrail이 읽는 값은 ACTION 최상위의 `risk_level`이다. KNOB 안의
   동명 필드는 현재 Guardrail 판정에 쓰이지 않는다.
5. KNOB의 가역성·예산·사전 조건은 조회 응답에 붙지만, 저장소 Dify DSL은 이를
   결정론적으로 검사하지 않는다. 따라서 “노브 메타데이터가 있다”와 “안전
   게이트가 동작한다”는 같은 말이 아니다.
6. 실테이블에는 코드 원본에 없는 구형 Runbook 네 개가 상태 없이 남아 있다.
   현행 Lookup 규칙으로는 네 개 모두 실행 후보가 된다.

## 2. 이름이 같은 두 Runbook 자산

| 자산 | 목적 | 원본 | 현재 상태 |
|---|---|---|---|
| 실행 카탈로그 | RCA별 조치 후보, 실행 대상, 검증 기준을 Agent에 제공 | `scripts/seed_runbook.py` | 구현·시딩됨 |
| 사람용 라벨 Runbook | 사람이 검증한 원인별 설명과 절차를 exact key로 조회 | `runbooks/<label>.md` 계획 | 디렉터리와 문서 없음 |

`labels.txt`와 `infra/06-agent/README.md`의 “런북이 아직 없다”는 두 번째 자산을
뜻한다. DynamoDB 실행 카탈로그가 없다는 뜻이 아니다.

## 3. 저장과 조회 흐름

```text
seed_runbook.py의 RUNBOOKS / KNOBS
  -> DynamoDB put_item / update_item
  -> runbook_lookup Lambda가 rca_type으로 Query
  -> active DEF + active ACTION만 반환하고 ACTION에 KNOB를 중첩
  -> Dify Node 11-B가 actions와 success_criteria만 보존
  -> Planner가 action_id 선택
  -> Guardrail이 ACTION.risk_level만 읽어 AUTO / APPROVAL / DENY 결정
```

중요한 경계는 다음과 같다.

- DynamoDB는 스키마리스다. 키 이외 필드의 타입·필수 여부를 테이블이 보장하지
  않는다.
- `validate_catalog()`도 현재 RCA/status 중복과 KNOB 참조 존재 여부만 검사한다.
  필수 필드, `risk_level` 허용값, ACTION-KNOB 위험도 일치, 실테이블 drift는
  검사하지 않는다.
- Lookup은 KNOB가 없어도 200으로 응답하고 해당 ACTION의 `knob` 키만 생략한다.
  호출자가 이를 거부하지 않으면 메타데이터 없는 조치도 다음 단계로 간다.

## 4. 아이템 형식

### 4.1 공통 키

| 필드 | 의미 |
|---|---|
| `rca_type` | 파티션 키. 통제 어휘 RCA 또는 예약값 `KNOB` |
| `sk` | 정렬 키. `DEF`, `ACTION#{action_id}`, `KNOB#{action_id}` 중 하나 |

### 4.2 DEF — Runbook 정의

`rca_type` 하나에 최대 한 개다.

| 필드 | 현재 용도 |
|---|---|
| `runbook_id` | 사람이 식별하는 Runbook ID |
| `runbook_kind` | `generic`, `dedicated`, `scenario` |
| `status` | `active`, `draft`, `retired` |
| `promotion_blockers` | 주로 draft의 미충족 검증·승인 조건 |
| `success_criteria.conditions` | 고정 threshold와 비교하는 절대 조건 |
| `success_criteria.baseline_conditions` | PRE baseline 필드를 `relative_to`로 가리키는 상대 조건 |
| `success_criteria.verification_metrics` | 검증에 사용할 지표 목록. 일부 정의에만 있음 |
| `success_criteria.logic` | 현재 `AND` 사용 |

### 4.3 ACTION — 실행 후보

| 필드 | 현재 용도 |
|---|---|
| `action_id` | 조치 식별자 |
| `runbook_id`, `status` | 새 형식에서는 DEF 값을 복사. 구형 아이템에는 없을 수 있음 |
| `risk_level` | Guardrail 승인 라우팅의 실제 입력 |
| `implementation_status` | `not_implemented` 표시용. Lookup과 Guardrail은 이 값으로 필터하지 않음 |
| `expected_effect` | Planner가 비교할 기대 효과 |
| `blast_radius` | Planner 입력과 Slack 승인 화면의 영향 범위 문구 |
| `parameters_schema` | 파라미터 타입·필수 여부·값 출처 |
| `execution_target` | HTTP method, endpoint, 선택적 인증 헤더 이름 |
| `stabilization_wait_seconds` | 안정화 대기 의도. 현재 값은 `None`이고 저장소 DSL도 실제 대기하지 않음 |

`parameters_schema.*.source`는 현재 다음 관례를 사용한다.

| 형식 | 의미 |
|---|---|
| `static:<value>` | 카탈로그가 고정한 값 |
| `observability.<path>` | 진단 context에서 가져올 값 |
| `incident_context.<path>` | Incident context에서 가져올 값 |

`retired_action_ids`는 DynamoDB 필드가 아니다. 시딩할 때 기존 ACTION을 삭제하지
않고 `status=retired`로 갱신하기 위한 코드 원본 전용 목록이다.
현재 `update_item`에는 기존 아이템 존재 조건이 없으므로 대상 ACTION이 원래
없어도 키와 status만 가진 sparse retired marker를 새로 만든다. live의
`ACTION#pg_read_replica_failover`가 이 형태였다. 따라서 retired 표식이 있다고
항상 원문 ACTION이 보존됐다고 해석하면 안 된다.

### 4.4 KNOB — 조치 안전성 메타데이터

`rca_type="KNOB"`, `sk="KNOB#{action_id}"`로 저장한다.

| 분류 | 필드 |
|---|---|
| 대상 | `action_id`, `target`, `max_blast_radius` |
| 가역성 | `knob_reversible`, `user_effect_reversible`, `rollback_method`, `rollback_call` |
| 실행 예산 | `max_duration_seconds`, `preapproved_budget`, `cooldown_seconds`, `max_attempts`, `measured` |
| 안전 판정 재료 | `preconditions`, `verification_metrics`, `diagnostic_contamination`, 선택적 오염 설명 |
| 중복 필드 | `risk_level` |

`measured=False`와 `None`은 “0”이 아니라 **아직 실측·승인되지 않음**이다. 현재
Guardrail은 이 상태를 자동으로 거부하지 않는다.

## 5. Lookup 응답 계약

응답의 외형은 다음과 같다.

```json
{
  "rca_type": "...",
  "runbook_id": "... | null",
  "runbook_status": "active | draft | retired | missing",
  "success_criteria": "object | null",
  "actions": [
    {
      "action_id": "...",
      "risk_level": "L1 | L2 | L3",
      "knob": "object, KNOB가 있을 때만"
    }
  ],
  "knobs": []
}
```

| DEF 상태 | `success_criteria` | `actions` |
|---|---|---|
| `active` | 반환 | active ACTION만 반환 |
| `draft` | `null` | `[]` |
| `retired` | `null` | `[]` |
| 없음 | `null` | `[]` |
| status 필드 없음 | `active`로 간주 | status 없는 ACTION도 active로 간주 |

Dify Node 11-B는 이 응답에서 `runbook_id`, `runbook_status`, 최상위 `knobs`를
버리고 `actions`, `success_criteria`, `rca_category`만 다음 노드로 넘긴다.
ACTION에 이미 중첩된 `knob`는 남지만 Guardrail은 읽지 않는다.

## 6. 위험도 항목의 실제 동작

### 6.1 현재 라우팅 표

저장소 DSL의 Guardrail 코드를 그대로 해석하면 다음과 같다.

| 조건 | Guardrail 결과 | 실제 의미 |
|---|---|---|
| 선택한 `action_id`가 available actions에 없음 | `DENY`, `UNKNOWN` | 실행 차단 |
| ACTION `risk_level=L1` | `AUTO` | 승인 없이 실행 경로 |
| ACTION `risk_level=L2` | `AUTO` | 승인 없이 실행 경로. L1과 제어 차이 없음 |
| ACTION `risk_level=L3` | `APPROVAL` | Slack 승인 뒤 실행 경로 |
| ACTION에 `risk_level` 필드 없음 | `L3` 기본값 후 `APPROVAL` | 누락을 차단하지 않고 사람에게 넘김 |
| 알 수 없는 값 | `DENY` | 실행 차단 |

따라서 현재 `L1`과 `L2`는 운영 제어상 같은 등급이다. 비용 상한, 최대 지속
시간, 재시도 횟수, 사전 조건 또는 가역성을 다르게 강제하지 않는다.

### 6.2 위험도와 혼동하면 안 되는 것

- 장애 심각도와 `risk_level`은 다르다. 후자는 **조치 위험도**다.
- `blast_radius`는 문장이고, 현재 비교·상한 검사가 없다.
- Slack 승인 relay는 ACTION ID, `risk_level`, `blast_radius`만 보여 준다. 실제로
  치환된 파라미터, 기대 효과, precondition 결과, 원복 방법, 검증 기준은 승인
  화면에 나오지 않는다.
- `implementation_status=not_implemented`는 조회 차단 조건이 아니다. 지금은 해당
  S3 Runbook 전체가 draft라 반환되지 않는 것으로만 보호된다.
- `diagnostic_contamination`을 사용하는 Action State Lambda는 있으나 저장소 Dify
  DSL에서 호출하지 않는다. 현재 DSL의 Stabilization Gate도 실제 대기 없이
  `ready=true`를 반환한다.

### 6.3 현재 부여값에서 추론 가능한 경향

척도 정의는 없지만 기존 값은 대체로 다음 의도를 보인다. 이는 **현행 계약이
아니라 관찰 결과**다.

| 값 | 기존 항목에서 보이는 경향 | 현재 강제되는 것 |
|---|---|---|
| L1 | 단일 대상의 제한된 변경, 쉽게 원복할 수 있다고 본 조치 | `AUTO`뿐 |
| L2 | 서비스 설정·파드·consumer 등 더 넓은 조치 | `AUTO`뿐 |
| L3 | 배포 rollback, 정상 사용자 요청 거부처럼 사람 판단이 필요한 조치 | Slack 승인뿐 |

같은 조치라도 범위·파라미터·관측 근거가 달라지면 위험은 달라질 수 있으므로,
`action_id` 이름만 보고 등급을 부여하면 안 된다.

## 7. 2026-08-25 카탈로그 대조 결과

### 7.1 코드 원본

| Runbook | 종류 | status | ACTION 위험도 |
|---|---|---|---|
| `chat_channel_overload` | dedicated | active | `limit_channel_volume` L3 |
| `RB-API-LATENCY-001` | generic | draft | `scale_api_one_step` L1 |
| `RB-API-POD-RESOURCE-SKEW` | dedicated | draft | `isolate_slow_pod` L2 |
| `pg_external_failure` | scenario | draft | PG-A→PG-B 우회 L3. **2026-08-27 에 `active` 로 승격됐다 — 7.3 참조** |
| `legacy_read_path_degraded` | generic | retired | `hold_read_path_degraded` L1 |

코드 원본의 KNOB 정의는 (이 snapshot 시점) 6개다. 그러나 전체 dry-run이 실제 시딩 대상으로 고르는
것은 Runbook ACTION과 연결된 5개뿐이다. Runbook 없이 보존하려던
`set_read_path_degraded`는 `selected_action_ids` 필터에서 빠져 현재 시더로는 기록되지
않는다. 이는 “런북 없는 조치도 KNOB 파티션에 둔다”는 D-067 의도와 다르다.

또한 `limit_channel_volume`은 ACTION L3인데 KNOB `risk_level`은 L2다. 현재
Guardrail 기준 유효값은 ACTION의 L3지만, S1 KNOB를 다시 시딩하면 같은 응답 안에
서로 다른 등급이 공존한다.

### 7.2 실테이블 snapshot

읽기 전용 scan 결과는 `DEF 9개 + ACTION 24개 + KNOB 4개 = 37개`였다.

현행 Lookup의 status fallback을 적용하면 다음 다섯 RCA가 active다.

| active RCA | ACTION과 위험도 | live KNOB |
|---|---|---|
| `queue_backlog` | `consumer_scale_up` L1, `batch_size_increase` L2 | 없음 |
| `deploy_defect` | `feature_flag_disable` L1, `pod_restart` L2, `rollback` L3 | 없음 |
| `cache_invalidation_storm` | `target_cache_warm` L1, `full_cache_warm` L2, `ttl_extension` L2 | 없음 |
| `traffic_spike_overload` | `rate_limit_noncritical` L1, `autoscale_bump` L2, `queue_shed_low_priority` L2 | 없음 |
| `chat_channel_overload` | `limit_channel_volume` L3 | 없음 |

이 가운데 앞의 네 RCA는 코드 원본 `RUNBOOKS`에 없다. 다섯 RCA의 DEF와 ACTION은
모두 `status`가 없어서 하위 호환 규칙으로 active가 된다. Agent 후보로 반환된다는
뜻이며, 실제 외부 변경 여부는 Dify에 해당 execution target이 연결됐는지에 따라
달라진다.

나머지는 다음과 같다.

- draft DEF 3개, draft ACTION 4개: S2 두 개와 결제 PG S3
- retired DEF 1개, retired ACTION 8개: 옛 read-path와 교체된 S2/PG 조치
- KNOB 4개: S2 2개와 결제 PG 2개뿐
- 코드 원본에 있는 `limit_channel_volume`, `set_read_path_degraded` KNOB는 실테이블에
  없다

전체 시드를 다시 실행해도 코드에 없는 구형 네 RCA는 자동으로 삭제·retire되지
않는다. 현재 시더는 자신이 아는 항목을 put/update할 뿐 orphan을 정리하지 않는다.

### 7.3 2026-08-27 이후 코드 원본 변경분

`seed_runbook.py` 가 바뀌었고 7.1 표는 그 이전 상태다. 실테이블(7.2) 재대조는
아직 안 했다.

| 항목 | 7.1 시점 | 현재 코드 원본 |
|---|---|---|
| Runbook 수 | 5 | **6** |
| `traffic_spike_overload` | 실테이블에만 있던 구형 RCA | **코드 원본에 편입**(generic, `active`). `autoscale_bump` L2 는 S2 scale-executor 재사용이고 `queue_shed_low_priority`·`rate_limit_noncritical` 은 실행기가 없어 retired |
| `pg_external_failure` | `draft` | **`active`**. 근거는 코드의 `promotion_evidence` — 같은 주입(`delay_ms=1200`·`fail_rate=0.9`)에서 PG-A 5,401/6,001 실패·p95 1.32s 대 PG-B 실패 0·p95 102ms 를 라이브로 가르고 사람이 verified History 로 확정했다 |
| KNOB 정의 수 | 6 | **10** (`expand_payment_client_pool`, `tighten_payment_timeout_retry`, `autoscale_bump`, `queue_shed_low_priority`, `rate_limit_noncritical` 추가) |
| S2 복구 판정 | — | `traffic_spike_overload`·`RB-API-LATENCY-001` 둘 다 `p99_ms <= 50` 축으로 이동(2026-08-27) |

**`pg_external_failure` 승격은 시나리오 전제를 건드린다.** `scenario-experiment.md`
0.7 의 S3 1차 실행은 "실행 가능한 active Runbook 이 없어 `ESCALATED`" 가 성립
조건이다. 지금 상태로 1차를 다시 찍으면 Lookup 이 후보를 돌려주므로 그 장면이
재현되지 않는다. 1차 재촬영 전에는 이 런북을 다시 `draft` 로 내리거나, 격리
데이터셋으로 분리해야 한다.

`limit_channel_volume` 의 ACTION L3 / KNOB L2 불일치는 그대로다.

## 8. 위험도 관련 주요 리스크

| 우선순위 | 확인된 리스크 | 영향 |
|---|---|---|
| 높음 | 실테이블 구형 네 Runbook이 source에 없고 status fallback으로 active | 코드 리뷰·재구축 원본 밖 조치가 Agent 후보로 계속 반환됨 |
| 높음 | 모든 live active ACTION에 KNOB가 없고, Guardrail도 KNOB 조건을 검사하지 않음 | precondition·예산·가역성 검증 없이 L1/L2가 AUTO로 분기될 수 있음 |
| 높음 | L1/L2/L3 부여 척도가 없음 | 리뷰어마다 같은 조치에 다른 등급을 부여해도 검출할 수 없음 |
| 높음 | L3 승인 화면에 실제 파라미터와 원복·검증 정보가 없음 | 사람 승인이 안전성 검토가 아니라 이름 확인에 그칠 수 있음 |
| 중간 | ACTION과 KNOB에 `risk_level`이 중복되고 실제 불일치가 존재 | 소비 경로가 바뀌는 순간 승인 여부가 바뀔 수 있음 |
| 중간 | Runbook 없는 `set_read_path_degraded` KNOB가 시더 필터에서 제외됨 | KNOB 전체 조회로 독립 조치를 찾는다는 D-067 경로가 재현되지 않음 |
| 중간 | 없는 과거 ACTION도 `update_item`이 sparse retired marker로 생성 | “원문 보존”으로 오해할 수 있고 감사 시 실제 과거 필드가 없음 |
| 중간 | 누락 risk를 DENY가 아니라 L3 승인으로 보냄 | 불완전한 카탈로그를 사람이 승인해 실행할 수 있음 |
| 중간 | `validate_catalog()`가 필드·enum·cross-item·live drift를 검사하지 않음 | 잘못된 형식이 시딩·조회 시점까지 조용히 통과함 |
| 중간 | 안정화 대기와 노브 예산 값이 미측정·미연결 | 조치 효과가 나타나기 전 실패 판정하거나 과도한 조치를 유지할 수 있음 |

## 9. 위험도 척도 도입 권장안 — 아직 미적용

아래는 현재 구현 설명이 아니라 다음 변경에서 채택할 기준안이다. 채택 전에는
L1/L2/L3의 의미로 인용하지 않는다.

1. 위험도는 장애 심각도가 아니라 **구체적인 파라미터까지 확정된 조치의 잔여
   위험**으로 평가한다.
2. 사용자 영향 가역성, 제어 가역성, 최대 영향 범위, 데이터·보안·금전 영향,
   비용·지속시간 예산, 진단 오염, 사전 조건과 원복 검증 중 가장 높은 축을
   최종 등급으로 쓴다.
3. L1은 단일 대상·완전 가역·사전 승인 예산 안의 제한된 조치, L2는 가역적이지만
   서비스 설정·용량·토폴로지를 바꾸는 조치, L3는 사용자 영향이 비가역이거나
   데이터·권한·금전·광범위 가용성에 영향을 줄 수 있는 조치로 둔다.
4. 필수 증거가 없거나 값이 미측정이면 등급을 낮게 추정하지 않고 `DENY` 또는
   별도 `UNASSESSED`로 막는다. 사람 승인은 누락된 precondition을 대신하지 않는다.
5. 실행 위험도 원본은 ACTION 하나로 두고, KNOB에는 객관적 판정 재료만 둔다.
   시딩 검증기가 그 재료와 ACTION 등급의 모순을 검사한다.

## 10. 정리 순서

1. 실테이블의 status 없는 DEF/ACTION을 코드 원본으로 편입할지 retire할지 결정한다.
2. 모든 항목에 명시적 status를 시딩하고 live-source drift 검사를 통과시킨 뒤
   Lookup의 status-missing fallback을 제거한다.
3. ACTION을 `risk_level` 단일 원본으로 정하고 KNOB의 중복 필드를 제거한다.
4. 전체 시딩에서는 독립 KNOB도 기록하고, 선택 시딩의 KNOB 포함 규칙을 명시한다.
5. 위험도 enum·필수 필드·ACTION-KNOB 연결·`implementation_status`를
   `validate_catalog()`에서 fail-closed로 검증한다.
6. Guardrail 앞에서 precondition, 측정·예산, 최대 시도, 실제 파라미터를
   결정론적으로 검사한다.
7. L3 Slack 메시지에 실제 파라미터, 기대 효과, 영향 범위, 원복 방법, 검증·중단
   기준을 표시한다.
8. 별도 재현·오적용·원복 검증과 운영자 승인을 거친 draft만 active로 승격한다.

## 11. 재확인 명령

코드 원본 검증은 AWS 없이 실행할 수 있다.

```bash
uv run infra/06-agent/scripts/seed_runbook.py --dry-run
```

실테이블은 AWS SSO 자격이 유효할 때 Terraform output으로 이름을 구한 뒤 읽기
전용 scan으로 대조한다. 계정 ID나 endpoint를 문서에 고정하지 않는다.

```bash
RUNBOOK_TABLE_NAME="$(terraform -chdir=infra/06-agent output -raw runbook_table_name)"
aws dynamodb scan \
  --table-name "$RUNBOOK_TABLE_NAME" \
  --projection-expression 'rca_type, sk, runbook_id, #s, action_id, risk_level' \
  --expression-attribute-names '{"#s":"status"}' \
  --no-cli-pager
```
