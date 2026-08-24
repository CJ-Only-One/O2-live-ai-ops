from app.core.telemetry import packet


def test_packet_allows_only_contract_metrics_and_low_cardinality_tags():
    assert packet(
        "o2.app.business_event",
        1,
        {"service": "api", "event": "coupon.issue", "result": "success", "env": "dev"},
    ) == b"o2.app.business_event:1|c|#service:api,event:coupon.issue,result:success,env:dev"
    assert packet("o2.app.business_event", 1, {"user_id": "u_123"}) is None
    assert packet("o2.app.unknown", 1, {"service": "api"}) is None
    assert packet("o2.app.failure", 1, {"failure_code": "free text"}) is None


def test_duration_is_distribution():
    assert packet(
        "o2.app.operation.duration",
        12.5,
        {"service": "api", "operation": "inventory.read", "pod_name": "api-abc-123"},
    ) == b"o2.app.operation.duration:12.5|d|#service:api,operation:inventory.read,pod_name:api-abc-123"


def test_retry_and_fallback_metric_contract():
    assert packet(
        "o2.app.retry", 1, {"operation": "order.create", "reason": "IDEMPOTENT_REPLAY"}
    ) == b"o2.app.retry:1|c|#operation:order.create,reason:IDEMPOTENT_REPLAY"
    assert packet(
        "o2.app.fallback", 1, {"operation": "broadcast.meta"}
    ) == b"o2.app.fallback:1|c|#operation:broadcast.meta"
    assert packet(
        "o2.app.db.pool.active", 3, {"operation": "writer"}
    ) == b"o2.app.db.pool.active:3|g|#operation:writer"
