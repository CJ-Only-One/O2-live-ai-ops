#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3", "botocore[crt]"]
# ///
"""인시던트 하나를 지정해서 검증 처리한다.

    uv run scripts/verify_one.py <incident_id> <label> <state> [메모]

verify.py 와 같은 일을 하되, 미검증이 수십 건 쌓여 있을 때 특정 건만
집어서 처리한다. 검증 규칙 자체는 verify.py 와 같다 — 원인 라벨은
labels.txt 통제 어휘에서만 고르고, 벡터는 다시 만들지 않고 메타데이터만
갈아 끼운다.
"""

import json
import sys

import _history as H


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(2)

    incident_id, label, state = sys.argv[1], sys.argv[2], sys.argv[3]
    note = sys.argv[4] if len(sys.argv) > 4 else ""

    labels = H.labels()
    if label not in labels:
        print(f"'{label}' 은 통제 어휘에 없다. labels.txt 를 보라.")
        sys.exit(2)

    s3, s3vectors = H.clients()
    bucket = H.tf_output("history_bucket")

    hit = next(
        (
            v
            for v in H.all_vectors(s3vectors)
            if (v.get("metadata") or {}).get("s3_key", "").endswith(f"{incident_id}.json")
        ),
        None,
    )
    if hit is None:
        print(f"{incident_id} 벡터를 못 찾았다.")
        sys.exit(1)

    meta = hit["metadata"]
    incident = json.loads(s3.get_object(Bucket=bucket, Key=meta["s3_key"])["Body"].read())

    out = incident["outcome"]
    out["root_cause_label"] = label
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
    print("✓", worker._summary(incident["context"]["signal_summary"], out))


if __name__ == "__main__":
    main()
