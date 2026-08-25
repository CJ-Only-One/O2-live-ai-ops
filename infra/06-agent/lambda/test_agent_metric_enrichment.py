import importlib.util
import io
import json
import os
import pathlib
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).with_name("agent_metric_enrichment.py")
SPEC = importlib.util.spec_from_file_location("agent_metric_enrichment", MODULE_PATH)
metrics = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(metrics)


def response(body):
    return {"Payload": io.BytesIO(json.dumps({"statusCode": 200, "body": json.dumps(body)}).encode())}


class AgentMetricEnrichmentTest(unittest.TestCase):
    def payload(self, family):
        return {
            "normalized_context": {
                "incident_family": family,
                "environment": "dev",
                "broadcast_ids": ["bc_1042"],
            },
            "signals": [{
                "source": "DATADOG_MONITOR",
                "evidence": {"assessment_input": {"measurements": {"existing": 1}}},
            }],
        }

    def test_chat_family_reads_catalog_metrics_and_keeps_input_immutable(self):
        client = mock.Mock()
        client.invoke.side_effect = [
            response({"status": "OK", "value": 355}),
            response({"status": "OK", "value": 0.05}),
        ]
        original = self.payload("CHAT_DEGRADATION")
        with mock.patch.dict(os.environ, {"HOT_API_FUNCTION": "o2-hot-api"}):
            enriched, errors = metrics.enrich(original, client, mock.Mock())
        self.assertEqual(errors, [])
        self.assertEqual(
            enriched["signals"][0]["evidence"]["assessment_input"]["measurements"],
            {"existing": 1, "chat_propagation_p95_ms": 355.0, "channel_block_rate": 0.05},
        )
        self.assertEqual(
            original["signals"][0]["evidence"]["assessment_input"]["measurements"],
            {"existing": 1},
        )

    def test_read_path_family_combines_warm_and_authoritative_state(self):
        client = mock.Mock()
        client.invoke.return_value = response({"latest": {
            "p95_ms": 210,
            "inventory_check_rate": 0.95,
            "overall_failure_rate": 0.01,
            "baseline_p95_ms": 180,
        }})
        ssm = mock.Mock()
        ssm.get_parameter.side_effect = [
            {"Parameter": {"Value": "warm-key"}},
            {"Parameter": {"Value": "admin-key"}},
        ]
        opener = mock.Mock(return_value=mock.MagicMock(
            __enter__=lambda value: io.BytesIO(json.dumps({
                "read_path_degraded_active": True,
            }).encode()),
            __exit__=lambda *args: None,
        ))
        env = {
            "WARM_API_FUNCTION": "o2-warm-api",
            "WARM_API_KEY_PARAM": "/o2/warm/api-key",
            "READ_PATH_ADMIN_KEY_PARAM": "/o2/api/read-path-degraded-admin-key",
            "READ_PATH_STATUS_URL": "https://example/api/admin/read-path-degraded",
        }
        with mock.patch.dict(os.environ, env):
            enriched, errors = metrics.enrich(
                self.payload("READ_PATH_DEGRADATION"), client, ssm, opener
            )
        self.assertEqual(errors, [])
        observed = enriched["signals"][0]["evidence"]["assessment_input"]["measurements"]
        self.assertEqual(observed["p95_ms"], 210.0)
        self.assertEqual(observed["inventory_check_rate"], 0.95)
        self.assertEqual(observed["read_path_degraded_active"], 1.0)

    def test_collection_failure_is_missing_not_zero(self):
        client = mock.Mock()
        client.invoke.side_effect = RuntimeError("unavailable")
        with mock.patch.dict(os.environ, {"HOT_API_FUNCTION": "o2-hot-api"}):
            enriched, errors = metrics.enrich(
                self.payload("CHAT_DEGRADATION"), client, mock.Mock()
            )
        self.assertEqual(errors, ["hot"])
        self.assertNotIn(
            "chat_propagation_p95_ms",
            enriched["signals"][0]["evidence"]["assessment_input"]["measurements"],
        )


if __name__ == "__main__":
    unittest.main()
