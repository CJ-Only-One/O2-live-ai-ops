import base64
import importlib.util
import json
import os
import pathlib
import unittest
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).with_name("datadog_source_adapter.py")
SPEC = importlib.util.spec_from_file_location("datadog_source_adapter", MODULE_PATH)
adapter = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(adapter)

REPO_ROOT = pathlib.Path(__file__).parents[3]
EXAMPLE_PATH = (
    REPO_ROOT / "docs" / "contracts" / "examples" / "agent-trigger-datadog-v1.example.json"
)


def source_payload(**changes):
    example = json.loads(EXAMPLE_PATH.read_text())
    evidence = example["evidence"]
    payload = {
        "schema_version": "1",
        "event_id": evidence["event_id"],
        "cycle_key": evidence["cycle_key"],
        "monitor_id": evidence["monitor_id"],
        "occurred_at": example["occurred_at"],
        "alert_transition": evidence["transition"],
        "priority": evidence["priority"],
        "env": evidence["env"],
        "service": evidence["service"],
        "alert_title": evidence["alert_title"],
        "alert_body": evidence["alert_body"],
        "alert_query": evidence["alert_query"],
        "host": evidence["host"],
        "tags": evidence["tags"],
        "link": evidence["link"],
    }
    payload.update(changes)
    return payload


def function_event(payload=None, *, secret="synthetic-secret", encoded=False):
    body = json.dumps(payload or source_payload())
    if encoded:
        body = base64.b64encode(body.encode()).decode()
    return {
        "headers": {"X-DD-Secret": secret},
        "body": body,
        "isBase64Encoded": encoded,
    }


class FakeSecretsManager:
    def get_secret_value(self, **request):
        if request["SecretId"] != "synthetic-secret-name":
            raise RuntimeError("unexpected secret")
        return {"SecretString": json.dumps({"webhook-secret": "synthetic-secret"})}


class FakeSqs:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.messages = []

    def send_message(self, **request):
        if self.fail:
            raise RuntimeError("synthetic send failure")
        self.messages.append(request)
        return {"MessageId": "synthetic-message"}


class DatadogSourceAdapterTest(unittest.TestCase):
    def setUp(self):
        adapter._clients.clear()
        adapter._secrets = None
        self.sqs = FakeSqs()
        adapter._clients.update(
            {"secretsmanager": FakeSecretsManager(), "sqs": self.sqs}
        )
        self.environment = {
            "DATADOG_SOURCE_ADAPTER_EXECUTION_ENABLED": "true",
            "DATADOG_SOURCE_ADAPTER_ALLOWED_CYCLE_KEYS": "cycle_example_001",
            "DATADOG_SOURCE_ADAPTER_NOT_BEFORE_EPOCH": "0",
            "DATADOG_SOURCE_ADAPTER_SECRET_NAME": "synthetic-secret-name",
            "AGENT_TRIGGER_QUEUE_URL": "https://example.invalid/agent-trigger",
        }
        self.context = SimpleNamespace(aws_request_id="request-example")

    def invoke(self, event=None, **environment):
        with mock.patch.dict(
            os.environ, {**self.environment, **environment}, clear=False
        ):
            return adapter.lambda_handler(
                event if event is not None else function_event(), self.context
            )

    def test_valid_payload_creates_exact_common_envelope(self):
        result = self.invoke()

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"], "queued")
        self.assertEqual(len(self.sqs.messages), 1)
        envelope = json.loads(self.sqs.messages[0]["MessageBody"])
        expected = json.loads(EXAMPLE_PATH.read_text())
        expected["trigger_id"] = envelope["trigger_id"]
        self.assertEqual(envelope, expected)
        self.assertRegex(envelope["trigger_id"], r"^trg_[0-9A-HJKMNP-TV-Z]{26}$")
        self.assertEqual(
            self.sqs.messages[0]["MessageAttributes"]["source"]["StringValue"],
            "DATADOG_MONITOR",
        )

    def test_posix_timestamp_is_normalized_to_rfc3339(self):
        result = self.invoke(function_event(source_payload(occurred_at="1787443216")))

        self.assertEqual(result["statusCode"], 200)
        envelope = json.loads(self.sqs.messages[0]["MessageBody"])
        self.assertEqual(envelope["occurred_at"], "2026-08-23T00:00:16.000Z")

    def test_duplicate_payload_builds_same_trigger_and_idempotency_keys(self):
        payload, _ = adapter.validate_source(source_payload())
        first = adapter.build_envelope(payload)
        second = adapter.build_envelope(payload)

        self.assertEqual(first["trigger_id"], second["trigger_id"])
        self.assertEqual(
            first["idempotency_key"], "datadog:cycle_example_001:Triggered"
        )

    def test_recovered_is_forwarded_for_incident_lifecycle(self):
        result = self.invoke(
            function_event(source_payload(alert_transition="Recovered"))
        )

        self.assertEqual(result["statusCode"], 200)
        envelope = json.loads(self.sqs.messages[0]["MessageBody"])
        self.assertEqual(envelope["evidence"]["transition"], "Recovered")
        self.assertTrue(envelope["idempotency_key"].endswith(":Recovered"))

    def test_base64_function_url_body_is_supported(self):
        result = self.invoke(function_event(encoded=True))

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(len(self.sqs.messages), 1)

    def test_bad_secret_is_rejected_without_queue_write(self):
        result = self.invoke(function_event(secret="wrong"))

        self.assertEqual(result["statusCode"], 403)
        self.assertEqual(result["body"], "AUTH_REJECTED")
        self.assertEqual(self.sqs.messages, [])

    def test_disabled_gate_accepts_webhook_without_queue_write(self):
        result = self.invoke(
            DATADOG_SOURCE_ADAPTER_EXECUTION_ENABLED="false",
            DATADOG_SOURCE_ADAPTER_ALLOWED_CYCLE_KEYS="",
            DATADOG_SOURCE_ADAPTER_NOT_BEFORE_EPOCH="4102444800",
        )

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"], "disabled")
        self.assertEqual(self.sqs.messages, [])

    def test_unlisted_cycle_is_ignored_without_queue_write(self):
        result = self.invoke(
            function_event(source_payload(cycle_key="cycle_not_allowed"))
        )

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"], "ignored")
        self.assertEqual(self.sqs.messages, [])

    def test_event_before_cutover_is_ignored_without_queue_write(self):
        result = self.invoke(DATADOG_SOURCE_ADAPTER_NOT_BEFORE_EPOCH="4102444800")

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"], "ignored")
        self.assertEqual(self.sqs.messages, [])

    def test_extra_source_field_is_contract_rejected(self):
        payload = source_payload(raw_chat="forbidden")
        result = self.invoke(function_event(payload))

        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(result["body"], "CONTRACT_REJECTED:SOURCE_FIELDS")
        self.assertEqual(self.sqs.messages, [])

    def test_invalid_transition_is_contract_rejected(self):
        result = self.invoke(
            function_event(source_payload(alert_transition="Unknown"))
        )

        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(result["body"], "CONTRACT_REJECTED:ALERT_TRANSITION")
        self.assertEqual(self.sqs.messages, [])

    def test_empty_allowlist_fails_closed(self):
        result = self.invoke(DATADOG_SOURCE_ADAPTER_ALLOWED_CYCLE_KEYS="")

        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(result["body"], "SYNTHETIC_CYCLE_ALLOWLIST_INVALID")
        self.assertEqual(self.sqs.messages, [])

    def test_queue_failure_returns_retryable_500(self):
        adapter._clients["sqs"] = FakeSqs(fail=True)
        result = self.invoke()

        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(result["body"], "AGENT_TRIGGER_SEND_FAILED")


if __name__ == "__main__":
    unittest.main()
