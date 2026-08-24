import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path


class FakeClient:
    pass


def load_handler(monkeypatch):
    monkeypatch.setenv("CANARY_STREAM", "stream-business")
    monkeypatch.setenv("CANARY_SERVICE", "o2-canary")
    monkeypatch.setenv("WARM_TABLE", "o2-agent-context")
    monkeypatch.setenv("DATA_LAKE_BUCKET", "o2-data-lake-test")
    monkeypatch.setattr("boto3.client", lambda service: FakeClient())
    path = Path(__file__).with_name("handler.py")
    spec = importlib.util.spec_from_file_location("o2_canary_handler", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_previous_hour_prefix_handles_day_boundary(monkeypatch):
    module = load_handler(monkeypatch)
    now = datetime(2026, 8, 24, 0, 5, tzinfo=timezone.utc)
    assert module._previous_hour_prefix(now) == (
        "raw/business/year=2026/month=08/day=23/hour=23/"
    )


def test_emit_health_reports_age_and_partition(monkeypatch, capsys):
    module = load_handler(monkeypatch)
    now = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(module, "_warm_window_age", lambda epoch: 42.0)
    monkeypatch.setattr(module, "_business_partition_missing", lambda dt: 0)

    module._emit_health(now)

    payload = json.loads(capsys.readouterr().out)
    assert payload["WarmWindowAgeSeconds"] == 42.0
    assert payload["BusinessPartitionMissing"] == 0
    assert payload["Environment"] == "dev"


def test_missing_warm_window_omits_age_metric(monkeypatch, capsys):
    module = load_handler(monkeypatch)
    now = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(module, "_warm_window_age", lambda epoch: None)
    monkeypatch.setattr(module, "_business_partition_missing", lambda dt: 1)

    module._emit_health(now)

    payload = json.loads(capsys.readouterr().out)
    assert "WarmWindowAgeSeconds" not in payload
    assert payload["BusinessPartitionMissing"] == 1
