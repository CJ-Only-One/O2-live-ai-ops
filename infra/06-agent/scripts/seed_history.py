#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3", "botocore[crt]"]
# ///
"""시연을 "알려진 장애"로 분류시키기 위한 이력 시딩.

    python3 scripts/seed_history.py                       # S1 기본 사례만
    python3 scripts/seed_history.py pg_external_failure    # S3 만
    python3 scripts/seed_history.py pg_external_failure --unverified
                                    # 사람이 원인을 확정하기 전 상태로 넣는다.
                                    # scripts/verify.py 화면에 뜬다.

★ **S3(pg_external_failure)는 1차 실행을 찍은 뒤에 넣는다.** S3 는 1차에
  verified 사례가 없어서 ESCALATED 로 멈추는 것이 전제다(0.7 Phase 2).
  1차 촬영 전에 넣으면 1차가 곧바로 History 분기를 타 시나리오가 성립하지
  않는다. 여기 있는 사례는 Phase 3(사람 해결 → 지식화)의 결과물이다.

`docs/scenario-experiment.md` 0.2 — 분류(알려진/처음 보는 장애)는 **과거에
같은 원인의 검증된 사례가 있는가**로 갈린다. S1 흐름(0.5)이 "유사 과거
사례 있음 → 전용 런북"으로 가려면, 실제 시연 알림이 뜨기 전에 검증된
`chat_channel_overload` 사례가 이력 저장소에 최소 하나 있어야 한다.

★ **S2(pod_load_skew)는 일부러 여기 안 채운다.** S2 흐름(0.6)의 전제 자체가
  "처음 보는 장애라 범용 런북으로 시작"이다 — 여기서 검증된 pod_load_skew
  사례를 미리 넣으면 시연 알림이 "알려진 장애"로 잘못 분류돼 S2 분기를 안
  탄다. 이력이 없는 것 자체가 이 시나리오의 조건이다.

★ worker.py 의 포매터(`_build_incident`·`_metadata`·`_summary`)를 그대로
  가져다 쓴다 — seed_runbook.py 가 labels.txt 를 원본으로 삼는 것과 같은
  이유로, 저장 경로와 시딩 경로가 다른 문장을 만들면 안 된다.

★ 여기 있는 알림 문구·시각·MTTR 은 전부 이 시연을 위해 지어낸 값이다.
  실측이 아니다 — AGENTS.md "숫자를 지어내지 않는다"는 실제 성능·용량
  주장에 적용되는 규칙이고, 이건 검색 코퍼스를 채우는 합성 시연 데이터라
  다르다. 그래도 실측처럼 보이지 않게 인시던트 본문에 성격을 분명히 적는다.

★ verify.py 와 달리 사람이 하나씩 확인하지 않는다 — 시딩이라 이미
  verified=True 로 만든다. 실제 운영 인시던트에는 절대 이 패턴을 쓰지
  않는다(그건 추측을 검증 없이 사실로 승격시키는 것과 같다, worker.py
  `_summary` 참고).
"""

import datetime
import json
import os
import sys

import _history as H

# worker.py 는 이 값을 모듈 임포트 시점에 환경변수로 읽는다(Lambda 에선
# history.tf 의 EMBED_MODEL_ID 로 주입됨). 로컬에서 그 값과 어긋나면 임베딩
# 모델이 갈려 검색 결과가 조용히 나빠진다 — history.tf 의 local.embed_model_id
# 와 반드시 같아야 한다.
os.environ.setdefault("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")

INCIDENTS = [
    {
        "rca_type": "chat_channel_overload",
        "occurred_days_ago": 6,
        "mttr_min": 14,
        "event": {
            "event_id": "seed-s1-001",
            "cycle_key": "seed-s1-001",
            "monitor_id": "seed-monitor-chat-volume",
            "priority": "P2",
            "link": "",
            "service": "chat-gateway",
            "env": "dev",
            "host": "",
            "tags": "service:chat-gateway,scenario:s1",
            "alert_title": "[Recovered] O2 채팅 전파 지연 — 채널 총량 초과",
            "alert_query": "avg(last_5m):avg:o2.chat.propagation.p95{service:chat-gateway} >= 800",
            "alert_body": (
                "채널 하나에 시청자가 몰리며 초당 채팅 아이템 수가 안전선을 넘었고, "
                "전파 p95 가 계약 기준을 초과했다. 개별 사용자는 전부 분당 발화 "
                "한도 안이었다 — 총량 문제였지 도배가 아니었다."
            ),
        },
        "dify_data": {
            "elapsed_time": 4.8,
            "outputs": {
                "result": (
                    "인입 아이템/s 가 감당 선을 넘었고 개별 사용자 차단 이력은 없음 "
                    "— 총량 문제로 판단. 채널 총량 제한 노브를 하향 적용 권고."
                )
            },
        },
        "root_cause_label": "chat_channel_overload",
        "state": "agent_fixed",
        "human_correction": "채널 총량 노브 하향 후 전파 p95 회복, 정상 사용자 차단 없음 확인.",
    },
    {
        "rca_type": "pg_external_failure",
        "occurred_days_ago": 3,
        "mttr_min": 26,
        "event": {
            "event_id": "seed-s3-001",
            "cycle_key": "seed-s3-001",
            "monitor_id": "seed-monitor-pg-latency",
            "priority": "P1",
            "link": "",
            "service": "api",
            "env": "dev",
            "host": "",
            "tags": "service:api,scenario:s3",
            "alert_title": "[Recovered] [O2][S3] 결제 처리 지연 — PG 왕복 p95",
            "alert_query": (
                "max(last_5m):p95:o2.app.operation.duration"
                "{service:api,env:dev,operation:payment.process} >= 3000"
            ),
            "alert_body": (
                "결제 처리 p95 가 임계를 넘고 주문 실패율이 함께 올랐다. "
                "실패는 전부 failure_stage=PG_CALL · failure_code=PG_TIMEOUT 이었고 "
                "pg_latency_ms 가 전체 지연의 대부분을 차지했다. 클러스터 자원 "
                "지표는 정상이었다 — 우리 쪽이 아니라 외부 PG-A 가 느렸다."
            ),
        },
        "dify_data": {
            "elapsed_time": 6.1,
            "outputs": {
                "result": (
                    "pg_provider=PG-A 의 PG_TIMEOUT 이 결제 실패의 전부이고 "
                    "pg_latency_ratio 가 1.0 에 가까움 — 외부 PG 장애로 판단. "
                    "검증된 Failover 절차가 없어 임의 전환 없이 사람에게 넘김."
                )
            },
        },
        "root_cause_label": "pg_external_failure",
        "state": "human_fixed",
        "human_correction": (
            "운영자가 결제 경로를 PG-A 에서 PG-B 로 수동 전환. PG-A 주입은 유지한 "
            "채 pg_provider=PG-B · result=SUCCESS 이벤트, 주문 실패율·결제 p95 회복, "
            "채팅 결제 불만 감소까지 확인. 자연 회복이 아니라 우회 효과임을 확인했다."
        ),
    },
]


def _seed_incident(spec, s3, s3vectors, worker, verified=True):
    now = datetime.datetime.now(datetime.timezone.utc)
    occurred = now - datetime.timedelta(days=spec["occurred_days_ago"])
    recovered = occurred + datetime.timedelta(minutes=spec["mttr_min"])

    event = {**spec["event"], "occurred_at": str(int(occurred.timestamp()))}
    if not verified:
        # 검증본과 키가 겹치면 서로 덮어쓴다. cycle_key 가 incident_id 다.
        event["cycle_key"] = f"{event['cycle_key']}-raw"
        event["event_id"] = f"{event['event_id']}-raw"

    incident = worker._build_incident(event, spec["dify_data"], past_cases=False)
    # _build_incident 은 started_at 을 "지금"으로 찍는다 — 시딩은 과거 사례처럼
    # 보여야 하므로 발생 시각으로 되돌린다. s3_key 도 그 날짜를 따라간다.
    incident["started_at"] = occurred.isoformat()
    incident["occurred_at"] = event["occurred_at"]
    incident["s3_key"] = f"incidents/dt={occurred:%Y-%m-%d}/{incident['incident_id']}.json"
    incident["recovered_at"] = recovered.isoformat()
    if verified:
        incident["outcome"] = {
            "state": spec["state"],
            "mttr_sec": spec["mttr_min"] * 60,
            "root_cause_label": spec["root_cause_label"],
            "verified": True,
            "human_correction": spec["human_correction"],
        }
    else:
        # worker._handle_recovery 가 남기는 그대로 — Recovered 는 "지표가 임계
        # 아래로 돌아왔다" 일 뿐이라 state 는 auto_recovered 이고 원인은 비어
        # 있다. 이걸 사람이 scripts/verify.py 에서 채운다.
        incident["outcome"] = {
            "state": "auto_recovered",
            "mttr_sec": spec["mttr_min"] * 60,
            "root_cause_label": None,
            "verified": False,
            "human_correction": None,
        }

    text = worker._alert_text(event)
    vector = worker._embed(text)

    s3.put_object(
        Bucket=H.tf_output("history_bucket"),
        Key=incident["s3_key"],
        Body=json.dumps(incident, ensure_ascii=False).encode(),
        ContentType="application/json",
    )
    s3vectors.put_vectors(
        vectorBucketName=H.tf_output("history_vector_bucket"),
        indexName=H.tf_output("history_vector_index"),
        vectors=[
            {
                "key": incident["incident_id"],
                "data": {"float32": vector},
                "metadata": worker._metadata(incident),
            }
        ],
    )
    return incident


def _select_specs(args):
    flags = {a for a in args if a.startswith("-")}
    unknown_flags = flags - {"--unverified"}
    if unknown_flags:
        raise SystemExit(f"지원하지 않는 옵션: {', '.join(sorted(unknown_flags))}")

    only = {a for a in args if not a.startswith("-")}
    available = {s["rca_type"] for s in INCIDENTS}
    unknown = only - available
    if unknown:
        raise SystemExit(
            f"{sorted(unknown)} 에 해당하는 시딩 대상이 없다. 가능한 값: "
            + ", ".join(s["rca_type"] for s in INCIDENTS)
        )
    # S3 verified 이력은 1차 ESCALATED 뒤에만 넣어야 한다. 기존 무인자 실행이
    # S3까지 시딩해 1차 조건을 깨지 않도록 기본값은 원래 S1 사례만 유지한다.
    selected = only or {"chat_channel_overload"}
    return [s for s in INCIDENTS if s["rca_type"] in selected], "--unverified" not in flags


def main():
    # 인자로 rca_type 을 주면 그것만 시딩한다. 시나리오별로 따로 찍을 때 쓴다.
    #   ./scripts/seed_history.py pg_external_failure
    specs, verified = _select_specs(sys.argv[1:])

    known = set(H.labels())
    for spec in specs:
        if spec["rca_type"] not in known:
            raise SystemExit(
                f"'{spec['rca_type']}' 는 labels.txt 에 없다 — 오타이거나 "
                "새 라벨을 labels.txt 에 먼저 추가해야 한다."
            )

    import worker  # noqa: PLC0415 — H 가 sys.path 를 깔아 준 뒤에야 된다

    s3, s3vectors = H.clients()

    for spec in specs:
        incident = _seed_incident(spec, s3, s3vectors, worker, verified=verified)
        mark = "verified" if verified else "미검증"
        print(f"✓ {spec['rca_type']} · {mark} — {incident['s3_key']}")

    print(f"\n완료. {len(specs)}건 시딩됨.")
    print(
        "\nS2(pod_load_skew)는 의도적으로 안 채웠다 — 그 시나리오는 "
        "'처음 보는 장애'가 전제라 검증된 과거 사례가 없어야 맞다."
    )


if __name__ == "__main__":
    main()
