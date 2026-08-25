"""Lambda o2-agg — Warm Path 집계기.

    stream-business ─┐
                     ├─▶ 이 함수 ─▶ DynamoDB METRIC#<service>/TS#<10초>
    stream-client  ──┘           └─▶ Datadog 커스텀 메트릭

두 스트림이 **각각의 이벤트 소스 매핑으로 따로 호출**됩니다. 같은 윈도우
아이템에 두 호출이 쓰므로 병합은 낙관적 잠금으로 처리합니다(store.py).

## 이 함수가 하지 않는 것

- 원본 이벤트 저장 — Firehose 가 이미 S3로 보냅니다. 여기서 또 쓰면
  같은 데이터에 두 개의 진실이 생깁니다.
- 알림 판단 — 감지는 Datadog Monitor 의 일입니다. 여기서는 계산만 합니다.

## 실패 처리

DynamoDB 병합 실패는 예외를 던져 배치를 재처리시킵니다. 재처리로 인한
이중 집계는 샤드별 sequence number 가드가 막습니다(sketch.already_applied).
Datadog 전송 실패는 삼킵니다 — 부가 작업이 본류를 막으면 안 됩니다.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import traceback

# Lambda ZIP 은 루트에 handlers/ 없이 평평하게 담기지만, 로컬에서 이 파일을
# 직접 실행할 때를 위해 src 를 경로에 넣어 둡니다.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from o2warm import baseline as baseline_mod  # noqa: E402
from o2warm import datadog  # noqa: E402
from o2warm.metrics import derive  # noqa: E402
from o2warm.settings import settings  # noqa: E402
from o2warm.sketch import WindowSketch, event_epoch  # noqa: E402
from o2warm.store import WarmStore  # noqa: E402
from o2warm.windows import group_by_window  # noqa: E402

_store: WarmStore | None = None

# 배포 이력은 자주 바뀌지 않습니다. 매 호출마다 GetItem 하면 초당 수 회의
# 불필요한 읽기가 발생하므로 컨테이너 재사용 구간에서 캐시합니다.
_DEPLOY_TTL = 60.0
_deploy_cache: dict[str, tuple[float, dict | None]] = {}

# 평시 기준을 갱신하려다 실패한 윈도우를 기억합니다. 없으면 같은 윈도우에
# 대해 매 호출마다 조회가 반복됩니다.
_baseline_probe: dict[str, int] = {}
_cold_start = True


def _emit_operational_metrics(*, source: str, **values: float) -> None:
    metrics = []
    payload = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": "O2/Warm",
                "Dimensions": [["FunctionName", "Environment", "Source"]],
                "Metrics": metrics,
            }],
        },
        "FunctionName": "o2-agg",
        "Environment": settings.dd_env,
        "Source": source,
    }
    units = {
        "HandlerDurationMs": "Milliseconds",
        "BatchSize": "Count",
        "DuplicateDiscarded": "Count",
        "LateArrival": "Count",
        "DecodeErrors": "Count",
        "ColdStart": "Count",
        "MaxMemoryUsedMB": "Megabytes",
        "SourceRecordCount": "Count",
        "AggregateEventCount": "Count",
    }
    for name, value in values.items():
        metrics.append({"Name": name, "Unit": units[name]})
        payload[name] = value
    print(json.dumps(payload, separators=(",", ":")))


def _max_memory_used_mb() -> float:
    try:
        import resource

        # Lambda Linux의 ru_maxrss는 KiB입니다.
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except (ImportError, OSError):
        return 0


def store() -> WarmStore:
    global _store
    if _store is None:
        _store = WarmStore()
    return _store


def _source_of(record: dict) -> str:
    """이 배치가 어느 (스트림, 샤드) 에서 왔는가.

    두 스트림 모두 샤드 ID 가 'shardId-000000000000' 이라 샤드 ID 만으로는
    구분되지 않습니다. 스트림 이름을 붙여야 sequence number 가드가
    서로를 덮어쓰지 않습니다.
    """
    arn = record.get("eventSourceARN") or ""
    stream = arn.rsplit("/", 1)[-1] or "unknown"
    shard = (record.get("eventID") or ":").split(":")[0] or "unknown"
    return f"{stream}:{shard}"


def decode(records: list[dict]) -> tuple[list[dict], list[str], dict[str, str]]:
    """Kinesis 레코드 → 봉투 목록. 깨진 레코드는 버리고 세어만 둡니다.

    한 레코드가 배치를 통째로 실패시키면 정상 이벤트까지 재처리됩니다.
    계약 위반은 SDK 가 발행 시점에 raise 하므로 여기까지 오는 깨진 값은
    사실상 없고, 온다면 그건 버리는 편이 맞습니다.
    """
    envelopes: list[dict] = []
    errors: list[str] = []
    seq_hi: dict[str, str] = {}

    for rec in records:
        source = _source_of(rec)
        seq = (rec.get("kinesis") or {}).get("sequenceNumber")
        if seq and (source not in seq_hi or int(seq) > int(seq_hi[source])):
            seq_hi[source] = seq
        try:
            raw = base64.b64decode((rec.get("kinesis") or {})["data"]).decode("utf-8")
        except Exception as e:
            errors.append(f"decode: {e}")
            continue
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"json: {e}")
                continue
            if isinstance(obj, dict) and obj.get("event_name"):
                envelopes.append(obj)
            else:
                errors.append("event_name 없는 레코드")
    return envelopes, errors, seq_hi


def deploy_context(service: str, now: float) -> dict | None:
    hit = _deploy_cache.get(service)
    if hit and now - hit[0] < _DEPLOY_TTL:
        return hit[1]
    try:
        ctx = store().deploy_context(service)
    except Exception as e:
        print(f"[warn] 배포 이력 조회 실패 {service}: {e}")
        ctx = hit[1] if hit else None
    _deploy_cache[service] = (now, ctx)
    return ctx


def advance_baseline(service: str, current_window: int, now: float) -> dict | None:
    """이미 닫힌 직전 윈도우로 평시 기준을 갱신하고, 그 기준을 돌려줍니다.

    지금 들어오는 윈도우는 아직 이벤트가 더 올 수 있어 rps 가 과소평가됩니다.
    그래서 한 칸 앞선 윈도우만 학습에 씁니다.
    """
    st = store()
    try:
        base = st.load_baseline(service)
    except Exception as e:
        print(f"[warn] 평시 기준 조회 실패 {service}: {e}")
        return None

    closed = current_window - settings.window_seconds
    last = int((base or {}).get("last_window") or 0)
    if closed <= last or _baseline_probe.get(service) == closed:
        return base
    _baseline_probe[service] = closed

    try:
        prev = st.recent_metrics(service, 3)
    except Exception:
        return base
    target = next((m for m in prev if int(m.get("window_start", -1)) == closed), None)
    if not target:
        return base

    updated = baseline_mod.update(base, closed, {
        "rps": target.get("rps"),
        "p95_ms": target.get("latency_p95"),
        "inventory_check_rate": target.get("inventory_check_rate"),
        "overall_failure_rate": target.get("overall_failure_rate"),
    })
    if updated is None:
        return base
    try:
        st.save_baseline(service, updated)
    except Exception as e:
        print(f"[warn] 평시 기준 저장 실패 {service}: {e}")
    return updated


def handler(event, context):
    global _cold_start
    started = time.time()
    records = event.get("Records", [])
    source_name = (
        ((records[0].get("eventSourceARN") or "").rsplit("/", 1)[-1])
        if records else "unknown"
    )
    envelopes, errors, seq_hi = decode(records)

    if not envelopes:
        _emit_operational_metrics(
            source=source_name,
            HandlerDurationMs=(time.time() - started) * 1000,
            BatchSize=len(records),
            DuplicateDiscarded=0,
            LateArrival=0,
            DecodeErrors=len(errors),
            ColdStart=1 if _cold_start else 0,
            MaxMemoryUsedMB=_max_memory_used_mb(),
            SourceRecordCount=len(records),
            AggregateEventCount=0,
        )
        _cold_start = False
        print(json.dumps({"records": len(records), "events": 0, "errors": len(errors)}))
        return {"statusCode": 200, "events": 0, "windows": 0}

    grouped = group_by_window(envelopes)
    published: list[dict] = []
    failures: list[str] = []
    duplicate_discarded = 0
    late_arrivals = sum(
        1
        for envelope in envelopes
        if started - event_epoch(envelope) > settings.window_seconds * 2
    )

    for (service, win), items in sorted(grouped.items()):
        partial = WindowSketch(service, win)
        for env in items:
            partial.add(env)
        for source, seq in seq_hi.items():
            partial.note_source(source, seq)

        try:
            merged, duplicate = store().merge_sketch_with_status(partial)
            if duplicate:
                duplicate_discarded += len(items)
        except Exception as e:
            # 여기 실패는 삼키면 안 됩니다. 집계 누락은 조용히 잘못된
            # 판단으로 이어지므로 배치를 재처리시킵니다.
            failures.append(f"{service}@{win}: {e}")
            traceback.print_exc()
            continue

        now = time.time()
        metrics = derive(
            merged,
            baseline=advance_baseline(service, win, now),
            deploy=deploy_context(service, now),
            now=now,
        )
        try:
            store().put_metrics(metrics)
            published.append(metrics)
        except Exception as e:
            failures.append(f"{service}@{win} put_metrics: {e}")
            traceback.print_exc()

    sent = datadog.publish(published) if published else 0
    _emit_operational_metrics(
        source=source_name,
        HandlerDurationMs=(time.time() - started) * 1000,
        BatchSize=len(records),
        DuplicateDiscarded=duplicate_discarded,
        LateArrival=late_arrivals,
        DecodeErrors=len(errors),
        ColdStart=1 if _cold_start else 0,
        MaxMemoryUsedMB=_max_memory_used_mb(),
        SourceRecordCount=len(records),
        AggregateEventCount=len(envelopes),
    )
    _cold_start = False

    print(json.dumps({
        "records": len(records),
        "events": len(envelopes),
        "windows": len(grouped),
        "published": len(published),
        "datadog_series": sent,
        "decode_errors": len(errors),
        "failures": failures,
        "elapsed_ms": int((time.time() - started) * 1000),
    }, ensure_ascii=False))

    if failures:
        raise RuntimeError(f"윈도우 {len(failures)}개 집계 실패 — 배치 재처리 필요")

    return {"statusCode": 200, "events": len(envelopes), "windows": len(published)}
