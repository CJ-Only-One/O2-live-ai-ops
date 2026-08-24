"""cue-warmer 전용 경로 — POST /api/internal/warm/{broadcast_id}.

test_admin.py 와 같은 패턴이다. warm_meta() 를 대역으로 갈아끼워
DB·Valkey 왕복 없이 라우트 자체(인증·상태 코드 매핑)만 본다.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.routes import internal as internal_route
from app.core.config import settings
from app.main import app

client = TestClient(app)


def _url(broadcast_id: str) -> str:
    return f"/api/internal/warm/{broadcast_id}"


@pytest.fixture
def admin_key(monkeypatch):
    monkeypatch.setattr(settings, "CUE_WARMER_ADMIN_KEY", "test-warmer-key")
    return "test-warmer-key"


def test_no_key_configured_rejects(monkeypatch):
    monkeypatch.setattr(settings, "CUE_WARMER_ADMIN_KEY", "")
    res = client.post(_url("bc_1042"), headers={"x-admin-key": "anything"})
    assert res.status_code == 403


def test_wrong_key_rejects(admin_key):
    res = client.post(_url("bc_1042"), headers={"x-admin-key": "wrong"})
    assert res.status_code == 403


def test_warms_existing_broadcast(admin_key, monkeypatch):
    monkeypatch.setattr(internal_route, "warm_meta", lambda broadcast_id: True)

    res = client.post(_url("bc_1042"), headers={"x-admin-key": admin_key})

    assert res.status_code == 200
    assert res.json() == {"broadcast_id": "bc_1042", "warmed": True}


def test_missing_broadcast_is_404_not_silent_200(admin_key, monkeypatch):
    # 없는 broadcast_id 로 200 을 주면 큐시트의 broadcast_id 오타를 아무도
    # 못 알아챈다 — 조용히 넘기지 않는다는 것이 이 시험의 요점이다.
    monkeypatch.setattr(internal_route, "warm_meta", lambda broadcast_id: False)

    res = client.post(_url("bc_9999"), headers={"x-admin-key": admin_key})

    assert res.status_code == 404


def test_malformed_broadcast_id_rejected(admin_key):
    # BroadcastId 패턴(^bc_[0-9]+$) — admin.py 와 같은 검증(test_admin.py 참조).
    res = client.post(_url("not-a-broadcast"), headers={"x-admin-key": admin_key})
    assert res.status_code == 400
