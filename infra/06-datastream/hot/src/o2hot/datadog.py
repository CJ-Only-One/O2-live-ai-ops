"""Datadog Hot Path 시계열 지표 역쿼리.

o2warm/datadog.py 는 Datadog 을 **감지용 싱크**로 쓴다(집계 결과를
보낸다). 이 모듈은 반대 방향이다 — Agent 가 알림을 받은 뒤 "그래서 지금
수치가 얼마인가"를 되묻는 **조회 대상**으로 쓴다. v2 series API 는 전송
전용이라 조회에 못 쓰므로 v1 /query 를 쓴다.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from . import secrets
from .settings import settings

MAX_POINTS = 10  # 응답 크기를 억제한다. Agent 는 최근 추세만 보면 된다.


class DatadogKeyError(RuntimeError):
    """Datadog api-key/app-key 를 구하지 못했을 때. 호출자가 500 으로 바꾼다."""


def _keys() -> tuple[str, str]:
    api_key = secrets.datadog_api_key()
    app_key = secrets.datadog_app_key()
    if not api_key or not app_key:
        raise DatadogKeyError(
            "Datadog api-key/app-key 를 구하지 못했습니다 (시크릿 미설정 또는 조회 실패)"
        )
    return api_key, app_key


def query(query_str: str, from_ts: int, to_ts: int) -> dict:
    """Datadog v1 `/query` 를 호출해 시계열을 되돌려준다.

    실패(HTTP 오류·타임아웃)는 여기서 삼키지 않는다 — 조회 실패는 Agent
    에게 그대로 보여야 다음 판단(재시도·다른 쿼리)을 할 수 있다. o2warm 의
    "전송 실패를 삼킨다"와 반대 방향인 이유는 이 모듈 docstring 참고.
    """
    api_key, app_key = _keys()

    url = (
        f"https://api.{settings.dd_site}/api/v1/query"
        f"?from={from_ts}&to={to_ts}&query={urllib.parse.quote(query_str)}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "DD-API-KEY": api_key,
            "DD-APPLICATION-KEY": app_key,
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(req, timeout=settings.dd_timeout) as resp:
        dd_res = json.loads(resp.read().decode("utf-8"))

    series_out = [
        {
            "metric": s.get("metric"),
            "scope": s.get("scope"),
            "expression": s.get("expression"),
            "pointlist": (s.get("pointlist") or [])[-MAX_POINTS:],
        }
        for s in dd_res.get("series", [])
    ]

    return {
        "query": query_str,
        "from_ts": from_ts,
        "to_ts": to_ts,
        "status": dd_res.get("status"),
        "series_count": len(series_out),
        "series": series_out,
    }
