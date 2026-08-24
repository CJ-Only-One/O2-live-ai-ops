import importlib.util
import json
import os
import pathlib
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).with_name("agent_entry_worker.py")
SPEC = importlib.util.spec_from_file_location("agent_entry_worker", MODULE_PATH)
worker = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(worker)

REPO_ROOT = pathlib.Path(__file__).parents[3]
EXAMPLES = REPO_ROOT / "docs" / "contracts" / "examples"


def load_example(name):
    return json.loads((EXAMPLES / name).read_text())


class AgentEntryWorkerTest(unittest.TestCase):
    def setUp(self):
        worker._clients.clear()
        worker._cached_api_key = None
        chat = load_example("agent-trigger-chat-v1.example.json")
        self.environment = {
            "AGENT_ENTRY_ALLOWED_IDEMPOTENCY_KEYS": chat["idempotency_key"]
        }
        self.environment_patch = mock.patch.dict(
            os.environ, self.environment, clear=False
        )
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)

    def test_accepts_chat_and_datadog_examples(self):
        chat = load_example("agent-trigger-chat-v1.example.json")
        datadog = load_example("agent-trigger-datadog-v1.example.json")

        self.assertEqual(worker.validate_envelope(chat)["source"], "CHAT_INCIDENT_CANDIDATE")
        self.assertEqual(worker.validate_envelope(datadog)["source"], "DATADOG_MONITOR")

    def test_rejects_source_schema_mismatch_without_echoing_input(self):
        payload = load_example("agent-trigger-chat-v1.example.json")
        payload["source_schema"] = "datadog.alert.v1"

        with self.assertRaisesRegex(worker.ContractError, r"^CONTRACT_REJECTED:SOURCE_SCHEMA$"):
            worker.validate_envelope(payload)

    def test_rejects_raw_chat_field(self):
        payload = load_example("agent-trigger-chat-v1.example.json")
        payload["evidence"]["raw_chat"] = "synthetic text"

        with self.assertRaisesRegex(worker.ContractError, r"^CONTRACT_REJECTED:EVIDENCE_FIELDS$"):
            worker.validate_envelope(payload)

    def test_rejects_payload_larger_than_published_dify_input_before_preflight(self):
        payload = load_example("agent-trigger-datadog-v1.example.json")
        payload["evidence"]["alert_body"] = "x" * worker.DIFY_INPUT_MAX_CHARS
        record = {"messageId": "oversized", "body": json.dumps(payload)}

        with mock.patch.dict(
            os.environ,
            {"AGENT_ENTRY_ALLOWED_IDEMPOTENCY_KEYS": payload["idempotency_key"]},
            clear=False,
        ):
            with mock.patch.object(worker, "_api_key") as api_key:
                with mock.patch.object(worker, "_acquire") as acquire:
                    with self.assertRaisesRegex(
                        worker.ContractError,
                        r"^CONTRACT_REJECTED:DIFY_INPUT_TOO_LARGE$",
                    ):
                        worker._process_record(record)

        api_key.assert_not_called()
        acquire.assert_not_called()

    def test_disabled_gate_returns_all_records_as_failures_without_processing(self):
        event = {
            "Records": [
                {"messageId": "one", "body": "{}"},
                {"messageId": "two", "body": "{}"},
            ]
        }
        with mock.patch.dict(os.environ, {"AGENT_ENTRY_EXECUTION_ENABLED": "false"}, clear=False):
            with mock.patch.object(worker, "_process_record") as process:
                result = worker.lambda_handler(event, None)

        process.assert_not_called()
        self.assertEqual(
            result,
            {"batchItemFailures": [{"itemIdentifier": "one"}, {"itemIdentifier": "two"}]},
        )

    def test_enabled_gate_reports_only_failed_record(self):
        event = {
            "Records": [
                {"messageId": "ok", "body": "{}"},
                {"messageId": "bad", "body": "{}"},
            ]
        }

        def process(record):
            if record["messageId"] == "bad":
                raise worker.WorkerError("EXPECTED_FAILURE")
            return {"status": "SUCCEEDED", "source": "TEST", "key": "fingerprint"}

        with mock.patch.dict(os.environ, {"AGENT_ENTRY_EXECUTION_ENABLED": "true"}, clear=False):
            with mock.patch.object(worker, "_process_record", side_effect=process):
                result = worker.lambda_handler(event, None)

        self.assertEqual(result, {"batchItemFailures": [{"itemIdentifier": "bad"}]})

    def test_duplicate_succeeded_does_not_call_dify(self):
        payload = load_example("agent-trigger-chat-v1.example.json")
        record = {"messageId": "duplicate", "body": json.dumps(payload)}

        with mock.patch.object(worker, "_api_key", return_value="app-test"):
            with mock.patch.object(worker, "_acquire", return_value=False):
                with mock.patch.object(worker, "_call_dify") as call_dify:
                    result = worker._process_record(record)

        call_dify.assert_not_called()
        self.assertEqual(result["status"], "DUPLICATE")

    def test_empty_synthetic_allowlist_rejects_before_secret_and_ledger(self):
        payload = load_example("agent-trigger-chat-v1.example.json")
        record = {"messageId": "allowlist-empty", "body": json.dumps(payload)}

        with mock.patch.dict(
            os.environ, {"AGENT_ENTRY_ALLOWED_IDEMPOTENCY_KEYS": ""}, clear=False
        ):
            with mock.patch.object(worker, "_api_key") as api_key:
                with mock.patch.object(worker, "_acquire") as acquire:
                    with self.assertRaisesRegex(
                        worker.WorkerError,
                        r"^SYNTHETIC_IDEMPOTENCY_ALLOWLIST_INVALID$",
                    ):
                        worker._process_record(record)

        api_key.assert_not_called()
        acquire.assert_not_called()

    def test_unlisted_synthetic_key_rejects_before_secret_and_ledger(self):
        payload = load_example("agent-trigger-chat-v1.example.json")
        record = {"messageId": "not-allowed", "body": json.dumps(payload)}

        with mock.patch.dict(
            os.environ,
            {
                "AGENT_ENTRY_ALLOWED_IDEMPOTENCY_KEYS": (
                    "chat:cand_01ARZ3NDEKTSV4RRFFQ69G5FAA"
                )
            },
            clear=False,
        ):
            with mock.patch.object(worker, "_api_key") as api_key:
                with mock.patch.object(worker, "_acquire") as acquire:
                    with self.assertRaisesRegex(
                        worker.WorkerError,
                        r"^SYNTHETIC_IDEMPOTENCY_KEY_NOT_ALLOWED$",
                    ):
                        worker._process_record(record)

        api_key.assert_not_called()
        acquire.assert_not_called()

    def test_failed_dify_call_marks_ledger_failed(self):
        payload = load_example("agent-trigger-datadog-v1.example.json")
        record = {"messageId": "failed", "body": json.dumps(payload)}

        with mock.patch.dict(
            os.environ,
            {"AGENT_ENTRY_ALLOWED_IDEMPOTENCY_KEYS": payload["idempotency_key"]},
            clear=False,
        ):
            with mock.patch.object(worker, "_api_key", return_value="app-test"):
                with mock.patch.object(worker, "_acquire", return_value=True):
                    with mock.patch.object(
                        worker, "_call_dify", side_effect=worker.WorkerError("DIFY_FAIL")
                    ):
                        with mock.patch.object(worker, "_mark") as mark:
                            with self.assertRaisesRegex(worker.WorkerError, "DIFY_FAIL"):
                                worker._process_record(record)

        self.assertEqual(mark.call_args.args[1], "FAILED")
        self.assertEqual(mark.call_args.kwargs["error_code"], "DIFY_FAIL")

    def test_existing_failed_record_is_not_reacquired(self):
        class ConditionalFailure(Exception):
            response = {"Error": {"Code": "ConditionalCheckFailedException"}}

        class FakeDynamoDB:
            def update_item(self, **_kwargs):
                raise ConditionalFailure()

            def get_item(self, **_kwargs):
                return {"Item": {"status": {"S": "FAILED"}}}

        payload = load_example("agent-trigger-chat-v1.example.json")
        with mock.patch.dict(
            os.environ,
            {"IDEMPOTENCY_TABLE": "test-table", "IDEMPOTENCY_TTL": "2592000"},
            clear=False,
        ):
            with mock.patch.object(worker, "_client", return_value=FakeDynamoDB()):
                with self.assertRaisesRegex(worker.WorkerError, "IDEMPOTENCY_FAILED"):
                    worker._acquire(payload, 100)


if __name__ == "__main__":
    unittest.main()
