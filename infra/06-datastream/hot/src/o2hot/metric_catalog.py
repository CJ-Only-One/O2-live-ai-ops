"""Dify가 물리 Datadog query를 몰라도 되는 논리 지표 Adapter."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Callable

from .datadog import query as datadog_query

CONTRACT_VERSION = "metric-read.v1"
_SAFE_TAG = re.compile(r"^[A-Za-z0-9_.:/-]{1,80}$")
_SERVICES = {"api", "chat-gateway", "order-worker", "o2-canary"}
_GROUPS = {"pod_name"}

METRIC_CATALOG = {
    "rps": {
        "source": "datadog_native",
        "primary": {
            "api": "sum:trace.fastapi.request.hits{$scope}$group.as_rate()",
            "chat-gateway": "sum:o2.app.business_event{$scope,event:chat.send}$group.as_rate()",
            "order-worker": "sum:o2.app.business_event{$scope,event:order.confirm}$group.as_rate()",
        },
        "sample": {
            "api": "sum:trace.fastapi.request.hits{$scope}.as_count()",
            "chat-gateway": "sum:o2.app.business_event{$scope,event:chat.send}.as_count()",
            "order-worker": "sum:o2.app.business_event{$scope,event:order.confirm}.as_count()",
        },
        "fallback": None,
        "unit": "request/s",
        "primary_scale": 1,
        "fallback_scale": 1,
        "value_type": "rate",
        "default_window_seconds": 300,
        "minimum_samples": 1,
        "maximum_freshness_seconds": 120,
    },
    "latency_p95": {
        "source": "datadog_apm",
        "primary": "p95:trace.fastapi.request{$scope}$group",
        "sample": "sum:trace.fastapi.request.hits{$scope}.as_count()",
        "fallback": None,
        "unit": "ms",
        # Datadog APM trace metric의 API 단위는 second, 기존 논리 계약은 ms다.
        "primary_scale": 1000,
        "fallback_scale": 1,
        "value_type": "gauge",
        "default_window_seconds": 300,
        "minimum_samples": 1,
        "maximum_freshness_seconds": 120,
    },
    "failure_rate": {
        "source": "dogstatsd",
        "primary": "sum:o2.app.business_event{$scope,result:failed}.as_count() / sum:o2.app.business_event{$scope}.as_count()",
        "sample": "sum:o2.app.business_event{$scope}.as_count()",
        "fallback": None,
        "unit": "ratio",
        "primary_scale": 1,
        "fallback_scale": 1,
        "value_type": "ratio",
        "default_window_seconds": 300,
        "minimum_samples": 1,
        "maximum_freshness_seconds": 120,
    },
    "cache_hit_rate": {
        "source": "dogstatsd",
        "primary": "sum:o2.app.cache_access{$scope,result:hit}.as_count() / sum:o2.app.cache_access{$scope}.as_count()",
        "sample": "sum:o2.app.cache_access{$scope}.as_count()",
        "fallback": None,
        "unit": "ratio",
        "primary_scale": 1,
        "fallback_scale": 1,
        "value_type": "ratio",
        "default_window_seconds": 300,
        "minimum_samples": 1,
        "maximum_freshness_seconds": 120,
    },
    "chat_fanout_p95": {
        "source": "dogstatsd",
        "primary": "p95:o2.app.operation.duration{$scope,operation:chat.fanout}",
        "sample": "sum:o2.app.business_event{$scope,event:chat.send}.as_count()",
        "fallback": None,
        "unit": "ms",
        "primary_scale": 1,
        "fallback_scale": 1,
        "value_type": "gauge",
        "default_window_seconds": 300,
        "minimum_samples": 1,
        "maximum_freshness_seconds": 120,
    },
    "chat_propagation_p95_ms": {
        "source": "dogstatsd",
        "primary": "p95:o2.chat.propagation{$scope}$group",
        "sample": "sum:o2.app.fanout.items{$scope,result:delivered}.as_count()",
        "fallback": None,
        "unit": "ms",
        "primary_scale": 1,
        "fallback_scale": 1,
        "value_type": "gauge",
        "default_window_seconds": 300,
        "minimum_samples": 1,
        "maximum_freshness_seconds": 120,
    },
    "block_rate": {
        "source": "dogstatsd",
        # Datadog tag index는 값도 소문자로 정규화한다. 송신 패킷의
        # CHANNEL_LIMITED를 그대로 쿼리하면 metric은 있는데 영구 No Data다.
        "primary": "sum:o2.app.failure{$scope,event:chat.send,failure_code:channel_limited}.as_count() / sum:o2.app.business_event{$scope,event:chat.send}.as_count()",
        "sample": "sum:o2.app.business_event{$scope,event:chat.send}.as_count()",
        "fallback": None,
        "unit": "ratio",
        "primary_scale": 1,
        "fallback_scale": 1,
        "value_type": "ratio",
        "default_window_seconds": 300,
        "minimum_samples": 1,
        "maximum_freshness_seconds": 120,
    },
    "items_per_sec": {
        "source": "dogstatsd",
        "primary": "sum:o2.app.fanout.items{$scope,result:delivered}.as_rate()",
        "sample": "sum:o2.app.fanout.items{$scope,result:delivered}.as_count()",
        "fallback": None,
        "unit": "item/s",
        "primary_scale": 1,
        "fallback_scale": 1,
        "value_type": "rate",
        "default_window_seconds": 300,
        "minimum_samples": 1,
        "maximum_freshness_seconds": 120,
    },
    "pipeline_freshness": {
        "source": "warm_stream_derived",
        "primary": "max:o2.warm.pipeline_freshness_seconds{$scope}",
        "sample": None,
        "fallback": None,
        "unit": "s",
        "primary_scale": 1,
        "fallback_scale": 1,
        "value_type": "gauge",
        "default_window_seconds": 300,
        "minimum_samples": 0,
        "maximum_freshness_seconds": 120,
    },
}

# Native 전환이 끝난 지표는 Warm fallback을 두지 않는다. 데이터가 없으면
# NO_DATA로 드러나야 계측/배포 문제를 Warm 값이 가리지 않는다.
METRIC_CATALOG.update({
    "latency_p50": {**METRIC_CATALOG["latency_p95"], "primary": "p50:trace.fastapi.request{$scope}$group"},
    "latency_p99": {**METRIC_CATALOG["latency_p95"], "primary": "p99:trace.fastapi.request{$scope}$group"},
    "event_count": {
        "source": "dogstatsd", "primary": "sum:o2.app.business_event{$scope}$group.as_count()",
        "sample": "sum:o2.app.business_event{$scope}.as_count()", "fallback": None,
        "unit": "event", "primary_scale": 1, "fallback_scale": 1, "value_type": "count",
        "default_window_seconds": 300, "minimum_samples": 1, "maximum_freshness_seconds": 120,
    },
    "retry_rate": {
        "source": "dogstatsd", "primary": "sum:o2.app.retry{$scope}.as_count() / sum:o2.app.retry_eligible{$scope}.as_count()",
        "sample": "sum:o2.app.retry_eligible{$scope}.as_count()", "fallback": None,
        "unit": "ratio", "primary_scale": 1, "fallback_scale": 1, "value_type": "ratio",
        "default_window_seconds": 300, "minimum_samples": 1, "maximum_freshness_seconds": 120,
    },
    "fallback_rate": {
        "source": "dogstatsd", "primary": "sum:o2.app.fallback{$scope}.as_count() / sum:o2.app.fallback_attempt{$scope}.as_count()",
        "sample": "sum:o2.app.fallback_attempt{$scope}.as_count()", "fallback": None,
        "unit": "ratio", "primary_scale": 1, "fallback_scale": 1, "value_type": "ratio",
        "default_window_seconds": 300, "minimum_samples": 1, "maximum_freshness_seconds": 120,
    },
    "cancel_rate": {
        "source": "dogstatsd", "primary": "sum:o2.app.cancel{$scope}.as_count() / sum:o2.app.order_create{$scope}.as_count()",
        "sample": "sum:o2.app.order_create{$scope}.as_count()", "fallback": None,
        "unit": "ratio", "primary_scale": 1, "fallback_scale": 1, "value_type": "ratio",
        "default_window_seconds": 300, "minimum_samples": 1, "maximum_freshness_seconds": 120,
    },
    "db_latency_p95": {
        "source": "datadog_span_metric", "primary": "p95:o2.apm.db.duration{$scope}$group",
        "sample": "sum:trace.fastapi.request.hits{$scope}.as_count()", "fallback": None,
        "unit": "ms", "primary_scale": 0.000001, "fallback_scale": 1, "value_type": "gauge",
        "default_window_seconds": 300, "minimum_samples": 1, "maximum_freshness_seconds": 120,
    },
})


class MetricRequestError(ValueError):
    pass


def _request(body: dict[str, Any]) -> tuple[str, dict[str, Any], str, str, int, list[str]]:
    metric = body.get("metric")
    if metric not in METRIC_CATALOG:
        raise MetricRequestError("unsupported metric")
    service = body.get("service")
    env = body.get("env", "dev")
    event = body.get("event")
    groups = body.get("group_by", [])
    if service not in _SERVICES or not isinstance(env, str) or not _SAFE_TAG.fullmatch(env):
        raise MetricRequestError("invalid service or env")
    if event is not None and (not isinstance(event, str) or not _SAFE_TAG.fullmatch(event)):
        raise MetricRequestError("invalid event")
    if not isinstance(groups, list) or any(group not in _GROUPS for group in groups):
        raise MetricRequestError("invalid group_by")
    raw_window = body.get("window_seconds", METRIC_CATALOG[metric]["default_window_seconds"])
    if not isinstance(raw_window, int) or not 60 <= raw_window <= 3600:
        raise MetricRequestError("invalid window_seconds")
    scope = f"service:{service},env:{env}" + (f",event:{event}" if event else "")
    group = f" by {{{','.join(groups)}}}" if groups else ""
    return metric, METRIC_CATALOG[metric], scope, group, raw_window, groups


def _render(template: str, scope: str, group: str) -> str:
    return template.replace("$scope", scope).replace("$group", group)


def _template(value: str | dict[str, str] | None, service: str) -> str | None:
    return value.get(service) if isinstance(value, dict) else value


def _points(series: dict[str, Any], to_ts: int | None) -> list[tuple[int, float]]:
    """이 series 의 유효한 점들. **아직 안 닫힌 마지막 버킷은 뺀다.**

    Datadog 은 창 끝의 버킷을 집계 중인 상태로도 돌려주는데, 그때 값이
    `null` 이 아니라 **0** 으로 온다. 그 0 을 그대로 지표 값으로 쓰면
    "처리량이 0" 이나 "실패율 1.0" 같은 극단값이 나온다(T-040).

    `interval` 은 Datadog 응답이 series 마다 주는 롤업 간격이다. 버킷 시작
    시각에 그 간격을 더해 `to_ts` 를 넘으면 아직 안 닫힌 것으로 본다 —
    매직넘버를 쓰지 않는 이유다.
    """
    interval = series.get("interval")
    cutoff_ms: float | None = None
    if to_ts is not None and isinstance(interval, (int, float)) and interval > 0:
        cutoff_ms = (to_ts - float(interval)) * 1000

    out: list[tuple[int, float]] = []
    for point in series.get("pointlist") or []:
        if not (isinstance(point, list) and len(point) == 2 and point[1] is not None):
            continue
        timestamp_ms = int(point[0])
        if cutoff_ms is not None and timestamp_ms > cutoff_ms:
            continue
        out.append((timestamp_ms, float(point[1])))
    return out


def _all_points(result: dict[str, Any], to_ts: int | None) -> list[tuple[int, float]]:
    return [pt for series in result.get("series") or [] for pt in _points(series, to_ts)]


def _reduce(points: list[tuple[int, float]], value_type: str) -> float | None:
    """창 전체를 하나의 값으로 줄인다. **점 하나를 고르지 않는다.**

    `_latest()` 는 300초 창에서 몇 초짜리 점 하나를 썼다. 그 버킷이
    완성됐더라도 창의 1% 도 안 되는 표본이라, 조치 효과를 판정하는 자리에
    쓰기에는 통계적으로 부족했다. 창을 길게 잡은 이유가 노이즈를 평균내기
    위해서인데 마지막에 점 하나로 되돌아갔다.

    `ratio` 는 여기 오지 않는다 — 비율의 평균은 비율이 아니라서
    `_observed_ratio()` 가 분자·분모를 각각 합산한 뒤 나눈다.
    """
    if not points:
        return None
    values = [v for _, v in points]
    if value_type == "count":
        return sum(values)
    if value_type == "gauge":
        # 백분위는 평균낼 수 없다. 복구 판정에서는 **최댓값**이 보수적이다 —
        # 운 좋은 버킷 하나로 "복구" 를 선언하지 않는다.
        return max(values)
    # rate: 창 평균이 "지금 처리량" 이다.
    return sum(values) / len(values)


def _latest(result: dict[str, Any]) -> tuple[float | None, int | None]:
    candidates = _all_points(result, None)
    if not candidates:
        return None, None
    timestamp_ms, value = max(candidates, key=lambda item: item[0])
    return value, timestamp_ms


def _observed(
    query_fn,
    query_text: str,
    from_ts: int,
    to_ts: int,
    scale: float = 1,
    *,
    sum_points: bool = False,
    value_type: str = "gauge",
) -> dict[str, Any]:
    result = query_fn(query_text, from_ts, to_ts)
    points = _all_points(result, to_ts)
    timestamp_ms = max((ts for ts, _ in points), default=None)
    if sum_points:
        value = sum(v for _, v in points) if points else None
    else:
        value = _reduce(points, value_type)
    value = value * scale if value is not None else None
    groups = []
    for series in result.get("series") or []:
        series_points = _points(series, to_ts)
        group_value = _reduce(series_points, value_type)
        if group_value is not None:
            groups.append({
                "scope": series.get("scope"),
                "value": group_value * scale,
                "timestamp_ms": max(ts for ts, _ in series_points),
            })
    return {"query": query_text, "value": value, "timestamp_ms": timestamp_ms, "groups": groups}


def _observed_ratio(
    query_fn,
    numerator_text: str,
    denominator_text: str,
    from_ts: int,
    to_ts: int,
    scale: float = 1,
) -> dict[str, Any]:
    """비율은 **합의 비율**로 낸다. 비율의 평균이 아니다.

    카탈로그의 `primary` 가 `분자 / 분모` 한 문자열이라 Datadog 이 버킷마다
    나눠 준다. 그 점들을 평균내면 분모가 버킷마다 다를 때 틀린 값이 된다.
    창 끝에서 분자·분모 버킷이 어긋나면 0 이나 1.0 같은 극단값도 나온다(T-040).

    그래서 쿼리를 ` / ` 로 쪼개 각각 창 전체를 합산한 뒤 나눈다. 카탈로그
    스키마는 안 바꾼다 — 여섯 ratio 지표가 모두 정확히 두 조각이다.
    """
    numerator = _observed(query_fn, numerator_text, from_ts, to_ts, sum_points=True)
    denominator = _observed(query_fn, denominator_text, from_ts, to_ts, sum_points=True)
    top, bottom = numerator["value"], denominator["value"]
    value = (top / bottom) * scale if top is not None and bottom else None
    timestamps = [t for t in (numerator["timestamp_ms"], denominator["timestamp_ms"]) if t is not None]
    return {
        "query": f"{numerator_text} / {denominator_text}",
        "value": value,
        "timestamp_ms": min(timestamps) if timestamps else None,
        "groups": [],
    }


def read_metric(
    body: dict[str, Any],
    *,
    query_fn: Callable[[str, int, int], dict[str, Any]] = datadog_query,
    now: int | None = None,
) -> dict[str, Any]:
    metric, catalog, scope, group, window, groups = _request(body)
    to_ts = int(now if now is not None else time.time())
    from_ts = to_ts - window
    service = body["service"]
    primary_template = _template(catalog["primary"], service)
    sample_template = _template(catalog["sample"], service)
    if primary_template is None:
        raise MetricRequestError("metric is not available for service")
    value_type = catalog["value_type"]
    primary_query = _render(primary_template, scope, group)
    if value_type == "ratio" and " / " in primary_query:
        # 비율은 분자·분모를 각각 창 전체로 합산한 뒤 나눈다(_observed_ratio).
        numerator_text, denominator_text = primary_query.split(" / ", 1)
        primary = _observed_ratio(
            query_fn,
            numerator_text,
            denominator_text,
            from_ts,
            to_ts,
            catalog["primary_scale"],
        )
    else:
        primary = _observed(
            query_fn,
            primary_query,
            from_ts,
            to_ts,
            catalog["primary_scale"],
            value_type=value_type,
        )
    sample = (
        _observed(
            query_fn,
            _render(sample_template, scope, ""),
            from_ts,
            to_ts,
            sum_points=True,
        )
        if sample_template
        else {"query": None, "value": 1 if primary["value"] is not None else 0, "timestamp_ms": primary["timestamp_ms"], "groups": []}
    )
    fallback = (
        _observed(
            query_fn,
            _render(catalog["fallback"], scope, group),
            from_ts,
            to_ts,
            catalog["fallback_scale"],
            value_type=value_type,
        )
        if catalog["fallback"]
        else {"query": None, "value": None, "timestamp_ms": None, "groups": []}
    )

    sample_count = int(sample["value"]) if sample["value"] is not None else 0
    freshness = max(0, to_ts - primary["timestamp_ms"] // 1000) if primary["timestamp_ms"] is not None else None
    primary_ok = (
        primary["value"] is not None
        and freshness is not None
        and freshness <= catalog["maximum_freshness_seconds"]
        and sample_count >= catalog["minimum_samples"]
    )
    selected = primary if primary_ok else fallback
    fallback_used = not primary_ok and fallback["value"] is not None
    selected_freshness = max(0, to_ts - selected["timestamp_ms"] // 1000) if selected["timestamp_ms"] is not None else None
    status = "OK" if selected["value"] is not None else "NO_DATA"
    point_time = (
        datetime.fromtimestamp(selected["timestamp_ms"] / 1000, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
        if selected["timestamp_ms"] is not None
        else None
    )
    difference_ratio = None
    if primary["value"] is not None and fallback["value"] not in (None, 0):
        difference_ratio = abs(primary["value"] - fallback["value"]) / abs(fallback["value"])

    return {
        "metric": metric,
        "value": selected["value"],
        "unit": catalog["unit"],
        "status": status,
        "window_start": datetime.fromtimestamp(from_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "window_end": datetime.fromtimestamp(to_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "point_timestamp": point_time,
        "freshness_seconds": selected_freshness,
        "sample_count": sample_count,
        "source": (catalog["source"] if primary_ok else "warm_stream_derived") if status == "OK" else None,
        "contract_version": CONTRACT_VERSION,
        "fallback_used": fallback_used,
        "group_by": groups,
        "groups": selected["groups"] if groups else [],
        "shadow": {
            "primary_source": catalog["source"],
            "primary_value": primary["value"],
            "fallback_value": fallback["value"],
            "difference_ratio": difference_ratio,
        },
    }
