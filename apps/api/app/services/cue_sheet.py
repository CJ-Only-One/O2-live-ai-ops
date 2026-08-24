"""큐시트 저장·조회.

계약은 contracts/cue-sheet-v1.schema.json 이 원본이다. 형식(오프셋 유무·
segment_type enum 등)의 세부 검증은 scripts/validate-cue-sheet.py 가 CI 에서
하지만, 이 모듈이 그 검증을 우회할 수 있는 유일한 경로이기도 하다 — CI를
안 거친 값이 여기로 바로 들어올 수 있으므로 오프셋 누락 하나는 여기서도
막는다(그 값을 잘못 해석하면 사람이 못 알아채는 채로 몇 시간이 어긋난다).

DB 컬럼은 naive UTC 다. body 안의 시각은 오프셋을 그대로 담은 사람이 쓴
값이라, scheduled_at·ends_at 을 컬럼으로 뽑아낼 때 이 파일이 유일하게
오프셋을 해석한다 — 그 뒤로는 아무도 시간대를 다시 만지지 않는다.
"""

from datetime import datetime, timezone

from sqlalchemy import case, func
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import Session

from app.models.cue_sheet import CueSheet


def _to_naive_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        # 오프셋이 없으면 astimezone() 이 이 프로세스가 도는 서버의 로컬
        # 시간대로 조용히 해석한다. UTC 가 아닌 곳에서 돌면 scheduled_at 이
        # 몇 시간씩 밀려 저장되고도 아무 에러가 안 난다 — 그래서 여기서 죽인다.
        raise ValueError(f"offset is required in cue sheet timestamps: {value!r}")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def save_cue_sheet(db: Session, body: dict) -> int:
    """큐시트를 저장한다. 같은 broadcast_id 면 통째로 덮어쓴다.

    큐시트는 방송당 하나이고 수정은 새 cue_version 으로 표현되므로(계약),
    이전 버전을 별도로 보존하지 않는다 — 필요해지면 그때 이력 테이블을 둔다.

    cue_version 이 기존 값보다 낮으면 쓰지 않는다 — 지연된 재시도나 겹친
    요청이 최신 버전을 예전 버전으로 덮어쓰는 것을 막는다. 반환값은 저장
    시도 후 실제로 DB 에 남은 cue_version 이다. 요청한 값과 다르면 이번
    호출이 무시됐다는 뜻이다(호출자가 판단할 수 있게 값으로만 알린다 —
    별도 예외를 던지지 않는 이유는 겹친 쓰기 자체는 정상 상황이기 때문이다).
    """
    scheduled_at = _to_naive_utc(body["scheduled_at"])
    ends_at = _to_naive_utc(body["ends_at"]) if body.get("ends_at") else None

    stmt = insert(CueSheet).values(
        broadcast_id=body["broadcast_id"],
        cue_version=body["cue_version"],
        scheduled_at=scheduled_at,
        ends_at=ends_at,
        body=body,
    )
    inserted = stmt.inserted
    is_newer = inserted.cue_version >= CueSheet.cue_version
    stmt = stmt.on_duplicate_key_update(
        cue_version=case((is_newer, inserted.cue_version), else_=CueSheet.cue_version),
        scheduled_at=case((is_newer, inserted.scheduled_at), else_=CueSheet.scheduled_at),
        ends_at=case((is_newer, inserted.ends_at), else_=CueSheet.ends_at),
        body=case((is_newer, inserted.body), else_=CueSheet.body),
        # 새 값이 실제로 반영될 때만 갱신한다. 무시된 쓰기까지 시각을
        # 새로 찍으면 updated_at 이 "마지막으로 바뀐 시각"이 아니라
        # "마지막으로 시도한 시각"이 되어 이름과 뜻이 어긋난다.
        updated_at=case((is_newer, func.current_timestamp(3)), else_=CueSheet.updated_at),
    )
    db.execute(stmt)
    db.commit()

    return db.get(CueSheet, body["broadcast_id"]).cue_version


def get_cue_sheet(db: Session, broadcast_id: str) -> dict | None:
    row = db.get(CueSheet, broadcast_id)
    return row.body if row else None
