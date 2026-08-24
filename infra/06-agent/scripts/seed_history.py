#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3", "botocore[crt]"]
# ///
"""S1(chat_channel_overload) 시연을 "알려진 장애"로 분류시키기 위한 이력 시딩.

    python3 scripts/seed_history.py

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
]


def _seed_incident(spec, s3, s3vectors, worker):
    now = datetime.datetime.now(datetime.timezone.utc)
    occurred = now - datetime.timedelta(days=spec["occurred_days_ago"])
    recovered = occurred + datetime.timedelta(minutes=spec["mttr_min"])

    event = {**spec["event"], "occurred_at": str(int(occurred.timestamp()))}

    incident = worker._build_incident(event, spec["dify_data"], past_cases=False)
    # _build_incident 은 started_at 을 "지금"으로 찍는다 — 시딩은 과거 사례처럼
    # 보여야 하므로 발생 시각으로 되돌린다. s3_key 도 그 날짜를 따라간다.
    incident["started_at"] = occurred.isoformat()
    incident["occurred_at"] = event["occurred_at"]
    incident["s3_key"] = f"incidents/dt={occurred:%Y-%m-%d}/{incident['incident_id']}.json"
    incident["recovered_at"] = recovered.isoformat()
    incident["outcome"] = {
        "state": spec["state"],
        "mttr_sec": spec["mttr_min"] * 60,
        "root_cause_label": spec["root_cause_label"],
        "verified": True,
        "human_correction": spec["human_correction"],
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


def main():
    known = set(H.labels())
    for spec in INCIDENTS:
        if spec["rca_type"] not in known:
            raise SystemExit(
                f"'{spec['rca_type']}' 는 labels.txt 에 없다 — 오타이거나 "
                "새 라벨을 labels.txt 에 먼저 추가해야 한다."
            )

    import worker  # noqa: PLC0415 — H 가 sys.path 를 깔아 준 뒤에야 된다

    s3, s3vectors = H.clients()

    for spec in INCIDENTS:
        incident = _seed_incident(spec, s3, s3vectors, worker)
        print(f"✓ {spec['rca_type']} — {incident['s3_key']}")

    print(f"\n완료. {len(INCIDENTS)}건 시딩됨.")
    print(
        "\nS2(pod_load_skew)는 의도적으로 안 채웠다 — 그 시나리오는 "
        "'처음 보는 장애'가 전제라 검증된 과거 사례가 없어야 맞다."
    )


if __name__ == "__main__":
    main()
