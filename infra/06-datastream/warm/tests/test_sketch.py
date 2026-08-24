"""부분 집계의 병합 성질 검증.

여기가 깨지면 지표 전부가 조용히 틀립니다. 배치 경계는 매 호출 달라지고
두 스트림은 따로 도착하므로, **어떻게 쪼개 넣어도 같은 결과**가 나와야
합니다.
"""

from __future__ import annotations

import random

import factory
from o2warm.sketch import (
    DistinctCounter,
    Histogram,
    IntervalStats,
    SpaceSaving,
    WindowSketch,
    build,
)
from o2warm.windows import window_start


def _split_build(events, chunks):
    """이벤트를 chunks 조각으로 쪼개 각각 집계한 뒤 병합합니다."""
    size = max(1, len(events) // chunks)
    parts = [events[i:i + size] for i in range(0, len(events), size)]
    merged = WindowSketch("coupon-api", window_start(factory.BASE))
    for p in parts:
        merged.merge(build("coupon-api", window_start(factory.BASE), p))
    return merged


def _split_build_svc(service, events, chunks):
    """_split_build 와 같지만 service 를 지정합니다."""
    size = max(1, len(events) // chunks)
    parts = [events[i:i + size] for i in range(0, len(events), size)]
    merged = WindowSketch(service, window_start(factory.BASE))
    for p in parts:
        merged.merge(build(service, window_start(factory.BASE), p))
    return merged


def test_merge_is_associative_on_counts():
    events = factory.normal(n_users=50, per_user=4, rng=random.Random(11))
    events = [e for e in events if not e["event_name"].startswith("client.")]

    whole = build("coupon-api", window_start(factory.BASE), events)
    for chunks in (2, 3, 7, 13):
        merged = _split_build(events, chunks)
        assert merged.n == whole.n, chunks
        assert merged.by_event == whole.by_event, chunks
        assert merged.users.total == whole.users.total, chunks
        assert merged.results == whole.results, chunks


def test_merge_reconnects_interval_across_batches():
    """배치 경계에서 끊긴 간격 하나를 이어 붙이는지.

    이어 붙이지 않으면 매크로의 규칙적인 간격이 배치 수만큼 사라져
    interval_cv 가 실제보다 높게(=사람처럼) 나옵니다.
    """
    ts = [factory.BASE + i * 0.5 for i in range(10)]
    whole = IntervalStats(64)
    for t in ts:
        whole.add("u_1", t)

    a, b = IntervalStats(64), IntervalStats(64)
    for t in ts[:4]:
        a.add("u_1", t)
    for t in ts[4:]:
        b.add("u_1", t)
    a.merge(b)

    assert a.u["u_1"][2] == whole.u["u_1"][2] == 10
    assert abs(a.u["u_1"][3] - whole.u["u_1"][3]) < 1e-6  # 간격 합
    assert abs(a.u["u_1"][4] - whole.u["u_1"][4]) < 1e-6  # 간격 제곱합


def test_space_saving_keeps_heavy_hitters():
    s = SpaceSaving(capacity=16)
    for i in range(500):
        s.add(f"noise_{i}")
    for _ in range(300):
        s.add("whale")

    assert s.truncated
    top = dict(s.top(1))
    assert "whale" in top
    assert top["whale"] >= 300  # 상속 때문에 과소평가되지 않습니다
    assert s.total == 800


def test_distinct_counter_stays_within_capacity_and_unbiased():
    c = DistinctCounter(capacity=256)
    for i in range(20000):
        c.add(f"u_{i}")
    assert len(c.keys) <= 256
    assert c.approximate
    est = c.estimate()
    assert 0.7 * 20000 < est < 1.3 * 20000, est


def test_distinct_counter_merge_matches_union():
    a, b = DistinctCounter(128), DistinctCounter(128)
    for i in range(5000):
        a.add(f"u_{i}")
    for i in range(2500, 7500):
        b.add(f"u_{i}")
    a.merge(b)
    assert 0.7 * 7500 < a.estimate() < 1.3 * 7500, a.estimate()


def test_histogram_quantile():
    h = Histogram()
    for _ in range(90):
        h.add(0.1)
    for _ in range(10):
        h.add(0.95)
    assert h.quantile(0.5) < 0.2


def test_sequence_guard_blocks_double_counting():
    """Kinesis 재시도로 같은 배치가 두 번 와도 이중 집계되지 않아야 합니다."""
    events = factory.normal(n_users=10, per_user=2, rng=random.Random(12))
    partial = build("coupon-api", window_start(factory.BASE), events)
    partial.note_source("stream-business:shardId-000000000000", "4959033827149025660855")

    merged = WindowSketch("coupon-api", window_start(factory.BASE))
    merged.merge(partial)
    n_once = merged.n
    merged.merge(partial)  # 재시도
    assert merged.n == n_once

    # 다른 스트림의 같은 샤드 번호는 별개로 취급되어야 합니다.
    other = build("coupon-api", window_start(factory.BASE), events)
    other.note_source("stream-client:shardId-000000000000", "4959033827149025660855")
    merged.merge(other)
    assert merged.n == n_once * 2


def test_merge_does_not_mutate_other():
    """낙관적 잠금 재시도 때 같은 부분 집계를 다시 써야 합니다."""
    events = factory.normal(n_users=10, per_user=2, rng=random.Random(13))
    partial = build("coupon-api", window_start(factory.BASE), events)
    before = partial.to_dict()

    WindowSketch("coupon-api", window_start(factory.BASE)).merge(partial)
    assert partial.to_dict() == before


def test_cache_hit_by_pod_isolates_one_bad_pod():
    """파드 하나만 무효화를 놓쳐도 전체 평균에 묻히지 않는지.

    시나리오 1(README) — 파드 3개 중 1개만 캐시가 계속 미스나도 service 단위
    평균은 여전히 정상 범위로 보인다. pod_name 축이 있어야 그 파드만 집을 수 있다.
    """
    events = []
    ts = factory.BASE
    for pod in ("pod-a", "pod-b", "pod-c"):
        for i in range(10):
            hit = pod != "pod-c"  # pod-c 만 전부 미스
            events.append(factory.inventory(ts + i, f"u{pod}{i}", "1.1.1.1", cache_hit=hit, pod_name=pod))

    s = build("coupon-api", window_start(factory.BASE), events)

    assert s.cache_hit_by_pod == {"pod-a": 10, "pod-b": 10}
    assert s.cache_miss_by_pod == {"pod-c": 10}
    # service 단위 합산은 20 히트 / 10 미스 — pod-c 하나가 완전히 죽어도
    # 전체 히트율은 2/3(66.7%)로, 단독으로는 "위험"이라 보기 어렵다.
    assert s.cache_hit == 20
    assert s.cache_miss == 10


def test_cache_hit_by_pod_merges_across_batches():
    events = []
    ts = factory.BASE
    for pod in ("pod-a", "pod-b"):
        for i in range(6):
            events.append(
                factory.inventory(ts + i, f"u{pod}{i}", "1.1.1.1", cache_hit=(pod == "pod-a"), pod_name=pod)
            )

    whole = build("coupon-api", window_start(factory.BASE), events)
    for chunks in (2, 3, 5):
        merged = _split_build(events, chunks)
        assert merged.cache_hit_by_pod == whole.cache_hit_by_pod, chunks
        assert merged.cache_miss_by_pod == whole.cache_miss_by_pod, chunks


def test_cache_hit_by_pod_roundtrips():
    events = [
        factory.inventory(factory.BASE, "u1", "1.1.1.1", cache_hit=True, pod_name="pod-a"),
        factory.inventory(factory.BASE + 1, "u2", "1.1.1.1", cache_hit=False, pod_name="pod-b"),
    ]
    s = build("coupon-api", window_start(factory.BASE), events)
    restored = WindowSketch.from_dict(s.to_dict())
    assert restored.cache_hit_by_pod == s.cache_hit_by_pod == {"pod-a": 1}
    assert restored.cache_miss_by_pod == s.cache_miss_by_pod == {"pod-b": 1}


def test_roundtrip_serialization():
    events = factory.macro(rng=random.Random(14))
    s = build("coupon-api", window_start(factory.BASE), events)
    restored = WindowSketch.from_dict(s.to_dict())
    assert restored.to_dict() == s.to_dict()

    # 저장 시 간격 통계를 소수점 4자리로 줄이므로 CV 는 완전히 같지 않습니다.
    # 감별 임계는 소수 첫째 자리 수준이라 이 정도 손실은 무해합니다.
    a = restored.intervals.cv_weighted_median()[0]
    b = s.intervals.cv_weighted_median()[0]
    assert abs(a - b) < 1e-3


def test_latency_by_pod_isolates_one_slow_pod():
    """파드 하나만 느려도 service 단위 분포에 묻히지 않는지.

    시나리오 5(README) 의 재분석 근거다 — 1차 조치가 듣지 않았을 때
    에이전트가 "어느 파드인가" 로 내려가려면 이 축이 있어야 한다.
    """
    events = []
    ts = factory.BASE
    for pod in ("pod-a", "pod-b", "pod-c"):
        for i in range(10):
            latency = 2000 if pod == "pod-c" else 50  # pod-c 만 느리다
            events.append(
                factory.order_create(ts + i, f"u{pod}{i}", "1.1.1.1", latency=latency, pod_name=pod)
            )

    s = build("order-api", window_start(factory.BASE), events)

    assert set(s.latency_by_pod) == {"pod-a", "pod-b", "pod-c"}
    assert all(h.n == 10 for h in s.latency_by_pod.values())
    # 느린 파드만 꼬리가 올라가 있다.
    assert s.latency_by_pod["pod-c"].quantile(0.95) > 1500
    assert s.latency_by_pod["pod-a"].quantile(0.95) < 100
    # service 단위 히스토그램은 30건 전부를 합쳐 들고 있다 — p95 하나로는
    # 어느 파드인지 알 수 없다는 것이 이 축이 필요한 이유다.
    assert s.latency.n == 30


def test_latency_by_pod_merges_across_batches():
    events = []
    ts = factory.BASE
    for pod in ("pod-a", "pod-b"):
        for i in range(6):
            events.append(
                factory.order_create(
                    ts + i, f"u{pod}{i}", "1.1.1.1",
                    latency=(900 if pod == "pod-b" else 40), pod_name=pod,
                )
            )

    whole = build("order-api", window_start(factory.BASE), events)
    for chunks in (2, 3, 5):
        merged = _split_build_svc("order-api", events, chunks)
        assert set(merged.latency_by_pod) == set(whole.latency_by_pod), chunks
        for pod, hist in whole.latency_by_pod.items():
            assert merged.latency_by_pod[pod].n == hist.n, (chunks, pod)
            assert merged.latency_by_pod[pod].b == hist.b, (chunks, pod)


def test_latency_by_pod_roundtrips():
    events = [
        factory.order_create(factory.BASE, "u1", "1.1.1.1", latency=30, pod_name="pod-a"),
        factory.order_create(factory.BASE + 1, "u2", "1.1.1.1", latency=1800, pod_name="pod-b"),
    ]
    s = build("order-api", window_start(factory.BASE), events)
    restored = WindowSketch.from_dict(s.to_dict())

    assert set(restored.latency_by_pod) == set(s.latency_by_pod) == {"pod-a", "pod-b"}
    for pod in s.latency_by_pod:
        assert restored.latency_by_pod[pod].to_dict() == s.latency_by_pod[pod].to_dict()


def test_latency_without_pod_name_stays_out_of_pod_axis():
    """pod_name 이 없는 봉투는 service 집계에만 들어간다.

    SDK 구버전이나 파드 밖에서 발행된 이벤트가 빈 문자열 키로 끼어들면
    outlier 탐지에 정체 불명의 시계열이 하나 생긴다.
    """
    events = [factory.order_create(factory.BASE + i, f"u{i}", "1.1.1.1", latency=100) for i in range(5)]
    s = build("order-api", window_start(factory.BASE), events)

    assert s.latency.n == 5
    assert s.latency_by_pod == {}
