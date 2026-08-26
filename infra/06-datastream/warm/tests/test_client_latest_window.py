"""`latest` 가 열린 윈도우를 주면 안 된다 (T-040).

집계 Lambda 는 이벤트를 받는 대로 DynamoDB 를 갱신하므로, 방금 시작한
윈도우는 **부분 집계 상태**다. 아직 실패가 안 담긴 창에서
`channel_limited_rate = 0`, `failure_codes = {}` 가 나오고, 그 값이 Agent 의
복구 판정으로 그대로 들어가 "정상 복귀" 로 읽힌 사례가 있다.

`windows` 는 열린 창까지 준다 — 추세를 보려면 필요하다. `latest` 만 닫힌
창으로 제한한다.
"""

from __future__ import annotations

from o2warm.client import WarmClient


class FakeStore:
    def __init__(self, items):
        self._items = items

    def recent_metrics(self, service, limit=6):
        return list(self._items)[-limit:]


def window(start, span=10, **extra):
    item = {
        "service": "chat-gateway",
        "window_start": start,
        "window_end": start + span,
        "window_seconds": span,
        "confidence": {},
    }
    item.update(extra)
    return item


NOW = 1787558405.0  # 1787558400 창이 열린 지 5초


def client(items):
    return WarmClient(store=FakeStore(items))


def test_open_window_is_not_returned_as_latest():
    closed = window(1787558390, channel_limited_rate=0.49)
    still_open = window(1787558400, channel_limited_rate=0.0)
    got = client([closed, still_open]).latest("chat-gateway", now=NOW)
    assert got["window_start"] == 1787558390
    assert got["channel_limited_rate"] == 0.49


def test_latest_is_none_when_every_window_is_open():
    """부분값을 주느니 없다고 말한다."""
    assert client([window(1787558400)]).latest("chat-gateway", now=NOW) is None


def test_snapshot_latest_follows_the_same_rule_but_windows_keep_the_open_one():
    closed = window(1787558390, channel_limited_rate=0.49)
    still_open = window(1787558400, channel_limited_rate=0.0)
    bundle = client([closed, still_open]).snapshot(
        "chat-gateway", include=("metrics",), now=NOW
    )
    assert bundle["latest"]["window_start"] == 1787558390
    # 추세용 series 에는 열린 창도 그대로 남는다.
    assert [w["window_start"] for w in bundle["windows"]] == [1787558390, 1787558400]
