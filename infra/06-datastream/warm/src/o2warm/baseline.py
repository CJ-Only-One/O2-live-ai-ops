"""평시 기준 지표의 rolling baseline.

`rps_ratio`와 복구 판정용 기준값은 평시 값을 어디선가 가져와야 합니다.
Datadog 에 물어보면 조회 지연과 장애 시 의존이 생기므로, 집계 Lambda가
스스로 EWMA 로 들고 있습니다.

α 를 작게(0.05) 둔 이유는 **급증 자체가 기준을 끌어올리면 안 되기** 때문입니다.
10초 윈도우 기준 α=0.05 는 반감기 약 2분이라, 수십 초짜리 스파이크는
기준을 거의 흔들지 못합니다.

닫힌 윈도우만 반영합니다. 아직 이벤트가 들어오는 중인 윈도우를 넣으면
평시 기준이 실제보다 낮게 잡힙니다.
"""

from __future__ import annotations

from .settings import settings

# 급증 구간이 기준에 섞여 들어가는 것을 막는 상한.
# 평시의 3배를 넘는 윈도우는 '평시'가 아니므로 학습하지 않습니다.
SPIKE_GUARD = 3.0

BASELINE_FIELDS = (
    "rps",
    "p95_ms",
    "inventory_check_rate",
    "overall_failure_rate",
)


def update(baseline: dict | None, window_start: int, sample: float | dict) -> dict | None:
    """윈도우 하나를 반영한 새 기준. 반영할 것이 없으면 None.

    None 을 돌려주면 호출자가 쓰기를 건너뜁니다 — 매 배치마다 DynamoDB에
    쓰지 않기 위한 신호입니다.
    """
    cur = dict(baseline or {})
    last = int(cur.get("last_window") or 0)
    if window_start <= last:
        return None  # 이미 반영했거나 지나간 윈도우

    samples = int(cur.get("samples") or 0)
    values = {"rps": sample} if isinstance(sample, (int, float)) else sample
    a = settings.baseline_alpha
    skipped = False
    for field in BASELINE_FIELDS:
        value = values.get(field)
        if not isinstance(value, (int, float)):
            continue
        prev = cur.get(field)
        field_samples = int(cur.get(f"{field}_samples") or (samples if field == "rps" else 0))
        if (
            prev is not None
            and field_samples >= settings.baseline_min_samples
            and value > prev * SPIKE_GUARD
        ):
            skipped = True
            continue
        cur[field] = value if prev is None else (a * value + (1 - a) * prev)
        cur[f"{field}_samples"] = field_samples + 1

    # 기존 소비자가 쓰는 samples는 rps 표본 수와 같은 의미를 유지합니다.
    cur["samples"] = int(cur.get("rps_samples") or samples)
    cur["last_window"] = window_start
    if skipped:
        cur["skipped"] = int(cur.get("skipped") or 0) + 1
    return cur


def ready(baseline: dict | None, field: str = "rps") -> bool:
    if not baseline:
        return False
    samples = baseline.get(f"{field}_samples")
    if samples is None and field == "rps":
        samples = baseline.get("samples")
    return int(samples or 0) >= settings.baseline_min_samples
