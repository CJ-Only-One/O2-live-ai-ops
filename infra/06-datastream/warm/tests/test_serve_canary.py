"""warm serve 가 카나리를 실제 서비스로 내주지 않는지.

D-052 는 파이프라인 생존 카나리를 도입하면서 대가를 하나 명시했습니다 —
**합성 트래픽이 에이전트가 읽는 경로에 새어 나가면 안 된다.** 그 대가를
갚는 두 자리 중 하나가 여기입니다(다른 하나는 Athena 의 `business_events` 뷰).

여기가 비면 조용히 틀립니다. `service=o2-canary` 는 오류를 내지 않고
**그럴듯한 지표를 돌려줍니다** — rps 는 항상 0.1, 실패율은 0. 에이전트가
그걸 "아주 건강한 서비스" 로 읽어도 막을 것이 없습니다.
"""

from __future__ import annotations

import json

import serve


def _call(path, params=None, method="GET", body=None):
    event = {
        "requestContext": {"http": {"method": method, "path": path}},
        "queryStringParameters": params or {},
        "body": json.dumps(body) if body else None,
    }
    return serve.handler(event, None)


def _bypass_auth(monkeypatch):
    monkeypatch.setattr(serve, "_authorized", lambda event: True)


def test_metrics_rejects_the_canary_service(monkeypatch):
    _bypass_auth(monkeypatch)
    res = _call("/v1/warm/metrics", {"service": serve.CANARY_SERVICE})

    assert res["statusCode"] == 400
    # 거절 이유가 응답에 있어야 다음 질문이 달라진다.
    assert serve.CANARY_SERVICE in json.loads(res["body"])["error"]


def test_snapshot_rejects_the_canary_service(monkeypatch):
    _bypass_auth(monkeypatch)
    res = _call("/v1/warm/snapshot", {"service": serve.CANARY_SERVICE})
    assert res["statusCode"] == 400


def test_incident_snapshot_rejects_the_canary_service(monkeypatch):
    """조치 전후 비교에 카나리가 섞이면 복구 판정이 통째로 무의미해집니다."""
    _bypass_auth(monkeypatch)
    res = _call(
        "/v1/warm/incidents/INC-1/snapshot",
        method="POST",
        body={"phase": "PRE", "service": serve.CANARY_SERVICE},
    )
    assert res["statusCode"] == 400


def test_rejection_is_case_insensitive_and_ignores_padding(monkeypatch):
    """`O2-Canary ` 로 물으면 통과하는 우회로를 두지 않습니다."""
    _bypass_auth(monkeypatch)
    for probe in (" o2-canary", "O2-Canary", "O2-CANARY "):
        res = _call("/v1/warm/metrics", {"service": probe})
        assert res["statusCode"] == 400, probe


def test_real_services_are_untouched(monkeypatch):
    """카나리와 이름이 겹치지 않는 서비스는 그대로 지나가야 합니다."""
    _bypass_auth(monkeypatch)
    seen = {}

    class _Fake:
        def windows(self, service, count):
            seen["service"] = service
            return []

    monkeypatch.setattr(serve, "client", lambda: _Fake())
    res = _call("/v1/warm/metrics", {"service": "o2-canary-api"})

    assert res["statusCode"] == 200
    assert seen["service"] == "o2-canary-api"
