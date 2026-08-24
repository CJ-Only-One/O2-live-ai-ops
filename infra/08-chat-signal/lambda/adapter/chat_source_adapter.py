"""Convert privacy-safe Chat Candidate INSERTs to agent.trigger.v1.

Phase 2 deploys this Lambda with both the DynamoDB Stream event source and
CHAT_SOURCE_ADAPTER_ENABLED disabled. Phase 3 additionally requires exactly
one synthetic broadcast id before the adapter may enqueue anything. Logs
contain sequence ids, stable error codes, and statuses only. Candidate payloads
and Queue bodies are never logged.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

DIFY_INPUT_MAX_CHARS = 30000

CANDIDATE_FIELDS = {
    "schema_version",
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
    "raw_chat_included",
    "agent_handoff_status",
    "created_at",
}

EVIDENCE_FIELDS = {
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

GUARDRAILS = {
    "analysis_mode": "READ_ONLY",
    "automatic_remediation_allowed": False,
    "must_preserve_uncertainty": True,
    "raw_chat_included": False,
}

_clients: dict[str, Any] = {}


class AdapterError(Exception):
    """Retryable or contract-safe error with a content-free code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ContractError(AdapterError):
    pass


def _fail(code: str) -> None:
    raise ContractError(f"CONTRACT_REJECTED:{code}")


def _enabled() -> bool:
    return os.environ.get("CHAT_SOURCE_ADAPTER_ENABLED", "false").lower() == "true"


def _allowed_broadcast_id() -> str:
    raw = os.environ.get("CHAT_SOURCE_ADAPTER_ALLOWED_BROADCAST_IDS", "")
    values = raw.split(",") if raw else []
    if len(values) != 1 or not re.fullmatch(r"bc_[0-9]+", values[0]):
        raise AdapterError("SYNTHETIC_BROADCAST_ALLOWLIST_INVALID")
    return values[0]


def _client(name: str) -> Any:
    if name not in _clients:
        import boto3

        _clients[name] = boto3.client(name)
    return _clients[name]


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


def _deserialize_attribute(value: Any) -> Any:
    """Deserialize the AttributeValue subset used by Candidate table records."""

    if not isinstance(value, dict) or len(value) != 1:
        _fail("DYNAMODB_ATTRIBUTE")
    kind, raw = next(iter(value.items()))
    if kind == "S" and isinstance(raw, str):
        return raw
    if kind == "N" and isinstance(raw, str) and re.fullmatch(r"-?[0-9]+", raw):
        return int(raw)
    if kind == "BOOL" and isinstance(raw, bool):
        return raw
    if kind == "NULL" and raw is True:
        return None
    if kind == "L" and isinstance(raw, list):
        return [_deserialize_attribute(item) for item in raw]
    if kind == "M" and isinstance(raw, dict):
        return {name: _deserialize_attribute(item) for name, item in raw.items()}
    if kind == "SS" and isinstance(raw, list) and all(
        isinstance(item, str) for item in raw
    ):
        return list(raw)
    _fail("DYNAMODB_ATTRIBUTE_TYPE")


def _deserialize_image(image: Any) -> dict[str, Any]:
    if not isinstance(image, dict):
        _fail("DYNAMODB_NEW_IMAGE")
    return {name: _deserialize_attribute(value) for name, value in image.items()}


def validate_candidate(candidate: Any) -> dict[str, Any]:
    _require_exact_keys(candidate, CANDIDATE_FIELDS, "CANDIDATE_FIELDS")

    if candidate["schema_version"] != "1.0":
        _fail("CANDIDATE_SCHEMA_VERSION")
    if not isinstance(candidate["candidate_id"], str) or not re.fullmatch(
        r"cand_[0-9A-HJKMNP-TV-Z]{26}", candidate["candidate_id"]
    ):
        _fail("CANDIDATE_ID")
    if candidate["candidate_type"] != "USER_PERCEIVED_LATENCY":
        _fail("CANDIDATE_TYPE")
    if not isinstance(candidate["broadcast_id"], str) or not re.fullmatch(
        r"bc_[0-9]+", candidate["broadcast_id"]
    ):
        _fail("BROADCAST_ID")
    if candidate["suspected_surface"] not in {
        "READ_PATH",
        "PLAYBACK",
        "CHAT",
        "UNKNOWN",
    }:
        _fail("SUSPECTED_SURFACE")
    if candidate["confidence"] not in {"MEDIUM", "LOW"}:
        _fail("CONFIDENCE")

    for field in ("window_start", "window_end", "created_at"):
        _require_datetime(candidate[field], field.upper())

    for field in ("matched_messages", "unique_users"):
        value = candidate[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            _fail("POSITIVE_COUNTS")
    for field in ("strong_signal_count", "weak_signal_count"):
        value = candidate[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            _fail("NONNEGATIVE_COUNTS")

    rule_ids = candidate["matched_rule_ids"]
    if not isinstance(rule_ids, list) or not rule_ids or len(rule_ids) != len(set(rule_ids)):
        _fail("RULE_IDS")
    if any(
        not isinstance(value, str) or not re.fullmatch(r"[a-z0-9_]+", value)
        for value in rule_ids
    ):
        _fail("RULE_IDS")

    if candidate["metric_status"] != "NOT_CHECKED":
        _fail("METRIC_STATUS")
    if candidate["root_cause"] != "UNDETERMINED":
        _fail("ROOT_CAUSE")
    if candidate["requires_metric_corroboration"] is not True:
        _fail("METRIC_GATE")
    if candidate["raw_chat_included"] is not False:
        _fail("RAW_CHAT_POLICY")
    if candidate["agent_handoff_status"] != "NOT_CONFIGURED":
        _fail("HANDOFF_STATUS")

    return candidate


def build_envelope(candidate: dict[str, Any]) -> dict[str, Any]:
    suffix = candidate["candidate_id"].removeprefix("cand_")
    evidence = {field: candidate[field] for field in EVIDENCE_FIELDS}
    return {
        "schema_version": "1.0",
        "trigger_id": f"trg_{suffix}",
        "source": "CHAT_INCIDENT_CANDIDATE",
        "source_schema": "chat.incident_candidate.v1",
        "trigger_type": "USER_SYMPTOM_CLUSTER",
        "idempotency_key": f"chat:{candidate['candidate_id']}",
        "occurred_at": candidate["created_at"],
        "trace_id": None,
        "evidence": evidence,
        "guardrails": dict(GUARDRAILS),
    }


def _serialize_envelope(envelope: dict[str, Any]) -> str:
    serialized = json.dumps(
        envelope, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    if len(serialized) > DIFY_INPUT_MAX_CHARS:
        _fail("DIFY_INPUT_TOO_LARGE")
    return serialized


def _sequence_number(record: Any) -> str:
    try:
        value = record["dynamodb"]["SequenceNumber"]
    except (KeyError, TypeError):
        raise AdapterError("STREAM_SEQUENCE_MISSING") from None
    if not isinstance(value, str) or not value:
        raise AdapterError("STREAM_SEQUENCE_MISSING")
    return value


def _process_record(record: dict[str, Any]) -> str:
    if record.get("eventSource") != "aws:dynamodb":
        raise AdapterError("STREAM_SOURCE_INVALID")
    if record.get("eventName") != "INSERT":
        return "IGNORED_NON_INSERT"

    try:
        image = record["dynamodb"]["NewImage"]
    except (KeyError, TypeError):
        _fail("DYNAMODB_NEW_IMAGE")
    item = _deserialize_image(image)

    pk = item.get("pk")
    sk = item.get("sk")
    if not isinstance(pk, str) or not pk.startswith("CANDIDATE#") or sk != "META":
        return "IGNORED_NON_CANDIDATE"

    candidate = validate_candidate(item.get("payload"))
    if pk != f"CANDIDATE#{candidate['candidate_id']}":
        _fail("CANDIDATE_KEY_MISMATCH")

    allowed_broadcast_id = _allowed_broadcast_id()
    if candidate["broadcast_id"] != allowed_broadcast_id:
        return "IGNORED_BROADCAST_NOT_ALLOWED"

    # A disabled Stream mapping can retain records until Phase 3. The cutover
    # timestamp prevents old production Candidates from becoming test traffic.
    not_before_epoch = int(
        os.environ.get("CHAT_SOURCE_ADAPTER_NOT_BEFORE_EPOCH", "4102444800")
    )
    created_epoch = int(
        datetime.fromisoformat(candidate["created_at"].replace("Z", "+00:00")).timestamp()
    )
    if created_epoch < not_before_epoch:
        return "IGNORED_BEFORE_ACTIVATION"

    envelope = build_envelope(candidate)
    serialized = _serialize_envelope(envelope)
    try:
        _client("sqs").send_message(
            QueueUrl=os.environ["AGENT_TRIGGER_QUEUE_URL"],
            MessageBody=serialized,
            MessageAttributes={
                "schema": {"DataType": "String", "StringValue": "agent.trigger.v1"},
                "source": {
                    "DataType": "String",
                    "StringValue": "CHAT_INCIDENT_CANDIDATE",
                },
            },
        )
    except Exception as error:
        raise AdapterError("AGENT_TRIGGER_SEND_FAILED") from error
    return "ENQUEUED"


def handler(event: dict[str, Any], _context: Any) -> dict[str, list[dict[str, str]]]:
    records = event.get("Records") if isinstance(event, dict) else None
    if not isinstance(records, list):
        raise AdapterError("STREAM_RECORDS_INVALID")

    failures: list[dict[str, str]] = []
    execution_enabled = _enabled()
    for record in records:
        try:
            sequence_number = _sequence_number(record)
        except AdapterError:
            # Without a sequence number Lambda cannot checkpoint a partial batch safely.
            raise

        if not execution_enabled:
            LOGGER.warning(
                "chat_source_adapter sequence=%s status=EXECUTION_DISABLED",
                sequence_number,
            )
            failures.append({"itemIdentifier": sequence_number})
            continue

        try:
            status = _process_record(record)
            LOGGER.info(
                "chat_source_adapter sequence=%s status=%s",
                sequence_number,
                status,
            )
        except AdapterError as error:
            LOGGER.warning(
                "chat_source_adapter sequence=%s status=FAILED error_code=%s",
                sequence_number,
                error.code,
            )
            failures.append({"itemIdentifier": sequence_number})
        except Exception:
            LOGGER.error(
                "chat_source_adapter sequence=%s status=FAILED error_code=UNEXPECTED",
                sequence_number,
            )
            failures.append({"itemIdentifier": sequence_number})

    return {"batchItemFailures": failures}
