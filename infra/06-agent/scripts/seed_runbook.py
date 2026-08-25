#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3", "botocore[crt]"]
# ///
"""Runbook 카탈로그 시딩. 테이블의 원본은 DB 가 아니라 이 스크립트다 —

    python3 scripts/seed_runbook.py

테이블이 날아가도 이걸 다시 돌리면 그대로 복구돼야 한다 (runbook.tf 의 PITR
안 거는 이유와 같은 전제). 이 파일이 실행 데이터의 원본이다.
`docs/runbook-catalog.md`는 사람이 읽는 형식·위험도 분석과 live drift snapshot이며,
시딩값의 두 번째 원본이 아니다.

★ 사람이 로컬에서 SSO 자격으로 돌린다. Node 11(runbook_lookup Lambda)은
  읽기만 하고, 이 스크립트가 스스로 채우는 걸 대신하지 않는다 (runbook.tf).
★ rca_type 은 labels.txt 의 통제 어휘 그대로 써야 한다. 여기서 오타를 내면
  Node 11 이 조회해도 조용히 빈 결과만 돌아온다 — 에러가 안 난다.
★ 이미 있는 rca_type 을 다시 돌리면 그대로 덮어쓴다(put_item). 지우고
  다시 만드는 게 아니라 값만 최신으로 맞추는 것이므로 여러 번 돌려도 안전하다.
"""

import argparse
from decimal import Decimal

import _history as H
import boto3

# ── 카탈로그 ───────────────────────────────────────────────────────
#
# `status=active` 만 Runbook Lookup 이 Agent 에 돌려준다. `draft` 는 같은
# 테이블에 시딩하되 자동 조회·실행에서 제외한다(D-077). 한 번의 복구 결과를
# 곧바로 active 전용 런북으로 올리지 않기 위한 경계다.
#
# 현재 시나리오에서 필요한 네 항목:
#   S1  chat_channel_overload                 active 전용
#   S2  RB-API-LATENCY-001                    draft 범용
#   S2  RB-API-POD-RESOURCE-SKEW              draft 전용 후보
#   S3  pg_external_failure                   draft 시나리오 런북
#
# S2 범용은 실험 검증 증거가, S2 전용 후보는 승격 증거가, S3 는 실제 조치
# 실행기가 아직 없다. 시딩은 하되 이 세 항목을 active 로 가장하지 않는다.

RUNBOOKS = [
    {
        # S2(scenario-experiment.md 0.6·2.2) 최종 진단 — canary 격리로
        # 검증하고, 증설분 원복 후에도 유지되는지가 이 라벨의 통과 기준.
        "runbook_id": "RB-API-POD-RESOURCE-SKEW",
        "runbook_kind": "dedicated",
        "status": "draft",
        "rca_type": "pod_load_skew",
        "promotion_blockers": [
            "repeatability evidence missing",
            "misapplication impact not verified",
            "rollback and baseline recovery evidence missing",
            "operator approval missing",
        ],
        "success_criteria": {
            # 절대 SLO — architecture.md 12.1 계약, M-009 실측이 이 기준으로 판정됨.
            "conditions": [
                {"metric": "latency_p95", "comparison": "<=", "threshold": 800},
                {"metric": "overall_failure_rate", "comparison": "<=", "threshold": Decimal("0.01")},
            ],
            # 기준선 상대(D-058) — canary 붙이기 전 정상 파드만의 p95 가
            # baseline_p95_ms 로 Baseline 상태에서 기록된다(0.4). 격리 후,
            # 그리고 증설분 원복 후에도 그 값 이하를 유지해야 "용량이 아니라
            # 그 파드였다"는 근거가 된다(2.2 최종 재검증).
            # 허용 오차는 아직 안 잰다 — 정하는 대로 이 값을 채운다.
            "baseline_conditions": [
                {"metric": "latency_p95", "comparison": "<=", "relative_to": "baseline_p95_ms"},
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
                        "source": "static:api-canary",
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
                "stabilization_wait_seconds": 60,
            },
        ],
    },
    {
        # S2 1차 조치. 원인을 확정하기 전에 서비스 지연이라는 증상만으로
        # 정상 api Deployment 를 2 -> 3 한 단계만 늘린다. 현재 실행기는
        # 절대 replicas 값을 받으므로 static:3 으로 경계를 고정한다.
        #
        # 등록 기준 자체는 코드로 표현했지만 실제 canary 반복 재현·원복
        # 증거가 아직 없어 draft 다(scenario-readiness.md 2.3).
        "runbook_id": "RB-API-LATENCY-001",
        "runbook_kind": "generic",
        "status": "draft",
        "rca_type": "pod_resource_exhaustion",
        "promotion_blockers": [
            "bounded scale action not validated in the S2 experiment",
            "rollback and final baseline recovery evidence missing",
            "owner review and approval missing",
        ],
        "success_criteria": {
            "conditions": [
                {"metric": "latency_p95", "comparison": "<=", "threshold": 800},
                {"metric": "overall_failure_rate", "comparison": "<=", "threshold": Decimal("0.01")},
            ],
            "baseline_conditions": [
                {"metric": "latency_p95", "comparison": "<=", "relative_to": "baseline_p95_ms"},
            ],
            "verification_metrics": ["latency_p95", "overall_failure_rate"],
            "logic": "AND",
        },
        "actions": [
            {
                "action_id": "scale_api_one_step",
                "risk_level": "L1",
                "expected_effect": "api deployment replicas 2 -> 3; p50 may improve while a slow-pod p95 outlier remains",
                "blast_radius": "api deployment only, o2-dev namespace; one additional replica",
                "parameters_schema": {
                    "namespace": {
                        "type": "string",
                        "required": True,
                        "source": "static:o2-dev",
                    },
                    "deployment": {
                        "type": "string",
                        "required": True,
                        "source": "static:api",
                    },
                    "replicas": {
                        "type": "int",
                        "required": True,
                        "source": "static:3",
                    },
                },
                "execution_target": {
                    "method": "POST",
                    "endpoint": "$SCALE_EXECUTOR_URL",
                },
                "stabilization_wait_seconds": 60,
            },
        ],
        # 실테이블에만 남아 있던 옛 범용 액션. 새 S2 흐름의 "한 단계 증설
        # 1회"와 다르므로 삭제하지 않고 retired 로 표시해 조회에서 제외한다.
        "retired_action_ids": [
            "horizontal_scale_up",
            "memory_limit_increase",
            "unhealthy_pod_restart",
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
        #
        #   2026-08-24 데이터팀 회신(specification/2026-08-24-AIAgent-
        #   시나리오테스트.md)으로 필드명 정리됨, 같은 날 observability
        #   telemetry 마이그레이션(olavvn, c6a846b)에서 실제로 구현됨:
        #   - block_rate → channel_block_rate 로 개명 확정됐지만 아직 Warm
        #     API에 안 붙어있다(chat.send 의 failure_code=CHANNEL_LIMITED
        #     로 데이터팀이 계산해 노출할 예정). 지금 실제로 존재하는 이름은
        #     여전히 block_rate 라 그걸 쓴다 — 개명되면 이 표도 같이 고칠 것.
        #   - chat_propagation_p95_ms 후보였던 서버측 지표는 olavvn 쪽
        #     telemetry 마이그레이션에서 chat_fanout_p95(수락→fanout
        #     publish)로 이미 구현됨. 실제 end-to-end 전파는 별도(합성
        #     카나리아) 지표로 간다.
        "runbook_id": "chat_channel_overload",
        "runbook_kind": "dedicated",
        "status": "active",
        "rca_type": "chat_channel_overload",
        # 2026-08-25: 원래 필드명(chat_fanout_p95/block_rate)은 낡은 이름이었다.
        # olavvn의 telemetry 작업으로 실제 구현된 이름은
        # chat_propagation_p95_ms/channel_block_rate다(o2.chat.propagation
        # Datadog 메트릭, apps/chat-gateway/src/telemetry.ts, hot-proxy
        # /v1/hot/datadog/metric) — Dify DSL 22-G→22-H→22-I→22-J 체인도
        # verification_shape까지 연결 완료(같은 날, 한 번 끊겼던 걸 복원함).
        # 그래도 실 부하(loadtest/s1-e2e.sh) 없이는 표본 부족으로 이 필드가
        # null일 수 있어, RESOLVED까지 실측 검증된 p95_ms/error_rate를
        # OR로 같이 둔다 — 부하 없어도 데모가 죽지 않게 하는 안전망이다.
        # 실 부하 재현으로 chat_propagation_p95_ms가 안정적으로 채워지는 게
        # 확인되면 뒤의 안전망 두 조건은 정리해도 된다.
        "success_criteria": {
            "conditions": [
                {"metric": "chat_propagation_p95_ms", "comparison": "<=", "threshold": 800},
                {"metric": "channel_block_rate", "comparison": "<=", "threshold": Decimal("0.05")},
                {"metric": "p95_ms", "comparison": "<=", "threshold": 500},
                {"metric": "error_rate", "comparison": "<=", "threshold": Decimal("0.05")},
            ],
            "logic": "OR",
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
        # 2026-08-25 추가 — 실테이블에는 이미 있었지만(코드 원본 누락,
        # runbook-catalog.md 6번) 이 스크립트엔 없었다. error_rate 조건은
        # 뺐다 — overall_failure_rate가 표본 부족으로 자주 null이라 AND
        # 조건이 구조적으로 통과 불가능했다(실측으로 확인).
        "runbook_id": "traffic_spike_overload",
        "runbook_kind": "generic",
        "status": "active",
        "rca_type": "traffic_spike_overload",
        "success_criteria": {
            "conditions": [
                {"metric": "p95_ms", "comparison": "<=", "threshold": 350},
            ],
            "logic": "AND",
        },
        "actions": [
            {
                # autoscale_bump이라는 이름의 mock 엔드포인트였다가, 이미
                # 실제로 동작하는 S2 scale-executor를 재사용하도록 바꿨다
                # (namespace/deployment/replicas 파라미터만 다르고 같은
                # Lambda). 신규 실행기를 안 만든 이유는 action-design-
                # s1-s2-s3.md 공통 원칙 2번과 같다.
                "action_id": "autoscale_bump",
                "risk_level": "L2",
                "expected_effect": "api Deployment replicas를 4로 늘려 HPA 반응 전에 여유를 확보(scale-executor 재사용, 실제 patch)",
                "blast_radius": "service pod count",
                "parameters_schema": {
                    "namespace": {"type": "string", "required": True, "source": "static:o2-dev"},
                    "deployment": {"type": "string", "required": True, "source": "static:api"},
                    "replicas": {"type": "int", "required": True, "source": "static:4"},
                },
                "execution_target": {
                    "method": "POST",
                    "endpoint": "$SCALE_EXECUTOR_URL",
                },
            },
            {
                # TEMP: Action Handler 없어 mock. 실제 큐 서비스가 생기면
                # 그쪽 엔드포인트로 교체.
                "action_id": "queue_shed_low_priority",
                "risk_level": "L2",
                "expected_effect": "drop or defer low-priority queued work to protect latency-sensitive paths",
                "blast_radius": "background job queue",
                "parameters_schema": {
                    "queue": {"type": "string", "required": True, "source": "static:low_priority"},
                },
                "execution_target": {
                    "method": "POST",
                    "endpoint": "/actions/queue-shed",
                },
            },
            {
                # TEMP: 위와 같은 이유로 mock.
                "action_id": "rate_limit_noncritical",
                "risk_level": "L1",
                "expected_effect": "throttle low-priority endpoints to protect checkout path",
                "blast_radius": "non-critical API traffic",
                "parameters_schema": {
                    "limit_rps": {"type": "int", "required": True, "source": "static:50"},
                    "scope": {"type": "string", "required": True, "source": "static:non_critical"},
                },
                "execution_target": {
                    "method": "POST",
                    "endpoint": "/actions/rate-limit",
                },
            },
        ],
    },
    {
        # 새 S3(scenario-experiment.md 0.7) — 외부 결제 PG 지연은 우리
        # 시스템의 풀·타임아웃 조정으로 근본 해결되지 않는다. 조치 둘을 한
        # 번씩 시도하고 같은 RCA 로 후보가 소진되면 멈추는 경로다.
        #
        # 실제 payment stub·Action Handler 가 아직 없어 draft 다. 수치를
        # 지어내지 않고 "기준선 복귀"만 성공 조건으로 둔다. 외부 PG 지연을
        # 유지하는 실험에서는 두 조치 모두 이 조건을 통과하지 않아야 정상이다.
        "runbook_id": "pg_external_failure",
        "runbook_kind": "scenario",
        "status": "draft",
        "rca_type": "pg_external_failure",
        "promotion_blockers": [
            "mock payment PG stub deployment and live validation missing",
            "payment action handler endpoints not implemented",
            "rollback and candidate-exhaustion E2E evidence missing",
        ],
        "success_criteria": {
            "baseline_conditions": [
                {"metric": "latency_p95", "comparison": "<=", "relative_to": "baseline_latency_p95"},
                {"metric": "overall_failure_rate", "comparison": "<=", "relative_to": "baseline_overall_failure_rate"},
            ],
            "verification_metrics": ["latency_p95", "overall_failure_rate", "pg_latency_ratio"],
            "logic": "AND",
        },
        "actions": [
            {
                "action_id": "expand_payment_client_pool",
                "risk_level": "L2",
                "implementation_status": "not_implemented",
                "expected_effect": "increase local payment-client concurrency; external PG latency itself is unchanged",
                "blast_radius": "checkout payment client configuration",
                "parameters_schema": {
                    "service": {
                        "type": "string",
                        "required": True,
                        "source": "observability.service",
                    },
                    "change": {
                        "type": "string",
                        "required": True,
                        "source": "static:one_bounded_step",
                    },
                },
                "execution_target": {
                    "method": "POST",
                    "endpoint": "/actions/payment-client-pool-expand",
                },
                "stabilization_wait_seconds": None,
            },
            {
                "action_id": "tighten_payment_timeout_retry",
                "risk_level": "L2",
                "implementation_status": "not_implemented",
                "expected_effect": "fail fast and bound retries; external PG latency itself is unchanged",
                "blast_radius": "checkout payment timeout and retry policy",
                "parameters_schema": {
                    "service": {
                        "type": "string",
                        "required": True,
                        "source": "observability.service",
                    },
                    "change": {
                        "type": "string",
                        "required": True,
                        "source": "static:bounded_fail_fast",
                    },
                },
                "execution_target": {
                    "method": "POST",
                    "endpoint": "/actions/payment-timeout-retry-tighten",
                },
                "stabilization_wait_seconds": None,
            },
            {
                # 2026-08-25 회의 결정 — 위 둘(client pool·timeout/retry)은
                # 방어 조치라 PG-A 자체가 느린 근본 원인을 못 고친다. 이건
                # 다르다 — 목업 PG 스텁(apps/api/app/services/payment.py)의
                # 활성 provider를 PG-B로 바꿔 "다른 게이트웨이로 우회"를
                # 실제로 재현한다. 결제 경로 전환이라 L3(Slack 승인 필수).
                "action_id": "switch_pg_provider",
                "risk_level": "L3",
                "implementation_status": "implemented",
                "expected_effect": "route payments to PG-B instead of PG-A; bypasses whatever is slow on PG-A rather than just tolerating it",
                "blast_radius": "service-wide checkout payments (global provider switch, not scoped to a single broadcast_id)",
                "parameters_schema": {
                    "action": {
                        "type": "string",
                        "required": True,
                        "source": "static:set",
                    },
                },
                "execution_target": {
                    "method": "POST",
                    "endpoint": "$PG_PROVIDER_SWITCH_URL",
                },
                "stabilization_wait_seconds": None,
            },
        ],
        # 기존 pg_external_failure 는 PG를 PostgreSQL로 해석한 액션이었다.
        # 새 결제 PG 시나리오에서는 의미가 달라 삭제 대신 retired 처리한다.
        "retired_action_ids": [
            "pg_circuit_open",
            "pg_query_timeout_tighten",
            "pg_read_replica_failover",
            "pg_retry_backoff_widen",
        ],
    },
    {
        # D-076 에서 시연 시나리오에서는 빠졌지만 read-path 보호 자산은
        # 보존하기로 했다. `other` catch-all 이 자동 실행하는 것은 위험하므로
        # 정의와 노브는 남기되 retired 로 시딩해 조회에서는 제외한다.
        "runbook_id": "legacy_read_path_degraded",
        "runbook_kind": "generic",
        "status": "retired",
        "rca_type": "other",
        "success_criteria": {
            # 2026-08-24 데이터팀 회신(specification/2026-08-24-AIAgent-
            # 시나리오테스트.md 4.3)으로 원래 있던 block_rate<=0 조건을
            # 뺐다 — 이 조치는 설계상 사용자를 절대 차단하지 않으므로
            # (D-062) block_rate는 조치 성패와 무관하게 항상 0이라 아무것도
            # 검증하지 못한다는 지적. 대신 데이터팀이 제안한 조합으로
            # 바꿨다: 조치 플래그가 실제로 켜져 있는지 + 부가 이벤트가
            # 줄었는지 + 응답 지연·오류율이 악화되지 않았는지.
            #
            # TEMP: 2026-08-24 직접 코드 확인(infra/06-datastream/warm/src/
            # o2warm/metrics.py) 결과 — latency_p95·overall_failure_rate는
            # 이미 derive() 가 계산해 내놓는 실재 필드다(문서의 "미구현"
            # 설명과 달리 이 둘은 이미 있음). 진짜 없는 건
            # read_path_degraded_active, inventory_check_rate 둘뿐 —
            # metrics.py 전체에 두 이름 다 없다. 필드명은 문서가 제안한
            # 이름을 그대로 썼고, 실제 구현 시 이름이 다르면 여기도 맞춰
            # 고칠 것.
            # 또한 baseline_conditions 자체가 Dify Verify 노드 코드에서
            # 아직 읽히지 않는다(o2-aiops-workflow.yml 확인, D-058 스키마는
            # 있지만 평가 로직 미연결) — 이 조건들은 현재 데이터가 있어도
            # 실행 시 무시된다. 별도로 고쳐야 함.
            # "재고·가격 응답 계약 유지"는 수치 조건이 아니라 액션 자체의
            # 설계(응답 내용 불변, D-062)로 이미 보장돼 별도 조건을 안 뒀다.
            "conditions": [
                {"metric": "read_path_degraded_active", "comparison": "==", "threshold": True},
            ],
            "baseline_conditions": [
                {"metric": "inventory_check_rate", "comparison": "<=", "relative_to": "baseline_inventory_check_rate"},
                {"metric": "latency_p95", "comparison": "<=", "relative_to": "baseline_latency_p95"},
                {"metric": "overall_failure_rate", "comparison": "<=", "relative_to": "baseline_overall_failure_rate"},
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
# ★ risk_level 의 L1/L2/L3 부여 척도는 아직 없다. 현재 실제 동작과
#   중복·불일치는 docs/runbook-catalog.md 및 D-079를 본다. 기존 ACTION
#   아이템이 쓰던 값을 그대로 옮겼고, Guardrail은 ACTION 쪽 값만 읽는다.

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
        # 서버 fanout 완료와 합성 consumer E2E는 서로 다른 지표다. 자동 검증은
        # 항상 수집되는 서버측 논리 지표를 쓰고 E2E는 k6 수용 시험에서 확인한다.
        "verification_metrics": ["chat_fanout_p95", "block_rate", "items_per_sec"],
        # 결정론적 사전 검사. 통과 못 하면 자동 실행하지 않는다.
        "preconditions": [
            {"check": "broadcast_is_live", "source": "observability.alert.broadcast_id"},
            {"check": "no_active_channel_limit", "source": "cfg:channel_limit:{broadcast_id}"},
        ],
    },
    {
        "action_id": "scale_api_one_step",
        "target": "o2-dev/api Deployment 2 -> 3",
        "knob_reversible": True,
        "user_effect_reversible": True,
        "max_blast_radius": "api deployment only · one additional replica",
        "max_duration_seconds": None,
        "preapproved_budget": None,
        "cooldown_seconds": None,
        # 원인 미확정 상태의 범용 런북은 같은 인시던트에서 한 번만 쓴다.
        # 측정값이 아니라 반복 금지 정책이라 1을 명시한다.
        "max_attempts": 1,
        "measured": False,
        "risk_level": "L1",
        "diagnostic_contamination": True,
        "rollback_method": "previous_value",
        "rollback_call": {"endpoint": "$SCALE_EXECUTOR_URL", "note": "replicas 를 이전 값으로"},
        "verification_metrics": ["latency_p95", "overall_failure_rate"],
        "preconditions": [
            {"check": "target_deployment_is_api"},
            {"check": "current_replicas_equal_normal_baseline"},
            {"check": "node_headroom_for_one_api_pod"},
            {"check": "no_hpa_or_keda_owns_api_replicas"},
            {"check": "no_previous_attempt_in_incident"},
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
        "verification_metrics": ["latency_p95", "overall_failure_rate"],
        # 이게 없으면 서비스를 통째로 내릴 수 있다 (scenario-experiment.md 3절).
        "preconditions": [
            {"check": "healthy_capacity_at_or_above_safe_minimum"},
            {"check": "target_is_not_the_only_capacity"},
            {"check": "outlier_observed_repeatedly"},
            {"check": "target_resolves_to_exactly_one_deployment"},
        ],
    },
    {
        "action_id": "expand_payment_client_pool",
        "target": "api payment client configuration",
        "knob_reversible": True,
        "user_effect_reversible": True,
        "max_blast_radius": "checkout payment client only",
        "max_duration_seconds": None,
        "preapproved_budget": None,
        "cooldown_seconds": None,
        "max_attempts": 1,
        "measured": False,
        "risk_level": "L2",
        "diagnostic_contamination": True,
        "rollback_method": "previous_value",
        "rollback_call": {"endpoint": "/actions/payment-client-pool-restore"},
        "verification_metrics": ["latency_p95", "overall_failure_rate", "pg_latency_ratio"],
        "preconditions": [
            {"check": "payment_action_handler_available"},
            {"check": "external_payment_pg_evidence_present"},
            {"check": "change_is_one_bounded_step"},
            {"check": "restore_value_recorded"},
        ],
    },
    {
        "action_id": "tighten_payment_timeout_retry",
        "target": "api payment timeout and retry policy",
        "knob_reversible": True,
        "user_effect_reversible": True,
        "max_blast_radius": "checkout payment requests only",
        "max_duration_seconds": None,
        "preapproved_budget": None,
        "cooldown_seconds": None,
        "max_attempts": 1,
        "measured": False,
        "risk_level": "L2",
        "diagnostic_contamination": True,
        "rollback_method": "previous_value",
        "rollback_call": {"endpoint": "/actions/payment-timeout-retry-restore"},
        "verification_metrics": ["latency_p95", "overall_failure_rate", "pg_latency_ratio"],
        "preconditions": [
            {"check": "payment_action_handler_available"},
            {"check": "external_payment_pg_evidence_present"},
            {"check": "retry_budget_is_bounded"},
            {"check": "restore_value_recorded"},
        ],
    },
    {
        "action_id": "switch_pg_provider",
        "target": "api 전체 결제 경로 (활성 PG provider)",
        "knob_reversible": True,
        # 전환 전 이미 실패한 결제는 되돌아오지 않는다 — 사용자에게 남는
        # 손실이 없는 S1의 채널 제한 원복과는 다르다.
        "user_effect_reversible": False,
        "max_blast_radius": "service-wide checkout — 단일 broadcast_id 스코프가 아니라 모든 방송의 결제에 영향",
        "max_duration_seconds": None,
        "preapproved_budget": None,
        "cooldown_seconds": None,
        "max_attempts": 1,
        "measured": False,
        "risk_level": "L3",
        # provider가 바뀌면 PG-A 쪽 pg_latency_ratio 표본이 사라진다 — "복구됐다"가
        # "PG-A가 나아졌다"가 아니라 "PG-A를 안 쓴다"는 뜻임을 판정에서 구분해야 한다.
        "diagnostic_contamination": True,
        "diagnostic_contamination_note": "PG-A 표본이 끊겨 pg_latency_ratio가 빈다 — provider 성공 이벤트로 대신 확인할 것",
        "rollback_method": "immediate_delete",
        "rollback_call": {"endpoint": "$PG_PROVIDER_SWITCH_URL", "action": "clear"},
        "verification_metrics": ["latency_p95", "overall_failure_rate", "pg_latency_ratio"],
        "preconditions": [
            {"check": "external_payment_pg_evidence_present"},
        ],
    },
    {
        # 옛 S3 에서 쓰던 read-path 보호 노브. D-076 에 따라 자산은 남기되
        # 현재 시나리오 런북에는 연결하지 않는다.
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
        "verification_metrics": ["latency_p95", "overall_failure_rate"],
        "preconditions": [
            {"check": "broadcast_is_live", "source": "observability.alert.broadcast_id"},
            {"check": "read_path_not_already_degraded", "source": "cfg:read_path_degraded:{broadcast_id}"},
        ],
    },
]


VALID_STATUSES = {"active", "draft", "retired"}


def validate_catalog():
    known = set(H.labels())
    seen_rca_types = set()
    seen_runbook_ids = set()
    for entry in RUNBOOKS:
        if entry["rca_type"] not in known:
            # labels.txt 가 원본이라 여기서 지어낸 값은 애초에 못 들어가게 막는다.
            raise SystemExit(
                f"'{entry['rca_type']}' 는 labels.txt 에 없다 — 오타이거나 "
                "새 라벨을 labels.txt 에 먼저 추가해야 한다."
            )
        if entry["status"] not in VALID_STATUSES:
            raise SystemExit(
                f"'{entry['rca_type']}' status={entry['status']!r} — "
                f"허용값은 {sorted(VALID_STATUSES)}"
            )
        if entry["rca_type"] in seen_rca_types:
            raise SystemExit(f"rca_type 중복: {entry['rca_type']}")
        if entry["runbook_id"] in seen_runbook_ids:
            raise SystemExit(f"runbook_id 중복: {entry['runbook_id']}")
        seen_rca_types.add(entry["rca_type"])
        seen_runbook_ids.add(entry["runbook_id"])

    # retired 런북은 Lookup이 액션을 반환하지 않으므로 노브가 없어도 된다.
    # active·draft는 지금 또는 승격 뒤 게이트 판정에 쓰이므로 모두 필요하다.
    known_actions = {
        action["action_id"]
        for entry in RUNBOOKS
        if entry["status"] != "retired"
        for action in entry["actions"]
    }
    knob_actions = {k["action_id"] for k in KNOBS}
    missing = known_actions - knob_actions
    if missing:
        raise SystemExit(
            f"런북이 참조하는데 노브 카탈로그에 없다: {sorted(missing)} — "
            "게이트 진입을 판정할 근거가 없어진다."
        )


def parse_args():
    parser = argparse.ArgumentParser(description="O2 Runbook DynamoDB 카탈로그 시딩")
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="RCA_OR_RUNBOOK_ID",
        help="지정한 rca_type 또는 runbook_id 만 시딩. 여러 번 지정 가능",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="AWS와 Terraform을 호출하지 않고 선택·검증 결과만 출력",
    )
    return parser.parse_args()


def select_runbooks(only):
    if not only:
        return RUNBOOKS
    wanted = set(only)
    selected = [
        entry
        for entry in RUNBOOKS
        if entry["rca_type"] in wanted or entry["runbook_id"] in wanted
    ]
    found = {entry["rca_type"] for entry in selected} | {
        entry["runbook_id"] for entry in selected
    }
    missing = wanted - found
    if missing:
        raise SystemExit(f"카탈로그에 없는 --only 값: {sorted(missing)}")
    return selected


def main():
    args = parse_args()
    validate_catalog()
    selected = select_runbooks(args.only)
    selected_action_ids = {
        action["action_id"] for entry in selected for action in entry["actions"]
    }
    selected_knobs = [
        knob for knob in KNOBS if knob["action_id"] in selected_action_ids
    ]

    if args.dry_run:
        for entry in selected:
            print(
                f"DRY-RUN {entry['rca_type']} / {entry['runbook_id']} — "
                f"{entry['status']} · ACTION {len(entry['actions'])}개 · "
                f"retired {len(entry.get('retired_action_ids', []))}개"
            )
        print(f"DRY-RUN KNOB {len(selected_knobs)}개")
        return

    table_name = H.tf_output("runbook_table_name")
    table = boto3.resource("dynamodb").Table(table_name)

    for entry in selected:
        rca_type = entry["rca_type"]
        definition = {
            key: value
            for key, value in entry.items()
            if key not in {"actions", "retired_action_ids"}
        }

        table.put_item(
            Item={
                **definition,
                "sk": "DEF",
            }
        )
        for action in entry["actions"]:
            table.put_item(
                Item={
                    "rca_type": rca_type,
                    "sk": f"ACTION#{action['action_id']}",
                    "runbook_id": entry["runbook_id"],
                    "status": entry["status"],
                    **action,
                }
            )
        # 삭제하지 않는다. 기존 아이템이 있으면 원문을 보존한 채 status 만
        # retired 로 바꾼다. 다만 지금은 존재 조건이 없어 대상이 원래 없으면
        # key+status 뿐인 sparse marker가 생긴다(D-079). 그 표식은 원문 보존
        # 증거로 해석하면 안 된다.
        for action_id in entry.get("retired_action_ids", []):
            table.update_item(
                Key={"rca_type": rca_type, "sk": f"ACTION#{action_id}"},
                UpdateExpression="SET #status = :retired",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":retired": "retired"},
            )
        print(
            f"✓ {rca_type} — {entry['status']} · DEF + ACTION "
            f"{len(entry['actions'])}개 · retired {len(entry.get('retired_action_ids', []))}개"
        )

    # 노브는 rca_type 축이 아니라 노브 축이라 KNOB 파티션에 따로 넣는다.
    for knob in selected_knobs:
        table.put_item(
            Item={
                "rca_type": KNOB_PARTITION,
                "sk": f"KNOB#{knob['action_id']}",
                **knob,
            }
        )
        print(f"✓ KNOB#{knob['action_id']}")

    print(
        f"\n완료. {table_name} 에 rca_type {len(selected)}개 · "
        f"노브 {len(selected_knobs)}개 시딩됨."
    )


if __name__ == "__main__":
    main()
