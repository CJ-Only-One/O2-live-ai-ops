import unittest

from worker.telemetry import packet


class TelemetryPacketTest(unittest.TestCase):
    def test_allowlist_rejects_identifiers_and_unknown_metrics(self):
        self.assertEqual(
            packet("o2.app.business_event", 1, {"event": "order.confirm", "result": "success"}),
            b"o2.app.business_event:1|c|#event:order.confirm,result:success",
        )
        self.assertIsNone(packet("o2.app.business_event", 1, {"order_id": "od_123"}))
        self.assertIsNone(packet("o2.app.unknown", 1, {"service": "order-worker"}))

    def test_duration_is_distribution(self):
        self.assertEqual(
            packet("o2.app.operation.duration", 5, {"operation": "order.confirm"}),
            b"o2.app.operation.duration:5|d|#operation:order.confirm",
        )

    def test_retry_and_batch_metrics_are_allowlisted(self):
        self.assertEqual(
            packet("o2.app.retry", 1, {"operation": "order.confirm", "reason": "DB_OPERATIONAL_ERROR"}),
            b"o2.app.retry:1|c|#operation:order.confirm,reason:DB_OPERATIONAL_ERROR",
        )
        self.assertEqual(
            packet("o2.app.batch.size", 3, {"operation": "order.confirm"}),
            b"o2.app.batch.size:3|d|#operation:order.confirm",
        )


if __name__ == "__main__":
    unittest.main()
