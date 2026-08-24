#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3", "botocore[crt]"]
# ///
"""Runbook 카탈로그 시딩. 테이블의 원본은 DB 가 아니라 이 스크립트다 —

    python3 scripts/seed_runbook.py

테이블이 날아가도 이걸 다시 돌리면 그대로 복구된다 (runbook.tf 의 PITR
안 거는 이유와 같은 전제). 그래서 이 파일이 곧 카탈로그 문서다 — 별도로
스키마를 어딘가에 다시 적지 않는다.

★ 사람이 로컬에서 SSO 자격으로 돌린다. Node 11(runbook_lookup Lambda)은
  읽기만 하고, 이 스크립트가 스스로 채우는 걸 대신하지 않는다 (runbook.tf).
★ rca_type 은 labels.txt 의 통제 어휘 그대로 써야 한다. 여기서 오타를 내면
  Node 11 이 조회해도 조용히 빈 결과만 돌아온다 — 에러가 안 난다.
★ 이미 있는 rca_type 을 다시 돌리면 그대로 덮어쓴다(put_item). 지우고
  다시 만드는 게 아니라 값만 최신으로 맞추는 것이므로 여러 번 돌려도 안전하다.
"""

from decimal import Decimal

import _history as H
import boto3

# ── 카탈로그 ───────────────────────────────────────────────────────
#
# S1(chat_channel_overload)·S2(pod_load_skew)·S3 는 docs/scenario-experiment.md
# 의 시연 시나리오 셋이다. 나머지 rca_type 은 시나리오 설계가 끝나면 각자
# 항목으로 채운다 — labels.txt 의 통제 어휘 전체가 여기 다 있어야
# label-report.py 의 "쓸 때 됐다" 경고가 의미가 있다.

RUNBOOKS = [
    {
        # S2(scenario-experiment.md 0.6·2.2) 최종 진단 — canary 격리로
        # 검증하고, 증설분 원복 후에도 유지되는지가 이 라벨의 통과 기준.
        "rca_type": "pod_load_skew",
        "success_criteria": {
            # 절대 SLO — architecture.md 12.1 계약, M-009 실측이 이 기준으로 판정됨.
            "conditions": [
                {"metric": "p95_ms", "comparison": "<=", "threshold": 800},
                {"metric": "error_rate", "comparison": "<=", "threshold": Decimal("0.01")},
            ],
            # 기준선 상대(D-058) — canary 붙이기 전 정상 파드만의 p95 가
            # baseline_p95_ms 로 Baseline 상태에서 기록된다(0.4). 격리 후,
            # 그리고 증설분 원복 후에도 그 값 이하를 유지해야 "용량이 아니라
            # 그 파드였다"는 근거가 된다(2.2 최종 재검증).
            # 허용 오차는 아직 안 잰다 — 정하는 대로 이 값을 채운다.
            "baseline_conditions": [
                {"metric": "p95_ms", "comparison": "<=", "relative_to": "baseline_p95_ms"},
            ],
            "logic": "AND",
        },
        "actions": [
            {
                # 격리 = 문제 Deployment 의 replicas 를 0 으로. Pod 만 지우면
                # Deployment 가 같은 스펙으로 즉시 재생성하므로 Deployment
                # 자체를 조정해야 한다. 조치 실행기(infra/06-agent/
                # action_executor.tf, lambda/scale_deployment.py)가 이걸
                # 하나로 처리한다 — 원복(rollback)도 같은 실행기를 replicas
                # 값만 바꿔 다시 부르는 것이라 별도 action_id 가 없다.
                "action_id": "isolate_slow_pod",
                "risk_level": "L2",
                "expected_effect": "target deployment replicas -> 0, removed from Service endpoints",
                "blast_radius": "single deployment, o2-dev namespace",
                "parameters_schema": {
                    "namespace": {
                        "type": "string",
                        "required": True,
                        "source": "static:o2-dev",
                    },
                    "deployment": {
                        "type": "string",
                        "required": True,
                        "source": "observability.pod.deployment_name",
                    },
                    "replicas": {
                        "type": "int",
                        "required": True,
                        "source": "static:0",
                    },
                },
                "execution_target": {
                    "method": "POST",
                    # Dify 환경변수 SCALE_EXECUTOR_URL 을 그대로 쓴다 — 다른
                    # 액션들처럼 공유 ACTION_API_BASE_URL 뒤에 붙는 상대
                    # 경로가 아니라, 이 조치 전용 Lambda Function URL
                    # 통째다(infra/06-agent/action_executor.tf 의
                    # scale_executor_url output).
                    "endpoint": "$SCALE_EXECUTOR_URL",
                },
                "stabilization_wait_seconds": None,
            },
        ],
    },
    {
        # S1(scenario-experiment.md 0.5) — 채널 총량이 감당 선을 넘어
        # 전파 지연이 생긴 케이스. 조치는 채널 총량 노브 하향 —
        # 별도 Lambda 가 아니라 apps/chat-gateway 의 `/ws/admin/channel-limit`
        # 라우트다(D-061). chat-gateway 가 이미 Valkey 에 붙어 있어서
        # 새 인프라 없이 라우트 하나로 끝난다.
        #
        # ★★ 아래 threshold 는 전부 임시값이다 — 실측이 아니다. ★★
        #   2.1 절이 명시한 대로 "정상 사용자 차단률 상한이 없으면 성공
        #   판정 자체가 성립하지 않는다"가 원칙이지만, 부하테스트로 그 값을
        #   재는 건 이 작업 범위 밖이라 자리만 채워 둔다(사용자 지시로
        #   임시값 허용). 실측 나오면 이 표를 실측값으로 덮어쓸 것 —
        #   숫자를 지어내지 않는다는 AGENTS.md 원칙의 예외이므로 굵게 표시.
        #   metric 이름(chat_propagation_p95_ms)도 Datadog/warm path 쪽
        #   실제 필드명과 맞는지 담당자 확인 필요 — o2warm/metrics.py 에는
        #   아직 채팅 전파 지표가 없다.
        "rca_type": "chat_channel_overload",
        "success_criteria": {
            "conditions": [
                # TEMP: 채팅 전파 계약 기준이 문서에 없다(2.1). read-path 계약
                # (800ms, architecture.md 12.1)을 자리채움으로 그대로 썼다.
                {"metric": "chat_propagation_p95_ms", "comparison": "<=", "threshold": 800},
                # TEMP: "이 값이 없으면 성공 판정이 성립 안 함"이라고 문서가
                # 못박은 바로 그 값. 5% 는 근거 없는 임시 상한이다.
                {"metric": "block_rate", "comparison": "<=", "threshold": Decimal("0.05")},
                # 실측값 — M-010 2파드 안전선(2026-08-21). 파드 수를 바꾸면
                # 다시 재야 한다(측정 조건, measurements.md M-010).
                {"metric": "items_per_sec", "comparison": "<=", "threshold": 20000},
            ],
            # 기준선 상대(D-058) — S1은 "복구"가 아니라 "감내 가능한 열화"라
            # (2.1) 절대 임계만으론 자연 회복과 조치 효과를 못 가른다.
            "baseline_conditions": [
                {"metric": "chat_propagation_p95_ms", "comparison": "<=", "relative_to": "baseline_propagation_p95_ms"},
            ],
            "logic": "AND",
        },
        "actions": [
            {
                "action_id": "limit_channel_volume",
                # L3 - 정상 사용자 발화를 일부러 거부하는 조치라 "대가 게이트"
                # 취지대로 실행 전 사람 승인(Slack)을 거치게 한다. 강도(limit)
                # 자체는 아직 사람이 직접 고르는 UI가 없어(options_temp 임시값,
                # Dify Parameter Resolver 참고) 승인이 그 대신 실행 여부를 확인한다.
                "risk_level": "L3",
                "expected_effect": "reject chat sends above per-channel total rate; propagation p95 recovers post-application",
                "blast_radius": "single broadcast_id — 정상 사용자 발화가 거부될 수 있음(부작용, 조치 자체의 목적)",
                "parameters_schema": {
                    "broadcast_id": {
                        "type": "string",
                        "required": True,
                        # observability(Warm API 응답)에는 alert가 없다 - 실제 조회로
                        # 확인함(2026-08-24). broadcast_id는 진단 컨텍스트 쪽에 있다.
                        "source": "incident_context.broadcast_id",
                    },
                    "action": {
                        "type": "string",
                        "required": True,
                        "source": "static:set",
                    },
                    # 강도 선택 UI를 안 만들기로 했다(Parameter Resolver가
                    # human_selected 소스를 처리할 방법이 없어서 실행 자체가
                    # Guardrail에서 막혔었음). 사람 개입은 Slack 승인
                    # (risk_level L3)이 대신한다 — "강도를 고른다"가 아니라
                    # "이 고정값으로 실행할지 승인/거부"로 단순화.
                    #
                    # TEMP: 500은 실측 없는 자리값이다(options_temp 중간값).
                    # 부하테스트로 실제 안전선 나오면 그 값으로 덮어쓸 것.
                    "limit": {
                        "type": "int",
                        "required": True,
                        "source": "static:500",
                    },
                },
                "execution_target": {
                    "method": "POST",
                    # 별도 실행기 Lambda 가 아니다 — chat-gateway 서비스 자체의
                    # 라우트다(main.ts handleChannelLimitAdmin). ALB 인그레스가
                    # `/ws` 를 prefix 로 이미 chat-gateway 에 매핑해 뒀으므로
                    # (O2-live-deploy frontend-ingress.yaml) 그 ALB 주소 +
                    # /ws/admin/channel-limit 가 전체 경로다. Dify 환경변수
                    # CHAT_GATEWAY_ADMIN_URL 로 그 완전한 주소를 받는다.
                    "endpoint": "$CHAT_GATEWAY_ADMIN_URL",
                    # 다른 액션들의 x-api-key 와 다르다 — chat-gateway 는
                    # x-admin-key 헤더를 본다(CHANNEL_LIMIT_ADMIN_KEY 값과 비교,
                    # config.ts). Secrets Manager 를 안 거치고 kubectl 로
                    # o2-dev 네임스페이스에 직접 넣은 값이다 — git 에 없다.
                    "auth_header": "x-admin-key",
                },
                "stabilization_wait_seconds": None,
            },
        ],
    },
    {
        # S3(scenario-experiment.md 0.7) — 읽기 급증인데 사람인지 자동화인지
        # 서버 증거로 못 가른다. 원인을 안 가르는 게 정답이라 other로 둔다.
        # 조치는 양쪽에 다 안전한 것 하나뿐 — 응답 내용은 안 바뀌고 부가
        # 이벤트 발행만 끈다(D-062). 다른 액션들처럼 여러 후보 중 고르는
        # 절차가 없다, 후보가 원래 1개다.
        "rca_type": "other",
        "success_criteria": {
            # TEMP: block_rate는 아직 warm path에 없는 지표다(o2warm/metrics.py
            # 확인 필요) — S1의 chat_propagation_p95_ms와 같은 처지, 자리만
            # 채워 둔다. 실측/실제 필드명 확인 후 덮어쓸 것.
            "conditions": [
                {"metric": "block_rate", "comparison": "<=", "threshold": 0},
            ],
            "logic": "AND",
        },
        "actions": [
            {
                "action_id": "hold_read_path_degraded",
                "risk_level": "L1",
                "expected_effect": "read-path 부가 이벤트 발행만 중단, 응답(재고/가격) 불변",
                "blast_radius": "single broadcast_id — 정상 사용자 차단 없음(조치 설계상 항상 0)",
                "parameters_schema": {
                    "broadcast_id": {
                        "type": "string",
                        "required": True,
                        # observability(Warm API 응답)에는 alert가 없다 - 실제 조회로
                        # 확인함(2026-08-24). broadcast_id는 진단 컨텍스트 쪽에 있다.
                        "source": "incident_context.broadcast_id",
                    },
                    "action": {
                        "type": "string",
                        "required": True,
                        "source": "static:set",
                    },
                },
                "execution_target": {
                    "method": "POST",
                    # S1/S2와 같은 패턴 — 공유 base 뒤 상대경로가 아니라
                    # 이 조치 전용 라우트 전체 주소를 Dify 환경변수로 받는다.
                    "endpoint": "$API_ADMIN_URL",
                    "auth_header": "x-admin-key",
                },
                "stabilization_wait_seconds": None,
            },
        ],
    },
    # TODO: rca_type 추가 — cache_cold_start
    # TODO: rca_type 추가 — queue_backlog_worker_shortage
    # TODO: rca_type 추가 — queue_backlog_db_lock_wait
    # TODO: rca_type 추가 — queue_poison_message
    # TODO: rca_type 추가 — db_connection_pool_exhaustion
    # TODO: rca_type 추가 — db_lock_contention
    # TODO: rca_type 추가 — node_memory_insufficient
    # TODO: rca_type 추가 — cpu_credit_exhausted
    # TODO: rca_type 추가 — monitor_false_alarm
]


# 노브 카탈로그가 사는 PK. lambda/runbook_lookup.py 의 같은 이름 상수와
# 반드시 같아야 한다 — 어긋나면 조회가 조용히 빈 목록을 준다.
KNOB_PARTITION = "KNOB"

# ── 노브 카탈로그 ────────────────────────────────────────────────────────
#
# 게이트 진입을 **결정론적으로** 판정하기 위한 표다. LLM 이 "이건 위험해 보인다"
# 로 정하면 테이크마다 달라진다 — 이 표를 조회해서 정한다.
#
# rca_type 축이 아니라 노브 축이다. 같은 노브가 여러 rca_type 의 조치로 쓰일 수
# 있고, S3 처럼 **런북이 아예 없는 시나리오의 조치**도 있어야 하기 때문이다
# (scenario-experiment.md 0.2 "런북을 썼다고 알려진 장애가 되는 것이 아니다").
#
# 저장 위치는 같은 runbook 테이블의 `rca_type="KNOB"` 파티션이다. 테이블도
# 조회 Lambda 도 IAM 도 새로 만들지 않는다 — PK 값 하나만 다르다.
#
# ★★ 숫자 넷은 안 쟀다 — max_duration_seconds · preapproved_budget ·
#    cooldown_seconds · max_attempts. `None` 으로 두고 measured=False 를 같이
#    싣는다. 지어낸 값을 넣으면 다음 사람이 그 위에 판정을 얹는다
#    (AGENTS.md "숫자를 지어내지 않는다"). 실측되면 measurements.md 에 남기고
#    여기를 그 값으로 덮어쓴다. ★★
#
# ★ risk_level 의 L1/L2/L3 척도는 저장소 어디에도 정의가 없다. 기존 ACTION
#   아이템이 쓰던 값을 그대로 옮겼다 — 척도 정의는 별도 과제다.

KNOBS = [
    {
        "action_id": "limit_channel_volume",
        "target": "chat-gateway · broadcast 단위",
        # 키를 지우면 노브 자체는 원상복구된다.
        "knob_reversible": True,
        # 거부당한 발화는 되돌릴 수 없다. 이미 못 한 말이다.
        "user_effect_reversible": False,
        "max_blast_radius": "single broadcast_id · 그 방송의 전체 시청자",
        "max_duration_seconds": None,
        "preapproved_budget": None,
        "cooldown_seconds": None,
        "max_attempts": None,
        "measured": False,
        "risk_level": "L2",
        # 인입이 줄어 채팅 관련 지표가 통째로 바뀐다.
        "diagnostic_contamination": True,
        "rollback_method": "immediate_delete",
        "rollback_call": {"endpoint": "$CHAT_GATEWAY_ADMIN_URL", "action": "clear"},
        "verification_metrics": ["chat_propagation_p95_ms", "block_rate", "items_per_sec"],
        # 결정론적 사전 검사. 통과 못 하면 자동 실행하지 않는다.
        "preconditions": [
            {"check": "broadcast_is_live", "source": "observability.alert.broadcast_id"},
            {"check": "no_active_channel_limit", "source": "cfg:channel_limit:{broadcast_id}"},
        ],
    },
    {
        "action_id": "isolate_slow_pod",
        "target": "o2-dev 네임스페이스의 Deployment 하나",
        "knob_reversible": True,
        # 격리 중 그 파드가 받던 요청은 나머지 파드로 간다. 사용자에게 남는
        # 영구 손실이 없다.
        "user_effect_reversible": True,
        "max_blast_radius": "single deployment, o2-dev namespace",
        "max_duration_seconds": None,
        "preapproved_budget": None,
        "cooldown_seconds": None,
        "max_attempts": None,
        "measured": False,
        "risk_level": "L2",
        "diagnostic_contamination": True,
        "rollback_method": "previous_value",
        "rollback_call": {"endpoint": "$SCALE_EXECUTOR_URL", "note": "replicas 를 이전 값으로"},
        "verification_metrics": ["p95_ms", "error_rate"],
        # 이게 없으면 서비스를 통째로 내릴 수 있다 (scenario-experiment.md 3절).
        "preconditions": [
            {"check": "healthy_capacity_at_or_above_safe_minimum"},
            {"check": "target_is_not_the_only_capacity"},
            {"check": "outlier_observed_repeatedly"},
            {"check": "target_resolves_to_exactly_one_deployment"},
        ],
    },
    {
        # S3 는 런북이 없다 — 그래서 이 노브는 rca_type 파티션에 집이 없다.
        # 노브 카탈로그를 rca_type 축에서 떼어낸 이유가 이것이다.
        "action_id": "set_read_path_degraded",
        "target": "api · broadcast 단위 읽기 경로",
        "knob_reversible": True,
        # 응답 내용(재고·가격)이 안 바뀐다. 차단이 0 이라 되돌릴 사용자 영향이
        # 없다 — S3 의 "안 고르고 버티기" 가 성립하는 근거다.
        "user_effect_reversible": True,
        "max_blast_radius": "single broadcast_id · 응답 내용 불변, 차단 0",
        "max_duration_seconds": None,
        "preapproved_budget": None,
        "cooldown_seconds": None,
        "max_attempts": None,
        "measured": False,
        "risk_level": "L1",
        # ★ 오염 방향이 다른 둘과 반대다. 이 노브는 `inventory.check` 발행을
        #   건너뛰므로 **관측이 사라진다** — cache_hit 계열 지표가 비는 것을
        #   "캐시가 죽었다" 로 읽으면 안 된다.
        "diagnostic_contamination": True,
        "diagnostic_contamination_note": "inventory.check 발행이 멈춰 cache_hit 계열 지표가 빈다",
        "rollback_method": "immediate_delete",
        "rollback_call": {"endpoint": "$API_ADMIN_URL", "action": "clear"},
        # 효율 축(포화점 이동)은 아직 못 넣는다 — 안 쟀다.
        "verification_metrics": ["block_rate", "api_cpu_per_request"],
        "preconditions": [
            {"check": "broadcast_is_live", "source": "observability.alert.broadcast_id"},
            {"check": "read_path_not_already_degraded", "source": "cfg:read_path_degraded:{broadcast_id}"},
        ],
    },
]


def main():
    known = set(H.labels())
    for entry in RUNBOOKS:
        if entry["rca_type"] not in known:
            # labels.txt 가 원본이라 여기서 지어낸 값은 애초에 못 들어가게 막는다.
            raise SystemExit(
                f"'{entry['rca_type']}' 는 labels.txt 에 없다 — 오타이거나 "
                "새 라벨을 labels.txt 에 먼저 추가해야 한다."
            )

    table_name = H.tf_output("runbook_table_name")
    table = boto3.resource("dynamodb").Table(table_name)

    for entry in RUNBOOKS:
        rca_type = entry["rca_type"]

        table.put_item(
            Item={
                "rca_type": rca_type,
                "sk": "DEF",
                "success_criteria": entry["success_criteria"],
            }
        )
        for action in entry["actions"]:
            table.put_item(
                Item={
                    "rca_type": rca_type,
                    "sk": f"ACTION#{action['action_id']}",
                    **action,
                }
            )
        print(f"✓ {rca_type} — DEF + ACTION {len(entry['actions'])}개")

    # 노브는 rca_type 축이 아니라 노브 축이라 KNOB 파티션에 따로 넣는다.
    known_actions = {a["action_id"] for e in RUNBOOKS for a in e["actions"]}
    for knob in KNOBS:
        table.put_item(
            Item={
                "rca_type": KNOB_PARTITION,
                "sk": f"KNOB#{knob['action_id']}",
                **knob,
            }
        )
        # 런북에 없는 노브는 정상이다(S3). 반대로 런북이 참조하는 노브가
        # 카탈로그에 없으면 게이트가 판정할 근거를 못 찾는다.
        orphan = "" if knob["action_id"] in known_actions else "  (런북 없음 — S3 처럼 조립하는 경우)"
        print(f"✓ KNOB#{knob['action_id']}{orphan}")

    missing = known_actions - {k["action_id"] for k in KNOBS}
    if missing:
        raise SystemExit(
            f"런북이 참조하는데 노브 카탈로그에 없다: {sorted(missing)} — "
            "게이트 진입을 판정할 근거가 없어진다."
        )

    print(f"\n완료. {table_name} 에 rca_type {len(RUNBOOKS)}개 · 노브 {len(KNOBS)}개 시딩됨.")


if __name__ == "__main__":
    main()
