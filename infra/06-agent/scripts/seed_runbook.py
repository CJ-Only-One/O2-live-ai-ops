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
# 지금은 인프라를 띄우는 단계라 cache_invalidation_storm 하나만 채운다.
# 나머지 10개 rca_type 은 시나리오 설계가 끝나면 각자 항목으로 채운다 —
# labels.txt 의 통제 어휘 전체가 여기 다 있어야 label-report.py 의
# "쓸 때 됐다" 경고가 의미가 있다.

RUNBOOKS = [
    {
        "rca_type": "cache_invalidation_storm",
        "success_criteria": {
            "conditions": [
                {"metric": "p95_ms", "comparison": "<=", "threshold": 250},
                {"metric": "cache_hit_rate", "comparison": ">=", "threshold": Decimal("0.80")},
                {"metric": "error_rate", "comparison": "<=", "threshold": Decimal("0.03")},
            ],
            "logic": "AND",
        },
        "actions": [
            {
                "action_id": "target_cache_warm",
                "risk_level": "L1",
                "expected_effect": "warm only featured product keys",
                "blast_radius": "single product",
                "parameters_schema": {
                    "product_ids": {
                        "type": "list<string>",
                        "required": True,
                        "source": "observability.cache.featured_product_id",
                    }
                },
                "execution_target": {
                    "method": "POST",
                    "endpoint": "/actions/target-cache-warm",
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
    # TODO: rca_type 추가 — pod_load_skew
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
