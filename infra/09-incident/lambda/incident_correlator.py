"""Deterministically correlate agent.trigger.v1 signals into agent.incident.v1.

Phase 3B deploys this Lambda with both the event source and execution gate
disabled. When Phase 3C explicitly enables it, a bounded synthetic allowlist
is checked before any DynamoDB or SQS access.

The Lambda logs identifiers and sanitized status codes only. Trigger evidence,
Incident snapshots, and queue bodies are never logged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
MAX_INCIDENT_INPUT_CHARS = 30000
MAX_SIGNALS = 20

INCIDENT_FAMILIES = {
    "READ_PATH_DEGRADATION",
    "CHECKOUT_ORDER_DEGRADATION",
    "PAYMENT_DEGRADATION",
    "INVENTORY_DEGRADATION",
    "CHAT_DEGRADATION",
    "PLAYBACK_DEGRADATION",
    "CAPACITY_SATURATION",
    "DEPLOYMENT_REGRESSION",
    "TELEMETRY_PIPELINE_FAILURE",
    "DATA_INTEGRITY_SECURITY_RISK",
    "UNKNOWN",
}

TOP_LEVEL_FIELDS = {
    "schema_version",
    "trigger_id",
    "source",
    "source_schema",
    "trigger_type",
    "idempotency_key",
    "occurred_at",
    "trace_id",
    "evidence",
    "guardrails",
}

TRIGGER_GUARDRAILS = {
    "analysis_mode": "READ_ONLY",
    "automatic_remediation_allowed": False,
    "must_preserve_uncertainty": True,
    "raw_chat_included": False,
}

INCIDENT_GUARDRAILS = {
    **TRIGGER_GUARDRAILS,
    "single_incident_action_lock_required": True,
}

DATADOG_EVIDENCE_FIELDS = {
    "event_id",
    "cycle_key",
    "monitor_id",
    "transition",
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

ASSESSMENT_EVIDENCE_TYPES = {
    "CHAT_PROPAGATION_P95", "CHAT_NORMAL_USER_BLOCK_RATE",
    "SERVICE_TAIL_LATENCY", "POD_TAIL_LATENCY", "POD_CPU_UTILIZATION",
    "POD_VERSION", "POD_AGE", "TELEMETRY_FRESHNESS", "INTEGRITY_VIOLATION",
    "COMPOSITE_CONDITION",
}
SEVERITY_LEVELS = {"UNKNOWN": 0, "INFORMATIONAL": 1, "WARNING": 2, "HIGH": 3, "CRITICAL": 4}

CHAT_EVIDENCE_FIELDS = {
    "candidate_id",
    "candidate_type",
    "broadcast_id",
    "suspected_surface",
    "confidence",
    "window_start",
    "window_end",
    "matched_messages",
    "unique_users",
    "strong_signal_count",
    "weak_signal_count",
    "matched_rule_ids",
    "metric_status",
    "root_cause",
    "requires_metric_corroboration",
}

SOURCE_RULES = {
    "DATADOG_MONITOR": (
        "datadog.alert.v1",
        "MONITOR_ALERT",
        DATADOG_EVIDENCE_FIELDS,
    ),
    "CHAT_INCIDENT_CANDIDATE": (
        "chat.incident_candidate.v1",
        "USER_SYMPTOM_CLUSTER",
        CHAT_EVIDENCE_FIELDS,
    ),
}

_clients: dict[str, Any] = {}


class CorrelatorError(Exception):
    """Expected failure with a content-free error code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ContractError(CorrelatorError):
    pass


def _fail(code: str) -> None:
    raise ContractError(f"CONTRACT_REJECTED:{code}")


def _exact_dict(value: Any, fields: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        _fail(code)
    return value


def _parse_datetime(value: Any, code: str) -> datetime:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail(code)
    if parsed.tzinfo is None:
        _fail(code)
    return parsed


def _string(value: Any, code: str, minimum: int = 0, maximum: int = 30000) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        _fail(code)
    return value


def validate_trigger(payload: Any) -> dict[str, Any]:
    """Validate the correlator-owned subset of agent-trigger-v1.schema.json."""

    payload = _exact_dict(payload, TOP_LEVEL_FIELDS, "TOP_LEVEL_FIELDS")
    if payload["schema_version"] != "1.0":
        _fail("SCHEMA_VERSION")
    if not isinstance(payload["trigger_id"], str) or not re.fullmatch(
        r"trg_[0-9A-HJKMNP-TV-Z]{26}", payload["trigger_id"]
    ):
        _fail("TRIGGER_ID")

    source = payload["source"]
    if source not in SOURCE_RULES:
        _fail("SOURCE")
    source_schema, trigger_type, evidence_fields = SOURCE_RULES[source]
    if payload["source_schema"] != source_schema:
        _fail("SOURCE_SCHEMA")
    if payload["trigger_type"] != trigger_type:
        _fail("TRIGGER_TYPE")
    _string(payload["idempotency_key"], "IDEMPOTENCY_KEY", 1, 256)
    _parse_datetime(payload["occurred_at"], "OCCURRED_AT")
    if payload["trace_id"] is not None:
        _string(payload["trace_id"], "TRACE_ID", 0, 128)

    if payload["guardrails"] != TRIGGER_GUARDRAILS:
        _fail("GUARDRAILS")
    evidence = _exact_dict(payload["evidence"], evidence_fields, "EVIDENCE_FIELDS")
    if source == "CHAT_INCIDENT_CANDIDATE":
        _validate_chat(evidence)
    else:
        _validate_datadog(evidence)
    return payload


def _validate_chat(evidence: dict[str, Any]) -> None:
    if not isinstance(evidence["candidate_id"], str) or not re.fullmatch(
        r"cand_[0-9A-HJKMNP-TV-Z]{26}", evidence["candidate_id"]
    ):
        _fail("CHAT_CANDIDATE_ID")
    if evidence["candidate_type"] != "USER_PERCEIVED_LATENCY":
        _fail("CHAT_CANDIDATE_TYPE")
    if not isinstance(evidence["broadcast_id"], str) or not re.fullmatch(
        r"bc_[0-9]+", evidence["broadcast_id"]
    ):
        _fail("CHAT_BROADCAST_ID")
    if evidence["suspected_surface"] not in {
        "READ_PATH",
        "PLAYBACK",
        "CHAT",
        "UNKNOWN",
    }:
        _fail("CHAT_SURFACE")
    if evidence["confidence"] not in {"MEDIUM", "LOW"}:
        _fail("CHAT_CONFIDENCE")
    _parse_datetime(evidence["window_start"], "CHAT_WINDOW_START")
    _parse_datetime(evidence["window_end"], "CHAT_WINDOW_END")
    for field in ("matched_messages", "unique_users"):
        if (
            not isinstance(evidence[field], int)
            or isinstance(evidence[field], bool)
            or evidence[field] < 1
        ):
            _fail("CHAT_POSITIVE_COUNTS")
    for field in ("strong_signal_count", "weak_signal_count"):
        if (
            not isinstance(evidence[field], int)
            or isinstance(evidence[field], bool)
            or evidence[field] < 0
        ):
            _fail("CHAT_NONNEGATIVE_COUNTS")
    rule_ids = evidence["matched_rule_ids"]
    if (
        not isinstance(rule_ids, list)
        or not rule_ids
        or len(rule_ids) != len(set(rule_ids))
        or any(
            not isinstance(value, str) or not re.fullmatch(r"[a-z0-9_]+", value)
            for value in rule_ids
        )
    ):
        _fail("CHAT_RULE_IDS")
    if evidence["metric_status"] != "NOT_CHECKED":
        _fail("CHAT_METRIC_STATUS")
    if evidence["root_cause"] != "UNDETERMINED":
        _fail("CHAT_ROOT_CAUSE")
    if evidence["requires_metric_corroboration"] is not True:
        _fail("CHAT_METRIC_GATE")


def _validate_datadog(evidence: dict[str, Any]) -> None:
    limits = {
        "event_id": (1, 256),
        "cycle_key": (1, 256),
        "monitor_id": (0, 128),
        "priority": (0, 64),
        "env": (0, 128),
        "service": (0, 128),
        "alert_title": (0, 1000),
        "alert_body": (0, 30000),
        "alert_query": (0, 30000),
        "host": (0, 512),
        "tags": (0, 30000),
        "link": (0, 4096),
    }
    for field, (minimum, maximum) in limits.items():
        _string(evidence[field], f"DATADOG_{field.upper()}", minimum, maximum)
    if evidence["transition"] not in {
        "Triggered",
        "Re-Triggered",
        "Recovered",
        "Warn",
        "No Data",
        "Renotify",
    }:
        _fail("DATADOG_TRANSITION")
    value = evidence["assessment_input"]
    if not isinstance(value, dict) or set(value) != {
        "evidence_type", "observed_at", "sample_count", "data_state",
        "signal_strength", "scope", "measurements",
    }:
        _fail("ASSESSMENT_INPUT_FIELDS")
    if value["evidence_type"] not in ASSESSMENT_EVIDENCE_TYPES:
        _fail("ASSESSMENT_EVIDENCE_TYPE")
    _parse_datetime(value["observed_at"], "ASSESSMENT_OBSERVED_AT")
    if not isinstance(value["sample_count"], int) or isinstance(value["sample_count"], bool) or value["sample_count"] < 0:
        _fail("ASSESSMENT_SAMPLE_COUNT")
    if value["data_state"] not in {"PRESENT", "NO_DATA", "STALE"}:
        _fail("ASSESSMENT_DATA_STATE")
    if value["signal_strength"] not in {"STANDARD", "STRONG"}:
        _fail("ASSESSMENT_SIGNAL_STRENGTH")
    scope = value["scope"]
    if not isinstance(scope, dict) or set(scope) != {"environment", "service", "pod", "version", "broadcast_id"}:
        _fail("ASSESSMENT_SCOPE_FIELDS")
    if scope["environment"] != evidence["env"] or scope["service"] != evidence["service"]:
        _fail("ASSESSMENT_SCOPE_MISMATCH")
    if any(scope[field] is not None and not isinstance(scope[field], str) for field in ("pod", "version", "broadcast_id")):
        _fail("ASSESSMENT_SCOPE")
    measurements = value["measurements"]
    if not isinstance(measurements, dict) or len(measurements) > 16 or any(
        not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key)
        or not isinstance(measurement, (int, float)) or isinstance(measurement, bool)
        for key, measurement in measurements.items()
    ):
        _fail("ASSESSMENT_MEASUREMENTS")
    evidence_type = value["evidence_type"]
    if evidence_type in {"CHAT_PROPAGATION_P95", "CHAT_NORMAL_USER_BLOCK_RATE"} and scope["broadcast_id"] is None:
        _fail("ASSESSMENT_S1_SCOPE")
    if evidence_type in {"POD_TAIL_LATENCY", "POD_CPU_UTILIZATION", "POD_VERSION", "POD_AGE"} and scope["pod"] is None:
        _fail("ASSESSMENT_S2_POD_SCOPE")
    if evidence_type == "POD_VERSION" and scope["version"] is None:
        _fail("ASSESSMENT_S2_VERSION_SCOPE")
    required_measurement = {
        "CHAT_PROPAGATION_P95": "p95_ms", "CHAT_NORMAL_USER_BLOCK_RATE": "block_rate_ratio",
        "SERVICE_TAIL_LATENCY": "p95_ms", "POD_TAIL_LATENCY": "p95_ms",
        "POD_CPU_UTILIZATION": "cpu_utilization_ratio", "POD_AGE": "pod_age_seconds",
    }.get(evidence_type)
    if value["data_state"] == "PRESENT" and required_measurement and required_measurement not in measurements:
        _fail("ASSESSMENT_REQUIRED_MEASUREMENT")


def _encode_crockford(value: int, length: int) -> str:
    encoded = ["0"] * length
    for index in range(length - 1, -1, -1):
        encoded[index] = CROCKFORD[value & 31]
        value >>= 5
    return "".join(encoded)


def new_incident_id(now_ms: int | None = None, entropy: bytes | None = None) -> str:
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    entropy = secrets.token_bytes(10) if entropy is None else entropy
    if not 0 <= now_ms < 2**48 or len(entropy) != 10:
        raise CorrelatorError("INCIDENT_ID_INPUT")
    value = (now_ms << 80) | int.from_bytes(entropy, "big")
    return f"inc_{_encode_crockford(value, 26)}"


def _epoch(value: str) -> int:
    return int(_parse_datetime(value, "OCCURRED_AT").timestamp())


def _mapping(raw: str, code: str) -> dict[str, dict[str, str]]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise CorrelatorError(code) from None
    if not isinstance(value, dict):
        raise CorrelatorError(code)
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, dict):
            raise CorrelatorError(code)
        if set(item) != {
            "evidence_role",
            "evidence_type",
            "incident_family",
            "symptom_family",
            "suspected_surface",
            "service",
            "minimum_samples",
            "freshness_seconds",
            "severity_level",
            "strong_exception_allowed",
        }:
            raise CorrelatorError(code)
        if item["incident_family"] not in INCIDENT_FAMILIES - {"UNKNOWN"}:
            raise CorrelatorError(code)
        if item["evidence_role"] not in {"PRIMARY", "CORROBORATING", "CONTEXT"}:
            raise CorrelatorError(code)
        if item["evidence_type"] not in ASSESSMENT_EVIDENCE_TYPES | {"USER_SYMPTOM_CLUSTER"}:
            raise CorrelatorError(code)
        if not isinstance(item["minimum_samples"], int) or item["minimum_samples"] < 1:
            raise CorrelatorError(code)
        if not isinstance(item["freshness_seconds"], int) or item["freshness_seconds"] < 1:
            raise CorrelatorError(code)
        if item["severity_level"] not in set(SEVERITY_LEVELS) - {"UNKNOWN"}:
            raise CorrelatorError(code)
        if not isinstance(item["strong_exception_allowed"], bool):
            raise CorrelatorError(code)
        if item["strong_exception_allowed"] and item["evidence_type"] not in {
            "INTEGRITY_VIOLATION",
            "USER_SYMPTOM_CLUSTER",
        }:
            raise CorrelatorError(code)
        if item["symptom_family"] not in {
            "LATENCY",
            "AVAILABILITY",
            "ERROR_RATE",
            "UNKNOWN",
        }:
            raise CorrelatorError(code)
        if item["suspected_surface"] not in {
            "READ_PATH",
            "PLAYBACK",
            "CHAT",
            "UNKNOWN",
        }:
            raise CorrelatorError(code)
        if not isinstance(item["service"], str) or not item["service"]:
            raise CorrelatorError(code)
    return value


def settings_from_environment() -> dict[str, Any]:
    try:
        window = int(os.environ.get("INCIDENT_CORRELATION_WINDOW_SECONDS", "0"))
    except ValueError:
        raise CorrelatorError("CORRELATION_WINDOW_INVALID") from None
    if window <= 0:
        raise CorrelatorError("CORRELATION_WINDOW_NOT_CONFIGURED")

    raw_allowlist = os.environ.get("INCIDENT_CORRELATOR_ALLOWED_IDEMPOTENCY_KEYS", "")
    allowlist = set(raw_allowlist.split(",")) if raw_allowlist else set()
    shadow_mode = os.environ.get("INCIDENT_SHADOW_MODE", "true").lower() == "true"
    if (shadow_mode and not 1 <= len(allowlist) <= 8) or (not shadow_mode and allowlist) or any(not value for value in allowlist):
        raise CorrelatorError("SYNTHETIC_ALLOWLIST_INVALID")

    environment = os.environ.get("DEPLOYMENT_ENVIRONMENT", "")
    if not environment:
        raise CorrelatorError("DEPLOYMENT_ENVIRONMENT_MISSING")

    try:
        recovery_window = int(os.environ.get("INCIDENT_RECOVERY_WINDOW_SECONDS", "0"))
        cooldown = int(os.environ.get("INCIDENT_COOLDOWN_SECONDS", "0"))
        reopen_window = int(os.environ.get("INCIDENT_REOPEN_WINDOW_SECONDS", "0"))
    except ValueError:
        raise CorrelatorError("INCIDENT_WINDOW_POLICY_INVALID") from None
    if min(recovery_window, cooldown, reopen_window) < 0:
        raise CorrelatorError("INCIDENT_WINDOW_POLICY_INVALID")
    return {
        "window_seconds": window,
        "allowed_idempotency_keys": allowlist,
        "shadow_mode": shadow_mode,
        "environment": environment,
        "recovery_window_seconds": recovery_window,
        "cooldown_seconds": cooldown,
        "reopen_window_seconds": reopen_window,
        "chat_surface_map": _mapping(
            os.environ.get("INCIDENT_CHAT_SURFACE_MAP_JSON", "{}"),
            "CHAT_SURFACE_MAP_INVALID",
        ),
        "datadog_monitor_map": _mapping(
            os.environ.get("INCIDENT_DATADOG_MONITOR_MAP_JSON", "{}"),
            "DATADOG_MONITOR_MAP_INVALID",
        ),
    }


def normalize_trigger(trigger: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    evidence = trigger["evidence"]
    occurred_at_epoch = _epoch(trigger["occurred_at"])
    if trigger["source"] == "CHAT_INCIDENT_CANDIDATE":
        mapping = settings["chat_surface_map"].get(evidence["suspected_surface"])
        broadcast_ids = [evidence["broadcast_id"]]
        environment = settings["environment"]
    else:
        mapping = settings["datadog_monitor_map"].get(evidence["monitor_id"])
        # Datadog evidence 도 방송 축을 가질 수 있다(D-086). S1 Monitor 를
        # `by {broadcast_id}` multi-alert 로 돌리면 그룹 태그가 webhook payload 를
        # 거쳐 `assessment_input.scope.broadcast_id` 로 들어온다.
        #
        # 여기서 버리면 Chat 과 Datadog 이 같은 장애를 잡았을 때 병합된 Incident 의
        # 방송 축이 **어느 source 가 먼저 왔느냐에 따라 달라진다.** 그리고 Dify
        # normalize 가 `LIVE-001` fallback 을 써서 없는 방송에 채널 제한을 걸고도
        # 200 OK 로 성공 기록된다.
        #
        # 필수 여부는 Adapter 와 `_validate_assessment_input` 이 이미 본다 —
        # S1 evidence type 이면 None 을 거부한다. 여기서는 있는 값을 채택만 한다.
        scope_broadcast_id = (evidence["assessment_input"]["scope"] or {}).get("broadcast_id")
        broadcast_ids = [scope_broadcast_id] if scope_broadcast_id else []
        environment = evidence["env"]
        if environment != settings["environment"]:
            return {
                "complete": False,
                "ambiguity_reason": "SOURCE_ENVIRONMENT_MISMATCH",
                "evidence_role": None,
                "event_epoch": occurred_at_epoch,
                "context": {
                    "environment": settings["environment"],
                    "incident_family": "UNKNOWN",
                    "symptom_family": "UNKNOWN",
                    "suspected_surfaces": ["UNKNOWN"],
                    "services": [],
                    "broadcast_ids": broadcast_ids,
                },
                "correlation_key": None,
            }
        if mapping is not None and evidence["service"] != mapping["service"]:
            mapping = None

    if mapping is None or not environment:
        return {
            "complete": False,
            "ambiguity_reason": "INSUFFICIENT_DIMENSIONS",
            "evidence_role": None,
            "event_epoch": occurred_at_epoch,
            "context": {
                "environment": environment or settings["environment"],
                "incident_family": "UNKNOWN",
                "symptom_family": "UNKNOWN",
                "suspected_surfaces": ["UNKNOWN"],
                "services": [],
                "broadcast_ids": broadcast_ids,
            },
            "correlation_key": None,
        }

    context = {
        "environment": environment,
        "incident_family": mapping["incident_family"],
        "symptom_family": mapping["symptom_family"],
        "suspected_surfaces": [mapping["suspected_surface"]],
        "services": [mapping["service"]],
        "broadcast_ids": broadcast_ids,
    }
    correlation_key = "#".join(
        [
            environment,
            mapping["incident_family"],
            mapping["symptom_family"],
            mapping["service"],
            mapping["suspected_surface"],
        ]
    )
    if trigger["source"] == "CHAT_INCIDENT_CANDIDATE":
        sample_count = evidence["unique_users"]
        observed_at = evidence["window_end"]
        data_state = "PRESENT"
        signal_strength = "STANDARD"
        evidence_type = mapping.get("evidence_type", "USER_SYMPTOM_CLUSTER")
        scope = {
            "environment": environment, "service": mapping["service"],
            "pod": None, "version": None, "broadcast_id": evidence["broadcast_id"],
        }
    else:
        assessment_input = evidence["assessment_input"]
        sample_count = assessment_input["sample_count"]
        observed_at = assessment_input["observed_at"]
        data_state = "NO_DATA" if evidence["transition"] == "No Data" else assessment_input["data_state"]
        signal_strength = assessment_input["signal_strength"]
        evidence_type = assessment_input["evidence_type"]
        scope = assessment_input["scope"]
    expected_type = mapping.get("evidence_type", evidence_type)
    minimum_samples = mapping.get("minimum_samples", 1)
    freshness_seconds = mapping.get("freshness_seconds", 300)
    age_seconds = abs(occurred_at_epoch - _epoch(observed_at))
    if evidence_type != expected_type:
        quality_state = "TYPE_MISMATCH"
    elif data_state == "NO_DATA":
        quality_state = "NO_DATA"
    elif data_state == "STALE" or age_seconds > freshness_seconds:
        quality_state = "STALE"
    elif sample_count < minimum_samples:
        quality_state = "INSUFFICIENT_SAMPLES"
    else:
        quality_state = "VALID"
    return {
        "complete": True,
        "ambiguity_reason": None,
        "evidence_role": mapping["evidence_role"] if quality_state == "VALID" else None,
        "configured_role": mapping["evidence_role"],
        "evidence_type": evidence_type,
        "quality_state": quality_state,
        "sample_count": sample_count,
        "minimum_samples": minimum_samples,
        "observed_at": observed_at,
        "freshness_seconds": freshness_seconds,
        "age_seconds": age_seconds,
        "scope": scope,
        "severity_level": mapping.get("severity_level", "WARNING"),
        "strong_exception": quality_state == "VALID"
        and mapping.get("strong_exception_allowed", False)
        and (
            (
                signal_strength == "STRONG"
                and mapping["incident_family"] == "DATA_INTEGRITY_SECURITY_RISK"
                and evidence_type == "INTEGRITY_VIOLATION"
            )
            or (
                trigger["source"] == "CHAT_INCIDENT_CANDIDATE"
                and evidence_type == "USER_SYMPTOM_CLUSTER"
                and evidence["confidence"] == "MEDIUM"
                and evidence["strong_signal_count"] >= 3
                and evidence["unique_users"] >= 4
                and evidence["matched_messages"] >= 4
            )
        ),
        "event_epoch": occurred_at_epoch,
        "context": context,
        "correlation_key": correlation_key,
    }


def _merge_context(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    result = {
        "environment": current["environment"],
        "incident_family": current["incident_family"],
        "symptom_family": current["symptom_family"],
    }
    for field in ("suspected_surfaces", "services", "broadcast_ids"):
        result[field] = sorted(set(current[field]) | set(incoming[field]))
    return result


def _requires_invocation(snapshot: dict[str, Any]) -> bool:
    """Only independently corroborated material revisions may wake the Agent."""

    return (
        snapshot["evidence_assessment"]["verification_state"] == "VERIFIED"
        and snapshot["lifecycle"] != "RECOVERING"
        and not snapshot["notification_policy"]["suppressed"]
    )


def _assess_evidence(
    trigger: dict[str, Any],
    normalized: dict[str, Any],
    correlation_state: str,
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assessment = {
        "primary": list((current or {}).get("primary", [])),
        "corroborating": list((current or {}).get("corroborating", [])),
        "context": list((current or {}).get("context", [])),
    }
    role = normalized["evidence_role"]
    if role is not None:
        field = role.lower()
        if trigger["trigger_id"] not in assessment[field]:
            assessment[field].append(trigger["trigger_id"])
            assessment[field].sort()

    strong_exception = normalized.get("strong_exception", False) or (current or {}).get("strong_exception_applied", False)
    missing = []
    if not assessment["primary"]:
        missing.append("PRIMARY")
    if not assessment["corroborating"]:
        missing.append("CORROBORATING")
    if strong_exception:
        missing = []
    assessment["missing_required_roles"] = missing
    assessment["strong_exception_applied"] = strong_exception
    if correlation_state == "AMBIGUOUS":
        assessment["verification_state"] = "AMBIGUOUS"
    elif not missing and (correlation_state == "CORRELATED" or strong_exception):
        assessment["verification_state"] = "VERIFIED"
    else:
        assessment["verification_state"] = "INSUFFICIENT_EVIDENCE"
    return assessment


def _data_quality(trigger: dict[str, Any], normalized: dict[str, Any], current: dict[str, Any] | None) -> dict[str, Any]:
    assessments = list((current or {}).get("assessments", []))
    assessments.append({
        "trigger_id": trigger["trigger_id"],
        "evidence_type": normalized.get("evidence_type", "UNMAPPED"),
        "configured_role": normalized.get("configured_role"),
        "state": normalized.get("quality_state", "UNMAPPED"),
        "sample_count": normalized.get("sample_count", 0),
        "minimum_samples": normalized.get("minimum_samples", 0),
        "observed_at": normalized.get("observed_at", trigger["occurred_at"]),
        "freshness_seconds": normalized.get("freshness_seconds", 0),
        "age_seconds": normalized.get("age_seconds", 0),
    })
    states = {item["state"] for item in assessments}
    if states == {"VALID"}:
        state = "SUFFICIENT"
    elif "VALID" in states:
        state = "MIXED"
    elif "NO_DATA" in states:
        state = "NO_DATA"
    elif "STALE" in states:
        state = "STALE"
    elif "INSUFFICIENT_SAMPLES" in states:
        state = "INSUFFICIENT_SAMPLES"
    else:
        state = "INVALID"
    return {"state": state, "assessments": assessments}


def _severity(trigger: dict[str, Any], normalized: dict[str, Any], current: dict[str, Any] | None) -> dict[str, Any]:
    previous = (current or {}).get("level", "UNKNOWN")
    incoming = normalized.get("severity_level", "UNKNOWN") if normalized.get("quality_state") == "VALID" else "UNKNOWN"
    level = incoming if SEVERITY_LEVELS[incoming] > SEVERITY_LEVELS[previous] else previous
    basis = list((current or {}).get("basis_trigger_ids", []))
    if incoming != "UNKNOWN" and trigger["trigger_id"] not in basis:
        basis.append(trigger["trigger_id"])
    return {
        "level": level,
        "previous_level": previous,
        "material_change": level != previous,
        "basis_trigger_ids": sorted(basis),
    }


def _recovery_assessment(trigger: dict[str, Any], normalized: dict[str, Any], current: dict[str, Any] | None, now_iso: str, recovery_window: int) -> dict[str, Any]:
    result = dict(current or {"state": "NOT_STARTED", "started_at": None, "required_until": None, "recovered_roles": []})
    recovered = trigger["source"] == "DATADOG_MONITOR" and trigger["evidence"]["transition"] == "Recovered" and normalized.get("quality_state") == "VALID"
    if not recovered:
        return result
    role = normalized.get("configured_role")
    roles = sorted(set(result.get("recovered_roles", [])) | ({role} if role in {"PRIMARY", "CORROBORATING"} else set()))
    if result.get("started_at") is None:
        result["started_at"] = now_iso
        start_epoch = _epoch(now_iso)
        result["required_until"] = datetime.fromtimestamp(start_epoch + recovery_window, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    result["recovered_roles"] = roles
    elapsed = _epoch(now_iso) >= _epoch(result["required_until"])
    result["state"] = "SATISFIED" if set(roles) >= {"PRIMARY", "CORROBORATING"} and elapsed else "OBSERVING"
    return result


def _snapshot(
    trigger: dict[str, Any],
    normalized: dict[str, Any],
    matches: list[dict[str, Any]],
    now_iso: str,
    incident_id_factory: Any,
    recovery_window_seconds: int = 0,
    cooldown_seconds: int = 0,
    reopen_window_seconds: int = 0,
    shadow_mode: bool = True,
) -> tuple[dict[str, Any] | None, int | None, str]:
    matches = [
        item for item in matches
        if item["lifecycle"] != "RESOLVED"
        or (reopen_window_seconds > 0 and abs(_epoch(trigger["occurred_at"]) - _epoch(item["updated_at"])) <= reopen_window_seconds)
    ]
    previous_assessment = None
    if not normalized["complete"]:
        incident_id = incident_id_factory()
        correlation = {
            "state": "AMBIGUOUS",
            "strategy": "DETERMINISTIC_V1",
            "confidence": "LOW",
            "reason_code": normalized["ambiguity_reason"],
            "matched_on": [],
            "operator_confirmation_required": True,
        }
        revision = 1
        expected_revision = None
        signals = [trigger]
        opened_at = trigger["occurred_at"]
        lifecycle = "OPEN"
        analysis_reason = "AMBIGUITY_RECORDED"
        context = normalized["context"]
    elif len(matches) == 0:
        incident_id = incident_id_factory()
        reason = (
            "CHAT_FIRST_NO_METRIC"
            if trigger["source"] == "CHAT_INCIDENT_CANDIDATE"
            else "DATADOG_FIRST_NO_CHAT"
        )
        strong_exception = normalized.get("strong_exception", False)
        correlation = {
            "state": "CORRELATED" if strong_exception else "PROVISIONAL",
            "strategy": "DETERMINISTIC_V1",
            "confidence": "HIGH" if strong_exception else "MEDIUM",
            "reason_code": "STRONG_EXCEPTION" if strong_exception else reason,
            "matched_on": [],
            "operator_confirmation_required": False,
        }
        revision = 1
        expected_revision = None
        signals = [trigger]
        opened_at = trigger["occurred_at"]
        lifecycle = "OPEN"
        analysis_reason = "STRONG_EXCEPTION_APPLIED" if strong_exception else "INITIAL_DETECTION"
        context = normalized["context"]
    elif len(matches) > 1:
        incident_id = incident_id_factory()
        correlation = {
            "state": "AMBIGUOUS",
            "strategy": "DETERMINISTIC_V1",
            "confidence": "LOW",
            "reason_code": "MULTIPLE_ACTIVE_MATCHES",
            "matched_on": [
                "ENVIRONMENT",
                "SYMPTOM_FAMILY",
                "AFFECTED_SCOPE",
                "EVENT_TIME",
            ],
            "operator_confirmation_required": True,
        }
        revision = 1
        expected_revision = None
        signals = [trigger]
        opened_at = trigger["occurred_at"]
        lifecycle = "OPEN"
        analysis_reason = "AMBIGUITY_RECORDED"
        context = normalized["context"]
    else:
        current = matches[0]
        previous_assessment = current["evidence_assessment"]
        if current["lifecycle"] == "RESOLVED":
            analysis_reason = "INCIDENT_REOPENED"
            lifecycle = "OPEN"
            signals = [*current["signals"], trigger]
            incident_id = current["incident_id"]
            expected_revision = current["revision"]
            revision = expected_revision + 1
            opened_at = current["opened_at"]
            correlation = dict(current["correlation"])
            correlation["reason_code"] = "REOPEN_WINDOW_MATCH"
            context = _merge_context(current["normalized_context"], normalized["context"])
        else:
            sources = {signal["source"] for signal in current["signals"]}
            current_severity = current.get("severity_assessment", {"level": "UNKNOWN"})
            incoming_level = normalized.get("severity_level", "UNKNOWN") if normalized.get("quality_state") == "VALID" else "UNKNOWN"
            severity_increased = SEVERITY_LEVELS[incoming_level] > SEVERITY_LEVELS[current_severity.get("level", "UNKNOWN")]
            quality_material = normalized.get("quality_state") in {"NO_DATA", "STALE", "INSUFFICIENT_SAMPLES", "TYPE_MISMATCH"}
            previous_candidate_ids = {
                signal["evidence"].get("candidate_id")
                for signal in current["signals"]
                if signal["source"] == "CHAT_INCIDENT_CANDIDATE"
            }
            strong_exception_added = normalized.get("strong_exception", False) and (
                not previous_assessment.get("strong_exception_applied", False)
                or (
                    trigger["source"] == "CHAT_INCIDENT_CANDIDATE"
                    and trigger["evidence"]["candidate_id"] not in previous_candidate_ids
                )
            )
            if trigger["source"] in sources:
                incoming_role = normalized["evidence_role"]
                role_field = incoming_role.lower() if incoming_role else None
                role_is_new = role_field is not None and not previous_assessment[role_field]
                if strong_exception_added:
                    analysis_reason = "STRONG_EXCEPTION_APPLIED"
                    lifecycle = current["lifecycle"]
                elif (
                    trigger["source"] == "DATADOG_MONITOR"
                    and trigger["evidence"]["transition"] == "Recovered"
                ):
                    analysis_reason = "RECOVERY_EVIDENCE_ADDED"
                    lifecycle = "RECOVERING"
                elif role_is_new:
                    analysis_reason = "EVIDENCE_ROLE_ADDED"
                    lifecycle = current["lifecycle"]
                elif severity_increased:
                    analysis_reason = "MATERIAL_SEVERITY_CHANGE"
                    lifecycle = current["lifecycle"]
                elif quality_material:
                    analysis_reason = "EVIDENCE_QUALITY_CHANGED"
                    lifecycle = current["lifecycle"]
                else:
                    return None, current["revision"], "NON_MATERIAL_SOURCE_UPDATE"
            else:
                analysis_reason = "CROSS_SOURCE_EVIDENCE_ADDED"
                lifecycle = current["lifecycle"]

            signals = [*current["signals"], trigger]
            incident_id = current["incident_id"]
            expected_revision = current["revision"]
            revision = expected_revision + 1
            opened_at = current["opened_at"]
            correlation = {
                "state": "CORRELATED", "strategy": "DETERMINISTIC_V1", "confidence": "HIGH",
                "reason_code": "UNIQUE_ACTIVE_MATCH",
                "matched_on": ["ENVIRONMENT", "SYMPTOM_FAMILY", "AFFECTED_SCOPE", "EVENT_TIME"],
                "operator_confirmation_required": False,
            }
            context = _merge_context(current["normalized_context"], normalized["context"])
        if len(signals) > MAX_SIGNALS:
            raise CorrelatorError("INCIDENT_SIGNAL_LIMIT")

    evidence_assessment = _assess_evidence(
        trigger,
        normalized,
        correlation["state"],
        previous_assessment,
    )
    current_snapshot = matches[0] if len(matches) == 1 else None
    data_quality = _data_quality(trigger, normalized, (current_snapshot or {}).get("data_quality"))
    severity_assessment = _severity(trigger, normalized, (current_snapshot or {}).get("severity_assessment"))
    recovery_assessment = _recovery_assessment(
        trigger, normalized,
        None if analysis_reason == "INCIDENT_REOPENED" else (current_snapshot or {}).get("recovery_assessment"),
        now_iso, recovery_window_seconds
    )
    if recovery_assessment["state"] == "SATISFIED":
        lifecycle = "RESOLVED"
        analysis_reason = "RECOVERY_SUSTAINED"
    suppressed = False
    suppression_reason = "NONE"
    if current_snapshot and cooldown_seconds > 0 and current_snapshot["evidence_assessment"]["verification_state"] == "VERIFIED":
        suppressed = _epoch(now_iso) - _epoch(current_snapshot["updated_at"]) < cooldown_seconds
        suppression_reason = "COOLDOWN_ACTIVE" if suppressed else "NONE"
    notification_policy = {
        "mode": "SHADOW" if shadow_mode else "OPERATIONAL",
        "cooldown_seconds": cooldown_seconds,
        "suppressed": suppressed,
        "reason": suppression_reason,
    }

    payload = {
        "schema_version": "1.0",
        "event_type": "agent.incident.v1",
        "incident_id": incident_id,
        "revision": revision,
        "idempotency_key": f"incident:{incident_id}:revision:{revision}",
        "lifecycle": lifecycle,
        "analysis_reason": analysis_reason,
        "opened_at": opened_at,
        "updated_at": now_iso,
        "correlation": correlation,
        "normalized_context": context,
        "evidence_assessment": evidence_assessment,
        "data_quality": data_quality,
        "severity_assessment": severity_assessment,
        "recovery_assessment": recovery_assessment,
        "notification_policy": notification_policy,
        "signals": signals,
        "guardrails": INCIDENT_GUARDRAILS,
    }
    rendered = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    if len(rendered) > MAX_INCIDENT_INPUT_CHARS:
        raise CorrelatorError("INCIDENT_INPUT_TOO_LARGE")
    return payload, expected_revision, "MATERIAL_REVISION"


def _client(name: str) -> Any:
    if name not in _clients:
        import boto3

        _clients[name] = boto3.client(name)
    return _clients[name]


def _serialize_item(item: dict[str, Any]) -> dict[str, Any]:
    from boto3.dynamodb.types import TypeSerializer

    serializer = TypeSerializer()
    return {key: serializer.serialize(value) for key, value in item.items()}


def _deserialize_item(item: dict[str, Any]) -> dict[str, Any]:
    from boto3.dynamodb.types import TypeDeserializer

    deserializer = TypeDeserializer()
    return {
        key: _json_compatible(deserializer.deserialize(value))
        for key, value in item.items()
    }


def _json_compatible(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value != value.to_integral_value():
            raise CorrelatorError("INCIDENT_STATE_NONINTEGER_NUMBER")
        return int(value)
    if isinstance(value, dict):
        return {key: _json_compatible(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_compatible(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_compatible(item) for item in value)
    return value


class AwsIncidentRepository:
    def __init__(self) -> None:
        self.client = _client("dynamodb")
        self.table = os.environ["INCIDENT_STATE_TABLE"]
        self.index = os.environ["INCIDENT_CORRELATION_INDEX"]
        self.claim_ttl = int(os.environ.get("INCIDENT_SIGNAL_CLAIM_TTL", "2592000"))

    @staticmethod
    def claim_key(idempotency_key: str) -> str:
        digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        return f"SIGNAL#{digest}"

    @staticmethod
    def pointer_key(correlation_key: str) -> str:
        digest = hashlib.sha256(correlation_key.encode("utf-8")).hexdigest()
        return f"CORRELATION#{digest}"

    def get_claim(self, idempotency_key: str) -> dict[str, Any] | None:
        response = self.client.get_item(
            TableName=self.table,
            Key={"pk": {"S": self.claim_key(idempotency_key)}},
            ConsistentRead=True,
        )
        item = response.get("Item")
        return _deserialize_item(item) if item else None

    def find_open(self, correlation_key: str, event_epoch: int, window: int) -> list[dict[str, Any]]:
        response = self.client.query(
            TableName=self.table,
            IndexName=self.index,
            KeyConditionExpression="#key = :key AND #last BETWEEN :lower AND :upper",
            FilterExpression="(#lifecycle = :open OR #lifecycle = :recovering OR #lifecycle = :resolved) AND #state <> :ambiguous",
            ExpressionAttributeNames={
                "#key": "correlation_key",
                "#last": "last_signal_at_epoch",
                "#lifecycle": "lifecycle",
                "#state": "correlation_state",
            },
            ExpressionAttributeValues={
                ":key": {"S": correlation_key},
                ":lower": {"N": str(event_epoch - window)},
                ":upper": {"N": str(event_epoch + window)},
                ":open": {"S": "OPEN"},
                ":recovering": {"S": "RECOVERING"},
                ":resolved": {"S": "RESOLVED"},
                ":ambiguous": {"S": "AMBIGUOUS"},
            },
        )
        return [_deserialize_item(item)["snapshot"] for item in response.get("Items", [])]

    def commit(
        self,
        trigger: dict[str, Any],
        snapshot: dict[str, Any],
        normalized: dict[str, Any],
        expected_revision: int | None,
        now_epoch: int,
        window_seconds: int,
        invocation_required: bool,
    ) -> str:
        claim = {
            "pk": self.claim_key(trigger["idempotency_key"]),
            "record_type": "SIGNAL_CLAIM",
            "source_idempotency_key": trigger["idempotency_key"],
            "status": "PENDING" if invocation_required else "NOT_REQUIRED",
            "snapshot": snapshot,
            "expires_at": now_epoch + self.claim_ttl,
        }
        incident = {
            "pk": f"INCIDENT#{snapshot['incident_id']}",
            "record_type": "INCIDENT",
            "incident_id": snapshot["incident_id"],
            "correlation_key": normalized["correlation_key"]
            or f"AMBIGUOUS#{snapshot['incident_id']}",
            "last_signal_at_epoch": normalized["event_epoch"],
            "lifecycle": snapshot["lifecycle"],
            "correlation_state": snapshot["correlation"]["state"],
            "revision": snapshot["revision"],
            "snapshot": snapshot,
        }
        transact_items: list[dict[str, Any]] = [
            {
                "Put": {
                    "TableName": self.table,
                    "Item": _serialize_item(claim),
                    "ConditionExpression": "attribute_not_exists(#pk)",
                    "ExpressionAttributeNames": {"#pk": "pk"},
                }
            }
        ]
        if expected_revision is None:
            transact_items.append(
                {
                    "Put": {
                        "TableName": self.table,
                        "Item": _serialize_item(incident),
                        "ConditionExpression": "attribute_not_exists(#pk)",
                        "ExpressionAttributeNames": {"#pk": "pk"},
                    }
                }
            )
        else:
            values = {
                ":snapshot": snapshot,
                ":revision": snapshot["revision"],
                ":expected": expected_revision,
                ":last": normalized["event_epoch"],
                ":lifecycle": snapshot["lifecycle"],
                ":open": "OPEN",
                ":recovering": "RECOVERING",
                ":resolved": "RESOLVED",
            }
            transact_items.append(
                {
                    "Update": {
                        "TableName": self.table,
                        "Key": {"pk": {"S": incident["pk"]}},
                        "UpdateExpression": (
                            "SET #snapshot = :snapshot, #revision = :revision, "
                            "#last = :last, #lifecycle = :lifecycle, #state = :state"
                        ),
                        "ConditionExpression": (
                            "#revision = :expected AND (#lifecycle = :open OR #lifecycle = :recovering OR #lifecycle = :resolved)"
                        ),
                        "ExpressionAttributeNames": {
                            "#snapshot": "snapshot",
                            "#revision": "revision",
                            "#last": "last_signal_at_epoch",
                            "#lifecycle": "lifecycle",
                            "#state": "correlation_state",
                        },
                        "ExpressionAttributeValues": _serialize_item(
                            {
                                **values,
                                ":state": snapshot["correlation"]["state"],
                            }
                        ),
                    }
                }
            )

        # 같은 correlation key의 첫 두 신호가 동시에 "0 matches"를 읽어도
        # 신규 Incident를 둘 만들지 못하게 pointer를 같은 transaction에 둔다.
        # GSI 반영이 늦은 패자는 conflict로 재시도되고, SQS redelivery까지
        # 가더라도 먼저 만들어진 Incident만 남는다.
        if (
            normalized["complete"]
            and snapshot["correlation"]["state"] != "AMBIGUOUS"
        ):
            pointer_names = {
                "#record": "record_type",
                "#incident": "active_incident_id",
                "#last": "pointer_last_signal_at_epoch",
                "#lifecycle": "pointer_lifecycle",
                "#revision": "pointer_revision",
            }
            pointer_values: dict[str, Any] = {
                ":record": "CORRELATION_POINTER",
                ":incident": snapshot["incident_id"],
                ":last": normalized["event_epoch"],
                ":lifecycle": snapshot["lifecycle"],
                ":revision": snapshot["revision"],
            }
            if expected_revision is None:
                pointer_condition = (
                    "attribute_not_exists(#incident) OR #last < :lower "
                    "OR #lifecycle <> :open"
                )
                pointer_values[":lower"] = (
                    normalized["event_epoch"] - window_seconds
                )
                pointer_values[":open"] = "OPEN"
            else:
                pointer_condition = (
                    "#incident = :incident AND #revision = :expected"
                )
                pointer_values[":expected"] = expected_revision
            transact_items.append(
                {
                    "Update": {
                        "TableName": self.table,
                        "Key": {
                            "pk": {
                                "S": self.pointer_key(normalized["correlation_key"])
                            }
                        },
                        "UpdateExpression": (
                            "SET #record = :record, #incident = :incident, "
                            "#last = :last, #lifecycle = :lifecycle, "
                            "#revision = :revision"
                        ),
                        "ConditionExpression": pointer_condition,
                        "ExpressionAttributeNames": pointer_names,
                        "ExpressionAttributeValues": _serialize_item(pointer_values),
                    }
                }
            )
        try:
            self.client.transact_write_items(TransactItems=transact_items)
            return "COMMITTED"
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code not in {"TransactionCanceledException", "ConditionalCheckFailedException"}:
                raise CorrelatorError("INCIDENT_STATE_WRITE") from exc
            return "CLAIM_EXISTS" if self.get_claim(trigger["idempotency_key"]) else "CONFLICT"

    def commit_ignored(self, trigger: dict[str, Any], now_epoch: int) -> str:
        claim = {
            "pk": self.claim_key(trigger["idempotency_key"]),
            "record_type": "SIGNAL_CLAIM",
            "source_idempotency_key": trigger["idempotency_key"],
            "status": "NOT_REQUIRED",
            "expires_at": now_epoch + self.claim_ttl,
        }
        try:
            self.client.put_item(
                TableName=self.table,
                Item=_serialize_item(claim),
                ConditionExpression="attribute_not_exists(#pk)",
                ExpressionAttributeNames={"#pk": "pk"},
            )
            return "IGNORED"
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code == "ConditionalCheckFailedException":
                return "CLAIM_EXISTS"
            raise CorrelatorError("SIGNAL_CLAIM_WRITE") from exc

    def mark_emitted(self, idempotency_key: str) -> None:
        try:
            self.client.update_item(
                TableName=self.table,
                Key={"pk": {"S": self.claim_key(idempotency_key)}},
                UpdateExpression="SET #status = :emitted",
                ConditionExpression="#status = :pending",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":emitted": {"S": "EMITTED"},
                    ":pending": {"S": "PENDING"},
                },
            )
        except Exception as exc:
            raise CorrelatorError("SIGNAL_CLAIM_FINALIZE") from exc


def _send_snapshot(snapshot: dict[str, Any]) -> None:
    body = json.dumps(snapshot, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    try:
        _client("sqs").send_message(
            QueueUrl=os.environ["AGENT_INVOCATION_QUEUE_URL"],
            MessageBody=body,
            MessageAttributes={
                "schema": {"DataType": "String", "StringValue": "agent.incident.v1"},
                "incident_id": {
                    "DataType": "String",
                    "StringValue": snapshot["incident_id"],
                },
                "revision": {
                    "DataType": "Number",
                    "StringValue": str(snapshot["revision"]),
                },
            },
        )
    except Exception as exc:
        raise CorrelatorError("INVOCATION_QUEUE_SEND") from exc


def process_trigger(
    trigger: dict[str, Any],
    settings: dict[str, Any],
    repository: Any,
    sender: Any,
    incident_id_factory: Any = new_incident_id,
    now_epoch: int | None = None,
) -> dict[str, Any]:
    trigger = validate_trigger(trigger)
    if settings.get("shadow_mode", True) and trigger["idempotency_key"] not in settings["allowed_idempotency_keys"]:
        raise CorrelatorError("SYNTHETIC_IDEMPOTENCY_KEY_NOT_ALLOWED")

    existing_claim = repository.get_claim(trigger["idempotency_key"])
    if existing_claim:
        if existing_claim["status"] == "PENDING":
            sender(existing_claim["snapshot"])
            repository.mark_emitted(trigger["idempotency_key"])
            return {"status": "PENDING_REPLAYED", "snapshot": existing_claim["snapshot"]}
        return {"status": "DUPLICATE", "snapshot": existing_claim.get("snapshot")}

    normalized = normalize_trigger(trigger, settings)
    now_epoch = int(time.time()) if now_epoch is None else now_epoch
    now_iso = (
        datetime.fromtimestamp(now_epoch, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    for _attempt in range(3):
        matches = (
            repository.find_open(
                normalized["correlation_key"],
                normalized["event_epoch"],
                max(settings["window_seconds"], settings.get("reopen_window_seconds", 0)),
            )
            if normalized["complete"]
            else []
        )
        snapshot, expected_revision, result = _snapshot(
            trigger,
            normalized,
            matches,
            now_iso,
            incident_id_factory,
            settings.get("recovery_window_seconds", 0),
            settings.get("cooldown_seconds", 0),
            settings.get("reopen_window_seconds", 0),
            settings.get("shadow_mode", True),
        )
        if snapshot is None:
            state = repository.commit_ignored(trigger, now_epoch)
            if state == "CLAIM_EXISTS":
                return {"status": "DUPLICATE", "snapshot": None}
            return {"status": result, "snapshot": None}

        state = repository.commit(
            trigger,
            snapshot,
            normalized,
            expected_revision,
            now_epoch,
            settings["window_seconds"],
            _requires_invocation(snapshot),
        )
        if state == "CONFLICT":
            continue
        if state == "CLAIM_EXISTS":
            claim = repository.get_claim(trigger["idempotency_key"])
            if claim and claim["status"] == "PENDING":
                sender(claim["snapshot"])
                repository.mark_emitted(trigger["idempotency_key"])
                return {"status": "PENDING_REPLAYED", "snapshot": claim["snapshot"]}
            return {"status": "DUPLICATE", "snapshot": claim.get("snapshot") if claim else None}

        if _requires_invocation(snapshot):
            sender(snapshot)
            repository.mark_emitted(trigger["idempotency_key"])
            return {"status": result, "snapshot": snapshot}
        return {"status": "STORED_WITHOUT_INVOCATION", "snapshot": snapshot}

    raise CorrelatorError("INCIDENT_CONCURRENT_UPDATE")


def _enabled() -> bool:
    return os.environ.get("INCIDENT_CORRELATOR_EXECUTION_ENABLED", "false").lower() == "true"


def _process_record(record: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(record["body"])
    except (KeyError, TypeError, json.JSONDecodeError):
        raise ContractError("CONTRACT_REJECTED:SQS_BODY") from None
    repository = AwsIncidentRepository()
    return process_trigger(payload, settings, repository, _send_snapshot)


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    records = event.get("Records", [])
    if not _enabled():
        for record in records:
            LOGGER.info(
                json.dumps(
                    {
                        "event": "incident_correlator_record",
                        "message_id": record.get("messageId", "unknown"),
                        "status": "EXECUTION_DISABLED",
                    }
                )
            )
        return {
            "batchItemFailures": [
                {"itemIdentifier": record.get("messageId", "unknown")}
                for record in records
            ]
        }

    try:
        settings = settings_from_environment()
    except CorrelatorError as exc:
        LOGGER.error(json.dumps({"event": "incident_correlator_config", "error_code": exc.code}))
        return {
            "batchItemFailures": [
                {"itemIdentifier": record.get("messageId", "unknown")}
                for record in records
            ]
        }

    failures = []
    for record in records:
        message_id = record.get("messageId", "unknown")
        try:
            result = _process_record(record, settings)
            snapshot = result.get("snapshot") or {}
            LOGGER.info(
                json.dumps(
                    {
                        "event": "incident_correlator_record",
                        "message_id": message_id,
                        "status": result["status"],
                        "incident_id": snapshot.get("incident_id"),
                        "revision": snapshot.get("revision"),
                    }
                )
            )
        except CorrelatorError as exc:
            LOGGER.error(
                json.dumps(
                    {
                        "event": "incident_correlator_record",
                        "message_id": message_id,
                        "status": "FAILED",
                        "error_code": exc.code,
                    }
                )
            )
            failures.append({"itemIdentifier": message_id})
        except Exception:
            LOGGER.exception(
                json.dumps(
                    {
                        "event": "incident_correlator_record",
                        "message_id": message_id,
                        "status": "FAILED",
                        "error_code": "UNEXPECTED",
                    }
                )
            )
            failures.append({"itemIdentifier": message_id})
    return {"batchItemFailures": failures}
