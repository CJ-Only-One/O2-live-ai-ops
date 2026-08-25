#!/usr/bin/env python3
"""Validate the evidence-backed initial Incident correlation window.

This is deliberately a worst-observed bounded calculation, not a percentile
claim. Three Datadog samples cannot establish a stable p95, while the deployed
operational monitor has a deterministic five-minute full evaluation window.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "infra" / "09-incident" / "correlation-window-evidence.json"


def require_config_int(path: Path, pattern: str, name: str) -> int:
    matches = re.findall(pattern, path.read_text(encoding="utf-8"), flags=re.MULTILINE)
    if len(matches) != 1:
        raise AssertionError(f"{name} must have exactly one machine-readable value")
    return int(matches[0])


def require_positive_ints(name: str, values: object) -> list[int]:
    if not isinstance(values, list) or not values:
        raise AssertionError(f"{name} must be a non-empty list")
    if any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in values):
        raise AssertionError(f"{name} must contain positive integer milliseconds")
    return values


def main() -> None:
    with EVIDENCE.open(encoding="utf-8") as file:
        evidence = json.load(file)

    if evidence.get("schema_version") != "1.0":
        raise AssertionError("schema_version must be 1.0")
    if evidence.get("scope") != "PHASE4F_SHADOW_INITIAL_WINDOW":
        raise AssertionError("scope must remain Shadow-only Phase 4F")
    if evidence.get("statistical_claim") != "NONE":
        raise AssertionError("the current samples must not be presented as a percentile claim")

    bounds = evidence["configured_bounds"]
    chat_window = bounds["chat_candidate_window_seconds"]
    datadog_window = bounds["datadog_operational_full_window_seconds"]
    quantum = bounds["rounding_quantum_seconds"]
    for name, value in (
        ("chat_candidate_window_seconds", chat_window),
        ("datadog_operational_full_window_seconds", datadog_window),
        ("rounding_quantum_seconds", quantum),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise AssertionError(f"{name} must be a positive integer")
    if chat_window >= datadog_window:
        raise AssertionError("Chat candidate window must be shorter than the Datadog full window")

    observations = evidence["observations"]
    require_positive_ints("chat_source_to_queue_ms", observations["chat_source_to_queue_ms"])
    datadog_ms = require_positive_ints(
        "datadog_triggered_source_to_queue_ms",
        observations["datadog_triggered_source_to_queue_ms"],
    )

    tail_guard = math.ceil((max(datadog_ms) / 1000) / quantum) * quantum
    window = datadog_window + tail_guard

    derivation = evidence["derivation"]
    if derivation["expected_datadog_tail_guard_seconds"] != tail_guard:
        raise AssertionError("expected Datadog tail guard does not match observations")
    if derivation["expected_correlation_window_seconds"] != window:
        raise AssertionError("expected correlation window does not match derivation")

    guardrails = evidence["guardrails"]
    if guardrails["activation_scope"] != "SHADOW_ONLY":
        raise AssertionError("Phase 4F may only prepare a Shadow window")
    if guardrails["production_agent_handoff_enabled"] is not False:
        raise AssertionError("Phase 4F must not enable production Agent handoff")
    if window > guardrails["maximum_correlation_window_seconds"]:
        raise AssertionError("derived window exceeds the configured safety maximum")
    if window % quantum != 0:
        raise AssertionError("derived window must align to the rounding quantum")

    configured_chat_window = require_config_int(
        ROOT / "infra" / "08-chat-signal" / "lambda" / "runtime" / "processor.py",
        r"^WINDOW_SECONDS\s*=\s*(\d+)\s*$",
        "Chat WINDOW_SECONDS",
    )
    datadog_minutes = require_config_int(
        ROOT / "infra" / "05-datadog" / "variables.tf",
        r'(?s)variable "scenario_entry_window_minutes".*?\n\s*default\s*=\s*(\d+)',
        "Datadog scenario_entry_window_minutes",
    )
    configured_incident_window = require_config_int(
        ROOT / "infra" / "09-incident" / "terraform.tfvars",
        r"^incident_correlation_window_seconds\s*=\s*(\d+)\s*$",
        "incident_correlation_window_seconds",
    )
    if configured_chat_window != chat_window:
        raise AssertionError("evidence Chat window differs from processor.py")
    if datadog_minutes * 60 != datadog_window:
        raise AssertionError("evidence Datadog window differs from variables.tf")
    if configured_incident_window != window:
        raise AssertionError("terraform.tfvars correlation window differs from derivation")

    print(
        "Incident correlation window validation passed: "
        f"datadog_full_window={datadog_window}s "
        f"tail_guard={tail_guard}s derived_window={window}s scope=SHADOW_ONLY"
    )


if __name__ == "__main__":
    main()
