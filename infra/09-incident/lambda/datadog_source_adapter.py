"""Normalize a Datadog webhook payload into agent.trigger.v1.

This is a shadow-only ingress. It has its own Function URL and never invokes
the legacy Worker or Dify. Terraform deploys it disabled with an empty monitor
allowlist and a 2100 cutover. A Shadow run must enable all three guards for one
synthetic Datadog monitor before a message can reach the Agent Signal Queue.

Logs contain request ids, statuses, and stable error codes only. Webhook bodies,
alert text, queue bodies, and secrets are never logged.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

SOURCE_FIELDS = {
    "schema_version",
    "event_id",
    "cycle_key",
    "monitor_id",
    "occurred_at",
    "alert_transition",
    "priority",
    "env",
    "service",
    "alert_title",
    "alert_body",
    "alert_query",
    "host",
    "tags",
    "link",
    "assessment_input",
}

STRING_LIMITS = {
    "event_id": (1, 256),
    "cycle_key": (1, 256),
    "monitor_id": (0, 128),
    "priority": (0, 64),
    "env": (1, 128),
    "service": (1, 128),
    "alert_title": (0, 1000),
    "alert_body": (0, 30000),
    "alert_query": (0, 30000),
    "host": (0, 512),
    "tags": (0, 30000),
    "link": (0, 4096),
}

TRANSITIONS = {
    "Triggered",
    "Re-Triggered",
    "Recovered",
    "Warn",
    "No Data",
    "Renotify",
}

EVIDENCE_FIELDS = {
    "event_id",
    "cycle_key",
    "monitor_id",
    "priority",
    "env",
    "service",
    "alert_title",
    "alert_body",
    "alert_query",
    "host",
    "tags",
    "link",
    "assessment_input",
}

GUARDRAILS = {
    "analysis_mode": "READ_ONLY",
    "automatic_remediation_allowed": False,
    "must_preserve_uncertainty": True,
    "raw_chat_included": False,
}

ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
MAX_QUEUE_BODY_BYTES = 30000

_clients: dict[str, Any] = {}
_secrets: dict[str, Any] | None = None


class AdapterError(Exception):
    """Expected failure with a content-free error code and HTTP status."""

    def __init__(self, code: str, status_code: int = 500):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class ContractError(AdapterError):
    def __init__(self, code: str):
        super().__init__(f"CONTRACT_REJECTED:{code}", 400)


def _client(name: str) -> Any:
    if name not in _clients:
        import boto3

        _clients[name] = boto3.client(name)
    return _clients[name]


def _request_id(context: Any) -> str:
    value = getattr(context, "aws_request_id", "unknown")
    return value if isinstance(value, str) and value else "unknown"


def _response(status_code: int, body: str) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "text/plain; charset=utf-8"},
        "body": body,
    }


def _enabled() -> bool:
    return (
        os.environ.get("DATADOG_SOURCE_ADAPTER_EXECUTION_ENABLED", "false").lower()
        == "true"
    )


def _load_secrets() -> dict[str, Any]:
    global _secrets
    if _secrets is None:
        try:
            result = _client("secretsmanager").get_secret_value(
                SecretId=os.environ["DATADOG_SOURCE_ADAPTER_SECRET_NAME"]
            )
            value = json.loads(result["SecretString"])
        except Exception as error:
            raise AdapterError("SECRET_READ_FAILED") from error
        if not isinstance(value, dict) or not isinstance(
            value.get("webhook-secret"), str
        ):
            raise AdapterError("SECRET_FORMAT_INVALID")
        _secrets = value
    return _secrets


def _authenticate(event: Any) -> None:
    if not isinstance(event, dict):
        raise ContractError("FUNCTION_EVENT")
    headers = event.get("headers") or {}
    if not isinstance(headers, dict):
        raise ContractError("HEADERS")
    normalized = {
        str(name).lower(): value
        for name, value in headers.items()
        if isinstance(value, str)
    }
    supplied = normalized.get("x-dd-secret", "")
    expected = _load_secrets()["webhook-secret"]
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise AdapterError("AUTH_REJECTED", 403)


def _decode_body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body")
    if not isinstance(raw, str):
        raise ContractError("BODY")
    if event.get("isBase64Encoded") is True:
        try:
            raw = base64.b64decode(raw, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            raise ContractError("BODY_BASE64") from None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise ContractError("BODY_JSON") from None
    if not isinstance(value, dict):
        raise ContractError("BODY_OBJECT")
    return value


def _string(value: Any, field: str) -> str:
    minimum, maximum = STRING_LIMITS[field]
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise ContractError(field.upper())
    return value


def _normalize_occurred_at(value: Any) -> tuple[str, int]:
    if not isinstance(value, str) or not value:
        raise ContractError("OCCURRED_AT")

    parsed: datetime
    try:
        epoch = Decimal(value)
    except InvalidOperation:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ContractError("OCCURRED_AT") from None
        if parsed.tzinfo is None:
            raise ContractError("OCCURRED_AT")
        parsed = parsed.astimezone(timezone.utc)
    else:
        if not epoch.is_finite() or epoch < 0:
            raise ContractError("OCCURRED_AT")
        try:
            parsed = datetime.fromtimestamp(float(epoch), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            raise ContractError("OCCURRED_AT") from None

    occurred_at = parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return occurred_at, int(parsed.timestamp())


def validate_source(payload: Any) -> tuple[dict[str, Any], int]:
    if not isinstance(payload, dict) or set(payload) != SOURCE_FIELDS:
        raise ContractError("SOURCE_FIELDS")
    if payload["schema_version"] != "1":
        raise ContractError("SOURCE_SCHEMA_VERSION")

    for field in STRING_LIMITS:
        _string(payload[field], field)
    transition = payload["alert_transition"]
    if transition not in TRANSITIONS:
        raise ContractError("ALERT_TRANSITION")
    observed_at = _validate_assessment_input(payload["assessment_input"])

    occurred_at, occurred_at_epoch = _normalize_occurred_at(payload["occurred_at"])
    normalized = dict(payload)
    normalized["occurred_at"] = occurred_at
    normalized["assessment_input"] = dict(payload["assessment_input"], observed_at=observed_at)
    return normalized, occurred_at_epoch


def _validate_assessment_input(value: Any) -> str:
    fields = {
        "evidence_type", "observed_at", "sample_count", "data_state",
        "signal_strength", "scope", "measurements",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ContractError("ASSESSMENT_INPUT_FIELDS")
    if value["evidence_type"] not in {
        "CHAT_PROPAGATION_P95", "CHAT_NORMAL_USER_BLOCK_RATE",
        "SERVICE_TAIL_LATENCY", "POD_TAIL_LATENCY", "POD_CPU_UTILIZATION",
        "POD_VERSION", "POD_AGE", "TELEMETRY_FRESHNESS", "INTEGRITY_VIOLATION",
        "COMPOSITE_CONDITION",
    }:
        raise ContractError("ASSESSMENT_EVIDENCE_TYPE")
    # $DATE_POSIX 웹훅 변수는 epoch 숫자 문자열이다. 여기서 검증만 하고 안
    # 바꾸면 그 원본 문자열이 그대로 Correlator까지 가는데, Correlator의
    # _parse_datetime()은 ISO8601만 받아 매번 CONTRACT_REJECTED:
    # ASSESSMENT_OBSERVED_AT로 죽는다(2026-08-26 real test로 재현). occurred_at과
    # 같은 정규화를 여기서도 적용해 호출자가 정규화된 값을 쓰게 한다.
    observed_at, _ = _normalize_occurred_at(value["observed_at"])
    if not isinstance(value["sample_count"], int) or isinstance(value["sample_count"], bool) or value["sample_count"] < 0:
        raise ContractError("ASSESSMENT_SAMPLE_COUNT")
    if value["data_state"] not in {"PRESENT", "NO_DATA", "STALE"}:
        raise ContractError("ASSESSMENT_DATA_STATE")
    if value["signal_strength"] not in {"STANDARD", "STRONG"}:
        raise ContractError("ASSESSMENT_SIGNAL_STRENGTH")
    scope = value["scope"]
    if not isinstance(scope, dict) or set(scope) != {"environment", "service", "pod", "version", "broadcast_id"}:
        raise ContractError("ASSESSMENT_SCOPE_FIELDS")
    for field in ("environment", "service"):
        if not isinstance(scope[field], str) or not 1 <= len(scope[field]) <= 128:
            raise ContractError("ASSESSMENT_SCOPE")
    for field, maximum in (("pod", 253), ("version", 128), ("broadcast_id", 128)):
        if scope[field] is not None and (not isinstance(scope[field], str) or not 1 <= len(scope[field]) <= maximum):
            raise ContractError("ASSESSMENT_SCOPE")
    measurements = value["measurements"]
    if not isinstance(measurements, dict) or len(measurements) > 16:
        raise ContractError("ASSESSMENT_MEASUREMENTS")
    for key, measurement in measurements.items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key):
            raise ContractError("ASSESSMENT_MEASUREMENTS")
        if not isinstance(measurement, (int, float)) or isinstance(measurement, bool):
            raise ContractError("ASSESSMENT_MEASUREMENTS")
    evidence_type = value["evidence_type"]
    if evidence_type in {"CHAT_PROPAGATION_P95", "CHAT_NORMAL_USER_BLOCK_RATE"} and scope["broadcast_id"] is None:
        raise ContractError("ASSESSMENT_S1_SCOPE")
    if evidence_type in {"POD_TAIL_LATENCY", "POD_CPU_UTILIZATION", "POD_VERSION", "POD_AGE"} and scope["pod"] is None:
        raise ContractError("ASSESSMENT_S2_POD_SCOPE")
    if evidence_type == "POD_VERSION" and scope["version"] is None:
        raise ContractError("ASSESSMENT_S2_VERSION_SCOPE")
    required_measurement = {
        "CHAT_PROPAGATION_P95": "p95_ms",
        "CHAT_NORMAL_USER_BLOCK_RATE": "block_rate_ratio",
        "SERVICE_TAIL_LATENCY": "p95_ms",
        "POD_TAIL_LATENCY": "p95_ms",
        "POD_CPU_UTILIZATION": "cpu_utilization_ratio",
        "POD_AGE": "pod_age_seconds",
    }.get(evidence_type)
    if value["data_state"] == "PRESENT" and required_measurement and required_measurement not in measurements:
        raise ContractError("ASSESSMENT_REQUIRED_MEASUREMENT")
    return observed_at


def _allowed_monitor_ids() -> set[str]:
    raw = os.environ.get("DATADOG_SOURCE_ADAPTER_ALLOWED_MONITOR_IDS", "")
    values = raw.split(",") if raw else []
    shadow_mode = os.environ.get("INCIDENT_SHADOW_MODE", "true").lower() == "true"
    if not values or any(not 1 <= len(value) <= 128 for value in values) or (shadow_mode and len(values) != 1):
        raise AdapterError("SYNTHETIC_MONITOR_ALLOWLIST_INVALID")
    return set(values)


def _deterministic_ulid(payload: dict[str, Any]) -> str:
    parsed = datetime.fromisoformat(payload["occurred_at"].replace("Z", "+00:00"))
    timestamp_ms = int(parsed.timestamp() * 1000)
    if not 0 <= timestamp_ms < 2**48:
        raise ContractError("OCCURRED_AT")
    stable_source = "\0".join(
        [payload["cycle_key"], payload["alert_transition"], payload["event_id"]]
    ).encode("utf-8")
    entropy = int.from_bytes(hashlib.sha256(stable_source).digest()[:10], "big")
    value = (timestamp_ms << 80) | entropy
    encoded: list[str] = []
    for _ in range(26):
        encoded.append(ULID_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(encoded))


def build_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    evidence = {field: payload[field] for field in EVIDENCE_FIELDS}
    evidence["transition"] = payload["alert_transition"]
    return {
        "schema_version": "1.0",
        "trigger_id": f"trg_{_deterministic_ulid(payload)}",
        "source": "DATADOG_MONITOR",
        "source_schema": "datadog.alert.v1",
        "trigger_type": "MONITOR_ALERT",
        "idempotency_key": (
            f"datadog:{payload['cycle_key']}:{payload['alert_transition']}"
        ),
        "occurred_at": payload["occurred_at"],
        "trace_id": None,
        "evidence": evidence,
        "guardrails": dict(GUARDRAILS),
    }


def _send(envelope: dict[str, Any]) -> None:
    rendered = json.dumps(
        envelope, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    if len(rendered.encode("utf-8")) > MAX_QUEUE_BODY_BYTES:
        raise ContractError("AGENT_TRIGGER_TOO_LARGE")
    try:
        _client("sqs").send_message(
            QueueUrl=os.environ["AGENT_TRIGGER_QUEUE_URL"],
            MessageBody=rendered,
            MessageAttributes={
                "schema": {"DataType": "String", "StringValue": "agent.trigger.v1"},
                "source": {
                    "DataType": "String",
                    "StringValue": "DATADOG_MONITOR",
                },
            },
        )
    except Exception as error:
        raise AdapterError("AGENT_TRIGGER_SEND_FAILED") from error


def lambda_handler(event: Any, context: Any) -> dict[str, Any]:
    request_id = _request_id(context)
    try:
        _authenticate(event)
        if not _enabled():
            LOGGER.info(
                "datadog_source_adapter request=%s status=EXECUTION_DISABLED",
                request_id,
            )
            return _response(200, "disabled")

        payload, occurred_at_epoch = validate_source(_decode_body(event))
        if payload["monitor_id"] not in _allowed_monitor_ids():
            LOGGER.info(
                "datadog_source_adapter request=%s status=IGNORED_MONITOR_NOT_ALLOWED",
                request_id,
            )
            return _response(200, "ignored")

        try:
            not_before_epoch = int(
                os.environ.get(
                    "DATADOG_SOURCE_ADAPTER_NOT_BEFORE_EPOCH", "4102444800"
                )
            )
        except ValueError:
            raise AdapterError("NOT_BEFORE_INVALID") from None
        if occurred_at_epoch < not_before_epoch:
            LOGGER.info(
                "datadog_source_adapter request=%s status=IGNORED_BEFORE_ACTIVATION",
                request_id,
            )
            return _response(200, "ignored")

        _send(build_envelope(payload))
        LOGGER.info(
            "datadog_source_adapter request=%s status=ENQUEUED",
            request_id,
        )
        return _response(200, "queued")
    except AdapterError as error:
        LOGGER.warning(
            "datadog_source_adapter request=%s status=FAILED error_code=%s",
            request_id,
            error.code,
        )
        return _response(error.status_code, error.code)
    except Exception:
        LOGGER.exception(
            "datadog_source_adapter request=%s status=FAILED error_code=UNEXPECTED",
            request_id,
        )
        return _response(500, "UNEXPECTED")
