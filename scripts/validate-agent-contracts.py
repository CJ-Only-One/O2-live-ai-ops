#!/usr/bin/env python3
"""Validate Agent JSON Schemas, examples, and cross-field invariants."""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "docs" / "contracts"
EXAMPLES = CONTRACTS / "examples"


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def build_validator() -> Draft202012Validator:
    trigger_schema = load_json(CONTRACTS / "agent-trigger-v1.schema.json")
    incident_schema = load_json(CONTRACTS / "agent-incident-v1.schema.json")
    Draft202012Validator.check_schema(trigger_schema)
    Draft202012Validator.check_schema(incident_schema)
    registry = Registry().with_resource(
        trigger_schema["$id"], Resource.from_contents(trigger_schema)
    )
    return Draft202012Validator(
        incident_schema,
        registry=registry,
        format_checker=FormatChecker(),
    )


def semantic_errors(payload: dict) -> list[str]:
    errors: list[str] = []
    expected_key = (
        f"incident:{payload.get('incident_id')}:revision:{payload.get('revision')}"
    )
    if payload.get("idempotency_key") != expected_key:
        errors.append("idempotency_key must be derived from incident_id and revision")

    trigger_ids = [signal.get("trigger_id") for signal in payload.get("signals", [])]
    if len(trigger_ids) != len(set(trigger_ids)):
        errors.append("signals must not contain duplicate trigger_id values")

    try:
        opened_at = datetime.fromisoformat(payload["opened_at"].replace("Z", "+00:00"))
        updated_at = datetime.fromisoformat(payload["updated_at"].replace("Z", "+00:00"))
        if updated_at < opened_at:
            errors.append("updated_at must be greater than or equal to opened_at")
    except (KeyError, TypeError, ValueError):
        pass

    return errors


def validate(validator: Draft202012Validator, payload: dict) -> list[str]:
    schema_errors = [
        error.message
        for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    ]
    return schema_errors + semantic_errors(payload)


def require_valid(
    validator: Draft202012Validator, name: str, payload: dict
) -> None:
    errors = validate(validator, payload)
    if errors:
        raise AssertionError(f"{name} must be valid: {'; '.join(errors)}")


def require_invalid(
    validator: Draft202012Validator, name: str, payload: dict
) -> None:
    if not validate(validator, payload):
        raise AssertionError(f"{name} must be rejected")


def main() -> None:
    validator = build_validator()
    chat_first = load_json(EXAMPLES / "agent-incident-chat-first-v1.example.json")
    correlated = load_json(EXAMPLES / "agent-incident-correlated-v1.example.json")

    require_valid(validator, "chat-first example", chat_first)
    require_valid(validator, "correlated example", correlated)

    missing_datadog = copy.deepcopy(correlated)
    missing_datadog["signals"] = missing_datadog["signals"][:1]
    require_invalid(validator, "CORRELATED without Datadog", missing_datadog)

    raw_chat = copy.deepcopy(chat_first)
    raw_chat["signals"][0]["evidence"]["raw_message"] = "must not cross boundary"
    require_invalid(validator, "raw Chat field", raw_chat)

    wrong_revision_key = copy.deepcopy(correlated)
    wrong_revision_key["idempotency_key"] = (
        f"incident:{wrong_revision_key['incident_id']}:revision:1"
    )
    require_invalid(validator, "revision idempotency mismatch", wrong_revision_key)

    duplicate_signal = copy.deepcopy(correlated)
    duplicate_signal["signals"].append(copy.deepcopy(duplicate_signal["signals"][0]))
    require_invalid(validator, "duplicate trigger_id", duplicate_signal)

    print("Agent contract validation passed: 2 positive, 4 negative cases")


if __name__ == "__main__":
    main()
