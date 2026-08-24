#!/usr/bin/env python3
"""Validate the cue sheet JSON Schema, its examples, and cross-field invariants.

Kept separate from validate-agent-contracts.py because that script's validator is
built from the two Agent schemas and knows their invariants. The cue sheet is a
different contract with different invariants; folding it in would make both
harder to read.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "docs" / "contracts"
EXAMPLES = CONTRACTS / "examples"

# 특가는 어느 상품인지 모르면 계획을 세울 수 없다. order_rate 만 있고 sku_id 가
# 없으면 "무엇의 주문인지" 가 비어 워머가 대상을 못 고른다.
SKU_REQUIRED = {"SALE_OPEN", "SALE_CLOSING"}


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # 오프셋 없는 값은 스키마가 이미 막는다. 여기서도 거부해야 aware 값과
    # 비교하다 TypeError 로 죽는 대신 스키마 오류만 남는다.
    if parsed.tzinfo is None:
        raise ValueError("offset is required")
    return parsed


def semantic_errors(payload: dict) -> list[str]:
    errors: list[str] = []
    segments = payload.get("segments") or []

    seqs = [segment.get("seq") for segment in segments]
    if len(seqs) != len(set(seqs)):
        errors.append("segments must not contain duplicate seq values")

    try:
        start = parse_dt(payload["scheduled_at"])
        end = parse_dt(payload["ends_at"]) if payload.get("ends_at") else None
    except (KeyError, TypeError, ValueError):
        start = end = None

    for segment in segments:
        seq = segment.get("seq")
        kind = segment.get("segment_type")

        if kind in SKU_REQUIRED and not segment.get("sku_id"):
            errors.append(f"seq {seq}: {kind} requires sku_id")

        expected = segment.get("expected") or {}
        # 근거 없는 검색 판정은 검토가 불가능하고 발표에서 띄울 것도 없다.
        if expected.get("by") == "web_search" and not expected.get("evidence"):
            errors.append(f"seq {seq}: by=web_search requires evidence")

        if start is None:
            continue
        try:
            at = parse_dt(segment["at"])
        except (KeyError, TypeError, ValueError):
            continue
        # 방송 창 밖의 세그먼트는 조용히 무시되거나 엉뚱한 시각에 실행된다.
        if at < start:
            errors.append(f"seq {seq}: at is before scheduled_at")
        if end is not None and at > end:
            errors.append(f"seq {seq}: at is after ends_at")

    return errors


def validate(validator: Draft202012Validator, payload: dict) -> list[str]:
    schema_errors = [
        error.message
        for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    ]
    return schema_errors + semantic_errors(payload)


def require_valid(validator: Draft202012Validator, name: str, payload: dict) -> None:
    errors = validate(validator, payload)
    if errors:
        raise AssertionError(f"{name} must be valid: {'; '.join(errors)}")


def require_invalid(validator: Draft202012Validator, name: str, payload: dict) -> None:
    if not validate(validator, payload):
        raise AssertionError(f"{name} must be rejected")


def main() -> None:
    schema = load_json(CONTRACTS / "cue-sheet-v1.schema.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    valued = load_json(EXAMPLES / "cue-sheet-v1.example.json")
    unvalued = load_json(EXAMPLES / "cue-sheet-unvalued-v1.example.json")

    require_valid(validator, "valued example", valued)
    # 수치가 비어 있어도 유효해야 한다. 그래야 스키마를 먼저 만들고 값을 나중에 채운다.
    require_valid(validator, "unvalued example", unvalued)

    naive = copy.deepcopy(valued)
    naive["segments"][0]["at"] = "2026-08-24T20:00:00"
    require_invalid(validator, "datetime without offset", naive)

    unknown_type = copy.deepcopy(valued)
    unknown_type["segments"][0]["segment_type"] = "PRODUCT_SWITCH"
    require_invalid(validator, "segment_type outside enum", unknown_type)

    numeric_sku = copy.deepcopy(valued)
    numeric_sku["segments"][3]["sku_id"] = 88213
    require_invalid(validator, "sku_id as integer", numeric_sku)

    no_sku = copy.deepcopy(valued)
    del no_sku["segments"][3]["sku_id"]
    require_invalid(validator, "SALE_OPEN without sku_id", no_sku)

    no_evidence = copy.deepcopy(valued)
    del no_evidence["segments"][1]["expected"]["evidence"]
    require_invalid(validator, "web_search without evidence", no_evidence)

    outside = copy.deepcopy(valued)
    outside["segments"][0]["at"] = "2026-08-24T19:00:00+09:00"
    require_invalid(validator, "segment before scheduled_at", outside)

    duplicate_seq = copy.deepcopy(valued)
    duplicate_seq["segments"][1]["seq"] = duplicate_seq["segments"][0]["seq"]
    require_invalid(validator, "duplicate seq", duplicate_seq)

    print("Cue sheet validation passed: 2 positive, 7 negative cases")


if __name__ == "__main__":
    main()
