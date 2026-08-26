import copy
import importlib.util
import json
import os
import pathlib
import re
import unittest
from decimal import Decimal
from importlib.util import find_spec
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).with_name("incident_correlator.py")
SPEC = importlib.util.spec_from_file_location("incident_correlator", MODULE_PATH)
correlator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(correlator)

REPO_ROOT = pathlib.Path(__file__).parents[3]
EXAMPLES = REPO_ROOT / "docs" / "contracts" / "examples"


def load_example(name):
    return json.loads((EXAMPLES / name).read_text())


def trigger(name):
    return load_example(name)


class FakeRepository:
    def __init__(self):
        self.claims = {}
        self.incidents = {}

    def get_claim(self, idempotency_key):
        return copy.deepcopy(self.claims.get(idempotency_key))

    def find_open(self, correlation_key, event_epoch, window):
        matches = []
        for item in self.incidents.values():
            snapshot = item["snapshot"]
            if (
                item["correlation_key"] == correlation_key
                and snapshot["lifecycle"] in {"OPEN", "RECOVERING", "RESOLVED"}
                and snapshot["correlation"]["state"] != "AMBIGUOUS"
                and abs(item["event_epoch"] - event_epoch) <= window
            ):
                matches.append(copy.deepcopy(snapshot))
        return matches

    def commit(
        self,
        trigger_payload,
        snapshot,
        normalized,
        expected_revision,
        now_epoch,
        window_seconds,
        invocation_required,
    ):
        key = trigger_payload["idempotency_key"]
        if key in self.claims:
            return "CLAIM_EXISTS"
        incident_id = snapshot["incident_id"]
        if expected_revision is None:
            if incident_id in self.incidents:
                return "CONFLICT"
        else:
            current = self.incidents.get(incident_id)
            if current is None or current["snapshot"]["revision"] != expected_revision:
                return "CONFLICT"
        self.claims[key] = {
            "status": "PENDING" if invocation_required else "NOT_REQUIRED",
            "snapshot": copy.deepcopy(snapshot),
        }
        self.incidents[incident_id] = {
            "correlation_key": normalized["correlation_key"] or f"AMBIGUOUS#{incident_id}",
            "event_epoch": normalized["event_epoch"],
            "snapshot": copy.deepcopy(snapshot),
        }
        return "COMMITTED"

    def commit_ignored(self, trigger_payload, _now_epoch):
        key = trigger_payload["idempotency_key"]
        if key in self.claims:
            return "CLAIM_EXISTS"
        self.claims[key] = {"status": "NOT_REQUIRED"}
        return "IGNORED"

    def mark_emitted(self, idempotency_key):
        self.claims[idempotency_key]["status"] = "EMITTED"


class Sender:
    def __init__(self, fail=False):
        self.fail = fail
        self.snapshots = []

    def __call__(self, snapshot):
        if self.fail:
            raise RuntimeError("synthetic send failure")
        self.snapshots.append(copy.deepcopy(snapshot))


class IncidentCorrelatorTest(unittest.TestCase):
    def setUp(self):
        correlator._clients.clear()
        self.chat = trigger("agent-trigger-chat-v1.example.json")
        self.datadog = trigger("agent-trigger-datadog-v1.example.json")
        self.settings = {
            "window_seconds": 120,
            "allowed_idempotency_keys": {
                self.chat["idempotency_key"],
                self.datadog["idempotency_key"],
            },
            "environment": "dev",
            "chat_surface_map": {
                "READ_PATH": {
                    "evidence_role": "PRIMARY",
                    "incident_family": "READ_PATH_DEGRADATION",
                    "symptom_family": "LATENCY",
                    "suspected_surface": "READ_PATH",
                    "service": "api",
                }
            },
            "datadog_monitor_map": {
                "monitor_example": {
                    "evidence_role": "CORROBORATING",
                    "incident_family": "READ_PATH_DEGRADATION",
                    "symptom_family": "LATENCY",
                    "suspected_surface": "READ_PATH",
                    "service": "api",
                }
            },
        }
        self.incident_id = "inc_01ARZ3NDEKTSV4RRFFQ69G5FAY"

    def process(self, payload, repository, sender, incident_id=None, now_epoch=1787443246):
        incident_id = incident_id or self.incident_id
        return correlator.process_trigger(
            payload,
            self.settings,
            repository,
            sender,
            incident_id_factory=lambda: incident_id,
            now_epoch=now_epoch,
        )

    def datadog_variant(self, *, monitor_id, trigger_id, cycle_key, role, evidence_type="SERVICE_TAIL_LATENCY", transition="Triggered", severity="WARNING"):
        value = copy.deepcopy(self.datadog)
        value["trigger_id"] = trigger_id
        value["idempotency_key"] = f"datadog:{cycle_key}:{transition}"
        value["evidence"]["event_id"] = f"event_{cycle_key}"
        value["evidence"]["cycle_key"] = cycle_key
        value["evidence"]["monitor_id"] = monitor_id
        value["evidence"]["transition"] = transition
        value["evidence"]["assessment_input"]["evidence_type"] = evidence_type
        self.settings["allowed_idempotency_keys"].add(value["idempotency_key"])
        self.settings["datadog_monitor_map"][monitor_id] = {
            "evidence_role": role, "evidence_type": evidence_type,
            "incident_family": "READ_PATH_DEGRADATION", "symptom_family": "LATENCY",
            "suspected_surface": "READ_PATH", "service": "api", "minimum_samples": 1,
            "freshness_seconds": 300, "severity_level": severity,
            "strong_exception_allowed": False,
        }
        return value

    def test_no_data_is_not_accepted_as_corroborating_evidence(self):
        repository, sender = FakeRepository(), Sender()
        self.process(self.chat, repository, sender)
        signal = copy.deepcopy(self.datadog)
        signal["idempotency_key"] = "datadog:cycle_example_001:No Data"
        signal["evidence"]["transition"] = "No Data"
        signal["evidence"]["assessment_input"]["data_state"] = "NO_DATA"
        signal["evidence"]["assessment_input"]["sample_count"] = 0
        signal["evidence"]["assessment_input"]["measurements"] = {}
        self.settings["allowed_idempotency_keys"].add(signal["idempotency_key"])
        result = self.process(signal, repository, sender, now_epoch=1787443276)
        self.assertEqual(result["snapshot"]["data_quality"]["state"], "MIXED")
        self.assertEqual(result["snapshot"]["evidence_assessment"]["missing_required_roles"], ["CORROBORATING"])
        self.assertEqual(sender.snapshots, [])

    def test_severity_increase_is_material_revision(self):
        repository, sender = FakeRepository(), Sender()
        self.process(self.chat, repository, sender)
        high = self.datadog_variant(monitor_id="monitor_high", trigger_id="trg_01ARZ3NDEKTSV4RRFFQ69G5FAB", cycle_key="high_001", role="CORROBORATING", severity="HIGH")
        result = self.process(high, repository, sender, now_epoch=1787443276)
        self.assertEqual(result["snapshot"]["severity_assessment"]["level"], "HIGH")
        self.assertTrue(result["snapshot"]["severity_assessment"]["material_change"])

    def test_recovery_requires_both_roles_and_sustained_window(self):
        repository, sender = FakeRepository(), Sender()
        self.settings["recovery_window_seconds"] = 60
        primary = self.datadog_variant(monitor_id="monitor_primary", trigger_id="trg_01ARZ3NDEKTSV4RRFFQ69G5FAB", cycle_key="primary", role="PRIMARY")
        self.process(self.datadog, repository, sender)
        self.process(primary, repository, sender, now_epoch=1787443276)
        recovery_c = self.datadog_variant(monitor_id="monitor_example", trigger_id="trg_01ARZ3NDEKTSV4RRFFQ69G5FAC", cycle_key="cycle_example_001", role="CORROBORATING", transition="Recovered")
        recovery_c["occurred_at"] = "2026-08-23T00:01:00.000Z"
        recovery_c["evidence"]["assessment_input"]["observed_at"] = recovery_c["occurred_at"]
        first = self.process(recovery_c, repository, sender, now_epoch=1787443260)
        self.assertEqual(first["snapshot"]["lifecycle"], "RECOVERING")
        recovery_p = self.datadog_variant(monitor_id="monitor_primary", trigger_id="trg_01ARZ3NDEKTSV4RRFFQ69G5FAD", cycle_key="primary", role="PRIMARY", transition="Recovered")
        recovery_p["occurred_at"] = "2026-08-23T00:02:01.000Z"
        recovery_p["evidence"]["assessment_input"]["observed_at"] = recovery_p["occurred_at"]
        final = self.process(recovery_p, repository, sender, now_epoch=1787443321)
        self.assertEqual(final["snapshot"]["lifecycle"], "RESOLVED")
        self.assertEqual(final["snapshot"]["analysis_reason"], "RECOVERY_SUSTAINED")

    def test_integrity_strong_exception_verifies_single_signal(self):
        repository, sender = FakeRepository(), Sender()
        signal = self.datadog_variant(monitor_id="integrity", trigger_id="trg_01ARZ3NDEKTSV4RRFFQ69G5FAB", cycle_key="integrity", role="PRIMARY", evidence_type="INTEGRITY_VIOLATION", severity="CRITICAL")
        signal["evidence"]["assessment_input"]["signal_strength"] = "STRONG"
        self.settings["datadog_monitor_map"]["integrity"].update({"incident_family":"DATA_INTEGRITY_SECURITY_RISK", "symptom_family":"ERROR_RATE", "suspected_surface":"UNKNOWN", "strong_exception_allowed":True})
        result = self.process(signal, repository, sender)
        self.assertEqual(result["snapshot"]["correlation"]["reason_code"], "STRONG_EXCEPTION")
        self.assertTrue(result["snapshot"]["evidence_assessment"]["strong_exception_applied"])
        self.assertEqual(len(sender.snapshots), 1)

    def test_s2_cpu_requires_pod_scope(self):
        signal = copy.deepcopy(self.datadog)
        assessment = signal["evidence"]["assessment_input"]
        assessment["evidence_type"] = "POD_CPU_UTILIZATION"
        assessment["measurements"] = {"cpu_utilization_ratio": 0.9}
        with self.assertRaisesRegex(correlator.ContractError, "ASSESSMENT_S2_POD_SCOPE"):
            correlator.validate_trigger(signal)

    def test_datadog_scope_broadcast_id_is_adopted_into_context(self):
        """D-086: Datadog evidence 의 방송 축을 버리지 않는다.

        버리면 Chat 이 먼저 왔는지 Datadog 이 먼저 왔는지에 따라 같은 Incident 의
        방송 축이 달라지고, Dify normalize 가 `LIVE-001` fallback 으로 없는 방송에
        조치를 건다.
        """
        repository, sender = FakeRepository(), Sender()
        signal = copy.deepcopy(self.datadog)
        signal["evidence"]["assessment_input"]["scope"]["broadcast_id"] = "bc_1042"
        result = self.process(signal, repository, sender)
        context = result["snapshot"]["normalized_context"]
        self.assertEqual(context["broadcast_ids"], ["bc_1042"])

    def test_datadog_without_broadcast_scope_keeps_empty_list(self):
        """방송 축이 없는 Monitor(S2 파드 등)는 빈 목록을 그대로 유지한다."""
        repository, sender = FakeRepository(), Sender()
        signal = copy.deepcopy(self.datadog)
        self.assertIsNone(signal["evidence"]["assessment_input"]["scope"]["broadcast_id"])
        result = self.process(signal, repository, sender)
        self.assertEqual(result["snapshot"]["normalized_context"]["broadcast_ids"], [])

    def test_material_revision_inside_cooldown_is_stored_without_invocation(self):
        repository, sender = FakeRepository(), Sender()
        self.settings["cooldown_seconds"] = 300
        self.process(self.chat, repository, sender)
        self.process(self.datadog, repository, sender, now_epoch=1787443276)
        high = self.datadog_variant(monitor_id="monitor_high", trigger_id="trg_01ARZ3NDEKTSV4RRFFQ69G5FAB", cycle_key="high_002", role="CORROBORATING", severity="HIGH")
        result = self.process(high, repository, sender, now_epoch=1787443300)
        self.assertTrue(result["snapshot"]["notification_policy"]["suppressed"])
        self.assertEqual(len(sender.snapshots), 1)

    def test_resolved_incident_reopens_with_same_id_inside_reopen_window(self):
        repository, sender = FakeRepository(), Sender()
        self.settings["reopen_window_seconds"] = 300
        self.process(self.chat, repository, sender)
        verified = self.process(self.datadog, repository, sender, now_epoch=1787443276)["snapshot"]
        verified["lifecycle"] = "RESOLVED"
        verified["updated_at"] = "2026-08-23T00:00:46Z"
        verified["recovery_assessment"] = {"state":"SATISFIED","started_at":"2026-08-23T00:00:20Z","required_until":"2026-08-23T00:00:40Z","recovered_roles":["PRIMARY","CORROBORATING"]}
        repository.incidents[self.incident_id]["snapshot"] = copy.deepcopy(verified)
        reopen = self.datadog_variant(monitor_id="monitor_reopen", trigger_id="trg_01ARZ3NDEKTSV4RRFFQ69G5FAB", cycle_key="reopen_001", role="CORROBORATING")
        reopen["occurred_at"] = "2026-08-23T00:01:00.000Z"
        reopen["evidence"]["assessment_input"]["observed_at"] = reopen["occurred_at"]
        result = self.process(reopen, repository, sender, now_epoch=1787443260)
        self.assertEqual(result["snapshot"]["incident_id"], self.incident_id)
        self.assertEqual(result["snapshot"]["lifecycle"], "OPEN")
        self.assertEqual(result["snapshot"]["analysis_reason"], "INCIDENT_REOPENED")

    def test_chat_first_then_datadog_uses_same_incident_and_revision_two(self):
        repository = FakeRepository()
        sender = Sender()

        first = self.process(self.chat, repository, sender)
        second = self.process(self.datadog, repository, sender, now_epoch=1787443276)

        self.assertEqual(first["snapshot"]["correlation"]["state"], "PROVISIONAL")
        self.assertEqual(second["snapshot"]["incident_id"], self.incident_id)
        self.assertEqual(second["snapshot"]["revision"], 2)
        self.assertEqual(second["snapshot"]["correlation"]["state"], "CORRELATED")
        self.assertEqual(second["snapshot"]["analysis_reason"], "CROSS_SOURCE_EVIDENCE_ADDED")
        self.assertEqual(
            second["snapshot"]["evidence_assessment"],
            {
                "primary": [self.chat["trigger_id"]],
                "corroborating": [self.datadog["trigger_id"]],
                "context": [],
                "missing_required_roles": [],
                "strong_exception_applied": False,
                "verification_state": "VERIFIED",
            },
        )
        self.assertEqual(len(sender.snapshots), 1)
        self.assertEqual(sender.snapshots[0]["revision"], 2)

    def test_strong_chat_candidate_can_invoke_read_only_agent_without_metric(self):
        repository = FakeRepository()
        sender = Sender()
        self.settings["chat_surface_map"]["READ_PATH"].update({
            "evidence_type": "USER_SYMPTOM_CLUSTER",
            "minimum_samples": 1,
            "freshness_seconds": 300,
            "severity_level": "WARNING",
            "strong_exception_allowed": True,
        })

        result = self.process(self.chat, repository, sender)

        self.assertEqual(result["status"], "MATERIAL_REVISION")
        self.assertEqual(result["snapshot"]["correlation"]["reason_code"], "STRONG_EXCEPTION")
        self.assertEqual(result["snapshot"]["evidence_assessment"]["verification_state"], "VERIFIED")
        self.assertTrue(result["snapshot"]["evidence_assessment"]["strong_exception_applied"])
        self.assertFalse(result["snapshot"]["guardrails"]["automatic_remediation_allowed"])
        self.assertEqual(len(sender.snapshots), 1)

    def test_strong_chat_candidate_promotes_existing_provisional_incident(self):
        repository = FakeRepository()
        sender = Sender()
        self.process(self.chat, repository, sender)
        self.settings["chat_surface_map"]["READ_PATH"].update({
            "evidence_type": "USER_SYMPTOM_CLUSTER",
            "minimum_samples": 1,
            "freshness_seconds": 300,
            "severity_level": "WARNING",
            "strong_exception_allowed": True,
        })
        second = copy.deepcopy(self.chat)
        second["trigger_id"] = "trg_01ARZ3NDEKTSV4RRFFQ69G5FAB"
        second["idempotency_key"] = "chat:cand_01ARZ3NDEKTSV4RRFFQ69G5FAB"
        second["evidence"]["candidate_id"] = "cand_01ARZ3NDEKTSV4RRFFQ69G5FAB"
        self.settings["allowed_idempotency_keys"].add(second["idempotency_key"])

        result = self.process(second, repository, sender, now_epoch=1787443276)

        self.assertEqual(result["status"], "MATERIAL_REVISION")
        self.assertEqual(result["snapshot"]["revision"], 2)
        self.assertEqual(result["snapshot"]["analysis_reason"], "STRONG_EXCEPTION_APPLIED")
        self.assertEqual(result["snapshot"]["evidence_assessment"]["verification_state"], "VERIFIED")
        self.assertEqual(len(sender.snapshots), 1)

    def test_new_strong_chat_candidate_reinvokes_agent_for_demo_rerun(self):
        repository = FakeRepository()
        sender = Sender()
        self.settings["chat_surface_map"]["READ_PATH"].update({
            "evidence_type": "USER_SYMPTOM_CLUSTER",
            "minimum_samples": 1,
            "freshness_seconds": 300,
            "severity_level": "WARNING",
            "strong_exception_allowed": True,
        })
        self.process(self.chat, repository, sender)
        second = copy.deepcopy(self.chat)
        second["trigger_id"] = "trg_01ARZ3NDEKTSV4RRFFQ69G5FAB"
        second["idempotency_key"] = "chat:cand_01ARZ3NDEKTSV4RRFFQ69G5FAB"
        second["evidence"]["candidate_id"] = "cand_01ARZ3NDEKTSV4RRFFQ69G5FAB"
        self.settings["allowed_idempotency_keys"].add(second["idempotency_key"])

        result = self.process(second, repository, sender, now_epoch=1787443276)

        self.assertEqual(result["status"], "MATERIAL_REVISION")
        self.assertEqual(result["snapshot"]["revision"], 2)
        self.assertEqual(len(sender.snapshots), 2)

    def test_datadog_first_then_chat_uses_same_incident_and_revision_two(self):
        repository = FakeRepository()
        sender = Sender()

        first = self.process(self.datadog, repository, sender)
        second = self.process(self.chat, repository, sender, now_epoch=1787443276)

        self.assertEqual(
            first["snapshot"]["correlation"]["reason_code"],
            "DATADOG_FIRST_NO_CHAT",
        )
        self.assertEqual(second["snapshot"]["incident_id"], self.incident_id)
        self.assertEqual(second["snapshot"]["revision"], 2)
        self.assertEqual(second["snapshot"]["correlation"]["state"], "CORRELATED")
        self.assertEqual(len(sender.snapshots), 1)
        self.assertEqual(sender.snapshots[0]["revision"], 2)

    def test_distinct_datadog_roles_can_verify_one_incident(self):
        repository = FakeRepository()
        sender = Sender()
        primary = copy.deepcopy(self.datadog)
        primary["trigger_id"] = "trg_01ARZ3NDEKTSV4RRFFQ69G5FAB"
        primary["idempotency_key"] = "datadog:cycle_example_002:Triggered"
        primary["evidence"]["event_id"] = "event_example_002"
        primary["evidence"]["cycle_key"] = "cycle_example_002"
        primary["evidence"]["monitor_id"] = "monitor_primary"
        self.settings["allowed_idempotency_keys"].add(primary["idempotency_key"])
        self.settings["datadog_monitor_map"]["monitor_primary"] = {
            "evidence_role": "PRIMARY",
            "incident_family": "READ_PATH_DEGRADATION",
            "symptom_family": "LATENCY",
            "suspected_surface": "READ_PATH",
            "service": "api",
        }

        first = self.process(self.datadog, repository, sender)
        second = self.process(primary, repository, sender, now_epoch=1787443276)

        self.assertEqual(first["status"], "STORED_WITHOUT_INVOCATION")
        self.assertEqual(second["snapshot"]["incident_id"], self.incident_id)
        self.assertEqual(second["snapshot"]["revision"], 2)
        self.assertEqual(second["snapshot"]["analysis_reason"], "EVIDENCE_ROLE_ADDED")
        self.assertEqual(
            second["snapshot"]["evidence_assessment"]["verification_state"],
            "VERIFIED",
        )
        self.assertEqual(len(sender.snapshots), 1)

    def test_single_datadog_signal_is_stored_without_invocation(self):
        repository = FakeRepository()
        sender = Sender()

        result = self.process(self.datadog, repository, sender)

        self.assertEqual(result["status"], "STORED_WITHOUT_INVOCATION")
        self.assertEqual(result["snapshot"]["correlation"]["state"], "PROVISIONAL")
        self.assertEqual(
            result["snapshot"]["evidence_assessment"]["missing_required_roles"],
            ["PRIMARY"],
        )
        self.assertEqual(
            result["snapshot"]["evidence_assessment"]["verification_state"],
            "INSUFFICIENT_EVIDENCE",
        )
        self.assertEqual(sender.snapshots, [])
        self.assertEqual(
            repository.claims[self.datadog["idempotency_key"]]["status"],
            "NOT_REQUIRED",
        )

    def test_ambiguous_signal_is_stored_without_invocation(self):
        repository = FakeRepository()
        sender = Sender()
        self.settings["datadog_monitor_map"] = {}

        result = self.process(self.datadog, repository, sender)

        self.assertEqual(result["status"], "STORED_WITHOUT_INVOCATION")
        self.assertEqual(result["snapshot"]["correlation"]["state"], "AMBIGUOUS")
        self.assertEqual(
            result["snapshot"]["evidence_assessment"]["verification_state"],
            "AMBIGUOUS",
        )
        self.assertEqual(sender.snapshots, [])

    def test_outside_window_creates_separate_incident(self):
        repository = FakeRepository()
        sender = Sender()
        self.process(self.chat, repository, sender)
        self.datadog["occurred_at"] = "2026-08-23T00:10:00.000Z"

        result = self.process(
            self.datadog,
            repository,
            sender,
            incident_id="inc_01ARZ3NDEKTSV4RRFFQ69G5FAZ",
        )

        self.assertEqual(result["snapshot"]["revision"], 1)
        self.assertEqual(result["snapshot"]["correlation"]["state"], "PROVISIONAL")
        self.assertEqual(len(repository.incidents), 2)

    def test_multiple_matching_incidents_are_not_forced_together(self):
        repository = FakeRepository()
        sender = Sender()
        first = self.process(self.chat, repository, sender)["snapshot"]
        duplicate = copy.deepcopy(first)
        duplicate["incident_id"] = "inc_01ARZ3NDEKTSV4RRFFQ69G5FAZ"
        duplicate["idempotency_key"] = (
            "incident:inc_01ARZ3NDEKTSV4RRFFQ69G5FAZ:revision:1"
        )
        repository.incidents[duplicate["incident_id"]] = {
            "correlation_key": (
                "dev#READ_PATH_DEGRADATION#LATENCY#api#READ_PATH"
            ),
            "event_epoch": repository.incidents[self.incident_id]["event_epoch"],
            "snapshot": duplicate,
        }

        result = self.process(
            self.datadog,
            repository,
            sender,
            incident_id="inc_01ARZ3NDEKTSV4RRFFQ69G5FB0",
        )

        self.assertEqual(result["snapshot"]["correlation"]["state"], "AMBIGUOUS")
        self.assertEqual(
            result["snapshot"]["correlation"]["reason_code"],
            "MULTIPLE_ACTIVE_MATCHES",
        )
        self.assertTrue(
            result["snapshot"]["correlation"]["operator_confirmation_required"]
        )

    def test_missing_monitor_mapping_is_ambiguous_without_text_inference(self):
        repository = FakeRepository()
        sender = Sender()
        self.settings["datadog_monitor_map"] = {}

        result = self.process(self.datadog, repository, sender)

        self.assertEqual(result["snapshot"]["correlation"]["state"], "AMBIGUOUS")
        self.assertEqual(
            result["snapshot"]["correlation"]["reason_code"],
            "INSUFFICIENT_DIMENSIONS",
        )
        self.assertEqual(result["snapshot"]["normalized_context"]["symptom_family"], "UNKNOWN")
        self.assertEqual(result["snapshot"]["normalized_context"]["incident_family"], "UNKNOWN")

    def test_datadog_environment_mismatch_is_ambiguous_without_foreign_incident(self):
        repository = FakeRepository()
        sender = Sender()
        self.datadog["evidence"]["env"] = "o2-dev"
        self.datadog["evidence"]["assessment_input"]["scope"]["environment"] = "o2-dev"

        result = self.process(self.datadog, repository, sender)

        self.assertEqual(result["snapshot"]["correlation"]["state"], "AMBIGUOUS")
        self.assertEqual(
            result["snapshot"]["correlation"]["reason_code"],
            "SOURCE_ENVIRONMENT_MISMATCH",
        )
        self.assertTrue(
            result["snapshot"]["correlation"]["operator_confirmation_required"]
        )
        self.assertEqual(result["snapshot"]["normalized_context"]["environment"], "dev")
        self.assertTrue(
            all(
                item["correlation_key"] != "o2-dev#LATENCY#api#READ_PATH"
                for item in repository.incidents.values()
            )
        )

    def test_environment_mismatch_does_not_join_matching_chat_incident(self):
        repository = FakeRepository()
        sender = Sender()
        self.process(self.chat, repository, sender)
        self.datadog["evidence"]["env"] = "o2-dev"
        self.datadog["evidence"]["assessment_input"]["scope"]["environment"] = "o2-dev"

        result = self.process(
            self.datadog,
            repository,
            sender,
            incident_id="inc_01ARZ3NDEKTSV4RRFFQ69G5FAZ",
        )

        self.assertEqual(result["snapshot"]["correlation"]["state"], "AMBIGUOUS")
        self.assertEqual(
            result["snapshot"]["correlation"]["reason_code"],
            "SOURCE_ENVIRONMENT_MISMATCH",
        )
        self.assertEqual(len(repository.incidents), 2)
        self.assertEqual(len(sender.snapshots), 0)

    def test_duplicate_signal_does_not_create_new_revision_or_output(self):
        repository = FakeRepository()
        sender = Sender()
        first = self.process(self.chat, repository, sender)
        second = self.process(self.chat, repository, sender)

        self.assertEqual(second["status"], "DUPLICATE")
        self.assertEqual(len(sender.snapshots), 0)
        self.assertEqual(len(repository.incidents), 1)
        self.assertEqual(first["snapshot"]["revision"], 1)

    def test_pending_output_is_replayed_without_new_revision(self):
        repository = FakeRepository()
        self.process(self.chat, repository, Sender())
        failing_sender = Sender(fail=True)
        with self.assertRaisesRegex(RuntimeError, "synthetic send failure"):
            self.process(self.datadog, repository, failing_sender)

        sender = Sender()
        result = self.process(self.datadog, repository, sender)

        self.assertEqual(result["status"], "PENDING_REPLAYED")
        self.assertEqual(result["snapshot"]["revision"], 2)
        self.assertEqual(len(repository.incidents), 1)
        self.assertEqual(len(sender.snapshots), 1)

    def test_same_source_non_material_update_is_stored_without_invocation(self):
        repository = FakeRepository()
        sender = Sender()
        self.process(self.chat, repository, sender)
        update = copy.deepcopy(self.chat)
        update["trigger_id"] = "trg_01ARZ3NDEKTSV4RRFFQ69G5FAB"
        update["evidence"]["candidate_id"] = "cand_01ARZ3NDEKTSV4RRFFQ69G5FAA"
        update["idempotency_key"] = "chat:cand_01ARZ3NDEKTSV4RRFFQ69G5FAA"
        self.settings["allowed_idempotency_keys"].add(update["idempotency_key"])

        result = self.process(update, repository, sender)

        self.assertEqual(result["status"], "NON_MATERIAL_SOURCE_UPDATE")
        self.assertEqual(len(sender.snapshots), 0)
        self.assertEqual(repository.incidents[self.incident_id]["snapshot"]["revision"], 1)

    def test_raw_chat_field_is_rejected(self):
        payload = copy.deepcopy(self.chat)
        payload["evidence"]["raw_message"] = "must not cross boundary"
        with self.assertRaisesRegex(
            correlator.ContractError,
            r"^CONTRACT_REJECTED:EVIDENCE_FIELDS$",
        ):
            correlator.validate_trigger(payload)

    def test_unlisted_key_rejects_before_repository_access(self):
        repository = mock.Mock()
        self.settings["allowed_idempotency_keys"] = {"chat:cand_01ARZ3NDEKTSV4RRFFQ69G5FAA"}
        with self.assertRaisesRegex(
            correlator.CorrelatorError,
            r"^SYNTHETIC_IDEMPOTENCY_KEY_NOT_ALLOWED$",
        ):
            self.process(self.chat, repository, Sender())
        repository.get_claim.assert_not_called()

    def test_disabled_handler_fails_all_records_without_processing(self):
        event = {
            "Records": [
                {"messageId": "one", "body": "{}"},
                {"messageId": "two", "body": "{}"},
            ]
        }
        with mock.patch.dict(
            os.environ,
            {"INCIDENT_CORRELATOR_EXECUTION_ENABLED": "false"},
            clear=False,
        ):
            with mock.patch.object(correlator, "_process_record") as process:
                result = correlator.lambda_handler(event, None)

        process.assert_not_called()
        self.assertEqual(
            result,
            {
                "batchItemFailures": [
                    {"itemIdentifier": "one"},
                    {"itemIdentifier": "two"},
                ]
            },
        )

    def test_zero_window_fails_closed_when_execution_is_enabled(self):
        with mock.patch.dict(
            os.environ,
            {
                "INCIDENT_CORRELATION_WINDOW_SECONDS": "0",
                "INCIDENT_CORRELATOR_ALLOWED_IDEMPOTENCY_KEYS": self.chat[
                    "idempotency_key"
                ],
            },
            clear=False,
        ):
            with self.assertRaisesRegex(
                correlator.CorrelatorError,
                r"^CORRELATION_WINDOW_NOT_CONFIGURED$",
            ):
                correlator.settings_from_environment()

    def test_unknown_incident_family_mapping_is_rejected(self):
        raw = json.dumps(
            {
                "monitor_example": {
                    "evidence_role": "PRIMARY",
                    "incident_family": "MADE_UP_FAMILY",
                    "symptom_family": "LATENCY",
                    "suspected_surface": "READ_PATH",
                    "service": "api",
                }
            }
        )

        with self.assertRaisesRegex(
            correlator.CorrelatorError,
            r"^DATADOG_MONITOR_MAP_INVALID$",
        ):
            correlator._mapping(raw, "DATADOG_MONITOR_MAP_INVALID")

    def test_complete_mapping_loads_from_environment_json(self):
        raw = json.dumps({"21940250": {
            "evidence_role":"CORROBORATING", "evidence_type":"SERVICE_TAIL_LATENCY",
            "incident_family":"READ_PATH_DEGRADATION", "symptom_family":"LATENCY",
            "suspected_surface":"READ_PATH", "service":"api", "minimum_samples":1,
            "freshness_seconds":300, "severity_level":"WARNING",
            "strong_exception_allowed":False,
        }})
        value = correlator._mapping(raw, "DATADOG_MONITOR_MAP_INVALID")
        self.assertEqual(value["21940250"]["severity_level"], "WARNING")

    def test_generated_incident_id_matches_contract_pattern(self):
        value = correlator.new_incident_id(0, b"\0" * 10)
        self.assertRegex(value, re.compile(r"^inc_[0-9A-HJKMNP-TV-Z]{26}$"))

    def test_dynamodb_numbers_are_converted_to_json_integers(self):
        value = correlator._json_compatible(
            {"revision": Decimal("2"), "counts": [Decimal("4")]}
        )
        self.assertEqual(value, {"revision": 2, "counts": [4]})

    @unittest.skipUnless(find_spec("boto3") is not None, "Lambda runtime boto3 required")
    def test_new_incident_transaction_contains_claim_incident_and_pointer(self):
        class FakeDynamoDB:
            def __init__(self):
                self.request = None

            def transact_write_items(self, **request):
                self.request = request

        fake = FakeDynamoDB()
        correlator._clients["dynamodb"] = fake
        with mock.patch.dict(
            os.environ,
            {
                "INCIDENT_STATE_TABLE": "test-incident-state",
                "INCIDENT_CORRELATION_INDEX": "test-index",
                "INCIDENT_SIGNAL_CLAIM_TTL": "2592000",
            },
            clear=False,
        ):
            repository = correlator.AwsIncidentRepository()
            normalized = correlator.normalize_trigger(self.chat, self.settings)
            snapshot, expected, _ = correlator._snapshot(
                self.chat,
                normalized,
                [],
                "2026-08-23T00:00:16Z",
                lambda: self.incident_id,
            )
            result = repository.commit(
                self.chat,
                snapshot,
                normalized,
                expected,
                1787443246,
                self.settings["window_seconds"],
                False,
            )

        self.assertEqual(result, "COMMITTED")
        self.assertEqual(len(fake.request["TransactItems"]), 3)
        claim = fake.request["TransactItems"][0]["Put"]["Item"]
        self.assertEqual(claim["status"], {"S": "NOT_REQUIRED"})
        pointer = fake.request["TransactItems"][2]["Update"]
        self.assertIn("attribute_not_exists", pointer["ConditionExpression"])
        self.assertIn("CORRELATION#", pointer["Key"]["pk"]["S"])


if __name__ == "__main__":
    unittest.main()
