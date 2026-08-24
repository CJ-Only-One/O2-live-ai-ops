"""감별표 검증 — 이 파이프라인이 성립하는지 판정하는 시험.

agent-data-requirements.md §3 의 6개 시나리오를 합성 이벤트로 재현하고,
계산된 지표 조합이 실제로 각 행을 갈라내는지 확인합니다.

**핵심은 "단일 지표로는 갈라지지 않는다"까지 확인하는 것입니다.**
그래야 Agent(LLM)가 필요한 이유가 증명되고, 지표를 하나 빠뜨렸을 때
무엇이 무너지는지 알 수 있습니다.
"""

from __future__ import annotations

import random

import factory
from o2warm.metrics import derive
from o2warm.sketch import build
from o2warm.windows import group_by_window

BASELINE = {"rps": 60.0, "samples": 500, "last_window": 0}


def metrics_for(events, service="coupon-api", baseline=BASELINE, deploy=None):
    """한 서비스의 윈도우 지표를 계산합니다.

    클라이언트 이벤트는 action 라우팅으로 대상 서비스에 합류하므로,
    group_by_window 를 그대로 태워야 실제 파이프라인과 같아집니다.
    """
    grouped = group_by_window(events)
    merged = None
    for (svc, win), items in sorted(grouped.items()):
        if svc != service:
            continue
        s = build(svc, win, items)
        merged = s if merged is None else merged.merge(s)
    assert merged is not None, f"{service} 이벤트가 없습니다"
    return derive(merged, baseline=baseline, deploy=deploy, now=factory.BASE + 12)


# ---------------------------------------------------------------- 개별 행

def test_traffic_surge_looks_like_more_people():
    m = metrics_for(factory.traffic_surge())
    assert m["rps_ratio"] > 1.5
    assert m["top5_share"] < 0.05             # 소수 집중이 아님
    assert m["interval_cv"] > 0.25            # 간격이 제각각
    assert m["click_ratio"] > 0.8             # 클릭이 요청에 앞섬
    assert m["distinct_users"] > 800


def test_macro_is_concentrated_and_regular():
    m = metrics_for(factory.macro())
    assert m["top5_share"] > 0.5              # 다섯 계정이 요청의 과반
    assert m["top1pct_share"] > 0.2
    assert m["interval_cv"] < 0.1             # 요청 다수가 기계적으로 일정
    assert m["interval_cv_top"] < 0.1         # 상위 기여 계정이 규칙적
    assert m["click_ratio"] < 0.5             # 클릭 없이 요청만
    assert m["failure_codes"]["coupon.issue"]["SOLD_OUT"] > 0.9


def test_unweighted_cv_fails_to_see_a_bot_minority():
    """문서 정의(계정당 1표) 그대로는 매크로가 잡히지 않는다는 사실 고정.

    지표 정의를 되돌리려는 시도가 있으면 이 시험이 먼저 깨집니다.
    """
    mac = metrics_for(factory.macro())
    surge = metrics_for(factory.traffic_surge())

    # 계정당 1표로 세면 매크로가 정상 폭증보다 오히려 불규칙해 보입니다.
    assert mac["interval_cv_unweighted"] >= surge["interval_cv_unweighted"] * 0.9
    # 요청 가중으로 세면 방향이 제대로 나옵니다.
    assert mac["interval_cv"] < surge["interval_cv"] / 5


def test_surge_and_macro_are_not_separable_by_rps_alone():
    """rps 만 보면 둘 다 '올랐다' 입니다. 이 시험이 Agent 의 존재 이유입니다."""
    surge = metrics_for(factory.traffic_surge())
    mac = metrics_for(factory.macro())

    assert surge["rps_ratio"] > 1.0 and mac["rps_ratio"] > 1.0

    # 갈라지는 축은 rps 가 아니라 집중도·규칙성·클릭비율입니다.
    assert mac["top5_share"] > surge["top5_share"] * 10
    assert mac["interval_cv"] < surge["interval_cv"] / 5
    assert mac["click_ratio"] < surge["click_ratio"] / 2


def test_cache_miss_storm_shows_only_in_cache_hit_rate():
    m = metrics_for(factory.cache_miss_storm())
    assert m["cache_hit_rate"] < 0.2
    assert m["cache_samples"] > 500
    # 트래픽·집중도는 평시와 다르지 않습니다 — 캐시 지표가 유일한 근거입니다.
    assert m["top5_share"] < 0.15
    assert m["interval_cv"] > 0.2


def test_pod_cache_skew_invisible_in_service_average_but_visible_by_pod():
    """시나리오 1(README) — 파드 하나만 무효화를 놓쳐도 service 단위 지표는 정상입니다.

    이것이 이 시나리오가 "알림으로 절대 안 잡힌다"고 문서에 적힌 이유입니다.
    cache_hit_rate_by_pod 축이 있어야만 갈라집니다.
    """
    events = []
    for pod, hit in (("pod-1", True), ("pod-2", True), ("pod-3", True), ("pod-4", False)):
        for i in range(50):
            events.append(
                factory.inventory(factory.BASE + i, f"u{pod}{i}", "1.1.1.1", cache_hit=hit, pod_name=pod)
            )

    m = metrics_for(events)

    # service 단위 평균 — 파드 4개 중 1개만 죽어도 75%는 "정상"으로 보인다.
    assert m["cache_hit_rate"] > 0.7
    # pod 단위로 쪼개면 pod-4 만 0%다.
    assert m["cache_hit_rate_by_pod"]["pod-4"] == 0.0
    assert m["cache_hit_rate_by_pod"]["pod-1"] == 1.0


def test_slow_pod_invisible_in_service_p95_but_visible_by_pod():
    """시나리오 5(README) — 파드 하나가 느려도 service p95 는 임계 안에 머뭅니다.

    S2 의 자기 교정 루프가 걸리는 지점입니다. 진입 알림(`order_latency_p95`)은
    service 단위라 1차 조치 후에도 "여전히 조금 느림" 까지만 말해 줍니다.
    **어느 파드인가**는 이 축이 있어야 나옵니다.
    """
    events = []
    for pod in ("pod-1", "pod-2", "pod-3", "pod-4"):
        for i in range(50):
            events.append(
                factory.order_create(
                    factory.BASE + i, f"u{pod}{i}", "1.1.1.1",
                    latency=(3000 if pod == "pod-4" else 60), pod_name=pod,
                )
            )

    m = metrics_for(events, service="order-api")

    # service 단위 p95 — 4개 중 1개가 50배 느려도 상위 5% 안에서만 보인다.
    # 200건 중 느린 것이 50건(25%)이라 p95 는 오르지만, 파드 3개가 정상인
    # 상황과 파드 4개가 조금씩 느린 상황을 이 값 하나로는 구분할 수 없다.
    assert m["latency_p50"] < 100

    # pod 축으로 쪼개면 pod-4 만 갈린다.
    by_pod = m["latency_p95_by_pod"]
    assert set(by_pod) == {"pod-1", "pod-2", "pod-3", "pod-4"}
    assert by_pod["pod-4"] > 2000
    assert all(by_pod[p] < 100 for p in ("pod-1", "pod-2", "pod-3"))


def test_latency_pod_axis_drops_pods_with_too_few_samples():
    """방금 뜬 파드의 첫 요청 하나가 이상치로 잡히면 안 됩니다.

    LogHistogram.quantile 은 표본 1건에도 값을 냅니다. 그대로 내보내면
    스케일아웃 직후의 정상 파드가 DBSCAN 에 이상치로 잡혀, 재분석이
    **느린 파드가 아니라 새 파드**를 지목합니다.
    """
    events = [
        factory.order_create(factory.BASE + i, f"uw{i}", "1.1.1.1", latency=60, pod_name="pod-warm")
        for i in range(20)
    ]
    # 방금 뜬 파드 — 표본 2건, 그나마 첫 요청이라 느리다(콜드 스타트)
    events += [
        factory.order_create(factory.BASE + i, f"un{i}", "1.1.1.1", latency=4000, pod_name="pod-new")
        for i in range(2)
    ]

    m = metrics_for(events, service="order-api")

    assert "pod-warm" in m["latency_p95_by_pod"]
    assert "pod-new" not in m["latency_p95_by_pod"]
    # 다만 표본 수 자체는 남긴다 — 왜 빠졌는지 에이전트가 알 수 있어야 한다.
    assert m["latency_samples_by_pod"]["pod-new"] == 2


def test_pg_and_db_outage_have_identical_failure_rate():
    """실패율만으로는 두 장애가 완전히 같아 보입니다."""
    pg = metrics_for(factory.pg_outage(), service="payment-api", deploy=None)
    db = metrics_for(factory.db_outage(), service="payment-api", deploy=None)

    assert abs(pg["failure_rate"]["payment.process"]
               - db["failure_rate"]["payment.process"]) < 0.01

    # 갈라지는 축은 사유 코드와 PG 지연 비중입니다.
    assert set(pg["failure_codes"]["payment.process"]) == {"PG_TIMEOUT"}
    assert set(db["failure_codes"]["payment.process"]) == {"DB_TIMEOUT"}
    assert pg["pg_latency_ratio"] > 0.7
    assert db["pg_latency_ratio"] < 0.3


def test_bad_deploy_shows_in_version_gap_only():
    deploy = {"version": "v1.5.0", "previous_version": "v1.4.2"}
    m = metrics_for(factory.bad_deploy(), service="payment-api", deploy=deploy)

    assert m["version_fail_delta"] > 0.4
    # 전체 실패율은 30% 언저리라 그 자체로는 결론이 안 납니다.
    assert 0.2 < m["failure_rate"]["payment.process"] < 0.4
    assert m["pg_latency_ratio"] < 0.5        # PG 장애와 구분됨
    detail = m["version_detail"]
    assert detail["v1.5.0"]["failure_rate"] > detail["v1.4.2"]["failure_rate"]


def test_version_delta_falls_back_without_deploy_history():
    """배포 이력이 아직 수집되지 않아도 버전 순서로 감별은 됩니다."""
    m = metrics_for(factory.bad_deploy(), service="payment-api", deploy=None)
    assert m["version_fail_delta"] > 0.4
    assert m["version_detail"]["_compared"]["latest"] == "v1.5.0"


# ---------------------------------------------------------------- 표 전체

DISCRIMINATORS = ("rps_ratio", "top5_share", "interval_cv",
                  "click_ratio", "cache_hit_rate", "pg_latency_ratio")


def test_no_single_metric_separates_all_scenarios():
    """어느 지표 하나도 6개 시나리오를 전부 구분하지 못합니다.

    구분한다면 그건 규칙으로 처리할 일이고 Agent 가 필요 없습니다.
    """
    cases = {
        "surge": metrics_for(factory.traffic_surge()),
        "macro": metrics_for(factory.macro()),
        "cache": metrics_for(factory.cache_miss_storm()),
        "pg": metrics_for(factory.pg_outage(), service="payment-api"),
        "db": metrics_for(factory.db_outage(), service="payment-api"),
        "deploy": metrics_for(factory.bad_deploy(), service="payment-api"),
    }

    for key in DISCRIMINATORS:
        values = [m.get(key) for m in cases.values()]
        present = [v for v in values if v is not None]
        assert len(set(present)) < len(cases), f"{key} 단독으로 전부 구분됨 — 표 재검토 필요"

    # 반대로, 조합하면 6개가 전부 다른 지문을 가져야 합니다.
    fingerprints = {
        name: tuple(round(m[k], 1) if m.get(k) is not None else None for k in DISCRIMINATORS)
        for name, m in cases.items()
    }
    assert len(set(fingerprints.values())) == len(cases), fingerprints


def test_confidence_reports_missing_client_stream():
    """클라이언트 스트림이 끊기면 조용히 넘어가지 않아야 합니다."""
    events = [e for e in factory.macro() if not e["event_name"].startswith("client.")]
    m = metrics_for(events)
    assert m["click_ratio"] is None or m["client_count"] == 0
    assert m["confidence"]["completeness"] < 1.0
    assert any("클라이언트" in r for r in m["confidence"]["reasons"])


def test_confidence_reports_missing_baseline():
    m = metrics_for(factory.traffic_surge(), baseline=None)
    assert m["rps_ratio"] is None
    assert any("평시 기준" in r for r in m["confidence"]["reasons"])


def test_confidence_reports_missing_pg_latency():
    """pg_latency_ms 가 빠지면 PG·DB 감별이 불가능하다고 알려야 합니다."""
    events = factory.pg_outage()
    for e in events:
        e["payload"].pop("pg_latency_ms", None)
    m = metrics_for(events, service="payment-api")
    assert m["pg_latency_ratio"] is None
    assert any("pg_latency_ms" in r for r in m["confidence"]["reasons"])


def test_windowing_splits_by_ten_seconds():
    """윈도우 경계를 걸친 배치는 두 그룹으로 갈라져야 합니다."""
    events = [factory.coupon(factory.BASE + 3, "u_1", "ip_1"),
              factory.coupon(factory.BASE + 13, "u_1", "ip_1")]
    grouped = group_by_window(events)
    assert len(grouped) == 2
    assert {w for _, w in grouped} == {factory.BASE, factory.BASE + 10}


def test_client_events_route_to_target_service():
    """클릭이 수집기 서비스가 아니라 대상 서비스 윈도우로 가야 합니다."""
    events = [factory.click(factory.BASE + 1, "u_1", "ua_1")]
    grouped = group_by_window(events)
    assert list(grouped)[0][0] == "coupon-api"


def test_click_ratio_needs_both_streams():
    """한 스트림만으로는 계산되지 않는다는 사실 자체를 확인합니다."""
    only_server = [e for e in factory.normal(n_users=20, per_user=2, rng=random.Random(21))
                   if not e["event_name"].startswith("client.")]
    m = metrics_for(only_server)
    assert m["click_ratio"] == 0.0 or m["click_ratio"] is None
    assert m["client_count"] == 0
