"""S3 목업 PG 주입·해제 API의 인증과 Valkey 상태 변경을 검증한다."""

import pytest
from fastapi.testclient import TestClient

from app.core import cache
from app.core.config import settings
from app.main import app
from app.services import payment

URL = "/api/admin/pg-stub"
client = TestClient(app)


class _FakeValkey:
    def __init__(self):
        self.values = {}

    def mget(self, keys):
        return [self.values.get(key) for key in keys]

    def mset(self, values):
        self.values.update(values)

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)


@pytest.fixture(autouse=True)
def fake_runtime(monkeypatch):
    fake = _FakeValkey()
    cache.clear()
    monkeypatch.setattr(payment, "valkey", fake)
    monkeypatch.setattr(settings, "PG_STUB_ADMIN_KEY", "test-pg-admin-key")
    yield fake
    cache.clear()


def test_missing_or_wrong_key_is_rejected(fake_runtime):
    assert client.get(URL).status_code == 403
    assert (
        client.post(
            URL,
            json={"action": "clear"},
            headers={"x-admin-key": "wrong"},
        ).status_code
        == 403
    )


def test_set_get_and_clear_round_trip(fake_runtime):
    headers = {"x-admin-key": "test-pg-admin-key"}
    response = client.post(
        URL,
        json={"action": "set", "delay_ms": 250, "fail_rate": 0.75},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == {
        "action": "set",
        "previous": {"delay_ms": 0, "fail_rate": 0.0, "active": False},
        "current": {"delay_ms": 250, "fail_rate": 0.75, "active": True},
    }
    assert fake_runtime.values == {
        payment.PG_DELAY_KEY: "250",
        payment.PG_FAIL_RATE_KEY: "0.75",
    }

    assert client.get(URL, headers=headers).json() == {
        "delay_ms": 250,
        "fail_rate": 0.75,
        "active": True,
    }

    response = client.post(URL, json={"action": "clear"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["current"] == {
        "delay_ms": 0,
        "fail_rate": 0.0,
        "active": False,
    }
    assert fake_runtime.values == {}


@pytest.mark.parametrize(
    "body",
    [
        {"action": "set"},
        {"action": "set", "delay_ms": -1, "fail_rate": 1},
        {"action": "set", "delay_ms": payment.MAX_DELAY_MS + 1, "fail_rate": 1},
        {"action": "set", "delay_ms": 1, "fail_rate": 1.1},
        {"action": "set", "delay_ms": 0, "fail_rate": 1},
        {"action": "unknown"},
    ],
)
def test_invalid_input_is_rejected_without_writing(body, fake_runtime):
    response = client.post(
        URL,
        json=body,
        headers={"x-admin-key": "test-pg-admin-key"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert fake_runtime.values == {}
