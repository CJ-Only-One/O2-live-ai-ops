"""저장 계층 검증 — 동시 쓰기와 재시도가 값을 망가뜨리지 않는지.

두 스트림이 같은 윈도우 아이템에 씁니다. 여기가 틀리면 클릭이 사라지거나
요청이 두 번 세어지고, **그 사실이 아무 데도 드러나지 않습니다.**
"""

from __future__ import annotations

import random

import factory
import pytest
from fake_table import FakeTable
from o2warm.metrics import derive
from o2warm.sketch import build
from o2warm.store import WarmStore, from_dynamo, to_dynamo, ts_sk
from o2warm.windows import window_start

WIN = window_start(factory.BASE)


@pytest.fixture
def store():
    return WarmStore(table=FakeTable())


def _partial(events, source, seq):
    s = build("coupon-api", WIN, events)
    s.note_source(source, seq)
    return s


def test_two_streams_converge_on_one_window(store):
    """비즈니스와 클라이언트가 따로 도착해도 한 윈도우로 합쳐져야 합니다."""
    events = factory.normal(n_users=30, per_user=2, rng=random.Random(31))
    server = [e for e in events if not e["event_name"].startswith("client.")]
    clicks = [e for e in events if e["event_name"].startswith("client.")]

    store.merge_sketch(_partial(server, "stream-business:s0", "100"))
    merged = store.merge_sketch(_partial(clicks, "stream-client:s0", "200"))

    assert merged.n == len(events)
    assert merged.n_business == len(server)
    assert merged.n_client == len(clicks)

    # click_ratio 는 두 스트림이 다 있어야만 나옵니다.
    m = derive(merged, baseline={"rps": 5.0, "samples": 999})
    assert m["click_ratio"] is not None and m["click_ratio"] > 0.8


def test_optimistic_lock_retries_and_keeps_both_writes(store):
    """조건 충돌이 나도 재시도로 양쪽 값이 모두 남아야 합니다."""
    table = store._table
    events = factory.normal(n_users=10, per_user=2, rng=random.Random(32))
    a, b = events[: len(events) // 2], events[len(events) // 2:]

    pa = _partial(a, "stream-business:s0", "100")
    pb = _partial(b, "stream-client:s0", "200")

    # b 가 읽은 뒤 a 가 먼저 쓰는 상황을 강제합니다.
    original = table.get_item
    fired = {"done": False}

    def racing_get(**kw):
        result = original(**kw)
        if not fired["done"] and kw["Key"]["sk"].startswith("SKETCH#"):
            fired["done"] = True
            store.merge_sketch(pa)  # 끼어드는 다른 스트림
        return result

    table.get_item = racing_get
    merged = store.merge_sketch(pb)

    assert table.conflicts >= 1, "충돌이 재현되지 않아 재시도 경로가 검증되지 않음"
    assert merged.n == len(events), "재시도 후 양쪽 이벤트가 모두 남아야 합니다"


def test_replayed_batch_is_not_counted_twice(store):
    """Kinesis 재처리로 같은 배치가 다시 와도 값이 부풀지 않아야 합니다."""
    events = factory.normal(n_users=10, per_user=2, rng=random.Random(33))
    partial = _partial(events, "stream-business:s0", "4959033827149025660855")

    first = store.merge_sketch(partial)
    again = store.merge_sketch(partial)

    assert again.n == first.n == len(events)
    assert store._table.puts == 1, "변화가 없으면 쓰기도 일어나지 않아야 합니다"

    merged, duplicate = store.merge_sketch_with_status(partial)
    assert merged.n == len(events)
    assert duplicate is True


def test_metric_write_is_monotonic(store):
    """늦게 도착한 오래된 상태가 최신 지표를 덮어쓰면 안 됩니다."""
    events = factory.normal(n_users=20, per_user=2, rng=random.Random(34))
    fresh = derive(build("coupon-api", WIN, events))
    stale = derive(build("coupon-api", WIN, events[:10]))

    store.put_metrics(fresh)
    store.put_metrics(stale)  # 뒤늦게 도착한 옛 상태

    saved = store._table.items[("METRIC#coupon-api", ts_sk(WIN))]
    assert int(saved["rev"]) == fresh["rev"] > stale["rev"]


def test_recent_metrics_sorts_numerically_not_lexically(store):
    """0 패딩이 빠지면 윈도우 순서가 뒤집힙니다."""
    for offset in (0, 10, 20, 30):
        m = derive(build("coupon-api", WIN + offset,
                         factory.normal(n_users=3, per_user=1, rng=random.Random(offset))))
        m["window_start"] = WIN + offset
        store.put_metrics(m)

    rows = store.recent_metrics("coupon-api", 4)
    assert [int(r["window_start"]) for r in rows] == [WIN + 30, WIN + 20, WIN + 10, WIN]


def test_none_survives_the_round_trip(store):
    """'계산 불가'가 0으로 바뀌면 Agent 가 정상으로 오판합니다."""
    m = derive(build("coupon-api", WIN, factory.normal(n_users=5, per_user=2)))
    assert m["rps_ratio"] is None          # 평시 기준이 없으므로
    store.put_metrics(m)
    saved = from_dynamo(store._table.items[("METRIC#coupon-api", ts_sk(WIN))])
    assert saved["rps_ratio"] is None


def test_floats_become_decimal():
    """float 를 그대로 넣으면 DynamoDB 가 거부합니다."""
    from decimal import Decimal

    out = to_dynamo({"a": 0.5, "b": [1.5, None], "c": {"d": True}, "e": float("nan")})
    assert isinstance(out["a"], Decimal)
    assert isinstance(out["b"][0], Decimal)
    assert out["b"][1] is None
    assert out["c"]["d"] is True   # bool 이 Decimal 로 바뀌면 안 됩니다
    assert out["e"] is None


def test_incident_snapshot_roundtrip(store):
    store.put_snapshot("INC-1", "PRE", {"service": "coupon-api", "snapshot": {"latest": {"rps": 10.0}}})
    got = store.get_snapshot("INC-1", "PRE")
    assert got["snapshot"]["latest"]["rps"] == 10

    with pytest.raises(ValueError):
        store.put_snapshot("INC-1", "MIDDLE", {})


def test_detect_snapshot_is_separate_from_pre(store):
    """감지 시점과 조치 직전은 다른 아이템이어야 합니다.

    같은 키에 쓰면 나중에 찍은 PRE 가 감지 시점 기록을 덮어써서
    "그때 Agent 가 본 것"이 사라집니다.
    """
    store.put_snapshot("INC-1", "DETECT", {"snapshot": {"latest": {"rps": 3.0}}})
    store.put_snapshot("INC-1", "PRE", {"snapshot": {"latest": {"rps": 9.0}}})

    assert store.get_snapshot("INC-1", "DETECT")["snapshot"]["latest"]["rps"] == 3
    assert store.get_snapshot("INC-1", "PRE")["snapshot"]["latest"]["rps"] == 9


def test_detect_alone_does_not_satisfy_compare(store):
    """DETECT 만 있는 것은 복구 판정에 아무 도움이 되지 않습니다.

    감지 시점과 조치 후를 비교하면 승인 대기 동안의 자기악화분까지
    조치 성과로 잡힙니다. 그래서 PRE 가 없으면 None(핸들러 409) 입니다.
    """
    from o2warm.client import WarmClient

    client = WarmClient(store=store)
    client._store.put_snapshot("INC-2", "DETECT", {"snapshot": {"latest": {"rps_ratio": 1.0}}})
    client._store.put_snapshot("INC-2", "POST", {"snapshot": {"latest": {"rps_ratio": 1.1}}})
    assert client.compare_snapshots("INC-2") is None

    client._store.put_snapshot("INC-2", "PRE", {"snapshot": {"latest": {"rps_ratio": 3.4}}})
    result = client.compare_snapshots("INC-2")
    assert result["delta"]["rps_ratio"]["before"] == 3.4   # DETECT 의 1.0 이 아님
