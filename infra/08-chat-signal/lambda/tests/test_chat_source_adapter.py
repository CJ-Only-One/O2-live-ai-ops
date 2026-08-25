import importlib.util
import json
import os
import pathlib
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).parents[1] / "adapter" / "chat_source_adapter.py"
SPEC = importlib.util.spec_from_file_location("chat_source_adapter", MODULE_PATH)
adapter = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(adapter)

REPO_ROOT = pathlib.Path(__file__).parents[4]
EXAMPLE_PATH = REPO_ROOT / "docs" / "contracts" / "examples" / "agent-trigger-chat-v1.example.json"


def _attribute(value):
    if value is None:
        return {"NULL": True}
    if isinstance(value, bool):
        return {"BOOL": value}
    if isinstance(value, str):
        return {"S": value}
    if isinstance(value, int):
        return {"N": str(value)}
    if isinstance(value, list):
        return {"L": [_attribute(item) for item in value]}
    if isinstance(value, dict):
        return {"M": {name: _attribute(item) for name, item in value.items()}}
    raise TypeError(type(value))


def load_candidate():
    envelope = json.loads(EXAMPLE_PATH.read_text())
    return {
        "schema_version": "1.0",
        **envelope["evidence"],
        "raw_chat_included": False,
        "agent_handoff_status": "NOT_CONFIGURED",
        "created_at": envelope["occurred_at"],
    }


def stream_record(*, sequence="1001", event_name="INSERT", candidate=None, pk=None):
    candidate = candidate or load_candidate()
    item = {
        "pk": pk or f"CANDIDATE#{candidate['candidate_id']}",
        "sk": "META",
        "payload": candidate,
        "version": 1,
    }
    return {
        "eventID": f"event-{sequence}",
        "eventName": event_name,
        "eventSource": "aws:dynamodb",
        "dynamodb": {
            "SequenceNumber": sequence,
            "NewImage": {name: _attribute(value) for name, value in item.items()},
        },
    }


class FakeSqs:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.messages = []

    def send_message(self, **request):
        if self.fail:
            raise RuntimeError("synthetic send failure")
        self.messages.append(request)
        return {"MessageId": "synthetic-message"}


class ChatSourceAdapterTest(unittest.TestCase):
    def setUp(self):
        adapter._clients.clear()
        self.environment = {
            "CHAT_SOURCE_ADAPTER_ENABLED": "true",
            "CHAT_SOURCE_ADAPTER_NOT_BEFORE_EPOCH": "0",
            "CHAT_SOURCE_ADAPTER_ALLOWED_BROADCAST_IDS": "bc_1042",
            "AGENT_TRIGGER_QUEUE_URL": "https://example.invalid/agent-trigger",
        }

    def test_insert_creates_exact_common_envelope_without_candidate_private_fields(self):
        client = FakeSqs()
        adapter._clients["sqs"] = client

        with mock.patch.dict(os.environ, self.environment, clear=False):
            result = adapter.handler({"Records": [stream_record()]}, None)

        self.assertEqual(result, {"batchItemFailures": []})
        self.assertEqual(len(client.messages), 1)
        envelope = json.loads(client.messages[0]["MessageBody"])
        expected = json.loads(EXAMPLE_PATH.read_text())
        expected["trigger_id"] = expected["evidence"]["candidate_id"].replace(
            "cand_", "trg_", 1
        )
        self.assertEqual(envelope, expected)
        rendered = client.messages[0]["MessageBody"]
        self.assertNotIn('"raw_chat":', rendered)
        self.assertNotIn("user_key", rendered)
        self.assertNotIn("agent_handoff_status", rendered)

    def test_repeated_insert_builds_same_trigger_and_idempotency_key(self):
        candidate = load_candidate()
        first = adapter.build_envelope(adapter.validate_candidate(candidate))
        second = adapter.build_envelope(adapter.validate_candidate(candidate))

        self.assertEqual(first, second)
        self.assertEqual(first["idempotency_key"], f"chat:{candidate['candidate_id']}")

    def test_modify_is_ignored_without_queue_write(self):
        client = FakeSqs()
        adapter._clients["sqs"] = client
        with mock.patch.dict(os.environ, self.environment, clear=False):
            result = adapter.handler(
                {"Records": [stream_record(event_name="MODIFY")]}, None
            )

        self.assertEqual(result, {"batchItemFailures": []})
        self.assertEqual(client.messages, [])

    def test_non_candidate_insert_is_ignored_without_queue_write(self):
        client = FakeSqs()
        adapter._clients["sqs"] = client
        with mock.patch.dict(os.environ, self.environment, clear=False):
            result = adapter.handler(
                {"Records": [stream_record(pk="WINDOW#bc_1042#latency#0")]}, None
            )

        self.assertEqual(result, {"batchItemFailures": []})
        self.assertEqual(client.messages, [])

    def test_candidate_before_activation_cutoff_is_ignored(self):
        client = FakeSqs()
        adapter._clients["sqs"] = client
        with mock.patch.dict(
            os.environ,
            {**self.environment, "CHAT_SOURCE_ADAPTER_NOT_BEFORE_EPOCH": "4102444800"},
            clear=False,
        ):
            result = adapter.handler({"Records": [stream_record()]}, None)

        self.assertEqual(result, {"batchItemFailures": []})
        self.assertEqual(client.messages, [])

    def test_unlisted_broadcast_is_ignored_without_queue_write(self):
        candidate = load_candidate()
        candidate["broadcast_id"] = "bc_9999"
        client = FakeSqs()
        adapter._clients["sqs"] = client

        with mock.patch.dict(os.environ, self.environment, clear=False):
            result = adapter.handler(
                {"Records": [stream_record(candidate=candidate)]}, None
            )

        self.assertEqual(result, {"batchItemFailures": []})
        self.assertEqual(client.messages, [])

    def test_empty_broadcast_allowlist_fails_closed_without_queue_write(self):
        client = FakeSqs()
        adapter._clients["sqs"] = client

        with mock.patch.dict(
            os.environ,
            {**self.environment, "CHAT_SOURCE_ADAPTER_ALLOWED_BROADCAST_IDS": ""},
            clear=False,
        ):
            result = adapter.handler(
                {"Records": [stream_record(sequence="allowlist-empty")]}, None
            )

        self.assertEqual(
            result,
            {"batchItemFailures": [{"itemIdentifier": "allowlist-empty"}]},
        )
        self.assertEqual(client.messages, [])

    def test_operational_mode_accepts_candidate_with_empty_allowlist(self):
        client = FakeSqs()
        adapter._clients["sqs"] = client
        with mock.patch.dict(
            os.environ,
            {
                **self.environment,
                "CHAT_SOURCE_ADAPTER_OPERATIONAL_MODE": "true",
                "CHAT_SOURCE_ADAPTER_ALLOWED_BROADCAST_IDS": "",
            },
            clear=False,
        ):
            result = adapter.handler({"Records": [stream_record()]}, None)
        self.assertEqual(result, {"batchItemFailures": []})
        self.assertEqual(len(client.messages), 1)

    def test_operational_mode_rejects_nonempty_synthetic_allowlist(self):
        client = FakeSqs()
        adapter._clients["sqs"] = client
        with mock.patch.dict(
            os.environ,
            {**self.environment, "CHAT_SOURCE_ADAPTER_OPERATIONAL_MODE": "true"},
            clear=False,
        ):
            result = adapter.handler(
                {"Records": [stream_record(sequence="operational-nonempty")]}, None
            )
        self.assertEqual(
            result,
            {"batchItemFailures": [{"itemIdentifier": "operational-nonempty"}]},
        )
        self.assertEqual(client.messages, [])

    def test_multiple_broadcast_allowlist_fails_closed_without_queue_write(self):
        client = FakeSqs()
        adapter._clients["sqs"] = client

        with mock.patch.dict(
            os.environ,
            {
                **self.environment,
                "CHAT_SOURCE_ADAPTER_ALLOWED_BROADCAST_IDS": "bc_1042,bc_9999",
            },
            clear=False,
        ):
            result = adapter.handler(
                {"Records": [stream_record(sequence="allowlist-multiple")]}, None
            )

        self.assertEqual(
            result,
            {"batchItemFailures": [{"itemIdentifier": "allowlist-multiple"}]},
        )
        self.assertEqual(client.messages, [])

    def test_candidate_with_user_key_is_rejected_and_retried(self):
        candidate = load_candidate()
        candidate["user_key"] = "forbidden"
        client = FakeSqs()
        adapter._clients["sqs"] = client

        with mock.patch.dict(os.environ, self.environment, clear=False):
            result = adapter.handler(
                {"Records": [stream_record(sequence="private", candidate=candidate)]},
                None,
            )

        self.assertEqual(
            result, {"batchItemFailures": [{"itemIdentifier": "private"}]}
        )
        self.assertEqual(client.messages, [])

    def test_disabled_gate_fails_every_record_without_queue_write(self):
        client = FakeSqs()
        adapter._clients["sqs"] = client
        with mock.patch.dict(
            os.environ, {**self.environment, "CHAT_SOURCE_ADAPTER_ENABLED": "false"}, clear=False
        ):
            result = adapter.handler(
                {"Records": [stream_record(sequence="one"), stream_record(sequence="two")]},
                None,
            )

        self.assertEqual(
            result,
            {
                "batchItemFailures": [
                    {"itemIdentifier": "one"},
                    {"itemIdentifier": "two"},
                ]
            },
        )
        self.assertEqual(client.messages, [])

    def test_queue_failure_reports_only_failed_sequence(self):
        adapter._clients["sqs"] = FakeSqs(fail=True)
        with mock.patch.dict(os.environ, self.environment, clear=False):
            result = adapter.handler(
                {"Records": [stream_record(sequence="send-failed")]}, None
            )

        self.assertEqual(
            result,
            {"batchItemFailures": [{"itemIdentifier": "send-failed"}]},
        )


if __name__ == "__main__":
    unittest.main()
