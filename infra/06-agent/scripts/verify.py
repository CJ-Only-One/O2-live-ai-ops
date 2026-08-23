#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3", "botocore[crt]"]
# ///
"""검증 안 된 인시던트를 하나씩 보여주고 사람이 원인을 확정한다.

    python3 scripts/verify.py            # 미검증 건을 순서대로 처리
    python3 scripts/verify.py --list     # 목록만 보고 끝

왜 사람이 하나.

  에이전트가 적은 원인은 **추측이다.** 그것을 검증 없이 검색 코퍼스에 넣으면
  다음 장애에서 같은 오판을 더 큰 확신으로 반복한다 (architecture.md 7.4).
  그래서 저장 시점의 요약에는 원인이 아예 들어가지 않고, **사람이 확정한
  뒤에만** 원인이 붙는다 (worker.py `_summary`).

  자동으로 채우는 방법도 있지만 그건 추측을 한 번 더 하는 것이지 검증이 아니다.

왜 자유 텍스트가 아니라 목록에서 고르나.

  같은 원인이 세 표현으로 갈리면 "이 원인이 N번 재발" 을 셀 수 없고, 그러면
  런북을 무엇부터 쓸지도 모른다. 목록은 labels.txt 다.

★ 이 도구는 작아야 한다. 손이 많이 가면 아무도 안 쓰고, 안 쓰면 이력은
  영원히 미검증으로 남는다. 한 건에 키 세 번을 넘기지 마라.
"""

import json
import sys

import _history as H

STATES = [
    ("auto_recovered", "저절로 복구됨 (아무도 안 고침)"),
    ("human_fixed", "사람이 조치해서 해결"),
    ("false_alarm", "오탐. 장애가 아니었음"),
    ("unresolved", "아직 안 끝남"),
]


def _ask(prompt, options, allow_skip=True):
    """번호로 고른다. 엔터는 '그대로 두기'."""
    for i, (_, desc) in enumerate(options, 1):
        print(f"    {i:2}) {desc}")
    if allow_skip:
        print("     s) 이 건을 건너뛴다")

    while True:
        raw = input(f"  {prompt} > ").strip().lower()
        if raw == "s" and allow_skip:
            return None
        if raw == "":
            return ""
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        print("    번호로 골라라.")


def main():
    s3, s3vectors = H.clients()
    bucket = H.tf_output("history_bucket")
    labels = [(x, x) for x in H.labels()]

    pending = [
        v
        for v in H.all_vectors(s3vectors)
        if not (v.get("metadata") or {}).get("verified")
    ]
    pending.sort(key=lambda v: (v.get("metadata") or {}).get("occurred_at", ""))

    if not pending:
        print("미검증 인시던트 없음.")
        return

    print(f"미검증 {len(pending)}건\n")
    if "--list" in sys.argv:
        for v in pending:
            print(" ", (v.get("metadata") or {}).get("summary", v["key"]))
        return

    for n, hit in enumerate(pending, 1):
        meta = hit["metadata"]
        print(f"\n[{n}/{len(pending)}] {meta.get('summary', '')}")

        raw = s3.get_object(Bucket=bucket, Key=meta["s3_key"])["Body"].read()
        incident = json.loads(raw)
        guess = (incident.get("agent") or {}).get("hypothesis", "").strip()
        if guess:
            # 추측은 여기서만 보인다. 검색 코퍼스에는 안 들어간다.
            print("  AI 추측:", guess.replace("\n", " ")[:200])

        label = _ask("원인?", labels)
        if label is None:
            continue

        state = _ask("어떻게 끝났나? (엔터 = 그대로)", STATES, allow_skip=False)
        note = input("  한 줄 메모 (선택) > ").strip()

        out = incident["outcome"]
        if label:
            out["root_cause_label"] = label
        if state:
            out["state"] = state
        if note:
            out["human_correction"] = note
        out["verified"] = True

        s3.put_object(
            Bucket=bucket,
            Key=meta["s3_key"],
            Body=json.dumps(incident, ensure_ascii=False).encode(),
            ContentType="application/json",
        )

        # ★ 벡터값은 그대로 두고 메타데이터만 갈아 끼운다. 임베딩을 다시 하지
        #   않는다 — 알림 텍스트가 바뀐 것이 아니라 결과를 알게 된 것뿐이다.
        got = s3vectors.get_vectors(
            vectorBucketName=H.tf_output("history_vector_bucket"),
            indexName=H.tf_output("history_vector_index"),
            keys=[hit["key"]],
            returnData=True,
        )
        import worker  # noqa: PLC0415 — H 가 sys.path 를 깔아 준 뒤에야 된다

        s3vectors.put_vectors(
            vectorBucketName=H.tf_output("history_vector_bucket"),
            indexName=H.tf_output("history_vector_index"),
            vectors=[
                {
                    "key": hit["key"],
                    "data": got["vectors"][0]["data"],
                    "metadata": worker._metadata(incident),
                }
            ],
        )
        print("  ✓", worker._summary(incident["context"]["signal_summary"], out))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n중단. 여기까지는 저장됐다.")
