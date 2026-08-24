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
        if set(item) != {"symptom_family", "suspected_surface", "service"}:
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
    if not 1 <= len(allowlist) <= 3 or any(not value for value in allowlist):
        raise CorrelatorError("SYNTHETIC_ALLOWLIST_INVALID")

    environment = os.environ.get("DEPLOYMENT_ENVIRONMENT", "")
    if not environment:
        raise CorrelatorError("DEPLOYMENT_ENVIRONMENT_MISSING")

    return {
        "window_seconds": window,
        "allowed_idempotency_keys": allowlist,
        "environment": environment,
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
        broadcast_ids = []
        environment = evidence["env"]
        if mapping is not None and evidence["service"] != mapping["service"]:
            mapping = None

    if mapping is None or not environment:
        return {
            "complete": False,
            "event_epoch": occurred_at_epoch,
            "context": {
                "environment": environment or settings["environment"],
                "symptom_family": "UNKNOWN",
                "suspected_surfaces": ["UNKNOWN"],
                "services": [],
                "broadcast_ids": broadcast_ids,
            },
            "correlation_key": None,
        }

    context = {
        "environment": environment,
        "symptom_family": mapping["symptom_family"],
        "suspected_surfaces": [mapping["suspected_surface"]],
        "services": [mapping["service"]],
        "broadcast_ids": broadcast_ids,
    }
    correlation_key = "#".join(
        [
            environment,
            mapping["symptom_family"],
            mapping["service"],
            mapping["suspected_surface"],
        ]
    )
    return {
        "complete": True,
        "event_epoch": occurred_at_epoch,
        "context": context,
        "correlation_key": correlation_key,
    }


def _merge_context(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    result = {
        "environment": current["environment"],
        "symptom_family": current["symptom_family"],
    }
    for field in ("suspected_surfaces", "services", "broadcast_ids"):
        result[field] = sorted(set(current[field]) | set(incoming[field]))
    return result


def _snapshot(
    trigger: dict[str, Any],
    normalized: dict[str, Any],
    matches: list[dict[str, Any]],
    now_iso: str,
    incident_id_factory: Any,
) -> tuple[dict[str, Any] | None, int | None, str]:
    if not normalized["complete"]:
        incident_id = incident_id_factory()
        correlation = {
            "state": "AMBIGUOUS",
            "strategy": "DETERMINISTIC_V1",
            "confidence": "LOW",
            "reason_code": "INSUFFICIENT_DIMENSIONS",
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
        correlation = {
            "state": "PROVISIONAL",
            "strategy": "DETERMINISTIC_V1",
            "confidence": "MEDIUM",
            "reason_code": reason,
            "matched_on": [],
            "operator_confirmation_required": False,
        }
        revision = 1
        expected_revision = None
        signals = [trigger]
        opened_at = trigger["occurred_at"]
        lifecycle = "OPEN"
        analysis_reason = "INITIAL_DETECTION"
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
        sources = {signal["source"] for signal in current["signals"]}
        if trigger["source"] in sources:
            if not (
                trigger["source"] == "DATADOG_MONITOR"
                and trigger["evidence"]["transition"] == "Recovered"
            ):
                return None, current["revision"], "NON_MATERIAL_SOURCE_UPDATE"
            analysis_reason = "RECOVERY_EVIDENCE_ADDED"
            lifecycle = "RECOVERING"
        else:
            analysis_reason = "CROSS_SOURCE_EVIDENCE_ADDED"
            lifecycle = current["lifecycle"]

        signals = [*current["signals"], trigger]
        if len(signals) > MAX_SIGNALS:
            raise CorrelatorError("INCIDENT_SIGNAL_LIMIT")
        incident_id = current["incident_id"]
        expected_revision = current["revision"]
        revision = expected_revision + 1
        opened_at = current["opened_at"]
        correlation = {
            "state": "CORRELATED" if len(sources | {trigger["source"]}) > 1 else current["correlation"]["state"],
            "strategy": "DETERMINISTIC_V1",
            "confidence": "HIGH" if len(sources | {trigger["source"]}) > 1 else current["correlation"]["confidence"],
            "reason_code": "UNIQUE_ACTIVE_MATCH",
            "matched_on": [
                "ENVIRONMENT",
                "SYMPTOM_FAMILY",
                "AFFECTED_SCOPE",
                "EVENT_TIME",
            ],
            "operator_confirmation_required": False,
        }
        context = _merge_context(current["normalized_context"], normalized["context"])

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
            FilterExpression="#lifecycle = :open AND #state <> :ambiguous",
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
    ) -> str:
        claim = {
            "pk": self.claim_key(trigger["idempotency_key"]),
            "record_type": "SIGNAL_CLAIM",
            "source_idempotency_key": trigger["idempotency_key"],
            "status": "PENDING",
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
                            "#revision = :expected AND #lifecycle = :open"
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
    if trigger["idempotency_key"] not in settings["allowed_idempotency_keys"]:
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
                settings["window_seconds"],
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

        sender(snapshot)
        repository.mark_emitted(trigger["idempotency_key"])
        return {"status": result, "snapshot": snapshot}

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
