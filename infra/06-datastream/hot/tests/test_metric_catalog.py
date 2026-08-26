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


# ── 창 집계 (T-040) ──────────────────────────────────────────────
#
# Datadog 은 창 끝의 안 닫힌 버킷을 null 이 아니라 0 으로 돌려준다. 예전에는
# 그 점 하나를 지표 값으로 써서, 처리량이 0 으로 보이거나 실패율이 1.0 으로
# 튀었다. 같은 조치가 마지막 버킷 상태에 따라 성공도 실패도 됐다.


def series(points, interval=10, scope="service:chat-gateway"):
    return {"pointlist": [[ts * 1000, v] for ts, v in points], "interval": interval, "scope": scope}


def test_trailing_open_bucket_is_excluded():
    """창 끝의 안 닫힌 버킷(0)이 값을 끌어내리지 않는다."""
    now = 1787558400
    # 마지막 점은 now 와 같은 시각이라 아직 안 닫혔다. interval=10 이므로
    # now-10 을 넘는 버킷은 제외된다.
    points = [(now - 40, 18000.0), (now - 30, 19000.0), (now - 20, 20000.0), (now, 0.0)]

    def query(query_text, _from, _to):
        if "as_count" in query_text and "fanout" in query_text:
            return {"series": [series([(now - 20, 1193650)])]}
        return {"series": [series(points)]}

    got = read_metric(
        {"metric": "items_per_sec", "service": "chat-gateway", "window_seconds": 300},
        query_fn=query,
        now=now,
    )
    # rate 는 창 평균이다. 0 이 섞였다면 평균이 14250 으로 떨어졌을 것이다.
    assert got["value"] == 19000.0
    assert got["status"] == "OK"


def test_gauge_uses_window_maximum_not_last_point():
    """백분위는 마지막 점이 아니라 창 최댓값이다 — 복구 판정에서 보수적이어야 한다."""
    now = 1787558400

    def query(query_text, _from, _to):
        if "as_count" in query_text:
            return {"series": [series([(now - 20, 500)])]}
        # 마지막 점만 보면 120ms 라 "복구" 로 보이지만 창 안에 900ms 가 있었다.
        return {"series": [series([(now - 40, 0.9), (now - 30, 0.4), (now - 20, 0.12)])]}

    got = read_metric(
        {"metric": "latency_p95", "service": "api", "window_seconds": 300},
        query_fn=query,
        now=now,
    )
    assert got["value"] == 900.0


def test_ratio_is_sum_over_sum_not_mean_of_ratios():
    """비율은 합의 비율이다. 버킷별 비율의 평균이 아니다."""
    now = 1787558400
    # 분자 600 / 분모 1200 = 0.5 여야 한다. 버킷별 비율의 평균이면
    # (100/1000 + 500/200) 로 엉뚱한 값이 된다.
    numerator = [(now - 40, 100.0), (now - 30, 500.0)]
    denominator = [(now - 40, 1000.0), (now - 30, 200.0)]

    def query(query_text, _from, _to):
        if "o2.app.failure" in query_text:
            return {"series": [series(numerator)]}
        return {"series": [series(denominator)]}

    got = read_metric(
        {"metric": "block_rate", "service": "chat-gateway", "window_seconds": 300},
        query_fn=query,
        now=now,
    )
    assert got["value"] == 0.5


def test_ratio_query_is_split_into_numerator_and_denominator():
    """카탈로그는 한 문자열이지만 조회는 두 번 나뉘어 나간다."""
    now = 1787558400
    seen = []

    def query(query_text, _from, _to):
        seen.append(query_text)
        return {"series": [series([(now - 20, 1.0)])]}

    read_metric(
        {"metric": "cache_hit_rate", "service": "api", "window_seconds": 300},
        query_fn=query,
        now=now,
    )
    assert not any(" / " in q for q in seen), seen
    assert "result:hit" in seen[0]
