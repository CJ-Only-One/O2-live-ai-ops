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
                and snapshot["lifecycle"] == "OPEN"
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
            "status": "PENDING",
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
                    "symptom_family": "LATENCY",
                    "suspected_surface": "READ_PATH",
                    "service": "api",
                }
            },
            "datadog_monitor_map": {
                "monitor_example": {
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
            "correlation_key": "dev#LATENCY#api#READ_PATH",
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

    def test_duplicate_signal_does_not_create_new_revision_or_output(self):
        repository = FakeRepository()
        sender = Sender()
        first = self.process(self.chat, repository, sender)
        second = self.process(self.chat, repository, sender)

        self.assertEqual(second["status"], "DUPLICATE")
        self.assertEqual(len(sender.snapshots), 1)
        self.assertEqual(len(repository.incidents), 1)
        self.assertEqual(first["snapshot"]["revision"], 1)

    def test_pending_output_is_replayed_without_new_revision(self):
        repository = FakeRepository()
        failing_sender = Sender(fail=True)
        with self.assertRaisesRegex(RuntimeError, "synthetic send failure"):
            self.process(self.chat, repository, failing_sender)

        sender = Sender()
        result = self.process(self.chat, repository, sender)

        self.assertEqual(result["status"], "PENDING_REPLAYED")
        self.assertEqual(result["snapshot"]["revision"], 1)
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
        self.assertEqual(len(sender.snapshots), 1)
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
            )

        self.assertEqual(result, "COMMITTED")
        self.assertEqual(len(fake.request["TransactItems"]), 3)
        pointer = fake.request["TransactItems"][2]["Update"]
        self.assertIn("attribute_not_exists", pointer["ConditionExpression"])
        self.assertIn("CORRELATION#", pointer["Key"]["pk"]["S"])


if __name__ == "__main__":
    unittest.main()
