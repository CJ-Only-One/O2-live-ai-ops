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
    # TODO: rca_type 추가 — chat_channel_overload (S1, scenario-experiment.md 0.5)
    #   채널 총량 제한 액션(4.1 절)이 아직 코드에 없고, 정상 사용자 차단률
    #   실측도 없다(2.1 — "이 값이 없으면 성공 판정 자체가 성립하지 않는다").
    #   액션 구현 + 부하테스트로 measurements.md 에 실측을 남긴 다음에 채운다.
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

    print(f"\n완료. {table_name} 에 {len(RUNBOOKS)}개 rca_type 시딩됨.")


if __name__ == "__main__":
    main()
