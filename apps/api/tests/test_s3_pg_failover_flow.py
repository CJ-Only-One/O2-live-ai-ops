"""S3 PG-A 장애 주입부터 PG-B 우회·안전 원복까지의 제어면 흐름을 검증한다.

Agent/Runbook 실행은 범위 밖이다. 이 테스트는 그 실행기가 호출하게 될 API와
결제 이벤트 계약만 한 Valkey 상태에서 연결한다.
"""

import pytest
from fastapi.testclient import TestClient

from app.core import cache
from app.core.config import settings
from app.main import app
from app.services import payment

PG_STUB_URL = "/api/admin/pg-stub"
PG_PROVIDER_URL = "/api/admin/pg-provider-switch"
client = TestClient(app)


class _FakeValkey:
    def __init__(self):
        self.values: dict[str, str] = {}

    def mget(self, keys):
        return [self.values.get(key) for key in keys]

    def mset(self, values):
        self.values.update(values)

    def set(self, key, value, ex=None):
        self.values[key] = value

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)


class _PaymentEvents:
    def __init__(self):
        self.calls = []

    def payment_process(self, **kwargs):
        self.calls.append(kwargs)


@pytest.fixture
def s3_control_plane(monkeypatch):
    fake_valkey = _FakeValkey()
    events = _PaymentEvents()
    cache.clear()
    monkeypatch.setattr(payment, "valkey", fake_valkey)
    monkeypatch.setattr(payment, "emit", events)
    monkeypatch.setattr(payment.time, "sleep", lambda _: None)
    monkeypatch.setattr(settings, "PG_STUB_ADMIN_KEY", "test-pg-stub-key")
    monkeypatch.setattr(settings, "READ_PATH_DEGRADED_ADMIN_KEY", "test-provider-key")
    yield events
    cache.clear()


def test_pg_a_failure_to_pg_b_failover_and_safe_rollback(s3_control_plane):
    """PG-A 주입은 PG-B 전환 뒤에도 유지되고, 해제 전 원복은 거부된다."""
    stub_headers = {"x-admin-key": "test-pg-stub-key"}
    provider_headers = {"x-admin-key": "test-provider-key"}

    injected = client.post(
        PG_STUB_URL,
        json={"action": "set", "delay_ms": 250, "fail_rate": 1},
        headers=stub_headers,
    )
    assert injected.status_code == 200

    pg_a = payment.process_payment(
        order_id="od_s3_pg_a", idempotency_key="s3-pg-a-failure", amount=12000
    )
    assert pg_a.succeeded is False
    assert s3_control_plane.calls[-1]["pg_provider"] == "PG-A"
    assert s3_control_plane.calls[-1]["failure_code"] == "PG_TIMEOUT"

    assert client.post(
        PG_PROVIDER_URL,
        json={"action": "set_pg_b_ready", "pg_b_ready": True},
        headers=provider_headers,
    ).status_code == 200
    switched = client.post(
        PG_PROVIDER_URL, json={"action": "set"}, headers=provider_headers
    )
    assert switched.status_code == 200
    assert switched.json()["provider"] == "PG-B"

    pg_b = payment.process_payment(
        order_id="od_s3_pg_b", idempotency_key="s3-pg-b-success", amount=12000
    )
    assert pg_b.succeeded is True
    assert s3_control_plane.calls[-1]["pg_provider"] == "PG-B"
    assert s3_control_plane.calls[-1]["result"] == "SUCCESS"

    blocked = client.post(
        PG_PROVIDER_URL, json={"action": "clear"}, headers=provider_headers
    )
    assert blocked.status_code == 409

    assert client.post(
        PG_STUB_URL, json={"action": "clear"}, headers=stub_headers
    ).status_code == 200
    rolled_back = client.post(
        PG_PROVIDER_URL, json={"action": "clear"}, headers=provider_headers
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["provider"] == "PG-A"
