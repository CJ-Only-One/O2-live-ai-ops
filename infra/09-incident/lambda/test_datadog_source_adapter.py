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
        "assessment_input": evidence["assessment_input"],
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
            "DATADOG_SOURCE_ADAPTER_ALLOWED_MONITOR_IDS": "monitor_example",
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

    def test_composite_condition_accepts_empty_measurements(self):
        assessment = source_payload()["assessment_input"]
        assessment.update(
            {"evidence_type": "COMPOSITE_CONDITION", "sample_count": 1, "measurements": {}}
        )
        result = self.invoke(function_event(source_payload(assessment_input=assessment)))
        self.assertEqual(result["statusCode"], 200)
        envelope = json.loads(self.sqs.messages[0]["MessageBody"])
        self.assertEqual(
            envelope["evidence"]["assessment_input"]["evidence_type"],
            "COMPOSITE_CONDITION",
        )

    def test_posix_timestamp_is_normalized_to_rfc3339(self):
        result = self.invoke(function_event(source_payload(occurred_at="1787443216")))

        self.assertEqual(result["statusCode"], 200)
        envelope = json.loads(self.sqs.messages[0]["MessageBody"])
        self.assertEqual(envelope["occurred_at"], "2026-08-23T00:00:16.000Z")

    def test_posix_assessment_observed_at_is_normalized_to_rfc3339(self):
        # 2026-08-26 real test로 재현: 웹훅 payload 템플릿이 assessment_input.
        # observed_at에 $DATE_POSIX(epoch 문자열)를 채우는데, 검증만 하고
        # 정규화된 값으로 안 바꾸면 원본이 그대로 Correlator까지 가서
        # CONTRACT_REJECTED:ASSESSMENT_OBSERVED_AT로 매번 죽는다.
        assessment = source_payload()["assessment_input"]
        assessment["observed_at"] = "1787443216"
        result = self.invoke(function_event(source_payload(assessment_input=assessment)))

        self.assertEqual(result["statusCode"], 200)
        envelope = json.loads(self.sqs.messages[0]["MessageBody"])
        self.assertEqual(
            envelope["evidence"]["assessment_input"]["observed_at"],
            "2026-08-23T00:00:16.000Z",
        )

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
            DATADOG_SOURCE_ADAPTER_ALLOWED_MONITOR_IDS="",
            DATADOG_SOURCE_ADAPTER_NOT_BEFORE_EPOCH="4102444800",
        )

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"], "disabled")
        self.assertEqual(self.sqs.messages, [])

    def test_new_cycle_on_allowed_monitor_is_forwarded_without_payload_rewrite(self):
        result = self.invoke(
            function_event(source_payload(cycle_key="datadog_generated_cycle_002"))
        )

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"], "queued")
        envelope = json.loads(self.sqs.messages[0]["MessageBody"])
        self.assertEqual(envelope["evidence"]["cycle_key"], "datadog_generated_cycle_002")
        self.assertEqual(
            envelope["idempotency_key"],
            "datadog:datadog_generated_cycle_002:Triggered",
        )

    def test_unlisted_monitor_is_ignored_without_queue_write(self):
        result = self.invoke(
            function_event(source_payload(monitor_id="monitor_not_allowed"))
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

    def test_s1_propagation_requires_broadcast_scope(self):
        payload = source_payload()
        payload["assessment_input"]["evidence_type"] = "CHAT_PROPAGATION_P95"
        payload["assessment_input"]["measurements"] = {"p95_ms": 800}
        result = self.invoke(function_event(payload))
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(result["body"], "CONTRACT_REJECTED:ASSESSMENT_S1_SCOPE")

    def test_s2_cpu_accepts_explicit_pod_and_version_scope(self):
        payload = source_payload()
        payload["assessment_input"].update({
            "evidence_type": "POD_CPU_UTILIZATION",
            "scope": {"environment":"dev", "service":"api", "pod":"api-canary-1", "version":"sha-123", "broadcast_id":None},
            "measurements": {"cpu_utilization_ratio": 0.9},
        })
        result = self.invoke(function_event(payload))
        self.assertEqual(result["statusCode"], 200)
        envelope = json.loads(self.sqs.messages[0]["MessageBody"])
        self.assertEqual(envelope["evidence"]["assessment_input"]["scope"]["pod"], "api-canary-1")

    def test_empty_allowlist_fails_closed(self):
        result = self.invoke(DATADOG_SOURCE_ADAPTER_ALLOWED_MONITOR_IDS="")

        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(result["body"], "SYNTHETIC_MONITOR_ALLOWLIST_INVALID")
        self.assertEqual(self.sqs.messages, [])

    def test_multiple_monitor_allowlist_fails_closed(self):
        result = self.invoke(
            DATADOG_SOURCE_ADAPTER_ALLOWED_MONITOR_IDS="monitor_example,other_monitor"
        )

        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(result["body"], "SYNTHETIC_MONITOR_ALLOWLIST_INVALID")
        self.assertEqual(self.sqs.messages, [])

    def test_queue_failure_returns_retryable_500(self):
        adapter._clients["sqs"] = FakeSqs(fail=True)
        result = self.invoke()

        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(result["body"], "AGENT_TRIGGER_SEND_FAILED")


if __name__ == "__main__":
    unittest.main()
