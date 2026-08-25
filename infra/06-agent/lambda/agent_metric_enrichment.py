"""Collect approved recovery metrics before invoking Dify.

The invocation-queue payload remains authoritative and immutable.  This module
adds current numeric observations only to the copy serialized for Dify, using
the existing ``assessment_input.measurements`` extension point.
"""

from __future__ import annotations

import copy
import json
import math
import os
import urllib.parse
import urllib.request
from typing import Any, Callable


FAMILY_METRICS = {
    "CHAT_DEGRADATION": {
        "hot": (
            ("chat_propagation_p95_ms", "chat_propagation_p95_ms"),
            ("block_rate", "channel_block_rate"),
        ),
        "service": "chat-gateway",
    },
    "READ_PATH_DEGRADATION": {
        "warm": (
            "p95_ms",
            "inventory_check_rate",
            "overall_failure_rate",
            "baseline_p95_ms",
            "baseline_inventory_check_rate",
            "baseline_overall_failure_rate",
        ),
        "service": "api",
        "read_path": True,
    },
}


def _lambda_json(client: Any, function_name: str, event: dict[str, Any]) -> dict[str, Any]:
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(event, separators=(",", ":")).encode(),
    )
    payload = response["Payload"].read()
    outer = json.loads(payload)
    if outer.get("statusCode") != 200:
        return {}
    body = outer.get("body", "{}")
    return json.loads(body) if isinstance(body, str) else body


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _hot(client: Any, family: dict[str, Any], environment: str) -> dict[str, float]:
    found: dict[str, float] = {}
    for logical_name, output_name in family.get("hot", ()):
        event = {
            "requestContext": {"http": {"method": "POST", "path": "/v1/hot/datadog/metric"}},
            "body": json.dumps({
                "metric": logical_name,
                "service": family["service"],
                "env": environment,
                "window_seconds": 300,
            }, separators=(",", ":")),
        }
        result = _lambda_json(client, os.environ["HOT_API_FUNCTION"], event)
        value = _number(result.get("value")) if result.get("status") == "OK" else None
        if value is not None:
            found[output_name] = value
    return found


def _warm(client: Any, ssm: Any, family: dict[str, Any], broadcast_id: str | None) -> dict[str, float]:
    key = ssm.get_parameter(
        Name=os.environ["WARM_API_KEY_PARAM"], WithDecryption=True,
    )["Parameter"]["Value"]
    params = {"service": family["service"], "windows": "6"}
    if broadcast_id:
        params["broadcast_id"] = broadcast_id
    event = {
        "requestContext": {"http": {"method": "GET", "path": "/v1/warm/snapshot"}},
        "headers": {"x-o2-key": key},
        "queryStringParameters": params,
    }
    latest = _lambda_json(client, os.environ["WARM_API_FUNCTION"], event).get("latest") or {}
    return {
        name: value
        for name in family.get("warm", ())
        if (value := _number(latest.get(name))) is not None
    }


def _read_path(ssm: Any, broadcast_id: str | None, opener: Callable[..., Any]) -> dict[str, float]:
    if not broadcast_id or not os.environ.get("READ_PATH_STATUS_URL"):
        return {}
    key = ssm.get_parameter(
        Name=os.environ["READ_PATH_ADMIN_KEY_PARAM"], WithDecryption=True,
    )["Parameter"]["Value"]
    separator = "&" if "?" in os.environ["READ_PATH_STATUS_URL"] else "?"
    url = os.environ["READ_PATH_STATUS_URL"] + separator + urllib.parse.urlencode(
        {"broadcast_id": broadcast_id}
    )
    request = urllib.request.Request(url, headers={"x-admin-key": key}, method="GET")
    with opener(request, timeout=5) as response:
        body = json.loads(response.read())
    value = _number(body.get("read_path_degraded_active"))
    return {"read_path_degraded_active": value} if value is not None else {}


def enrich(
    payload: dict[str, Any], lambda_client: Any, ssm_client: Any,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> tuple[dict[str, Any], list[str]]:
    """Return a Dify-only enriched copy and sanitized collection errors."""
    enriched = copy.deepcopy(payload)
    family_name = enriched["normalized_context"]["incident_family"]
    family = FAMILY_METRICS.get(family_name)
    if not family:
        return enriched, []
    environment = enriched["normalized_context"]["environment"]
    broadcast_ids = enriched["normalized_context"].get("broadcast_ids") or []
    broadcast_id = broadcast_ids[0] if broadcast_ids else None
    values: dict[str, float] = {}
    errors: list[str] = []
    for source, collect in (
        ("hot", lambda: _hot(lambda_client, family, environment)),
        ("warm", lambda: _warm(lambda_client, ssm_client, family, broadcast_id)),
        ("read_path", lambda: _read_path(ssm_client, broadcast_id, opener)),
    ):
        if source not in family and not (source == "read_path" and family.get("read_path")):
            continue
        try:
            values.update(collect())
        except Exception:
            errors.append(source)

    datadog = next(
        (signal for signal in enriched["signals"] if signal["source"] == "DATADOG_MONITOR"),
        None,
    )
    if datadog is not None:
        measurements = datadog["evidence"]["assessment_input"]["measurements"]
        available = max(0, 16 - len(measurements))
        for name, value in list(values.items())[:available]:
            measurements[name] = value
    return enriched, errors
