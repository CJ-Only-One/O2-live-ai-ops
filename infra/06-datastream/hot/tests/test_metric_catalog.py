from o2hot.metric_catalog import MetricRequestError, read_metric


def result(value, timestamp_ms=1787558400000):
    return {"series": [] if value is None else [{"pointlist": [[timestamp_ms, value]]}]}


def test_primary_is_selected_with_fresh_data_and_samples():
    seen = []

    def query(query_text, _from, _to):
        seen.append(query_text)
        if "hits{" in query_text and "as_count" in query_text:
            return result(12)
        if "o2.warm" in query_text:
            return result(190)
        return result(0.1842)

    got = read_metric(
        {"metric": "latency_p95", "service": "api", "window_seconds": 300},
        query_fn=query,
        now=1787558408,
    )
    assert got["value"] == 184.2
    assert got["source"] == "datadog_apm"
    assert got["fallback_used"] is False
    assert got["sample_count"] == 12
    assert seen[0] == "p95:trace.fastapi.request{service:api,env:dev}"


def test_sample_count_sums_all_buckets_in_requested_window():
    def query(query_text, _from, _to):
        if "as_count" in query_text:
            return {"series": [{"pointlist": [[1787558340000, 4], [1787558400000, 8]]}]}
        if "o2.warm" in query_text:
            return result(None)
        return result(0.2)

    got = read_metric(
        {"metric": "latency_p95", "service": "api", "window_seconds": 300},
        query_fn=query,
        now=1787558408,
    )
    assert got["sample_count"] == 12


def test_no_data_primary_does_not_hide_gap_with_warm_fallback():
    def query(query_text, _from, _to):
        return result(191.7) if "o2.warm" in query_text else result(None)

    got = read_metric({"metric": "latency_p95", "service": "api"}, query_fn=query, now=1787558408)
    assert got["value"] is None
    assert got["source"] is None
    assert got["fallback_used"] is False


def test_rps_uses_service_specific_native_source():
    seen = []

    def query(query_text, _from, _to):
        seen.append(query_text)
        return result(10)

    got = read_metric({"metric": "rps", "service": "chat-gateway"}, query_fn=query, now=1787558408)
    assert got["source"] == "datadog_native"
    assert "o2.app.business_event" in seen[0]
    assert "event:chat.send" in seen[0]
    assert not any("o2.warm" in item for item in seen)


def test_both_missing_returns_no_data_not_zero():
    got = read_metric(
        {"metric": "failure_rate", "service": "api", "event": "coupon.issue"},
        query_fn=lambda *_: result(None),
        now=1787558408,
    )
    assert got["status"] == "NO_DATA"
    assert got["value"] is None
    assert got["source"] is None


def test_high_cardinality_or_unknown_inputs_are_rejected():
    for body in (
        {"metric": "latency_p95", "service": "unknown"},
        {"metric": "latency_p95", "service": "api", "group_by": ["user_id"]},
        {"metric": "failure_rate", "service": "api", "event": "free text"},
    ):
        try:
            read_metric(body, query_fn=lambda *_: result(None))
        except MetricRequestError:
            pass
        else:
            raise AssertionError("invalid logical metric request was accepted")


def test_pod_group_results_are_preserved():
    def query(query_text, _from, _to):
        if "hits{" in query_text and "as_count" in query_text:
            return result(20)
        if "o2.warm" in query_text:
            return result(None)
        return {
            "series": [
                {"scope": "pod_name:api-a", "pointlist": [[1787558400000, 0.1]]},
                {"scope": "pod_name:api-b", "pointlist": [[1787558400000, 0.2]]},
            ]
        }

    got = read_metric(
        {"metric": "latency_p95", "service": "api", "group_by": ["pod_name"]},
        query_fn=query,
        now=1787558408,
    )
    assert [(item["scope"], item["value"]) for item in got["groups"]] == [
        ("pod_name:api-a", 100.0),
        ("pod_name:api-b", 200.0),
    ]


def test_chat_fanout_has_no_semantically_incorrect_warm_fallback():
    calls = []

    def query(query_text, _from, _to):
        calls.append(query_text)
        return result(None)

    got = read_metric(
        {"metric": "chat_fanout_p95", "service": "chat-gateway"},
        query_fn=query,
        now=1787558408,
    )
    assert got["status"] == "NO_DATA"
    assert got["fallback_used"] is False
    assert not any("o2.warm" in item for item in calls)


def test_chat_propagation_uses_dedicated_datadog_metric_without_warm_fallback():
    calls = []

    def query(query_text, _from, _to):
        calls.append(query_text)
        return result(None)

    got = read_metric(
        {"metric": "chat_propagation_p95_ms", "service": "chat-gateway"},
        query_fn=query,
        now=1787558408,
    )
    assert got["status"] == "NO_DATA"
    assert got["fallback_used"] is False
    assert any("p95:o2.chat.propagation" in item for item in calls)
    assert not any("o2.warm" in item for item in calls)


def test_block_rate_uses_datadog_normalized_failure_code_tag():
    calls = []

    def query(query_text, _from, _to):
        calls.append(query_text)
        return result(None)

    read_metric(
        {"metric": "block_rate", "service": "chat-gateway"},
        query_fn=query,
        now=1787558408,
    )
    assert any("failure_code:channel_limited" in item for item in calls)
    assert not any("failure_code:CHANNEL_LIMITED" in item for item in calls)
