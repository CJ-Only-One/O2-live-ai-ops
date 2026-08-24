"""Datadog series 페이로드 — 파드 축이 태그로 실려 나가는지.

집계와 전송 사이가 이 파이프라인에서 가장 조용히 끊기는 지점입니다.
`metrics.py` 가 파드별 값을 계산해도 `build_series()` 가 안 실으면
Datadog 쪽 쿼리(`by {pod_name}`)는 **비어 있는 것이 아니라 아예 안 갈립니다**
— 위젯은 "쿼리는 맞는데 시계열이 하나뿐" 인 모양이 되고, 그 하나가
service 단위 값이라 정상으로 보입니다.
"""

from __future__ import annotations

import factory
from o2warm.datadog import build_series
from o2warm.metrics import derive
from o2warm.sketch import build
from o2warm.windows import window_start


def _series_for(events, service="order-api"):
    sk = build(service, window_start(factory.BASE), events)
    return build_series(derive(sk), prefix="o2.warm.", env="dev")


def _pod_tag(entry):
    for t in entry["tags"]:
        if t.startswith("pod_name:"):
            return t.split(":", 1)[1]
    return None


def test_latency_p95_is_emitted_per_pod_with_pod_name_tag():
    events = []
    for pod in ("pod-a", "pod-b"):
        for i in range(10):
            events.append(
                factory.order_create(
                    factory.BASE + i, f"u{pod}{i}", "1.1.1.1",
                    latency=(2500 if pod == "pod-b" else 50), pod_name=pod,
                )
            )

    series = _series_for(events)
    lat = [s for s in series if s["metric"] == "o2.warm.latency_p95"]

    # service 단위 1개 + 파드 2개.
    assert len(lat) == 3
    assert {_pod_tag(s) for s in lat} == {None, "pod-a", "pod-b"}

    slow = next(s for s in lat if _pod_tag(s) == "pod-b")
    fast = next(s for s in lat if _pod_tag(s) == "pod-a")
    assert slow["points"][0]["value"] > 2000
    assert fast["points"][0]["value"] < 100


def test_pod_series_carry_the_same_service_and_env_tags():
    """cache_hit_rate 와 같은 축이어야 Monitor 의 scope 필터가 둘 다 잡습니다."""
    events = [
        factory.order_create(factory.BASE + i, f"u{i}", "1.1.1.1", latency=80, pod_name="pod-a")
        for i in range(10)
    ]
    series = _series_for(events)
    pod_entries = [s for s in series if _pod_tag(s) is not None]

    assert pod_entries
    for s in pod_entries:
        assert "service:order-api" in s["tags"]
        assert "env:dev" in s["tags"]


def test_no_pod_series_when_envelope_has_no_pod_name():
    events = [
        factory.order_create(factory.BASE + i, f"u{i}", "1.1.1.1", latency=80) for i in range(10)
    ]
    series = _series_for(events)

    assert [s for s in series if s["metric"] == "o2.warm.latency_p95"]
    assert not [s for s in series if _pod_tag(s) is not None]


def test_sample_counts_by_pod_are_not_sent():
    """맵은 보내지 않는다는 경계(datadog.py 머리말)를 유지합니다."""
    events = [
        factory.order_create(factory.BASE + i, f"u{i}", "1.1.1.1", latency=80, pod_name="pod-a")
        for i in range(10)
    ]
    series = _series_for(events)

    assert not [s for s in series if s["metric"].endswith("latency_samples_by_pod")]
    assert not [s for s in series if s["metric"].endswith("latency_p95_by_pod")]


def test_latency_p99_is_emitted():
    """계산만 되고 안 보내지던 값이다.

    명세 S2 의 1차 조치 검증은 p50·p95·**p99** 셋을 함께 본다. `metrics.py`
    는 오래 전부터 `latency_p99` 를 계산했지만 `DATADOG_SCALARS` 에 없어
    Datadog 에는 영영 오지 않았다 — DynamoDB 상세에만 있었다.

    **p95 로 대신할 수 없다.** 느린 파드의 몫이 전체의 5% 미만이면 p95 는
    안 움직이고 p99 만 움직인다. 아래가 그 상황을 그대로 만든다.
    """
    # 정상 98건 + 느린 2건(2%) — p95 는 정상 쪽에, p99 는 느린 쪽에 걸린다.
    events = [
        factory.order_create(factory.BASE + i, f"u{i}", "1.1.1.1", latency=50)
        for i in range(98)
    ]
    events += [
        factory.order_create(factory.BASE + 98 + i, f"us{i}", "1.1.1.1", latency=9000)
        for i in range(2)
    ]

    series = _series_for(events)
    by_name = {s["metric"]: s["points"][0]["value"] for s in series if _pod_tag(s) is None}

    assert "o2.warm.latency_p99" in by_name, "p99 가 series 에 없다"
    assert by_name["o2.warm.latency_p99"] > 5000
    # p95 는 꼬리를 못 본다 — 이것이 p99 를 따로 보내는 이유다.
    assert by_name["o2.warm.latency_p95"] < 500


def test_channel_limited_rate_uses_all_chat_attempts_as_denominator():
    """실패 사유 내부 분포가 아니라 전체 정상 사용자 발화 대비 차단률이어야 한다."""
    events = []
    for i in range(8):
        events.append(
            factory.envelope(
                "chat.send", factory.BASE + i / 10,
                service="chat-gateway", user=f"u{i}",
                payload={"result": "SUCCESS", "msg_length": 10, "msg_hash": f"h{i}", "is_duplicate": False},
            )
        )
    for i in range(2):
        events.append(
            factory.envelope(
                "chat.send", factory.BASE + 1 + i / 10,
                service="chat-gateway", user=f"ub{i}",
                payload={
                    "result": "FAILED", "failure_code": "CHANNEL_LIMITED",
                    "msg_length": 10, "msg_hash": f"hb{i}", "is_duplicate": False,
                },
            )
        )

    series = _series_for(events, service="chat-gateway")
    metric = next(s for s in series if s["metric"] == "o2.warm.channel_limited_rate")
    assert metric["points"][0]["value"] == 0.2
