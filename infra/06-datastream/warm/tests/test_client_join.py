"""클릭과 서버 요청이 같은 윈도우에서 만나는가.

`click_ratio` 는 이 시스템에서 유일하게 **두 스트림이 만나야만** 나오는
지표입니다. 매크로는 버튼을 누르지 않고 API 를 직접 부르므로, 클릭 대비 요청이
이것 하나로 갈립니다.

만나는 조건이 하나 더 있습니다 — 두 이벤트가 **같은 (service, 윈도우) 아이템**
으로 들어가야 합니다. 클라이언트 이벤트의 목적지는 봉투의 `service` 가 아니라
`O2_WARM_CLICK_ROUTE` 가 정하는데(`windows.service_of`), 그 값이 실제 서비스
이름과 다르면 클릭과 요청이 서로 다른 파티션으로 갈라집니다. **그 상태에서도
Lambda 는 성공하고 아이템도 만들어집니다.** click_ratio 만 영원히 null 입니다.

배포 값은 `infra/06-datastream/warm-path.tf` 의 `O2_WARM_CLICK_ROUTE` 에
있습니다. 여기서는 그 값이 갖춰야 할 성질을 고정합니다.
"""

from __future__ import annotations

import factory
import pytest
from o2warm.metrics import derive
from o2warm.settings import settings
from o2warm.sketch import build
from o2warm.windows import group_by_window

# 우리 서비스는 봉투의 service 가 `api` 하나다 (contracts.md 5.4).
SERVICE = "api"
TS = factory.BASE + 3


def _visit(user: str, ip: str, ua: str) -> list[dict]:
    """구매 버튼을 한 번 누른 방문자 하나.

    클릭 둘(쿠폰·체크아웃)과 서버 이벤트 둘이 짝을 이룬다 — 한 번의 누름이
    `coupon.issue` 와 `order.create` 를 만들기 때문이다 (contracts.md 5.2).
    """

    def client(action):
        return factory.envelope(
            "client.action", TS, service=SERVICE, user=user,
            payload={"action": action, "device_type": "MOBILE_WEB",
                     "ua_key": ua, "target_id": "88213"},
        )

    return [
        client("COUPON_BUTTON_CLICK"),
        client("CHECKOUT_CLICK"),
        factory.envelope(
            "coupon.issue", TS + 1, service=SERVICE, user=user, ip=ip,
            payload={"coupon_id": "88213", "campaign_id": "bc_1042",
                     "result": "SUCCESS", "latency_ms": 87},
        ),
        factory.envelope(
            "order.create", TS + 1, service=SERVICE, user=user, ip=ip,
            payload={"order_id": "od_1", "items": [{"sku_id": "88213", "qty": 1}],
                     "total_amount": 12000, "channel": "LIVE", "latency_ms": 140},
        ),
    ]


def _traffic(n: int = 5) -> list[dict]:
    events = []
    for i in range(n):
        events += _visit(f"u_{i:04d}", f"ip_{i:04d}", "ua_mobile_safari")
    return events


def _metrics(events: list[dict], service: str = SERVICE):
    grouped = group_by_window(events)
    merged = None
    for (svc, win), items in sorted(grouped.items()):
        if svc != service:
            continue
        s = build(svc, win, items)
        merged = s if merged is None else merged.merge(s)
    if merged is None:
        return None
    return derive(merged, now=factory.BASE + 12)


@pytest.fixture
def routed(monkeypatch):
    """warm-path.tf 가 주입하는 값과 같은 라우팅."""
    monkeypatch.setattr(
        settings, "click_route",
        {"COUPON_BUTTON_CLICK": SERVICE, "CHECKOUT_CLICK": SERVICE},
    )
    monkeypatch.setattr(settings, "client_service", SERVICE)


def test_clicks_meet_requests_in_one_window(routed):
    """정상 트래픽에서는 클릭과 요청이 1:1 이다."""
    assert set(group_by_window(_traffic()).keys()) == {(SERVICE, factory.BASE)}

    m = _metrics(_traffic())
    assert m["click_ratio"] == 1.0
    assert m["click_detail"]["coupon"] == {"clicks": 5, "requests": 5, "ratio": 1.0}
    assert m["click_detail"]["checkout"] == {"clicks": 5, "requests": 5, "ratio": 1.0}


def test_macro_traffic_drops_the_ratio(routed):
    """버튼 없이 API 만 부르면 비율이 무너진다 — 이 지표의 존재 이유."""
    human = _traffic(1)
    macro = [e for e in _traffic(20) if e["event_name"] != "client.action"]

    m = _metrics(human + macro)
    assert m["click_ratio"] < 0.1
    assert m["client_count"] == 2
    assert m["business_count"] == 42


def test_client_events_carry_ua_diversity(routed):
    """클라이언트 이벤트가 없으면 ua_diversity 는 null 이다 — 매크로 감별
    두 축 중 하나가 통째로 비어 있다는 뜻이다."""
    assert _metrics(_traffic())["ua_diversity"] is not None

    business_only = [e for e in _traffic() if e["event_name"] != "client.action"]
    assert _metrics(business_only)["ua_diversity"] is None


def test_wrong_route_looks_exactly_like_a_macro_attack(monkeypatch):
    """SDK 예제의 기본값(coupon-api / order-api)을 그대로 두면 어떻게 되는가.

    **빈 값이 아니라 0.0 이 나온다.** 그리고 0.0 은 "버튼 없이 API 만 두드리는
    트래픽"의 신호다 — 배선이 틀렸다는 사실이 매크로 공격과 똑같은 모습으로
    나타난다. 아이템은 만들어지고 Lambda 도 성공하므로 어디에도 오류가 없다.

    조용한 null 보다 나쁘다. 에이전트는 이 값을 근거로 판단하고, 사람은 그
    판단이 왜 틀렸는지 지표에서 찾을 수 없다.
    """
    monkeypatch.setattr(
        settings, "click_route",
        {"COUPON_BUTTON_CLICK": "coupon-api", "CHECKOUT_CLICK": "order-api"},
    )

    events = _traffic()
    assert len(set(group_by_window(events).keys())) == 3

    # 서버 이벤트만 남은 api 윈도우 — 클릭이 0 건이라 "전부 매크로" 로 보인다.
    assert _metrics(events)["click_ratio"] == 0.0

    # 클릭만 있는 윈도우 — 요청이 0 이라 짝이 성립하지 않는다.
    coupon_side = _metrics(events, "coupon-api")
    assert coupon_side["click_detail"]["coupon"]["requests"] == 0
    assert coupon_side["click_detail"]["coupon"]["ratio"] is None
