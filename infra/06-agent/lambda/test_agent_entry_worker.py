import importlib.util
import io
import json
import os
import pathlib
import re
import sys
import unittest
from unittest import mock

MODULE_PATH = pathlib.Path(__file__).with_name("agent_entry_worker.py")
sys.path.insert(0, str(MODULE_PATH.parent))
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
        # Metric enrichment is fail-open, but the worker must never construct
        # real boto clients in unit tests (GitHub runners do not provide a
        # default AWS region or credentials).
        worker._clients.update({"lambda": mock.Mock(), "ssm": mock.Mock()})
        worker._cached_api_key = None
        self.chat_first = load_example("agent-incident-chat-first-v1.example.json")
        self.correlated = load_example("agent-incident-correlated-v1.example.json")
        self.environment_mismatch = load_example(
            "agent-incident-environment-mismatch-v1.example.json"
        )
        self.environment_patch = mock.patch.dict(
            os.environ,
            {
                "AGENT_ENTRY_ALLOWED_INCIDENT_IDS": self.chat_first["incident_id"],
                "IDEMPOTENCY_TABLE": "execution-ledger",
                "INCIDENT_STATE_TABLE": "incident-state",
                "IDEMPOTENCY_TTL": "2592000",
                "DIFY_URL": "http://127.0.0.1/v1/workflows/run",
            },
            clear=False,
        )
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)

    def test_accepts_provisional_and_correlated_incident_examples(self):
        self.assertEqual(worker.validate_envelope(self.chat_first)["revision"], 1)
        self.assertEqual(worker.validate_envelope(self.correlated)["revision"], 2)
        self.assertEqual(
            worker.validate_envelope(self.environment_mismatch)["revision"], 1
        )

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

    def test_terraform_declares_least_privilege_history_access(self):
        terraform = (
            REPO_ROOT / "infra" / "06-agent" / "agent_entry_transport.tf"
        ).read_text()
        for action in {
            "bedrock:InvokeModel",
            "s3vectors:QueryVectors",
            "s3vectors:GetVectors",
            "s3vectors:PutVectors",
            "s3:PutObject",
        }:
            self.assertIn(f'"{action}"', terraform)
        self.assertIn("aws_s3vectors_index.incidents_o2.index_arn", terraform)
        self.assertIn('${aws_s3_bucket.history_o2.arn}/incidents/*', terraform)

    def test_terraform_allows_only_metric_lambdas_and_key_parameters(self):
        terraform = (
            REPO_ROOT / "infra" / "06-agent" / "agent_entry_transport.tf"
        ).read_text()
        self.assertIn('sid     = "InvokeMetricReadApis"', terraform)
        self.assertIn("function:o2-hot-api", terraform)
        self.assertIn("function:o2-warm-api", terraform)
        self.assertIn("parameter/o2/warm/api-key", terraform)
        self.assertIn("parameter/o2/api/read-path-degraded-admin-key", terraform)

    def test_contract_workflow_declares_and_consumes_past_cases(self):
        dsl = (
            REPO_ROOT / "infra" / "06-agent" / "dify"
            / "agent-entry-contract-test-v1.yml"
        ).read_text()
        self.assertGreaterEqual(dsl.count("variable: past_cases"), 2)
        self.assertIn("def main(custom_alert_json: str, past_cases: str", dsl)
        self.assertIn('"history_context_present": bool(past_cases)', dsl)

    def test_history_query_excludes_chat_identifiers_and_unverified_cause(self):
        rendered = worker._history_text(self.chat_first)
        chat = self.chat_first["signals"][0]["evidence"]
        self.assertIn("USER_PERCEIVED_LATENCY", rendered)
        self.assertIn(chat["matched_rule_ids"][0], rendered)
        self.assertNotIn(chat["candidate_id"], rendered)
        self.assertNotIn(chat["broadcast_id"], rendered)
        self.assertNotIn("UNDETERMINED", rendered)

    def test_history_lookup_filters_distance_and_returns_embedding_once(self):
        bedrock = mock.Mock()
        bedrock.invoke_model.return_value = {
            "body": io.BytesIO(json.dumps({"embedding": [0.1] * 1024}).encode())
        }
        vectors = mock.Mock()
        vectors.query_vectors.return_value = {"vectors": [
            {"distance": 0.10, "metadata": {"summary": "가까운 장애"}},
            {"distance": 0.90, "metadata": {"summary": "먼 장애"}},
        ]}
        worker._clients.update({"bedrock-runtime": bedrock, "s3vectors": vectors})
        history_env = {
            "HISTORY_BUCKET": "incident-history",
            "VECTOR_BUCKET": "incident-vectors",
            "VECTOR_INDEX": "incidents",
            "EMBED_MODEL_ID": "amazon.titan-embed-text-v2:0",
        }
        with mock.patch.dict(os.environ, history_env):
            embedding, past_cases = worker._history_lookup(self.chat_first)

        self.assertEqual(len(embedding), 1024)
        self.assertIn("가까운 장애", past_cases)
        self.assertNotIn("먼 장애", past_cases)
        bedrock.invoke_model.assert_called_once()

    def test_history_lookup_failure_is_fail_open(self):
        bedrock = mock.Mock()
        bedrock.invoke_model.side_effect = RuntimeError("unavailable")
        worker._clients["bedrock-runtime"] = bedrock
        history_env = {
            "HISTORY_BUCKET": "incident-history",
            "VECTOR_BUCKET": "incident-vectors",
            "VECTOR_INDEX": "incidents",
            "EMBED_MODEL_ID": "amazon.titan-embed-text-v2:0",
        }
        with mock.patch.dict(os.environ, history_env):
            self.assertEqual(worker._history_lookup(self.chat_first), (None, ""))

    def test_dify_request_declares_and_confirms_history_input(self):
        output = {
            "accepted": True,
            "status": "ACCEPTED",
            "event_type": "agent.incident.v1",
            "incident_id": self.chat_first["incident_id"],
            "revision": self.chat_first["revision"],
            "idempotency_key": self.chat_first["idempotency_key"],
            "history_context_present": True,
        }
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "data": {
                "status": "succeeded", "id": "run-1",
                "outputs": {"result": json.dumps(output)},
            }
        }).encode()
        rendered = worker._serialize_payload(self.chat_first)
        with mock.patch.object(worker, "_api_key", return_value="app-test"):
            with mock.patch.object(worker.urllib.request, "urlopen", return_value=response) as call:
                self.assertEqual(worker._call_dify(self.chat_first, rendered, "- case"), "run-1")
        request_body = json.loads(call.call_args.args[0].data)
        self.assertEqual(request_body["inputs"]["past_cases"], "- case")

    def test_history_store_uses_incident_id_and_never_stores_hypothesis(self):
        s3 = mock.Mock()
        vectors = mock.Mock()
        worker._clients.update({"s3": s3, "s3vectors": vectors})
        embedding = [0.1] * 1024

        history_env = {
            "HISTORY_BUCKET": "incident-history",
            "VECTOR_BUCKET": "incident-vectors",
            "VECTOR_INDEX": "incidents",
        }
        with mock.patch.dict(os.environ, history_env):
            worker._history_store(self.chat_first, embedding, "run-1", "- case")

        stored = json.loads(s3.put_object.call_args.kwargs["Body"])
        self.assertEqual(stored["incident_id"], self.chat_first["incident_id"])
        self.assertIsNone(stored["agent"]["hypothesis"])
        self.assertNotIn("root_cause_label", vectors.put_vectors.call_args.kwargs["vectors"][0]["metadata"])
        self.assertEqual(
            vectors.put_vectors.call_args.kwargs["vectors"][0]["key"],
            self.chat_first["incident_id"],
        )

    def test_rejects_revision_idempotency_mismatch(self):
        self.chat_first["revision"] = 2
        with self.assertRaisesRegex(worker.ContractError, "IDEMPOTENCY_KEY"):
            worker.validate_envelope(self.chat_first)

    def test_rejects_raw_chat_nested_in_signal(self):
        self.chat_first["signals"][0]["evidence"]["raw_chat"] = "synthetic"
        with self.assertRaisesRegex(worker.ContractError, "TRIGGER_EVIDENCE_FIELDS"):
            worker.validate_envelope(self.chat_first)

    def test_rejects_assessment_that_references_missing_signal(self):
        self.correlated["signals"] = [self.correlated["signals"][0]]
        with self.assertRaisesRegex(worker.ContractError, "EVIDENCE_ASSESSMENT_UNKNOWN_SIGNAL"):
            worker.validate_envelope(self.correlated)

    def test_rejects_unknown_incident_family(self):
        self.correlated["normalized_context"]["incident_family"] = "MADE_UP_FAMILY"
        with self.assertRaisesRegex(worker.ContractError, "CONTEXT_INCIDENT_FAMILY"):
            worker.validate_envelope(self.correlated)

    def test_rejects_signal_assigned_to_multiple_evidence_roles(self):
        self.correlated["evidence_assessment"]["context"] = [
            self.correlated["evidence_assessment"]["primary"][0]
        ]
        with self.assertRaisesRegex(worker.ContractError, "EVIDENCE_ASSESSMENT_ROLE_OVERLAP"):
            worker.validate_envelope(self.correlated)

    def test_rejects_verified_assessment_with_missing_required_role(self):
        self.correlated["evidence_assessment"]["missing_required_roles"] = [
            "CORROBORATING"
        ]
        with self.assertRaisesRegex(worker.ContractError, "VERIFIED_INVARIANT"):
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

    def test_operational_mode_accepts_any_valid_incident_with_empty_allowlist(self):
        with mock.patch.dict(
            os.environ,
            {
                "AGENT_ENTRY_OPERATIONAL_MODE": "true",
                "AGENT_ENTRY_ALLOWED_INCIDENT_IDS": "",
            },
        ):
            self.assertTrue(worker._incident_allowed(self.chat_first["incident_id"]))

    def test_operational_mode_rejects_nonempty_synthetic_allowlist(self):
        with mock.patch.dict(os.environ, {"AGENT_ENTRY_OPERATIONAL_MODE": "true"}):
            with self.assertRaisesRegex(worker.WorkerError, "ALLOWLIST_NOT_EMPTY"):
                worker._incident_allowed(self.chat_first["incident_id"])

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
                    with mock.patch.object(worker, "_history_lookup", return_value=([0.1], "- case")):
                        with mock.patch.object(worker, "_call_dify", return_value="run-1") as dify:
                            with mock.patch.object(worker, "_finalize") as finalize:
                                with mock.patch.object(worker, "_history_store") as store:
                                    result = worker._process_record(record)
        self.assertEqual(result["status"], "SUCCEEDED")
        dify.assert_called_once()
        self.assertEqual(dify.call_args.args[2], "- case")
        store.assert_called_once_with(self.chat_first, [0.1], "run-1", "- case")
        self.assertEqual(finalize.call_args.args[1], "SUCCEEDED")
        self.assertEqual(finalize.call_args.kwargs["workflow_run_id"], "run-1")

    def test_history_store_failure_does_not_fail_succeeded_execution(self):
        record = {"body": json.dumps(self.chat_first)}
        with mock.patch.object(worker, "_latest_revision", return_value=1):
            with mock.patch.object(worker, "_api_key", return_value="app-test"):
                with mock.patch.object(worker, "_acquire", return_value=True):
                    with mock.patch.object(worker, "_history_lookup", return_value=([0.1], "")):
                        with mock.patch.object(worker, "_call_dify", return_value="run-1"):
                            with mock.patch.object(worker, "_finalize") as finalize:
                                with mock.patch.object(
                                    worker, "_history_store", side_effect=RuntimeError("s3 down")
                                ):
                                    result = worker._process_record(record)
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(finalize.call_count, 1)
        self.assertEqual(finalize.call_args.args[1], "SUCCEEDED")

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
