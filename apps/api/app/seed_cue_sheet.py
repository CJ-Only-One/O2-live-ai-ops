"""큐시트 JSON 파일을 읽어 MySQL 에 적재한다. 여러 번 돌려도 안전하다(upsert).

    python -m app.seed_cue_sheet <파일 경로>
    kubectl exec -n o2-dev deploy/api -- python -m app.seed_cue_sheet <파일 경로>

형식 검증은 하지 않는다. scripts/validate-cue-sheet.py 로 먼저 확인한 뒤
이 스크립트로 적재한다 — 둘로 나눈 이유는 형식 검증(jsonschema)이 CI 의존성이지
런타임 의존성이 아니기 때문이다(requirements.txt 에 jsonschema 가 없다).
"""

import json
import sys

from app.db.session import SessionLocal
from app.services.cue_sheet import save_cue_sheet


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m app.seed_cue_sheet <파일 경로>", file=sys.stderr)
        raise SystemExit(1)

    with open(sys.argv[1], encoding="utf-8") as file:
        body = json.load(file)

    with SessionLocal() as db:
        applied_version = save_cue_sheet(db, body)

    if applied_version == body["cue_version"]:
        print(f"적재됨: {body['broadcast_id']} cue_version={applied_version}")
    else:
        # 요청한 버전보다 DB 값이 최신이다 — 오래된 큐시트로 최신을
        # 덮어쓰려 한 것이므로 무시됐다. 성공으로 보이면 안 된다.
        print(
            f"무시됨: {body['broadcast_id']} 요청 cue_version={body['cue_version']}"
            f" <= 기존 cue_version={applied_version}",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
