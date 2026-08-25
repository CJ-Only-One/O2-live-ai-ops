"""Phase 3D worker: agent.incident.v1 -> isolated contract-test Dify app.

The worker validates the revisioned Incident snapshot, checks the authoritative
Incident State revision, and uses DynamoDB to serialize executions per
incident_id. Logs never contain the envelope or Dify response.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

INCIDENT_FIELDS = {
    "schema_version", "event_type", "incident_id", "revision",
    "idempotency_key", "lifecycle", "analysis_reason", "opened_at",
    "updated_at", "correlation", "normalized_context", "evidence_assessment",
    "data_quality", "severity_assessment", "recovery_assessment", "notification_policy", "signals", "guardrails",
}
TRIGGER_FIELDS = {
    "schema_version", "trigger_id", "source", "source_schema", "trigger_type",
    "idempotency_key", "occurred_at", "trace_id", "evidence", "guardrails",
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
    "event_id", "cycle_key", "monitor_id", "transition", "priority", "env",
    "service", "alert_title", "alert_body", "alert_query", "host", "tags", "link", "assessment_input",
}
CHAT_EVIDENCE_FIELDS = {
    "candidate_id", "candidate_type", "broadcast_id", "suspected_surface",
    "confidence", "window_start", "window_end", "matched_messages", "unique_users",
    "strong_signal_count", "weak_signal_count", "matched_rule_ids", "metric_status",
    "root_cause", "requires_metric_corroboration",
}
SOURCE_RULES = {
    "DATADOG_MONITOR": ("datadog.alert.v1", "MONITOR_ALERT", DATADOG_EVIDENCE_FIELDS),
    "CHAT_INCIDENT_CANDIDATE": (
        "chat.incident_candidate.v1", "USER_SYMPTOM_CLUSTER", CHAT_EVIDENCE_FIELDS
    ),
}
CORRELATION_FIELDS = {
    "state", "strategy", "confidence", "reason_code", "matched_on",
    "operator_confirmation_required",
}
CONTEXT_FIELDS = {
    "environment", "incident_family", "symptom_family", "suspected_surfaces",
    "services", "broadcast_ids",
}
INCIDENT_FAMILIES = {
    "READ_PATH_DEGRADATION", "CHECKOUT_ORDER_DEGRADATION", "PAYMENT_DEGRADATION",
    "INVENTORY_DEGRADATION", "CHAT_DEGRADATION", "PLAYBACK_DEGRADATION",
    "CAPACITY_SATURATION", "DEPLOYMENT_REGRESSION", "TELEMETRY_PIPELINE_FAILURE",
    "DATA_INTEGRITY_SECURITY_RISK", "UNKNOWN",
}
EVIDENCE_ASSESSMENT_FIELDS = {
    "primary", "corroborating", "context", "missing_required_roles",
    "verification_state", "strong_exception_applied",
}
DIFY_INPUT_MAX_CHARS = 30000

_clients: dict[str, Any] = {}
_cached_api_key: str | None = None


class WorkerError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ContractError(WorkerError):
    pass


def _fail(code: str) -> None:
    raise ContractError(f"CONTRACT_REJECTED:{code}")


def _exact(value: Any, expected: set[str], code: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        _fail(code)


def _string(value: Any, code: str, minimum: int = 0, maximum: int = 30000) -> None:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        _fail(code)


def _datetime(value: Any, code: str) -> None:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail(code)
    if parsed.tzinfo is None:
        _fail(code)


def _validate_evidence(source: str, evidence: Any) -> None:
    source_schema, trigger_type, fields = SOURCE_RULES[source]
    del source_schema, trigger_type
    _exact(evidence, fields, "TRIGGER_EVIDENCE_FIELDS")
    if source == "DATADOG_MONITOR":
        string_limits = {
            "event_id": (1, 256), "cycle_key": (1, 256), "monitor_id": (0, 128),
            "priority": (0, 64), "env": (0, 128), "service": (0, 128),
            "alert_title": (0, 1000), "alert_body": (0, 30000),
            "alert_query": (0, 30000), "host": (0, 512), "tags": (0, 30000),
            "link": (0, 4096),
        }
        for field, (minimum, maximum) in string_limits.items():
            _string(evidence[field], f"DATADOG_{field.upper()}", minimum, maximum)
        if evidence["transition"] not in {
            "Triggered", "Re-Triggered", "Recovered", "Warn", "No Data", "Renotify"
        }:
            _fail("DATADOG_TRANSITION")
        assessment_input = evidence["assessment_input"]
        _exact(assessment_input, {"evidence_type", "observed_at", "sample_count", "data_state", "signal_strength", "scope", "measurements"}, "ASSESSMENT_INPUT_FIELDS")
        _datetime(assessment_input["observed_at"], "ASSESSMENT_OBSERVED_AT")
        return
    if not isinstance(evidence["candidate_id"], str) or not re.fullmatch(
        r"cand_[0-9A-HJKMNP-TV-Z]{26}", evidence["candidate_id"]
    ):
        _fail("CHAT_CANDIDATE_ID")
    if evidence["candidate_type"] != "USER_PERCEIVED_LATENCY":
        _fail("CHAT_CANDIDATE_TYPE")
    if not isinstance(evidence["broadcast_id"], str) or not re.fullmatch(r"bc_[0-9]+", evidence["broadcast_id"]):
        _fail("CHAT_BROADCAST_ID")
    if evidence["suspected_surface"] not in {"READ_PATH", "PLAYBACK", "CHAT", "UNKNOWN"}:
        _fail("CHAT_SURFACE")
    if evidence["confidence"] not in {"MEDIUM", "LOW"}:
        _fail("CHAT_CONFIDENCE")
    _datetime(evidence["window_start"], "CHAT_WINDOW_START")
    _datetime(evidence["window_end"], "CHAT_WINDOW_END")
    for field in ("matched_messages", "unique_users"):
        if not isinstance(evidence[field], int) or isinstance(evidence[field], bool) or evidence[field] < 1:
            _fail("CHAT_POSITIVE_COUNTS")
    for field in ("strong_signal_count", "weak_signal_count"):
        if not isinstance(evidence[field], int) or isinstance(evidence[field], bool) or evidence[field] < 0:
            _fail("CHAT_NONNEGATIVE_COUNTS")
    rules = evidence["matched_rule_ids"]
    if not isinstance(rules, list) or not rules or len(rules) != len(set(rules)):
        _fail("CHAT_RULE_IDS")
    if any(not isinstance(value, str) or not re.fullmatch(r"[a-z0-9_]+", value) for value in rules):
        _fail("CHAT_RULE_IDS")
    if evidence["metric_status"] != "NOT_CHECKED" or evidence["root_cause"] != "UNDETERMINED":
        _fail("CHAT_UNCERTAINTY")
    if evidence["requires_metric_corroboration"] is not True:
        _fail("CHAT_METRIC_GATE")


def validate_trigger(payload: Any) -> dict[str, Any]:
    _exact(payload, TRIGGER_FIELDS, "TRIGGER_TOP_LEVEL_FIELDS")
    if payload["schema_version"] != "1.0":
        _fail("TRIGGER_SCHEMA_VERSION")
    if not isinstance(payload["trigger_id"], str) or not re.fullmatch(
        r"trg_[0-9A-HJKMNP-TV-Z]{26}", payload["trigger_id"]
    ):
        _fail("TRIGGER_ID")
    source = payload["source"]
    if source not in SOURCE_RULES:
        _fail("TRIGGER_SOURCE")
    source_schema, trigger_type, _ = SOURCE_RULES[source]
    if payload["source_schema"] != source_schema:
        _fail("TRIGGER_SOURCE_SCHEMA")
    if payload["trigger_type"] != trigger_type:
        _fail("TRIGGER_TYPE")
    _string(payload["idempotency_key"], "TRIGGER_IDEMPOTENCY_KEY", 1, 256)
    _datetime(payload["occurred_at"], "TRIGGER_OCCURRED_AT")
    if payload["trace_id"] is not None:
        _string(payload["trace_id"], "TRIGGER_TRACE_ID", 0, 128)
    _exact(payload["guardrails"], set(TRIGGER_GUARDRAILS), "TRIGGER_GUARDRAIL_FIELDS")
    if payload["guardrails"] != TRIGGER_GUARDRAILS:
        _fail("TRIGGER_GUARDRAIL_VALUES")
    _validate_evidence(source, payload["evidence"])
    return payload


def validate_envelope(payload: Any) -> dict[str, Any]:
    """Validate the executable subset of agent-incident-v1.schema.json."""
    _exact(payload, INCIDENT_FIELDS, "TOP_LEVEL_FIELDS")
    if payload["schema_version"] != "1.0" or payload["event_type"] != "agent.incident.v1":
        _fail("SCHEMA_OR_EVENT_TYPE")
    incident_id = payload["incident_id"]
    if not isinstance(incident_id, str) or not re.fullmatch(r"inc_[0-9A-HJKMNP-TV-Z]{26}", incident_id):
        _fail("INCIDENT_ID")
    revision = payload["revision"]
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        _fail("REVISION")
    if payload["idempotency_key"] != f"incident:{incident_id}:revision:{revision}":
        _fail("IDEMPOTENCY_KEY")
    if payload["lifecycle"] not in {"OPEN", "RECOVERING", "RESOLVED"}:
        _fail("LIFECYCLE")
    if payload["analysis_reason"] not in {
        "INITIAL_DETECTION", "CROSS_SOURCE_EVIDENCE_ADDED", "EVIDENCE_ROLE_ADDED",
        "MATERIAL_SEVERITY_CHANGE",
        "AMBIGUITY_RECORDED", "RECOVERY_EVIDENCE_ADDED", "EVIDENCE_QUALITY_CHANGED",
        "RECOVERY_SUSTAINED", "STRONG_EXCEPTION_APPLIED", "INCIDENT_REOPENED",
    }:
        _fail("ANALYSIS_REASON")
    _datetime(payload["opened_at"], "OPENED_AT")
    _datetime(payload["updated_at"], "UPDATED_AT")

    correlation = payload["correlation"]
    _exact(correlation, CORRELATION_FIELDS, "CORRELATION_FIELDS")
    if correlation["state"] not in {"PROVISIONAL", "CORRELATED", "AMBIGUOUS"}:
        _fail("CORRELATION_STATE")
    if correlation["strategy"] != "DETERMINISTIC_V1":
        _fail("CORRELATION_STRATEGY")
    if correlation["confidence"] not in {"HIGH", "MEDIUM", "LOW"}:
        _fail("CORRELATION_CONFIDENCE")
    if correlation["reason_code"] not in {
        "CHAT_FIRST_NO_METRIC", "DATADOG_FIRST_NO_CHAT", "UNIQUE_ACTIVE_MATCH",
        "MULTIPLE_ACTIVE_MATCHES", "INSUFFICIENT_DIMENSIONS",
        "SOURCE_ENVIRONMENT_MISMATCH", "STRONG_EXCEPTION", "REOPEN_WINDOW_MATCH",
    }:
        _fail("CORRELATION_REASON")
    matched = correlation["matched_on"]
    if not isinstance(matched, list) or len(matched) != len(set(matched)) or any(
        value not in {"ENVIRONMENT", "SYMPTOM_FAMILY", "AFFECTED_SCOPE", "EVENT_TIME"}
        for value in matched
    ):
        _fail("CORRELATION_MATCHED_ON")
    if not isinstance(correlation["operator_confirmation_required"], bool):
        _fail("CORRELATION_OPERATOR_CONFIRMATION")
    if correlation["state"] == "AMBIGUOUS" and (
        correlation["operator_confirmation_required"] is not True
        or payload["analysis_reason"] != "AMBIGUITY_RECORDED"
    ):
        _fail("AMBIGUITY_GUARD")

    context = payload["normalized_context"]
    _exact(context, CONTEXT_FIELDS, "CONTEXT_FIELDS")
    _string(context["environment"], "CONTEXT_ENVIRONMENT", 1, 128)
    if context["incident_family"] not in INCIDENT_FAMILIES:
        _fail("CONTEXT_INCIDENT_FAMILY")
    if context["symptom_family"] not in {"LATENCY", "AVAILABILITY", "ERROR_RATE", "UNKNOWN"}:
        _fail("CONTEXT_SYMPTOM_FAMILY")
    surfaces = context["suspected_surfaces"]
    if not isinstance(surfaces, list) or len(surfaces) != len(set(surfaces)) or any(
        value not in {"READ_PATH", "PLAYBACK", "CHAT", "UNKNOWN"} for value in surfaces
    ):
        _fail("CONTEXT_SURFACES")
    services = context["services"]
    if not isinstance(services, list) or len(services) != len(set(services)):
        _fail("CONTEXT_SERVICES")
    for value in services:
        _string(value, "CONTEXT_SERVICES", 1, 128)
    broadcasts = context["broadcast_ids"]
    if not isinstance(broadcasts, list) or len(broadcasts) != len(set(broadcasts)) or any(
        not isinstance(value, str) or not re.fullmatch(r"bc_[0-9]+", value) for value in broadcasts
    ):
        _fail("CONTEXT_BROADCASTS")

    assessment = payload["evidence_assessment"]
    _exact(assessment, EVIDENCE_ASSESSMENT_FIELDS, "EVIDENCE_ASSESSMENT_FIELDS")
    assessed_ids: list[str] = []
    for field in ("primary", "corroborating", "context"):
        values = assessment[field]
        if not isinstance(values, list) or len(values) != len(set(values)) or any(
            not isinstance(value, str)
            or not re.fullmatch(r"trg_[0-9A-HJKMNP-TV-Z]{26}", value)
            for value in values
        ):
            _fail("EVIDENCE_ASSESSMENT_SIGNAL_IDS")
        assessed_ids.extend(values)
    if len(assessed_ids) != len(set(assessed_ids)):
        _fail("EVIDENCE_ASSESSMENT_ROLE_OVERLAP")
    missing_roles = assessment["missing_required_roles"]
    if (
        not isinstance(missing_roles, list)
        or len(missing_roles) != len(set(missing_roles))
        or any(value not in {"PRIMARY", "CORROBORATING"} for value in missing_roles)
    ):
        _fail("EVIDENCE_ASSESSMENT_MISSING_ROLES")
    if assessment["verification_state"] not in {
        "INSUFFICIENT_EVIDENCE",
        "VERIFIED",
        "AMBIGUOUS",
    }:
        _fail("EVIDENCE_ASSESSMENT_VERIFICATION_STATE")
    if not isinstance(assessment["strong_exception_applied"], bool):
        _fail("EVIDENCE_ASSESSMENT_STRONG_EXCEPTION")

    data_quality = payload["data_quality"]
    _exact(data_quality, {"state", "assessments"}, "DATA_QUALITY_FIELDS")
    if data_quality["state"] not in {"SUFFICIENT", "MIXED", "NO_DATA", "STALE", "INSUFFICIENT_SAMPLES", "INVALID"}:
        _fail("DATA_QUALITY_STATE")
    severity = payload["severity_assessment"]
    _exact(severity, {"level", "previous_level", "material_change", "basis_trigger_ids"}, "SEVERITY_FIELDS")
    if severity["level"] not in {"UNKNOWN", "INFORMATIONAL", "WARNING", "HIGH", "CRITICAL"}:
        _fail("SEVERITY_LEVEL")
    recovery = payload["recovery_assessment"]
    _exact(recovery, {"state", "started_at", "required_until", "recovered_roles"}, "RECOVERY_FIELDS")
    if recovery["state"] not in {"NOT_STARTED", "OBSERVING", "SATISFIED"}:
        _fail("RECOVERY_STATE")
    notification = payload["notification_policy"]
    _exact(notification, {"mode", "cooldown_seconds", "suppressed", "reason"}, "NOTIFICATION_POLICY_FIELDS")
    if notification["mode"] not in {"SHADOW", "OPERATIONAL"}:
        _fail("NOTIFICATION_POLICY_MODE")

    signals = payload["signals"]
    if not isinstance(signals, list) or not 1 <= len(signals) <= 20:
        _fail("SIGNALS")
    for signal in signals:
        validate_trigger(signal)
    signal_ids = {signal["trigger_id"] for signal in signals}
    if set(assessed_ids) - signal_ids:
        _fail("EVIDENCE_ASSESSMENT_UNKNOWN_SIGNAL")
    if assessment["verification_state"] == "VERIFIED" and (
        (not assessment["strong_exception_applied"] and (missing_roles or not assessment["primary"] or not assessment["corroborating"]))
        or correlation["state"] != "CORRELATED"
    ):
        _fail("EVIDENCE_ASSESSMENT_VERIFIED_INVARIANT")
    _exact(payload["guardrails"], set(INCIDENT_GUARDRAILS), "GUARDRAIL_FIELDS")
    if payload["guardrails"] != INCIDENT_GUARDRAILS:
        _fail("GUARDRAIL_VALUES")
    return payload


def _client(name: str) -> Any:
    if name not in _clients:
        import boto3
        _clients[name] = boto3.client(name)
    return _clients[name]


def _enabled() -> bool:
    return os.environ.get("AGENT_ENTRY_EXECUTION_ENABLED", "false").lower() == "true"


def _incident_allowed(incident_id: str) -> bool:
    raw = os.environ.get("AGENT_ENTRY_ALLOWED_INCIDENT_IDS", "")
    values = raw.split(",") if raw else []
    operational = os.environ.get("AGENT_ENTRY_OPERATIONAL_MODE", "false").lower() == "true"
    if operational:
        if values:
            raise WorkerError("OPERATIONAL_INCIDENT_ALLOWLIST_NOT_EMPTY")
        return True
    if len(values) != 1 or not re.fullmatch(r"inc_[0-9A-HJKMNP-TV-Z]{26}", values[0]):
        raise WorkerError("SYNTHETIC_INCIDENT_ALLOWLIST_INVALID")
    return incident_id == values[0]


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def _serialize_payload(payload: dict[str, Any]) -> str:
    rendered = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    if len(rendered) > DIFY_INPUT_MAX_CHARS:
        raise ContractError("CONTRACT_REJECTED:DIFY_INPUT_TOO_LARGE")
    return rendered


def _api_key() -> str:
    global _cached_api_key
    if _cached_api_key is None:
        response = _client("secretsmanager").get_secret_value(SecretId=os.environ["AGENT_ENTRY_SECRET"])
        try:
            value = json.loads(response["SecretString"])["dify-api-key"]
        except (KeyError, TypeError, json.JSONDecodeError):
            raise WorkerError("SECRET_FORMAT") from None
        if not isinstance(value, str) or not value.startswith("app-"):
            raise WorkerError("SECRET_FORMAT")
        _cached_api_key = value
    return _cached_api_key


def _attribute(item: dict[str, Any], name: str) -> str | None:
    value = item.get(name)
    return (value.get("S") or value.get("N")) if isinstance(value, dict) else None


def _execution_key(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {"idempotency_key": {"S": payload["idempotency_key"]}}


def _lock_key(payload: dict[str, Any]) -> str:
    return f"incident:{payload['incident_id']}:lock"


def _ledger_item(key: str) -> dict[str, Any]:
    return _client("dynamodb").get_item(
        TableName=os.environ["IDEMPOTENCY_TABLE"],
        Key={"idempotency_key": {"S": key}}, ConsistentRead=True,
    ).get("Item", {})


def _latest_revision(payload: dict[str, Any]) -> int:
    item = _client("dynamodb").get_item(
        TableName=os.environ["INCIDENT_STATE_TABLE"],
        Key={"pk": {"S": f"INCIDENT#{payload['incident_id']}"}},
        ConsistentRead=True,
        ProjectionExpression="#revision",
        ExpressionAttributeNames={"#revision": "revision"},
    ).get("Item", {})
    revision = _attribute(item, "revision")
    if revision is None:
        raise WorkerError("INCIDENT_STATE_MISSING")
    try:
        latest = int(revision)
    except ValueError:
        raise WorkerError("INCIDENT_STATE_INVALID") from None
    if latest < payload["revision"]:
        raise WorkerError("INCIDENT_STATE_LAG")
    return latest


def _record_superseded(payload: dict[str, Any], latest: int, now: int) -> bool:
    try:
        _client("dynamodb").put_item(
            TableName=os.environ["IDEMPOTENCY_TABLE"],
            Item={
                **_execution_key(payload), "status": {"S": "SUPERSEDED"},
                "incident_id": {"S": payload["incident_id"]},
                "revision": {"N": str(payload["revision"])},
                "superseded_by_revision": {"N": str(latest)},
                "updated_at": {"N": str(now)},
                "expires_at": {"N": str(now + int(os.environ.get("IDEMPOTENCY_TTL", "2592000")))},
            },
            ConditionExpression="attribute_not_exists(#pk)",
            ExpressionAttributeNames={"#pk": "idempotency_key"},
        )
        return True
    except Exception as exc:
        if getattr(exc, "response", {}).get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise WorkerError("IDEMPOTENCY_WRITE") from exc
        return False


def _acquire(payload: dict[str, Any], now: int) -> bool:
    table = os.environ["IDEMPOTENCY_TABLE"]
    lease = now + int(os.environ.get("IDEMPOTENCY_LEASE", "120"))
    expires = now + int(os.environ.get("IDEMPOTENCY_TTL", "2592000"))
    try:
        _client("dynamodb").transact_write_items(TransactItems=[
            {"Put": {
                "TableName": table,
                "Item": {
                    **_execution_key(payload), "status": {"S": "IN_PROGRESS"},
                    "incident_id": {"S": payload["incident_id"]},
                    "revision": {"N": str(payload["revision"])},
                    "lease_expires_at": {"N": str(lease)}, "expires_at": {"N": str(expires)},
                    "updated_at": {"N": str(now)}, "attempt_count": {"N": "1"},
                },
                "ConditionExpression": "attribute_not_exists(#pk)",
                "ExpressionAttributeNames": {"#pk": "idempotency_key"},
            }},
            {"Update": {
                "TableName": table, "Key": {"idempotency_key": {"S": _lock_key(payload)}},
                "UpdateExpression": (
                    "SET #status=:locked,#owner=:owner,#revision=:revision,#lease=:lease,#updated=:updated"
                ),
                "ConditionExpression": "attribute_not_exists(#pk)",
                "ExpressionAttributeNames": {
                    "#pk": "idempotency_key", "#status": "status", "#owner": "owner_key",
                    "#revision": "revision", "#lease": "lease_expires_at", "#updated": "updated_at",
                },
                "ExpressionAttributeValues": {
                    ":locked": {"S": "LOCKED"}, ":owner": {"S": payload["idempotency_key"]},
                    ":revision": {"N": str(payload["revision"])}, ":lease": {"N": str(lease)},
                    ":updated": {"N": str(now)},
                },
            }},
        ])
        return True
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if code not in {"TransactionCanceledException", "ConditionalCheckFailedException"}:
            raise WorkerError("IDEMPOTENCY_WRITE") from exc
    existing = _ledger_item(payload["idempotency_key"])
    status = _attribute(existing, "status")
    if status in {"SUCCEEDED", "SUPERSEDED"}:
        return False
    if status == "FAILED":
        raise WorkerError("IDEMPOTENCY_FAILED")
    if status == "IN_PROGRESS":
        record_lease = _attribute(existing, "lease_expires_at")
        if record_lease is not None and int(record_lease) < now:
            raise WorkerError("IDEMPOTENCY_STALE")
        raise WorkerError("IDEMPOTENCY_BUSY")
    lock = _ledger_item(_lock_key(payload))
    if lock:
        lock_lease = _attribute(lock, "lease_expires_at")
        if lock_lease is not None and int(lock_lease) < now:
            raise WorkerError("INCIDENT_LOCK_STALE")
        raise WorkerError("INCIDENT_BUSY")
    raise WorkerError("IDEMPOTENCY_WRITE")


def _finalize(payload: dict[str, Any], status: str, now: int, **extra: str) -> None:
    names = {"#status": "status", "#updated": "updated_at", "#lease": "lease_expires_at"}
    values = {
        ":status": {"S": status}, ":updated": {"N": str(now)}, ":lease": {"N": "0"},
        ":in_progress": {"S": "IN_PROGRESS"},
    }
    updates = ["#status=:status", "#updated=:updated", "#lease=:lease"]
    for index, (name, value) in enumerate(extra.items()):
        names[f"#extra{index}"] = name
        values[f":extra{index}"] = {"S": value}
        updates.append(f"#extra{index}=:extra{index}")
    try:
        _client("dynamodb").transact_write_items(TransactItems=[
            {"Update": {
                "TableName": os.environ["IDEMPOTENCY_TABLE"], "Key": _execution_key(payload),
                "UpdateExpression": "SET " + ",".join(updates),
                "ConditionExpression": "#status=:in_progress",
                "ExpressionAttributeNames": names, "ExpressionAttributeValues": values,
            }},
            {"Delete": {
                "TableName": os.environ["IDEMPOTENCY_TABLE"],
                "Key": {"idempotency_key": {"S": _lock_key(payload)}},
                "ConditionExpression": "#owner=:owner",
                "ExpressionAttributeNames": {"#owner": "owner_key"},
                "ExpressionAttributeValues": {":owner": {"S": payload["idempotency_key"]}},
            }},
        ])
    except Exception as exc:
        raise WorkerError("IDEMPOTENCY_FINALIZE") from exc


def _call_dify(payload: dict[str, Any], rendered: str) -> str:
    body = json.dumps({
        "inputs": {"custom_alert_json": rendered}, "response_mode": "blocking",
        "user": "agent-entry:incident",
    }, ensure_ascii=True, separators=(",", ":")).encode()
    request = urllib.request.Request(
        os.environ["DIFY_URL"], data=body,
        headers={"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(os.environ.get("DIFY_TIMEOUT_SECONDS", "45"))) as response:
            result = json.loads(response.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise WorkerError("DIFY_TRANSPORT") from exc
    data = result.get("data")
    if not isinstance(data, dict) or data.get("status") != "succeeded":
        raise WorkerError("DIFY_WORKFLOW_FAILED")
    try:
        output = json.loads(data["outputs"]["result"])
    except (KeyError, TypeError, json.JSONDecodeError):
        raise WorkerError("DIFY_OUTPUT_FORMAT") from None
    if (
        output.get("accepted") is not True or output.get("status") != "ACCEPTED"
        or output.get("event_type") != "agent.incident.v1"
        or output.get("incident_id") != payload["incident_id"]
        or output.get("revision") != payload["revision"]
        or output.get("idempotency_key") != payload["idempotency_key"]
    ):
        raise WorkerError("DIFY_OUTPUT_MISMATCH")
    run_id = data.get("id", "")
    return run_id if isinstance(run_id, str) else ""


def _process_record(record: dict[str, Any]) -> dict[str, str | int]:
    try:
        payload = json.loads(record["body"])
    except (KeyError, TypeError, json.JSONDecodeError):
        raise ContractError("CONTRACT_REJECTED:INVALID_JSON") from None
    payload = validate_envelope(payload)
    if not _incident_allowed(payload["incident_id"]):
        raise WorkerError("SYNTHETIC_INCIDENT_NOT_ALLOWED")
    rendered = _serialize_payload(payload)
    now = int(time.time())
    fingerprint = _fingerprint(payload["incident_id"])
    latest = _latest_revision(payload)
    if payload["revision"] < latest:
        created = _record_superseded(payload, latest, now)
        return {"status": "SUPERSEDED" if created else "DUPLICATE", "incident": fingerprint, "revision": payload["revision"]}
    _api_key()  # Preflight before acquiring the Incident lock.
    if not _acquire(payload, now):
        return {"status": "DUPLICATE", "incident": fingerprint, "revision": payload["revision"]}
    try:
        run_id = _call_dify(payload, rendered)
        _finalize(payload, "SUCCEEDED", int(time.time()), **({"workflow_run_id": run_id} if run_id else {}))
    except WorkerError as exc:
        try:
            _finalize(payload, "FAILED", int(time.time()), error_code=exc.code)
        except WorkerError:
            LOGGER.exception(json.dumps({
                "event": "agent_entry_finalize_failed", "incident": fingerprint,
                "revision": payload["revision"],
            }, separators=(",", ":")))
        raise
    return {"status": "SUCCEEDED", "incident": fingerprint, "revision": payload["revision"]}


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, list[dict[str, str]]]:
    records = event.get("Records")
    if not isinstance(records, list):
        raise WorkerError("INVALID_SQS_EVENT")
    failures: list[dict[str, str]] = []
    for record in records:
        message_id = str(record.get("messageId", "UNKNOWN"))
        if not _enabled():
            LOGGER.warning(json.dumps({
                "event": "agent_entry_record", "message_id": message_id,
                "status": "EXECUTION_DISABLED",
            }, separators=(",", ":")))
            failures.append({"itemIdentifier": message_id})
            continue
        try:
            result = _process_record(record)
            LOGGER.info(json.dumps({
                "event": "agent_entry_record", "message_id": message_id, **result,
            }, separators=(",", ":")))
        except WorkerError as exc:
            LOGGER.warning(json.dumps({
                "event": "agent_entry_record", "message_id": message_id,
                "status": "FAILED", "error_code": exc.code,
            }, separators=(",", ":")))
            failures.append({"itemIdentifier": message_id})
        except Exception:
            LOGGER.exception(json.dumps({
                "event": "agent_entry_record", "message_id": message_id,
                "status": "UNEXPECTED_FAILURE",
            }, separators=(",", ":")))
            failures.append({"itemIdentifier": message_id})
    return {"batchItemFailures": failures}
