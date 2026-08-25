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


def _latest(result: dict[str, Any]) -> tuple[float | None, int | None]:
    candidates: list[tuple[int, float]] = []
    for series in result.get("series") or []:
        for point in series.get("pointlist") or []:
            if isinstance(point, list) and len(point) == 2 and point[1] is not None:
                candidates.append((int(point[0]), float(point[1])))
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
) -> dict[str, Any]:
    result = query_fn(query_text, from_ts, to_ts)
    value, timestamp_ms = _latest(result)
    if sum_points:
        values = [
            float(point[1])
            for series in result.get("series") or []
            for point in series.get("pointlist") or []
            if isinstance(point, list) and len(point) == 2 and point[1] is not None
        ]
        value = sum(values) if values else None
    value = value * scale if value is not None else None
    groups = []
    for series in result.get("series") or []:
        group_value, group_timestamp = _latest({"series": [series]})
        if group_value is not None:
            groups.append({
                "scope": series.get("scope"),
                "value": group_value * scale,
                "timestamp_ms": group_timestamp,
            })
    return {"query": query_text, "value": value, "timestamp_ms": timestamp_ms, "groups": groups}


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
    primary = _observed(
        query_fn,
        _render(primary_template, scope, group),
        from_ts,
        to_ts,
        catalog["primary_scale"],
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
