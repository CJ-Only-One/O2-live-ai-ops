import importlib.util
import json
import os
import pathlib
import re
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


class ConditionalFailure(Exception):
    response = {"Error": {"Code": "TransactionCanceledException"}}


class AgentEntryWorkerTest(unittest.TestCase):
    def setUp(self):
        worker._clients.clear()
        worker._cached_api_key = None
        self.chat_first = load_example("agent-incident-chat-first-v1.example.json")
        self.correlated = load_example("agent-incident-correlated-v1.example.json")
        self.environment_patch = mock.patch.dict(
            os.environ,
            {
                "AGENT_ENTRY_ALLOWED_INCIDENT_IDS": self.chat_first["incident_id"],
                "IDEMPOTENCY_TABLE": "execution-ledger",
                "INCIDENT_STATE_TABLE": "incident-state",
                "IDEMPOTENCY_TTL": "2592000",
            },
            clear=False,
        )
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)

    def test_accepts_provisional_and_correlated_incident_examples(self):
        self.assertEqual(worker.validate_envelope(self.chat_first)["revision"], 1)
        self.assertEqual(worker.validate_envelope(self.correlated)["revision"], 2)

    def test_iam_policy_allows_finalize_transaction_operations(self):
        terraform = (
            REPO_ROOT / "infra" / "06-agent" / "agent_entry_transport.tf"
        ).read_text()
        statement = re.search(
            r'statement\s*\{\s*sid\s*=\s*"UseIdempotencyLedger"(?P<body>.*?)\n\s*\}',
            terraform,
            re.DOTALL,
        )
        self.assertIsNotNone(statement)
        for action in {
            "dynamodb:DeleteItem",
            "dynamodb:GetItem",
            "dynamodb:PutItem",
            "dynamodb:UpdateItem",
            "dynamodb:TransactWriteItems",
        }:
            self.assertIn(f'"{action}"', statement.group("body"))

    def test_rejects_revision_idempotency_mismatch(self):
        self.chat_first["revision"] = 2
        with self.assertRaisesRegex(worker.ContractError, "IDEMPOTENCY_KEY"):
            worker.validate_envelope(self.chat_first)

    def test_rejects_raw_chat_nested_in_signal(self):
        self.chat_first["signals"][0]["evidence"]["raw_chat"] = "synthetic"
        with self.assertRaisesRegex(worker.ContractError, "TRIGGER_EVIDENCE_FIELDS"):
            worker.validate_envelope(self.chat_first)

    def test_rejects_correlated_incident_without_both_sources(self):
        self.correlated["signals"] = [self.correlated["signals"][0]]
        with self.assertRaisesRegex(worker.ContractError, "CORRELATED_SOURCES"):
            worker.validate_envelope(self.correlated)

    def test_oversized_payload_fails_before_state_secret_and_lock(self):
        self.chat_first["signals"][0]["evidence"]["matched_rule_ids"] = [
            "x" * worker.DIFY_INPUT_MAX_CHARS
        ]
        record = {"body": json.dumps(self.chat_first)}
        with mock.patch.object(worker, "_latest_revision") as latest:
            with mock.patch.object(worker, "_api_key") as api_key:
                with mock.patch.object(worker, "_acquire") as acquire:
                    with self.assertRaises(worker.ContractError):
                        worker._process_record(record)
        latest.assert_not_called()
        api_key.assert_not_called()
        acquire.assert_not_called()

    def test_empty_incident_allowlist_fails_before_state_and_secret(self):
        record = {"body": json.dumps(self.chat_first)}
        with mock.patch.dict(os.environ, {"AGENT_ENTRY_ALLOWED_INCIDENT_IDS": ""}):
            with mock.patch.object(worker, "_latest_revision") as latest:
                with mock.patch.object(worker, "_api_key") as api_key:
                    with self.assertRaisesRegex(worker.WorkerError, "ALLOWLIST_INVALID"):
                        worker._process_record(record)
        latest.assert_not_called()
        api_key.assert_not_called()

    def test_unlisted_incident_fails_before_state_and_secret(self):
        record = {"body": json.dumps(self.chat_first)}
        with mock.patch.dict(
            os.environ,
            {"AGENT_ENTRY_ALLOWED_INCIDENT_IDS": "inc_01ARZ3NDEKTSV4RRFFQ69G5FB0"},
        ):
            with mock.patch.object(worker, "_latest_revision") as latest:
                with mock.patch.object(worker, "_api_key") as api_key:
                    with self.assertRaisesRegex(worker.WorkerError, "INCIDENT_NOT_ALLOWED"):
                        worker._process_record(record)
        latest.assert_not_called()
        api_key.assert_not_called()

    def test_older_revision_is_superseded_without_secret_lock_or_dify(self):
        record = {"body": json.dumps(self.chat_first)}
        with mock.patch.object(worker, "_latest_revision", return_value=2):
            with mock.patch.object(worker, "_record_superseded", return_value=True) as supersede:
                with mock.patch.object(worker, "_api_key") as api_key:
                    with mock.patch.object(worker, "_acquire") as acquire:
                        with mock.patch.object(worker, "_call_dify") as dify:
                            result = worker._process_record(record)
        self.assertEqual(result["status"], "SUPERSEDED")
        supersede.assert_called_once()
        api_key.assert_not_called()
        acquire.assert_not_called()
        dify.assert_not_called()

    def test_successful_current_revision_finalizes_and_calls_dify_once(self):
        record = {"body": json.dumps(self.chat_first)}
        with mock.patch.object(worker, "_latest_revision", return_value=1):
            with mock.patch.object(worker, "_api_key", return_value="app-test"):
                with mock.patch.object(worker, "_acquire", return_value=True):
                    with mock.patch.object(worker, "_call_dify", return_value="run-1") as dify:
                        with mock.patch.object(worker, "_finalize") as finalize:
                            result = worker._process_record(record)
        self.assertEqual(result["status"], "SUCCEEDED")
        dify.assert_called_once()
        self.assertEqual(finalize.call_args.args[1], "SUCCEEDED")
        self.assertEqual(finalize.call_args.kwargs["workflow_run_id"], "run-1")

    def test_duplicate_succeeded_does_not_call_dify(self):
        record = {"body": json.dumps(self.chat_first)}
        with mock.patch.object(worker, "_latest_revision", return_value=1):
            with mock.patch.object(worker, "_api_key", return_value="app-test"):
                with mock.patch.object(worker, "_acquire", return_value=False):
                    with mock.patch.object(worker, "_call_dify") as dify:
                        result = worker._process_record(record)
        self.assertEqual(result["status"], "DUPLICATE")
        dify.assert_not_called()

    def test_dify_failure_marks_failed_and_releases_lock(self):
        record = {"body": json.dumps(self.chat_first)}
        with mock.patch.object(worker, "_latest_revision", return_value=1):
            with mock.patch.object(worker, "_api_key", return_value="app-test"):
                with mock.patch.object(worker, "_acquire", return_value=True):
                    with mock.patch.object(
                        worker, "_call_dify", side_effect=worker.WorkerError("DIFY_FAIL")
                    ):
                        with mock.patch.object(worker, "_finalize") as finalize:
                            with self.assertRaisesRegex(worker.WorkerError, "DIFY_FAIL"):
                                worker._process_record(record)
        self.assertEqual(finalize.call_args.args[1], "FAILED")
        self.assertEqual(finalize.call_args.kwargs["error_code"], "DIFY_FAIL")

    def test_incident_lock_blocks_parallel_revision(self):
        client = mock.Mock()
        client.transact_write_items.side_effect = ConditionalFailure()
        worker._clients["dynamodb"] = client
        with mock.patch.object(
            worker,
            "_ledger_item",
            side_effect=[{}, {"status": {"S": "LOCKED"}, "lease_expires_at": {"N": "200"}}],
        ):
            with self.assertRaisesRegex(worker.WorkerError, "INCIDENT_BUSY"):
                worker._acquire(self.chat_first, 100)

    def test_acquire_atomically_creates_revision_and_incident_lock(self):
        client = mock.Mock()
        worker._clients["dynamodb"] = client
        self.assertTrue(worker._acquire(self.chat_first, 100))
        items = client.transact_write_items.call_args.kwargs["TransactItems"]
        self.assertEqual(len(items), 2)
        self.assertEqual(
            items[0]["Put"]["Item"]["idempotency_key"]["S"],
            self.chat_first["idempotency_key"],
        )
        self.assertEqual(
            items[1]["Update"]["Key"]["idempotency_key"]["S"],
            f"incident:{self.chat_first['incident_id']}:lock",
        )

    def test_finalize_atomically_updates_revision_and_releases_owned_lock(self):
        client = mock.Mock()
        worker._clients["dynamodb"] = client
        worker._finalize(self.chat_first, "SUCCEEDED", 101, workflow_run_id="run-1")
        items = client.transact_write_items.call_args.kwargs["TransactItems"]
        self.assertEqual(len(items), 2)
        self.assertIn("Update", items[0])
        self.assertEqual(
            items[1]["Delete"]["ExpressionAttributeValues"][":owner"]["S"],
            self.chat_first["idempotency_key"],
        )

    def test_latest_revision_uses_consistent_authoritative_state_read(self):
        client = mock.Mock()
        client.get_item.return_value = {"Item": {"revision": {"N": "2"}}}
        worker._clients["dynamodb"] = client
        self.assertEqual(worker._latest_revision(self.chat_first), 2)
        request = client.get_item.call_args.kwargs
        self.assertTrue(request["ConsistentRead"])
        self.assertEqual(
            request["Key"]["pk"]["S"], f"INCIDENT#{self.chat_first['incident_id']}"
        )

    def test_stale_incident_lock_fails_closed(self):
        client = mock.Mock()
        client.transact_write_items.side_effect = ConditionalFailure()
        worker._clients["dynamodb"] = client
        with mock.patch.object(
            worker,
            "_ledger_item",
            side_effect=[{}, {"status": {"S": "LOCKED"}, "lease_expires_at": {"N": "99"}}],
        ):
            with self.assertRaisesRegex(worker.WorkerError, "INCIDENT_LOCK_STALE"):
                worker._acquire(self.chat_first, 100)

    def test_failed_execution_is_never_reacquired_automatically(self):
        client = mock.Mock()
        client.transact_write_items.side_effect = ConditionalFailure()
        worker._clients["dynamodb"] = client
        with mock.patch.object(worker, "_ledger_item", return_value={"status": {"S": "FAILED"}}):
            with self.assertRaisesRegex(worker.WorkerError, "IDEMPOTENCY_FAILED"):
                worker._acquire(self.chat_first, 100)

    def test_disabled_gate_returns_all_records_as_failures(self):
        event = {"Records": [{"messageId": "one", "body": "{}"}, {"messageId": "two", "body": "{}"}]}
        with mock.patch.dict(os.environ, {"AGENT_ENTRY_EXECUTION_ENABLED": "false"}):
            with mock.patch.object(worker, "_process_record") as process:
                result = worker.lambda_handler(event, None)
        process.assert_not_called()
        self.assertEqual(result, {"batchItemFailures": [{"itemIdentifier": "one"}, {"itemIdentifier": "two"}]})

    def test_enabled_gate_reports_only_failed_record(self):
        event = {"Records": [{"messageId": "ok", "body": "{}"}, {"messageId": "bad", "body": "{}"}]}

        def process(record):
            if record["messageId"] == "bad":
                raise worker.WorkerError("EXPECTED")
            return {"status": "SUCCEEDED", "incident": "hash", "revision": 1}

        with mock.patch.dict(os.environ, {"AGENT_ENTRY_EXECUTION_ENABLED": "true"}):
            with mock.patch.object(worker, "_process_record", side_effect=process):
                result = worker.lambda_handler(event, None)
        self.assertEqual(result, {"batchItemFailures": [{"itemIdentifier": "bad"}]})


if __name__ == "__main__":
    unittest.main()
