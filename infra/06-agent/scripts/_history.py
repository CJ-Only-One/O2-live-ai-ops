"""이력 도구들이 공유하는 최소한의 배선.

★ 버킷 이름을 스크립트에 적지 않는다. `terraform output` 으로 읽는다 —
  손으로 적은 이름은 스택을 다시 세우면 조용히 낡는다 (D-018 과 같은 원칙).

★ worker.py 의 포매터를 그대로 가져다 쓴다. 요약 문구를 여기서 다시 구현하면
  저장 경로와 검증 경로가 서로 다른 문장을 만들고, **그 차이는 벡터 하나가
  갱신되기 전까지 아무도 모른다.** 원본이 하나여야 한다.
"""

import functools
import os
import pathlib
import subprocess
import sys

MODULE = pathlib.Path(__file__).resolve().parent.parent
LAMBDA_DIR = MODULE / "lambda"

# worker 는 이 둘을 import 시점에 필수로 읽는다. 여기서는 Dify 를 부르지 않으니
# 값은 아무거나 된다 — 포매터만 쓴다.
os.environ.setdefault("ALERT_SECRET_NAME", "unused-by-scripts")
os.environ.setdefault("DIFY_URL", "unused-by-scripts")

sys.path.insert(0, str(LAMBDA_DIR))


@functools.lru_cache(maxsize=None)
def tf_output(name):
    out = subprocess.run(
        ["terraform", f"-chdir={MODULE}", "output", "-raw", name],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        # 제일 흔한 원인은 apply 를 아직 안 한 것이다. 출력은 state 에 들어가야
        # 읽히는데, 코드에 추가한 것만으로는 state 가 안 바뀐다.
        sys.exit(
            f"terraform output '{name}' 을 못 읽었다. 흔한 순서로:\n"
            f"  1. {MODULE} 에서 terraform apply 를 했는가 (출력은 apply 뒤에 생긴다)\n"
            f"  2. terraform init 은 됐는가\n"
            f"  3. AWS 세션은 살아 있는가 (aws sts get-caller-identity)\n\n"
            f"{out.stderr.strip()}"
        )
    return out.stdout.strip()


def labels():
    """통제 어휘. labels.txt 가 원본이다."""
    text = (MODULE / "labels.txt").read_text()
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.startswith("#")
    ]


def runbook_labels():
    """런북이 이미 있는 라벨. 파일명이 곧 라벨이다."""
    d = MODULE / "runbooks"
    return {p.stem for p in d.glob("*.md")} if d.is_dir() else set()


def clients():
    import boto3

    # 스택이 ap-northeast-2 고정이다 (variables.tf). 다른 리전을 쓰게 되면
    # 그때 terraform output 으로 뺀다.
    region = os.environ.get("AWS_REGION", "ap-northeast-2")
    return (
        boto3.client("s3", region_name=region),
        boto3.client("s3vectors", region_name=region),
    )


def all_vectors(s3vectors, with_data=False):
    """인덱스 전체를 훑는다. 건수가 적어 페이지네이션만 지키면 충분하다."""
    kwargs = {
        "vectorBucketName": tf_output("history_vector_bucket"),
        "indexName": tf_output("history_vector_index"),
        "returnMetadata": True,
        "returnData": with_data,
    }
    token = None
    while True:
        page = s3vectors.list_vectors(**({**kwargs, "nextToken": token} if token else kwargs))
        yield from page.get("vectors", [])
        token = page.get("nextToken")
        if not token:
            return
