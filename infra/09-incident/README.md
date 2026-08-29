# 09-incident

모니터링 팀이 소유하는 Incident 생성 runtime이다. Datadog·Chat-derived 관측 신호를
`agent.trigger.v1`로 받아 결정론적으로 병합하고, 검증된 `agent.incident.v1` revision만
Agent Invocation Queue에 보낸다.

## 소유 경계

이 스택이 소유한다.

- Incident Signal Queue와 DLQ
- Datadog Source Adapter
- Incident Correlator와 rule mapping
- Incident State와 signal claim
- Agent Invocation Queue와 DLQ
- Incident pipeline alarm topic과 alarms

`infra/06-agent`가 소유한다.

- Agent Invocation Queue consumer
- authoritative revision 확인
- 실행 ledger와 Incident/action lock
- Dify 호출과 진단·복구 workflow

`infra/08-chat-signal`의 Chat Candidate Source Adapter는 현재 별도 스택에 남아 있지만,
출력은 이 스택의 Signal Queue로만 보낸다. Candidate 생성과 원문 개인정보 수명은 계속
`08-chat-signal`이 소유한다.

## 기본 안전 상태

**아래는 변수 기본값이다. 현재 dev 적용값은 `terraform.tfvars` 가 원본이며 실행
게이트는 켜져 있다** — Adapter·Correlator 실행 `true`, `incident_shadow_mode=false`,
`incident_operational_handoff_approved=true`, allowlist 7개 monitor.

- Datadog Source Adapter execution: `false`
- Correlator execution/event source: `false`
- 합성 allowlist: empty
- 운영 correlation window: 420초 (D-073, 적용됨)
- 구조화 evidence 입력: `assessment_input`의 type·scope·sample·freshness·NO_DATA 검증
- Incident 상태: severity material change, sustained recovery, strong exception, cooldown, reopen
- 운영 전환: `incident_shadow_mode=false`와 `incident_operational_handoff_approved=true`를 함께 요구

`incident_recovery_window_seconds`, `incident_cooldown_seconds`,
`incident_reopen_window_seconds`의 기본값은 실측 전 0이다. dev 적용값은 각각
300·300·1800초다(D-082). Operational mode에서는 세 값이 모두 0보다 커야
plan이 통과한다. 승인 플래그만 켜거나 운영 monitor를 Webhook에 붙이는 단독 변경은 금지한다.
- Agent/Dify 직접 호출 권한: 없음

## apply 순서

신규 환경에서는 `09-incident`를 `06-agent`와 `08-chat-signal`보다 먼저 적용한다.

```text
01 → 02 → (03 ∥ 05 ∥ 06-data ∥ 07) → 09-incident → (04 ∥ 06-agent ∥ 08-chat-signal)
```

여기서 `06-data`는 기존 `infra/06-datastream`을 뜻한다. `06-agent`와 번호가 겹치므로
경로 전체를 확인한다.

## 기존 dev state migration — 완료됨

> **이 절은 이력이다.** 이관은 끝났고 이 스택의 backend key 는 `incident/` 다.
> 같은 상황이 다시 생길 때의 절차로 남긴다.

현재 dev의 Incident 리소스는 `dify/terraform.tfstate`가 소유한다. 코드 디렉터리만 옮긴
상태에서 `09-incident apply`를 실행하면 같은 물리 이름을 새로 만들려 하고, `06-agent plan`은
기존 리소스 destroy를 제안할 수 있다. **state migration 전에는 두 스택 모두 apply하지 않는다.**

이전 대상은 다음 범주다.

- `aws_sqs_queue.agent_entry*`와 redrive policy
- `aws_sqs_queue.agent_invocation*`와 redrive policy
- `aws_dynamodb_table.incident_state`
- `aws_lambda_function.incident_correlator`와 IAM/log/event source/alarm
- `aws_lambda_function.datadog_source_adapter`와 IAM/log/Function URL/alarm
- Signal/Invocation Queue alarms

Incident 전용 SNS topic은 신규 리소스이므로 state 이동 대상이 아니다.

실행 절차:

1. 두 backend lock 소유자가 없는지 확인한다.
2. `dify/terraform.tfstate`를 로컬에 백업하고 대상 address를 `terraform state list`로 확정한다.
3. `incident/terraform.tfstate`를 초기화한다.
4. 대상 리소스만 새 state로 이동한다. 물리 리소스의 create/destroy는 없어야 한다.
5. `09-incident plan`에서 SNS topic 외 create가 없는지 확인한다.
6. `06-agent plan`에서 Incident 리소스 destroy가 0인지 확인한다.
7. 두 실행 gate와 event source가 모두 disabled인지 재확인한다.
8. Queue/DLQ message count와 Incident State item을 확인한 뒤에만 apply한다.

state 이동 명령은 실제 `state list` 결과와 backup 파일을 확인한 세션에서 작성한다. 문서에
추정 address나 식별자를 고정해 복사 실행하지 않는다.

## 검증

```powershell
terraform -chdir=infra/09-incident fmt -check
terraform -chdir=infra/09-incident validate -no-color
$env:PYTHONUTF8='1'
python infra/09-incident/lambda/test_incident_correlator.py
python infra/09-incident/lambda/test_datadog_source_adapter.py
python scripts/validate-agent-contracts.py
```

실제 `plan`과 `apply`는 로컬에서 순서대로 수행한다. CI는 실행하지 않는다.
