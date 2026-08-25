"""S3 목업 PG 서비스 — 지연·실패·관측 계약을 검증한다."""

import pytest

from app.core import cache
from app.services import payment


class _FakeValkey:
    def __init__(self, values=None, *, explode=False):
        self.values = dict(values or {})
        self.explode = explode

    def mget(self, keys):
        if self.explode:
            raise ConnectionError("valkey unavailable")
        return [self.values.get(key) for key in keys]

    def mset(self, values):
        self.values.update(values)

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)


class _Emit:
    def __init__(self, *, explode=False):
        self.calls = []
        self.explode = explode

    def payment_process(self, **kwargs):
        self.calls.append(kwargs)
        if self.explode:
            raise RuntimeError("sink unavailable")


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_injected_timeout_sleeps_and_emits_required_evidence(monkeypatch):
    fake_valkey = _FakeValkey(
        {
            payment.PG_DELAY_KEY: "250",
            payment.PG_FAIL_RATE_KEY: "1",
        }
    )
    sent = _Emit()
    slept = []
    ticks = iter([10.0, 10.25])
    monkeypatch.setattr(payment, "valkey", fake_valkey)
    monkeypatch.setattr(payment, "emit", sent)
    monkeypatch.setattr(payment.time, "sleep", slept.append)
    monkeypatch.setattr(payment.time, "perf_counter", lambda: next(ticks))

    result = payment.process_payment(
        order_id="od_01TEST",
        idempotency_key="00000000-0000-4000-8000-000000000001",
        amount=12000,
    )

    assert slept == [0.25]
    assert result.succeeded is False
    assert result.failure_code == "PG_TIMEOUT"
    assert result.pg_latency_ms == 250
    assert sent.calls == [
        {
            "order_id": "od_01TEST",
            "payment_id": result.payment_id,
            "amount": 12000,
            "result": "FAILED",
            "failure_code": "PG_TIMEOUT",
            "failure_stage": "PG_CALL",
            "pg_provider": "PG-A",
            "pg_response_code": "TIMEOUT",
            "pg_latency_ms": 250,
            "total_latency_ms": 250,
            "retry_count": 0,
        }
    ]


def test_same_idempotency_key_never_flips_sampled_result():
    key = "00000000-0000-4000-8000-000000000002"
    outcomes = {payment._fails(key, 0.5) for _ in range(20)}
    assert len(outcomes) == 1
    assert payment._payment_id(key) == payment._payment_id(key)


def test_default_config_is_success_without_delay(monkeypatch):
    sent = _Emit()
    monkeypatch.setattr(payment, "valkey", _FakeValkey())
    monkeypatch.setattr(payment, "emit", sent)
    monkeypatch.setattr(
        payment.time,
        "sleep",
        lambda _: pytest.fail("default config must not sleep"),
    )

    result = payment.process_payment(
        order_id="od_01TEST",
        idempotency_key="00000000-0000-4000-8000-000000000003",
        amount=12000,
    )

    assert result.succeeded is True
    assert result.failure_code is None
    assert sent.calls[0]["result"] == "SUCCESS"


@pytest.mark.parametrize(
    "values",
    [
        {payment.PG_DELAY_KEY: "-1", payment.PG_FAIL_RATE_KEY: "1"},
        {
            payment.PG_DELAY_KEY: str(payment.MAX_DELAY_MS + 1),
            payment.PG_FAIL_RATE_KEY: "1",
        },
        {payment.PG_DELAY_KEY: "1", payment.PG_FAIL_RATE_KEY: "nan"},
        {payment.PG_DELAY_KEY: "1", payment.PG_FAIL_RATE_KEY: "1.1"},
        {payment.PG_DELAY_KEY: "0", payment.PG_FAIL_RATE_KEY: "1"},
    ],
)
def test_invalid_manual_config_fails_open_to_normal(values, monkeypatch):
    monkeypatch.setattr(payment, "valkey", _FakeValkey(values))
    assert payment.get_config(authoritative=True) == payment.PgStubConfig()


def test_valkey_or_event_sink_failure_does_not_create_checkout_failure(monkeypatch):
    monkeypatch.setattr(payment, "valkey", _FakeValkey(explode=True))
    monkeypatch.setattr(payment, "emit", _Emit(explode=True))

    result = payment.process_payment(
        order_id="od_01TEST",
        idempotency_key="00000000-0000-4000-8000-000000000004",
        amount=12000,
    )

    assert result.succeeded is True
