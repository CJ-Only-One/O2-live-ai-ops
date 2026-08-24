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
