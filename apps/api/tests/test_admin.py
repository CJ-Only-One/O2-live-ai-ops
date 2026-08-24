"""S3 조치 실행 라우트 (docs/scenario-experiment.md 0.7).

`cfg:read_path_degraded:{broadcast_id}` 를 SET·DEL 한다. 실제 Valkey 를
안 쓴다 — `app.db.valkey.valkey` 를 딕셔너리 기반 가짜로 갈아끼운다.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.routes import admin as admin_route
from app.core.config import settings
from app.main import app

URL = "/api/admin/read-path-degraded"

client = TestClient(app)


class _FakeValkey:
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture
def fake_valkey(monkeypatch):
    fake = _FakeValkey()
    monkeypatch.setattr(admin_route, "valkey", fake)
    return fake


@pytest.fixture
def admin_key(monkeypatch):
    monkeypatch.setattr(settings, "READ_PATH_DEGRADED_ADMIN_KEY", "test-admin-key")
    return "test-admin-key"


def test_no_key_configured_rejects(fake_valkey, monkeypatch):
    monkeypatch.setattr(settings, "READ_PATH_DEGRADED_ADMIN_KEY", "")
    res = client.post(URL, json={"broadcast_id": "bc_1042", "action": "set"}, headers={"x-admin-key": "anything"})
    assert res.status_code == 403


def test_wrong_key_rejects(fake_valkey, admin_key):
    res = client.post(
        URL,
        json={"broadcast_id": "bc_1042", "action": "set"},
        headers={"x-admin-key": "wrong"},
    )
    assert res.status_code == 403


def test_set_then_clear(fake_valkey, admin_key):
    res = client.post(
        URL,
        json={"broadcast_id": "bc_1042", "action": "set"},
        headers={"x-admin-key": admin_key},
    )
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "broadcast_id": "bc_1042",
        "action": "set",
        "previously_degraded": False,
    }
    assert fake_valkey.get("cfg:read_path_degraded:bc_1042") == "1"

    res = client.post(
        URL,
        json={"broadcast_id": "bc_1042", "action": "clear"},
        headers={"x-admin-key": admin_key},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["previously_degraded"] is True
    assert fake_valkey.get("cfg:read_path_degraded:bc_1042") is None


def test_bad_action_rejected(fake_valkey, admin_key):
    # action 이 Literal["set", "clear"] 이라 Pydantic 이 파싱 단계에서 막는다
    # — 라우트 본문에 수동 검증을 안 둔다. app.core.errors 가 검증 오류를
    # 계약 오류 봉투(400 INVALID_REQUEST)로 바꾼다(errors.py 참조).
    res = client.post(
        URL,
        json={"broadcast_id": "bc_1042", "action": "nope"},
        headers={"x-admin-key": admin_key},
    )
    assert res.status_code == 400


def test_malformed_broadcast_id_rejected(fake_valkey, admin_key):
    # BroadcastId 패턴(^bc_[0-9]+$) 검증 — 오타 낸 broadcast_id 로 조용히
    # 엉뚱한 키에 SET 하고 200 을 돌려주는 사고를 막는다.
    res = client.post(
        URL,
        json={"broadcast_id": "not-a-broadcast", "action": "set"},
        headers={"x-admin-key": admin_key},
    )
    assert res.status_code == 400
