"""주문 예약과 목업 PG 호출 사이의 실패 격리·멱등 경계를 검증한다."""

from types import SimpleNamespace

import pytest

from app.core.errors import ApiError
from app.services import order, payment

REQ = SimpleNamespace(
    broadcast_id="bc_1042",
    sku_id="88213",
    qty=1,
)


@pytest.fixture
def order_path(monkeypatch):
    monkeypatch.setattr(
        order.broadcast_service,
        "get_product",
        lambda *_: {"state": "ON_SALE", "sale_price": 12000},
    )
    monkeypatch.setattr(order, "_emit_issue", lambda *args, **kwargs: None)
    monkeypatch.setattr(order, "_emit_create", lambda *args, **kwargs: None)


def test_payment_failure_restores_stock_and_never_publishes(order_path, monkeypatch):
    reserve_calls = []
    compensated = []
    monkeypatch.setattr(
        order,
        "_reserve",
        lambda *, keys, args: reserve_calls.append((keys, args)) or (0, "9"),
    )
    monkeypatch.setattr(
        order.payment_service,
        "process_payment",
        lambda **_: payment.PaymentResult(
            succeeded=False,
            payment_id="pay_test",
            failure_code="PG_TIMEOUT",
            pg_latency_ms=250,
            total_latency_ms=250,
        ),
    )
    monkeypatch.setattr(
        order,
        "_compensate",
        lambda idem_key, sku_id, qty: compensated.append((idem_key, sku_id, qty)),
    )
    monkeypatch.setattr(
        order,
        "_publish",
        lambda *args, **kwargs: pytest.fail("failed payment must not reach SQS"),
    )

    with pytest.raises(ApiError) as raised:
        order.create_order(REQ, "idem-1", "u_test")

    assert raised.value.code == "PAYMENT_FAILED"
    assert compensated == [("idem-1", "88213", 1)]
    assert reserve_calls[0][0] == [
        "idem:idem-1",
        "stock:88213",
        "idemstate:idem-1",
    ]


def test_successful_payment_continues_to_publish_and_accept(order_path, monkeypatch):
    published = []
    accepted = []
    monkeypatch.setattr(order, "_reserve", lambda **_: (0, "9"))
    monkeypatch.setattr(
        order.payment_service,
        "process_payment",
        lambda **_: payment.PaymentResult(
            succeeded=True,
            payment_id="pay_test",
            failure_code=None,
            pg_latency_ms=0,
            total_latency_ms=0,
        ),
    )
    monkeypatch.setattr(order, "_publish", lambda *args: published.append(args))
    monkeypatch.setattr(
        order,
        "_mark_accepted",
        lambda order_id, req, idem_key: accepted.append((order_id, idem_key)),
    )

    result = order.create_order(REQ, "idem-2", "u_test")

    assert result["state"] == "ACCEPTED"
    assert len(published) == 1
    assert accepted == [(result["order_id"], "idem-2")]


def test_duplicate_during_payment_does_not_return_false_accepted(
    order_path, monkeypatch
):
    class _Valkey:
        @staticmethod
        def get(key):
            if key == "idemstate:idem-3":
                return "PROCESSING"
            if key == "order:od_existing":
                return None
            raise AssertionError(key)

    monkeypatch.setattr(order, "valkey", _Valkey())
    monkeypatch.setattr(order, "_reserve", lambda **_: (1, "od_existing"))
    monkeypatch.setattr(
        order.payment_service,
        "process_payment",
        lambda **_: pytest.fail("duplicate must not call PG again"),
    )

    with pytest.raises(ApiError) as raised:
        order.create_order(REQ, "idem-3", "u_test")

    assert raised.value.code == "REQUEST_IN_PROGRESS"


def test_compensation_removes_both_idempotency_keys_and_restores_stock(monkeypatch):
    calls = []

    class _Valkey:
        @staticmethod
        def delete(*keys):
            calls.append(("delete", keys))

        @staticmethod
        def incrby(key, qty):
            calls.append(("incrby", key, qty))

    monkeypatch.setattr(order, "valkey", _Valkey())

    order._compensate("idem-4", "88213", 2)

    assert calls == [
        ("delete", ("idem:idem-4", "idemstate:idem-4")),
        ("incrby", "stock:88213", 2),
    ]
