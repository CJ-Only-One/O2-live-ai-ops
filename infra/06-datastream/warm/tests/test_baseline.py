from o2warm import baseline
from o2warm.metrics import derive
from o2warm.settings import settings
from o2warm.sketch import build

import factory


def test_updates_all_supported_rolling_baselines(monkeypatch):
    monkeypatch.setattr(baseline.settings, "baseline_alpha", 0.5)
    first = baseline.update(None, 10, {
        "rps": 10.0,
        "p95_ms": 100.0,
        "inventory_check_rate": 4.0,
        "overall_failure_rate": 0.02,
    })
    updated = baseline.update(first, 20, {
        "rps": 14.0,
        "p95_ms": 140.0,
        "inventory_check_rate": 6.0,
        "overall_failure_rate": 0.04,
    })

    assert updated["rps"] == 12.0
    assert updated["p95_ms"] == 120.0
    assert updated["inventory_check_rate"] == 5.0
    assert updated["overall_failure_rate"] == 0.03
    assert updated["samples"] == updated["rps_samples"] == 2
    assert updated["p95_ms_samples"] == 2


def test_missing_metric_does_not_create_a_zero_baseline():
    updated = baseline.update(None, 10, {"rps": 2.0, "p95_ms": None})
    assert updated["rps"] == 2.0
    assert "p95_ms" not in updated
    assert "p95_ms_samples" not in updated


def test_derive_exposes_ready_baselines_and_inventory_rate():
    events = [
        factory.inventory(factory.BASE + i, f"u{i}", f"ip{i}")
        for i in range(5)
    ]
    ready_samples = settings.baseline_min_samples
    metrics = derive(build("coupon-api", factory.BASE, events), baseline={
        "rps": 2.0,
        "samples": ready_samples,
        "p95_ms": 85.0,
        "p95_ms_samples": ready_samples,
        "inventory_check_rate": 3.5,
        "inventory_check_rate_samples": ready_samples,
        "overall_failure_rate": 0.01,
        "overall_failure_rate_samples": ready_samples,
    })

    assert metrics["inventory_check_rate"] == 0.5
    assert metrics["baseline_p95_ms"] == 85.0
    assert metrics["baseline_inventory_check_rate"] == 3.5
    assert metrics["baseline_overall_failure_rate"] == 0.01
