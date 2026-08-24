"""cue-warmer 가 부르는 warm_meta() — get_snapshot() 과 갈라지는 지점만 본다.

_load_meta() 자체(Valkey 조회·DB 폴백)는 실제 MySQL·Valkey 왕복이 필요해
여기서 보지 않는다 — 이 저장소의 다른 서비스 시험과 같은 결이다
(test_broadcast_degraded.py). 여기서 확인하는 것은 warm_meta() 가
_load_meta() 를 부르되 재고 조회와 이벤트 발행 경로를 안 타는지, 그리고
None 을 bool 로 정확히 옮기는지다.
"""

from app.services import broadcast


def test_delegates_to_load_meta_without_side_effects(monkeypatch):
    calls = []

    def fake_load_meta(broadcast_id, origin):
        calls.append((broadcast_id, dict(origin)))
        return {"broadcast_id": broadcast_id, "products": []}

    monkeypatch.setattr(broadcast, "_load_meta", fake_load_meta)

    assert broadcast.warm_meta("bc_1042") is True
    assert calls == [("bc_1042", {"source": "CACHE", "cache_hit": True})]


def test_missing_broadcast_returns_false(monkeypatch):
    monkeypatch.setattr(broadcast, "_load_meta", lambda broadcast_id, origin: None)

    assert broadcast.warm_meta("bc_9999") is False
