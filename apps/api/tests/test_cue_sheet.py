"""큐시트 저장.

오프셋 해석·재조회 반환값 구성 같은 순수 로직은 가짜 Session 으로 본다.
버전 역행 방지(ON DUPLICATE KEY UPDATE 의 CASE 가드)는 MySQL 서버가 SQL 을
실제로 평가해야 검증되는 부분이라 여기서는 못 본다 — 이 저장소의 다른
서비스 시험들도 DB 왕복은 실환경에서만 확인하고 단위 시험은 대역을 쓴다
(test_broadcast_degraded.py 와 같은 결). db.execute 를 가로채는 가짜로
"무엇을 저장하려 했는가" 만 본다.
"""

from datetime import datetime

import pytest
from sqlalchemy.dialects.mysql import dialect

from app.services.cue_sheet import _to_naive_utc, save_cue_sheet


class _FakeRow:
    def __init__(self, cue_version: int):
        self.cue_version = cue_version


class _FakeSession:
    """execute 를 가로채고, get() 은 방금 executed 에 담긴 cue_version 을
    그대로 돌려준다 — 가드가 실제로 예전 버전을 걸러내는지는 이 가짜로
    검증하지 못한다(그건 MySQL 이 하는 일이다). 여기서는 "재조회해서
    반환한다" 는 배선만 확인한다."""

    def __init__(self):
        self.executed = None
        self.committed = False

    def execute(self, stmt):
        self.executed = stmt

    def commit(self):
        self.committed = True

    def get(self, _model, _pk):
        cue_version = _params(self.executed)["cue_version"]
        return _FakeRow(cue_version)


def _params(stmt):
    return stmt.compile(dialect=dialect()).params


def test_offset_is_converted_to_naive_utc():
    """KST(+09:00) 20:00 은 UTC 로 11:00 이어야 한다."""
    db = _FakeSession()
    body = {
        "broadcast_id": "bc_1042",
        "cue_version": 1,
        "scheduled_at": "2026-08-24T20:00:00+09:00",
        "ends_at": "2026-08-24T21:30:00+09:00",
        "segments": [],
    }

    save_cue_sheet(db, body)

    params = _params(db.executed)
    assert params["scheduled_at"] == datetime(2026, 8, 24, 11, 0, 0)
    assert params["ends_at"] == datetime(2026, 8, 24, 12, 30, 0)
    assert db.committed


def test_missing_ends_at_is_none():
    """ends_at 은 선택 필드다 — 없으면 컬럼도 NULL 이어야지 예외가 나면 안 된다."""
    db = _FakeSession()
    body = {
        "broadcast_id": "bc_1043",
        "cue_version": 1,
        "scheduled_at": "2026-08-25T20:00:00+09:00",
        "segments": [],
    }

    save_cue_sheet(db, body)

    assert _params(db.executed)["ends_at"] is None


def test_body_round_trips_unchanged():
    """저장하는 body 는 파싱해서 다시 조립한 게 아니라 받은 그대로여야 한다
    — 세그먼트 필드가 늘어도 이 함수를 고칠 필요가 없다는 것의 근거."""
    db = _FakeSession()
    body = {
        "broadcast_id": "bc_1042",
        "cue_version": 2,
        "scheduled_at": "2026-08-24T20:00:00+09:00",
        "segments": [{"seq": 1, "segment_type": "SALE_OPEN"}],
    }

    save_cue_sheet(db, body)

    assert _params(db.executed)["body"] == body


def test_returns_applied_cue_version():
    """호출자가 결과를 판단할 수 있게 실제로 반영된 버전을 돌려준다."""
    db = _FakeSession()
    body = {
        "broadcast_id": "bc_1042",
        "cue_version": 5,
        "scheduled_at": "2026-08-24T20:00:00+09:00",
        "segments": [],
    }

    assert save_cue_sheet(db, body) == 5


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-24T20:00:00",  # 오프셋도 Z 도 없음
        "2026-08-24",  # 시각 자체가 없음
    ],
)
def test_offsetless_timestamp_is_rejected(value):
    """오프셋 없는 값을 서버 로컬 시간대로 조용히 해석하면 UTC 가 아닌
    환경에서 몇 시간이 말없이 어긋난다 — 조용히 넘기지 않고 즉시 실패해야
    한다."""
    with pytest.raises(ValueError):
        _to_naive_utc(value)
