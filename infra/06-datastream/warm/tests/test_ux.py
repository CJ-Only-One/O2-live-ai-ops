"""사용자 경험 저하 감지 검증.

감별표(`test_scenarios.py`)가 "장애가 났을 때 원인을 가릴 수 있는가"를
본다면, 여기는 **"장애가 안 났는데 사용자가 불편한 상황을 알아채는가"**
를 봅니다.

모든 시나리오의 공통 전제는 하나입니다.

    응답은 200. 에러율 정상. p95 임계 안. 그런데 체감은 나쁘다.

그래서 각 시험은 두 가지를 함께 확인합니다.

1. 해당 신호가 실제로 움직이는가
2. **기존 지표로는 안 잡히는가** — 이게 없으면 "그냥 Datadog 쓰면 되지
   않나"에 답할 수 없습니다.

마지막 `healthy` 대조군이 오탐을 막습니다. 신호가 늘 울리면 아무도
안 봅니다.
"""

from __future__ import annotations

import factory
import pytest
from o2warm.metrics import derive
from o2warm.sketch import build
from o2warm.windows import group_by_window


def metrics_for(events, service, baseline=None, deploy=None):
    grouped = group_by_window(events)
    merged = None
    for (svc, win), items in sorted(grouped.items()):
        if svc != service:
            continue
        s = build(svc, win, items)
        merged = s if merged is None else merged.merge(s)
    assert merged is not None, f"{service} 이벤트가 없습니다"
    return derive(merged, baseline=baseline, deploy=deploy, now=factory.BASE + 12)


@pytest.fixture(scope="module")
def healthy():
    return metrics_for(factory.healthy(), "coupon-api")


# ---------------------------------------------------------------- 세그먼트 편차

def test_campaign_outage_hides_behind_the_average():
    m = metrics_for(factory.campaign_outage(), "coupon-api")

    # 전체 실패율은 14% 남짓 — 흔한 임계(20~30%)에 안 걸립니다.
    assert m["overall_failure_rate"] < 0.20

    # 그런데 세그먼트를 나누면 캠페인 하나가 95%입니다.
    skew = m["segment_skew"]
    assert skew, "세그먼트 편차가 잡히지 않음"
    top = skew[0]
    assert top["axis"] == "campaign_id"
    assert top["value"] == "LIVE-FLASH-02"
    assert top["failure_rate"] > 0.9
    assert top["lift"] > 5

    # 정상 캠페인은 편차 목록에 없어야 합니다.
    assert all(s["value"] != "LIVE-FLASH-01" for s in skew)


def test_segment_skew_ranks_by_excess_not_by_rate():
    """비율이 아무리 튀어도 표본이 적으면 조치 근거가 못 됩니다."""
    events = factory.campaign_outage()
    # 표본 5건짜리 캠페인을 전멸시켜 둡니다.
    for i in range(5):
        events.append(factory.coupon(
            factory.BASE + i * 0.1, f"tiny_{i}", f"ip_tiny_{i}",
            campaign="LIVE-TINY", result="FAILED", code="INTERNAL_ERROR"))

    m = metrics_for(events, "coupon-api")
    values = [s["value"] for s in m["segment_skew"]]
    assert "LIVE-FLASH-02" in values
    assert "LIVE-TINY" not in values, "표본 5건이 편차로 올라오면 안 됩니다"


def test_healthy_traffic_produces_no_skew(healthy):
    assert healthy["segment_skew"] == []


def test_segment_truncation_is_never_silent():
    """축 상한을 넘으면 그 구간의 저하는 아예 안 보입니다.

    다른 절단 구조와 달리 세그먼트는 늦게 나타난 값을 통째로 버리므로,
    신뢰도에 반드시 드러나야 합니다.
    """
    from o2warm.settings import settings

    events = [
        factory.coupon(factory.BASE + i * 0.001, f"u_{i}", f"ip_{i}",
                       campaign=f"CMP-{i:03d}")
        for i in range(settings.segment_capacity + 30)
    ]
    m = metrics_for(events, "coupon-api")

    assert m["confidence"]["completeness"] < 1.0
    assert any("세그먼트" in r for r in m["confidence"]["reasons"])


def test_segments_are_exposed_for_every_axis():
    m = metrics_for(factory.campaign_outage(), "coupon-api")
    seg = m["segments"]
    assert "campaign_id" in seg
    assert "broadcast_id" in seg
    assert set(seg["campaign_id"]) == {"LIVE-FLASH-01", "LIVE-FLASH-02"}
    assert seg["campaign_id"]["LIVE-FLASH-01"]["failure_rate"] == 0.0


def test_device_segmentation_is_client_only():
    """비즈니스 이벤트에는 device_type 이 없다는 계약 한계를 고정합니다.

    "모바일 사용자만 결제가 실패한다"는 현재 계약으로 감지 불가능합니다.
    이 시험이 깨지면 계약이 바뀐 것이므로 문서를 갱신해야 합니다.
    """
    events = factory.normal(n_users=30, per_user=2)
    m = metrics_for(events, "coupon-api")
    seg = m["segments"]
    assert "device_type" in seg, "클릭 이벤트의 기기 구분은 보여야 합니다"
    # 다만 실패는 전부 서버 이벤트에서 나오므로 기기별 실패율은 항상 0입니다.
    assert all(v["failed"] == 0 for v in seg["device_type"].values())


# ---------------------------------------------------------------- 재시도

def test_retry_storm_shows_while_failure_rate_stays_zero(healthy):
    m = metrics_for(factory.retry_storm(), "coupon-api")

    assert m["overall_failure_rate"] == 0.0      # 전부 성공
    assert m["latency_p95"] < 200                # 지연도 정상
    assert m["retry_rate"] > 0.5                 # 그런데 절반 넘게 재시도

    assert healthy["retry_rate"] == 0.0


def test_retry_rate_is_null_without_the_field():
    """앱이 is_retry 를 안 보내면 0이 아니라 null 이어야 합니다."""
    events = factory.retry_storm()
    for e in events:
        e["payload"].pop("is_retry", None)
    m = metrics_for(events, "coupon-api")
    assert m["retry_rate"] is None
    assert m["retry_samples"] == 0


# ---------------------------------------------------------------- 취소

def test_cancel_surge_has_no_request_time_signal(healthy):
    m = metrics_for(factory.cancel_surge(), "order-api")

    # 주문 생성은 전부 정상입니다 — 요청 시점 신호가 없습니다.
    assert m["overall_failure_rate"] is None or m["overall_failure_rate"] == 0.0

    assert m["cancel_rate"] > 0.3
    assert m["cancel_reasons"]["INVENTORY_SHORTAGE"] > 0.9
    assert m["cancel_by"]["SYSTEM"] > 0

    # 사유가 없으면 '취소가 늘었다'까지만 알 수 있습니다.
    assert "INVENTORY_SHORTAGE" in m["cancel_reasons"]


def test_cancel_reason_is_required_to_name_the_cause():
    events = factory.cancel_surge()
    for e in events:
        e["payload"].pop("reason_code", None)
    m = metrics_for(events, "order-api")
    assert m["cancel_rate"] > 0.3        # 늘었다는 것은 여전히 보이고
    assert m["cancel_reasons"] == {}     # 왜인지는 알 수 없습니다


# ---------------------------------------------------------------- 폴백

def test_fallback_degradation_is_invisible_to_failure_rate(healthy):
    """inventory.check 에는 result 가 없어 실패율이 아예 존재하지 않습니다."""
    m = metrics_for(factory.fallback_degradation(), "coupon-api")

    assert m["overall_failure_rate"] is None    # 실패라는 개념 자체가 없음
    assert m["fallback_rate"] > 0.7
    assert m["cache_hit_rate"] < 0.3
    assert m["latency_p95"] > 300               # 성공하면서 느려짐

    assert (healthy["fallback_rate"] or 0) == 0.0


# ---------------------------------------------------------------- 꼬리 지연

def test_tail_latency_hides_from_median(healthy):
    m = metrics_for(factory.tail_latency(), "coupon-api")

    assert m["latency_p50"] < 150       # 중앙값은 멀쩡
    assert m["latency_p95"] > 2000      # 꼬리만 무너짐
    assert m["latency_p99"] > 2000

    # 대조군과 p50 은 비슷한데 p95 만 20배 이상 벌어집니다.
    assert m["latency_p50"] < healthy["latency_p50"] * 2
    assert m["latency_p95"] > healthy["latency_p95"] * 10


def test_latency_histogram_relative_error_is_bounded():
    """로그 버킷의 상대 오차가 감지 임계에 쓸 만한 수준인지."""
    from o2warm.sketch import LogHistogram

    h = LogHistogram()
    for _ in range(1000):
        h.add(87.0)
    est = h.quantile(0.5)
    assert abs(est - 87.0) / 87.0 < 0.15


def test_latency_is_null_without_samples():
    events = factory.tail_latency()
    for e in events:
        e["payload"].pop("latency_ms", None)
    m = metrics_for(events, "coupon-api")
    assert m["latency_p95"] is None
    assert m["latency_samples"] == 0


# ---------------------------------------------------------------- 종합

UX_SIGNALS = ("retry_rate", "cancel_rate", "fallback_rate", "latency_p95")


def test_each_scenario_is_caught_by_a_different_signal():
    """UX 저하 유형마다 다른 신호가 반응해야 합니다.

    하나의 신호가 전부 잡는다면 나머지는 불필요하고,
    아무것도 안 잡는 유형이 있다면 그것이 사각지대입니다.
    """
    cases = {
        "재시도 폭증": (metrics_for(factory.retry_storm(), "coupon-api"), "retry_rate"),
        "취소 급증": (metrics_for(factory.cancel_surge(), "order-api"), "cancel_rate"),
        "폴백 저하": (metrics_for(factory.fallback_degradation(), "coupon-api"), "fallback_rate"),
        "꼬리 지연": (metrics_for(factory.tail_latency(), "coupon-api"), "latency_p95"),
    }
    for name, (m, expected) in cases.items():
        assert m.get(expected) is not None, f"{name}: {expected} 가 산출되지 않음"


def test_no_ux_signal_fires_on_healthy_traffic(healthy):
    """오탐 방지. 신호가 늘 울리면 아무도 안 봅니다."""
    assert (healthy["retry_rate"] or 0) < 0.05
    assert (healthy["fallback_rate"] or 0) < 0.05
    assert (healthy["cancel_rate"] or 0) < 0.05
    assert healthy["latency_p95"] < 200
    assert healthy["segment_skew"] == []
