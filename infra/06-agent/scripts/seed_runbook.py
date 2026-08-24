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
                "risk_level": "L2",
                "expected_effect": "reject chat sends above per-channel total rate; propagation p95 recovers post-application",
                "blast_radius": "single broadcast_id — 정상 사용자 발화가 거부될 수 있음(부작용, 조치 자체의 목적)",
                "parameters_schema": {
                    "broadcast_id": {
                        "type": "string",
                        "required": True,
                        "source": "observability.alert.broadcast_id",
                    },
                    "action": {
                        "type": "string",
                        "required": True,
                        "source": "static:set",
                    },
                    # TEMP: 강도 선택지. 문서(0.5)는 "강도 선택"을 대가
                    # 게이트에서 사람이 고른다고 정했는데, 여기 값 3개는
                    # 실측 없이 지어낸 자리값이다 — 실측 뒤 조정.
                    "limit": {
                        "type": "int",
                        "required": True,
                        "source": "human_selected",
                        "options_temp": [200, 500, 1000],
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
