"""Generic agent.trigger.v1 SQS worker.

Phase 1B ships this worker with two independent execution gates disabled:
the Terraform event source mapping is disabled and
AGENT_ENTRY_EXECUTION_ENABLED=false. The handler deliberately returns every
record as failed while that flag is false, so an accidental mapping enablement
still cannot call Dify.

Logs contain only message ids, source names, sanitized error codes, and a short
hash of the idempotency key. The envelope and Dify response are never logged.
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

GUARDRAILS = {
    "analysis_mode": "READ_ONLY",
    "automatic_remediation_allowed": False,
    "must_preserve_uncertainty": True,
    "raw_chat_included": False,
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
}

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
    "DATADOG_MONITOR": {
        "source_schema": "datadog.alert.v1",
        "trigger_type": "MONITOR_ALERT",
        "evidence_fields": DATADOG_EVIDENCE_FIELDS,
    },
    "CHAT_INCIDENT_CANDIDATE": {
        "source_schema": "chat.incident_candidate.v1",
        "trigger_type": "USER_SYMPTOM_CLUSTER",
        "evidence_fields": CHAT_EVIDENCE_FIELDS,
    },
}

DIFY_INPUT_MAX_CHARS = 30000

_clients: dict[str, Any] = {}
_cached_api_key: str | None = None


class WorkerError(Exception):
    """An expected, sanitized processing failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ContractError(WorkerError):
    pass


def _fail(code: str) -> None:
    raise ContractError(f"CONTRACT_REJECTED:{code}")


def _require_exact_keys(value: Any, expected: set[str], code: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        _fail(code)


def _require_datetime(value: Any, code: str) -> None:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail(code)
    if parsed.tzinfo is None:
        _fail(code)


def _require_string(value: Any, code: str, minimum: int = 0, maximum: int = 30000) -> None:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        _fail(code)


def validate_envelope(payload: Any) -> dict[str, Any]:
    """Validate the executable subset of docs/contracts/agent-trigger-v1.schema.json."""

    _require_exact_keys(payload, TOP_LEVEL_FIELDS, "TOP_LEVEL_FIELDS")

    if payload["schema_version"] != "1.0":
        _fail("SCHEMA_VERSION")
    if not isinstance(payload["trigger_id"], str) or not re.fullmatch(
        r"trg_[0-9A-HJKMNP-TV-Z]{26}", payload["trigger_id"]
    ):
        _fail("TRIGGER_ID")

    source = payload["source"]
    if source not in SOURCE_RULES:
        _fail("SOURCE")
    rule = SOURCE_RULES[source]
    if payload["source_schema"] != rule["source_schema"]:
        _fail("SOURCE_SCHEMA")
    if payload["trigger_type"] != rule["trigger_type"]:
        _fail("TRIGGER_TYPE")

    _require_string(payload["idempotency_key"], "IDEMPOTENCY_KEY", 1, 256)
    _require_datetime(payload["occurred_at"], "OCCURRED_AT")
    if payload["trace_id"] is not None:
        _require_string(payload["trace_id"], "TRACE_ID", 0, 128)

    _require_exact_keys(payload["guardrails"], set(GUARDRAILS), "GUARDRAIL_FIELDS")
    if payload["guardrails"] != GUARDRAILS:
        _fail("GUARDRAIL_VALUES")

    evidence = payload["evidence"]
    _require_exact_keys(evidence, rule["evidence_fields"], "EVIDENCE_FIELDS")

    if source == "DATADOG_MONITOR":
        _validate_datadog_evidence(evidence)
    else:
        _validate_chat_evidence(evidence)

    return payload


def _validate_datadog_evidence(evidence: dict[str, Any]) -> None:
    string_limits = {
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
    for field, (minimum, maximum) in string_limits.items():
        _require_string(evidence[field], f"DATADOG_{field.upper()}", minimum, maximum)
    if evidence["transition"] not in {
        "Triggered",
        "Re-Triggered",
        "Recovered",
        "Warn",
        "No Data",
        "Renotify",
    }:
        _fail("DATADOG_TRANSITION")


def _validate_chat_evidence(evidence: dict[str, Any]) -> None:
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
    if evidence["suspected_surface"] not in {"READ_PATH", "PLAYBACK", "CHAT", "UNKNOWN"}:
        _fail("CHAT_SURFACE")
    if evidence["confidence"] not in {"MEDIUM", "LOW"}:
        _fail("CHAT_CONFIDENCE")

    _require_datetime(evidence["window_start"], "CHAT_WINDOW_START")
    _require_datetime(evidence["window_end"], "CHAT_WINDOW_END")

    for field in ("matched_messages", "unique_users"):
        value = evidence[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            _fail("CHAT_POSITIVE_COUNTS")
    for field in ("strong_signal_count", "weak_signal_count"):
        value = evidence[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            _fail("CHAT_NONNEGATIVE_COUNTS")

    rule_ids = evidence["matched_rule_ids"]
    if not isinstance(rule_ids, list) or not rule_ids or len(rule_ids) != len(set(rule_ids)):
        _fail("CHAT_RULE_IDS")
    if any(not isinstance(value, str) or not re.fullmatch(r"[a-z0-9_]+", value) for value in rule_ids):
        _fail("CHAT_RULE_IDS")

    if evidence["metric_status"] != "NOT_CHECKED":
        _fail("CHAT_METRIC_STATUS")
    if evidence["root_cause"] != "UNDETERMINED":
        _fail("CHAT_ROOT_CAUSE")
    if evidence["requires_metric_corroboration"] is not True:
        _fail("CHAT_METRIC_GATE")


def _client(name: str) -> Any:
    if name not in _clients:
        import boto3

        _clients[name] = boto3.client(name)
    return _clients[name]


def _enabled() -> bool:
    return os.environ.get("AGENT_ENTRY_EXECUTION_ENABLED", "false").lower() == "true"


def _fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _serialize_payload(payload: dict[str, Any]) -> str:
    serialized = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    if len(serialized) > DIFY_INPUT_MAX_CHARS:
        raise ContractError("CONTRACT_REJECTED:DIFY_INPUT_TOO_LARGE")
    return serialized


def _api_key() -> str:
    global _cached_api_key
    if _cached_api_key is not None:
        return _cached_api_key

    response = _client("secretsmanager").get_secret_value(
        SecretId=os.environ["AGENT_ENTRY_SECRET"]
    )
    try:
        value = json.loads(response["SecretString"])["dify-api-key"]
    except (KeyError, TypeError, json.JSONDecodeError):
        raise WorkerError("SECRET_FORMAT") from None
    if not isinstance(value, str) or not value.startswith("app-"):
        raise WorkerError("SECRET_FORMAT")
    _cached_api_key = value
    return value


def _attribute(item: dict[str, Any], name: str) -> str | None:
    value = item.get(name)
    if not isinstance(value, dict):
        return None
    return value.get("S") or value.get("N")


def _acquire(payload: dict[str, Any], now: int) -> bool:
    key = payload["idempotency_key"]
    lease_seconds = int(os.environ.get("IDEMPOTENCY_LEASE", "120"))
    ttl_seconds = int(os.environ.get("IDEMPOTENCY_TTL", "2592000"))
    table = os.environ["IDEMPOTENCY_TABLE"]

    try:
        _client("dynamodb").update_item(
            TableName=table,
            Key={"idempotency_key": {"S": key}},
            UpdateExpression=(
                "SET #status = :in_progress, #source = :source, #trigger = :trigger, "
                "#lease = :lease, #expires = :expires, #updated = :updated, "
                "#attempts = if_not_exists(#attempts, :zero) + :one"
            ),
            ConditionExpression=(
                "attribute_not_exists(#pk) OR #expires < :now"
            ),
            ExpressionAttributeNames={
                "#pk": "idempotency_key",
                "#status": "status",
                "#source": "source",
                "#trigger": "trigger_id",
                "#lease": "lease_expires_at",
                "#expires": "expires_at",
                "#updated": "updated_at",
                "#attempts": "attempt_count",
            },
            ExpressionAttributeValues={
                ":in_progress": {"S": "IN_PROGRESS"},
                ":source": {"S": payload["source"]},
                ":trigger": {"S": payload["trigger_id"]},
                ":lease": {"N": str(now + lease_seconds)},
                ":expires": {"N": str(now + ttl_seconds)},
                ":updated": {"N": str(now)},
                ":now": {"N": str(now)},
                ":zero": {"N": "0"},
                ":one": {"N": "1"},
            },
        )
        return True
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if code != "ConditionalCheckFailedException":
            raise WorkerError("IDEMPOTENCY_WRITE") from exc

    existing = _client("dynamodb").get_item(
        TableName=table,
        Key={"idempotency_key": {"S": key}},
        ConsistentRead=True,
    ).get("Item", {})
    if _attribute(existing, "status") == "SUCCEEDED":
        return False
    status = _attribute(existing, "status") or "UNKNOWN"
    lease = _attribute(existing, "lease_expires_at")
    if status == "IN_PROGRESS" and lease is not None and int(lease) < now:
        raise WorkerError("IDEMPOTENCY_STALE")
    if status == "FAILED":
        raise WorkerError("IDEMPOTENCY_FAILED")
    raise WorkerError("IDEMPOTENCY_BUSY")


def _mark(payload: dict[str, Any], status: str, now: int, **values: str) -> None:
    names = {"#status": "status", "#updated": "updated_at", "#lease": "lease_expires_at"}
    expression_values = {
        ":status": {"S": status},
        ":updated": {"N": str(now)},
        ":lease": {"N": "0"},
        ":in_progress": {"S": "IN_PROGRESS"},
    }
    updates = ["#status = :status", "#updated = :updated", "#lease = :lease"]
    for index, (name, value) in enumerate(values.items()):
        name_key = f"#extra{index}"
        value_key = f":extra{index}"
        names[name_key] = name
        expression_values[value_key] = {"S": value}
        updates.append(f"{name_key} = {value_key}")

    try:
        _client("dynamodb").update_item(
            TableName=os.environ["IDEMPOTENCY_TABLE"],
            Key={"idempotency_key": {"S": payload["idempotency_key"]}},
            UpdateExpression="SET " + ", ".join(updates),
            ConditionExpression="#status = :in_progress",
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=expression_values,
        )
    except Exception as exc:
        raise WorkerError("IDEMPOTENCY_FINALIZE") from exc


def _call_dify(payload: dict[str, Any], serialized_payload: str) -> str:
    request_body = json.dumps(
        {
            "inputs": {
                "custom_alert_json": serialized_payload
            },
            "response_mode": "blocking",
            "user": f"agent-entry:{payload['source'].lower()}",
        },
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")

    request = urllib.request.Request(
        os.environ["DIFY_URL"],
        data=request_body,
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=float(os.environ.get("DIFY_TIMEOUT_SECONDS", "45"))
        ) as response:
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
        output.get("accepted") is not True
        or output.get("status") != "ACCEPTED"
        or output.get("source") != payload["source"]
        or output.get("source_schema") != payload["source_schema"]
    ):
        raise WorkerError("DIFY_OUTPUT_MISMATCH")
    workflow_run_id = data.get("id", "")
    return workflow_run_id if isinstance(workflow_run_id, str) else ""


def _process_record(record: dict[str, Any]) -> dict[str, str]:
    try:
        payload = json.loads(record["body"])
    except (KeyError, TypeError, json.JSONDecodeError):
        raise ContractError("CONTRACT_REJECTED:INVALID_JSON") from None
    payload = validate_envelope(payload)
    serialized_payload = _serialize_payload(payload)
    now = int(time.time())
    fingerprint = _fingerprint(payload["idempotency_key"])

    # Secret 조회는 외부 Dify 호출 전에 끝낸다. 여기서 실패하면 ledger를 잡지
    # 않으므로 SQS 재전달이 안전하게 다시 시도할 수 있다.
    _api_key()
    acquired = _acquire(payload, now)
    if not acquired:
        return {"status": "DUPLICATE", "source": payload["source"], "key": fingerprint}

    try:
        workflow_run_id = _call_dify(payload, serialized_payload)
        extra = {"workflow_run_id": workflow_run_id} if workflow_run_id else {}
        _mark(payload, "SUCCEEDED", int(time.time()), **extra)
    except WorkerError as exc:
        try:
            _mark(payload, "FAILED", int(time.time()), error_code=exc.code)
        except WorkerError:
            LOGGER.exception(
                json.dumps(
                    {"event": "agent_entry_finalize_failed", "key": fingerprint},
                    separators=(",", ":"),
                )
            )
        raise

    return {"status": "SUCCEEDED", "source": payload["source"], "key": fingerprint}


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, list[dict[str, str]]]:
    records = event.get("Records")
    if not isinstance(records, list):
        raise WorkerError("INVALID_SQS_EVENT")

    failures: list[dict[str, str]] = []
    execution_enabled = _enabled()
    for record in records:
        message_id = str(record.get("messageId", "UNKNOWN"))
        if not execution_enabled:
            LOGGER.warning(
                json.dumps(
                    {
                        "event": "agent_entry_record",
                        "message_id": message_id,
                        "status": "EXECUTION_DISABLED",
                    },
                    separators=(",", ":"),
                )
            )
            failures.append({"itemIdentifier": message_id})
            continue

        try:
            result = _process_record(record)
            LOGGER.info(
                json.dumps(
                    {
                        "event": "agent_entry_record",
                        "message_id": message_id,
                        **result,
                    },
                    separators=(",", ":"),
                )
            )
        except WorkerError as exc:
            LOGGER.warning(
                json.dumps(
                    {
                        "event": "agent_entry_record",
                        "message_id": message_id,
                        "status": "FAILED",
                        "error_code": exc.code,
                    },
                    separators=(",", ":"),
                )
            )
            failures.append({"itemIdentifier": message_id})
        except Exception:
            LOGGER.exception(
                json.dumps(
                    {
                        "event": "agent_entry_record",
                        "message_id": message_id,
                        "status": "UNEXPECTED_FAILURE",
                    },
                    separators=(",", ":"),
                )
            )
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}
