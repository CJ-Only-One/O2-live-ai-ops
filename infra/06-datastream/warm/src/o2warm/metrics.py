"""부분 집계 → 파생 지표.

agent-data-requirements.md §3 감별표의 각 열이 여기서 하나씩 나옵니다.
**어느 지표도 단독으로 시나리오를 특정하지 못합니다.** 그래서 전부 계산해
한 아이템에 담고, 조합 판단은 Agent(LLM)에게 맡깁니다.

계산할 수 없는 지표는 0이 아니라 **None** 입니다. 표본이 없어서 0인 것과
실제로 0인 것을 Agent가 구분할 수 있어야 하기 때문입니다.
"""

from __future__ import annotations

import math
import re
import time

from . import contract as C
from .confidence import assess
from .settings import CLICK_PAIRS, settings
from .sketch import WindowSketch
from .windows import iso_from_epoch, iso_now

TOP_CONTRIBUTORS = 5

# 파드별 p95 를 만들기 위해 요구하는 최소 표본 수.
#
# 10초 윈도우라 방금 뜬 파드는 요청을 한두 건만 받고 지나간다. 표본
# 한 건짜리 p95 는 그 한 건의 값 그대로이고, outlier 탐지(DBSCAN)에
# 들어가면 **정상 파드가 스케일아웃했다는 사실만으로** 이상치가 된다.
# S2 재분석이 지목해야 하는 것은 "느린 파드" 이지 "새 파드" 가 아니다.
LATENCY_POD_MIN_SAMPLES = 5


def _ratio(num: float, den: float) -> float | None:
    return round(num / den, 4) if den else None


def _version_key(v: str):
    """v1.10.0 이 v1.9.0 보다 뒤라는 것을 문자열 비교로는 알 수 없습니다."""
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", v)]


def concentration(sk: WindowSketch) -> dict:
    """요청이 소수 계정에 얼마나 몰렸는가.

    트래픽 폭증은 사용자 수가 늘어난 것이고, 매크로는 소수가 많이 때린
    것입니다. 총 rps 는 둘 다 오르므로 이 축이 갈라냅니다.

    두 가지를 함께 냅니다.

    - `top1pct_share` — 문서(§3) 정의. 사용자 수에 비례해 상위 구간이
      정해지므로 규모가 커져도 의미가 유지됩니다.
    - `top5_share` — 상위 5개 계정의 점유율. 사용자가 수백 명 수준이면
      1% 가 2~3개밖에 안 되어 매크로 무리를 놓칩니다. 고정 개수 쪽이
      그 구간에서 훨씬 또렷합니다.
    """
    total = sk.users.total
    if total == 0:
        return {"top1pct_share": None, "top5_share": None, "distinct_users": 0, "top1pct_n": 0}

    distinct = max(sk.distinct_users.estimate(), len(sk.users.counts))
    k = max(1, math.ceil(distinct * 0.01))
    return {
        "top1pct_share": _ratio(sum(c for _, c in sk.users.top(k)), total),
        "top5_share": _ratio(sum(c for _, c in sk.users.top(5)), total),
        "distinct_users": distinct,
        "top1pct_n": k,
    }


def click_ratio(sk: WindowSketch) -> tuple[float | None, dict]:
    """클릭 대비 서버 요청.

    정상 사용자는 버튼을 누르고 요청이 갑니다. 매크로는 버튼 없이 API 를
    직접 부릅니다. 두 스트림을 같은 윈도우에 모아야만 나오는 지표입니다.
    """
    detail = {}
    clicks_total = 0
    reqs_total = 0
    for label, (action, event) in CLICK_PAIRS.items():
        clicks = sk.clicks.get(action, 0)
        reqs = sk.by_event.get(event, 0)
        if clicks == 0 and reqs == 0:
            continue
        detail[label] = {"clicks": clicks, "requests": reqs, "ratio": _ratio(clicks, reqs)}
        clicks_total += clicks
        reqs_total += reqs
    return _ratio(clicks_total, reqs_total), detail


def failure_breakdown(sk: WindowSketch) -> tuple[dict, dict]:
    """이벤트별 실패율과 사유 분포.

    PG 장애와 DB 장애는 실패율이 같습니다. 사유 코드 분포가 갈라냅니다.
    """
    attempts: dict[str, int] = {}
    fails: dict[str, int] = {}
    for key, cnt in sk.results.items():
        name, result = key.split("|", 1)
        attempts[name] = attempts.get(name, 0) + cnt
        if result == C.RESULT_FAILED:
            fails[name] = fails.get(name, 0) + cnt

    rates = {n: _ratio(fails.get(n, 0), attempts[n]) for n in attempts}

    codes: dict[str, dict[str, float]] = {}
    for key, cnt in sk.failures.items():
        name, code = key.split("|", 1)
        codes.setdefault(name, {})[code] = cnt
    for name, dist in codes.items():
        total = sum(dist.values())
        codes[name] = {c: round(v / total, 4) for c, v in sorted(dist.items(), key=lambda kv: -kv[1])}

    return rates, codes


def overall_failure(sk: WindowSketch) -> tuple[int, int]:
    """result 를 실은 이벤트 전체의 (시도, 실패)."""
    attempts = sum(sk.results.values())
    failed = sum(c for k, c in sk.results.items() if k.endswith(f"|{C.RESULT_FAILED}"))
    return attempts, failed


def failure_code_rate(sk: WindowSketch, event: str, code: str) -> float | None:
    """특정 실패 사유 / 해당 이벤트 전체 시도.

    `failure_codes`는 실패 사유끼리의 분포라 `CHANNEL_LIMITED=1.0`이어도 전체
    발화 중 1%가 막힌 것인지 90%가 막힌 것인지 알 수 없습니다. S1 성공 판정은
    정상 사용자 차단률 자체가 필요하므로 result 전체를 분모로 다시 계산합니다.
    """
    attempts = sum(
        count for key, count in sk.results.items() if key.startswith(f"{event}|")
    )
    blocked = sk.failures.get(f"{event}|{code}", 0)
    return _ratio(blocked, attempts)


def segment_view(sk: WindowSketch) -> dict:
    """축별·값별 시도·실패·실패율."""
    out: dict[str, dict] = {}
    for axis, values in sk.segments.axes.items():
        total = sum(n for n, _ in values.values())
        out[axis] = {
            v: {
                "n": n,
                "failed": f,
                "failure_rate": _ratio(f, n),
                "share": _ratio(n, total),
            }
            for v, (n, f) in sorted(values.items(), key=lambda kv: -kv[1][0])
        }
    return out


def segment_skew(sk: WindowSketch, attempts: int, failed: int) -> list[dict]:
    """전체 평균에서 크게 벗어난 세그먼트.

    **"평균은 멀쩡한데 어디가 죽는가"에 직접 답하는 지표입니다.**
    전체 실패율 3%가 사실 캠페인 하나에서 95%, 나머지에서 0%인 상황은
    전체 값만 보면 임계에 걸리지 않습니다.

    맵을 통째로 넘기지 않고 벗어난 것만 골라 순위를 매기는 이유는,
    Agent 가 판단할 대상을 좁혀 주기 위해서입니다. 축이 늘수록 맵은
    커지지만 실제로 볼 것은 한두 개입니다.

    순위는 **초과 실패 건수**로 매깁니다 — 비율이 아무리 튀어도 표본이
    5건이면 조치할 근거가 못 되기 때문입니다.
    """
    baseline = failed / attempts if attempts else 0.0
    out = []

    for axis, values in sk.segments.axes.items():
        for value, (n, f) in values.items():
            if n < settings.segment_min_samples:
                continue
            rate = f / n
            if rate <= baseline:
                continue
            excess = f - n * baseline
            # 전체가 0%인데 이 구간만 실패하면 배수가 무한대가 됩니다.
            # 그때는 절대 실패율로 판단합니다.
            lift = rate / baseline if baseline > 0 else None
            if lift is not None and lift < settings.segment_min_lift:
                continue
            if lift is None and rate < 0.05:
                continue
            out.append({
                "axis": axis,
                "value": value,
                "n": n,
                "failed": f,
                "failure_rate": round(rate, 4),
                "overall_failure_rate": round(baseline, 4),
                "lift": round(lift, 2) if lift is not None else None,
                "excess_failures": int(round(excess)),
            })

    out.sort(key=lambda s: -s["excess_failures"])
    return out[:5]


def version_delta(sk: WindowSketch, deploy: dict | None) -> tuple[float | None, dict]:
    """최신 버전과 직전 버전의 실패율 차이.

    배포 장애만 이 값이 벌어집니다. 인프라 지표로는 절대 보이지 않습니다.
    """
    detail = {
        v: {"n": n, "failed": f, "failure_rate": _ratio(f, n)}
        for v, (n, f) in sk.versions.items()
    }
    if len(detail) < 2:
        return None, detail

    latest = previous = None
    if deploy:
        latest = deploy.get("version") or deploy.get("current_version")
        previous = deploy.get("previous_version")
    if latest not in detail or previous not in detail:
        # 배포 이력이 아직 없으면 버전 문자열 순서로 대신합니다.
        ordered = sorted(detail, key=_version_key, reverse=True)
        latest, previous = ordered[0], ordered[1]

    a = detail[latest]["failure_rate"]
    b = detail[previous]["failure_rate"]
    if a is None or b is None:
        return None, detail
    detail["_compared"] = {"latest": latest, "previous": previous}
    return round(a - b, 4), detail


def derive(
    sk: WindowSketch,
    *,
    baseline: dict | None = None,
    deploy: dict | None = None,
    now: float | None = None,
) -> dict:
    """윈도우 하나의 Agent-facing 지표 아이템 본문."""
    now = now or time.time()
    span = settings.window_seconds
    rps = round(sk.n_business / span, 3)

    base_rps = (baseline or {}).get("rps")
    baseline_ready = bool(base_rps) and (baseline or {}).get("samples", 0) >= settings.baseline_min_samples

    conc = concentration(sk)
    cv, cv_users = sk.intervals.cv_weighted_median()
    cv_plain, _ = sk.intervals.cv_median()
    heavy = {k for k, _ in sk.users.top(max(5, conc["top1pct_n"]))}
    cv_top, cv_top_n = sk.intervals.cv_of(heavy)
    ratio, ratio_detail = click_ratio(sk)
    fail_rates, fail_codes = failure_breakdown(sk)
    vdelta, vdetail = version_delta(sk, deploy)
    cache_total = sk.cache_hit + sk.cache_miss
    attempts, failed = overall_failure(sk)
    cancels = sum(sk.cancel_reasons.values()) or sk.by_event.get(C.EVENT_ORDER_CANCEL, 0)
    orders = sk.by_event.get(C.EVENT_ORDER_CREATE, 0)
    cancel_total = sum(sk.cancel_reasons.values())

    out = {
        "service": sk.service,
        "window_start": sk.window_start,
        "window_end": sk.window_start + span,
        "window_seconds": span,
        "window_start_iso": iso_from_epoch(sk.window_start),

        "event_count": sk.n,
        "business_count": sk.n_business,
        "client_count": sk.n_client,
        "event_breakdown": dict(sorted(sk.by_event.items(), key=lambda kv: -kv[1])),
        # rps 는 service 단위 합산이라 이벤트 종류로 못 가른다(예: order.create
        # 대 order.confirm 정지 감지). failure_rate 와 같은 이유로 known
        # EVENT_NAMES 로만 제한한다 — 알 수 없는 event_name 까지 태그로 펼치면
        # 카디널리티가 입력값에 좌우된다.
        "event_rate": {
            name: round(count / span, 4)
            for name, count in sk.by_event.items()
            if name in C.EVENT_NAMES
        },

        # --- 감별표 열 ---
        "rps": rps,
        "rps_ratio": _ratio(rps, base_rps) if baseline_ready else None,
        "baseline_rps": round(base_rps, 3) if base_rps else None,

        "top1pct_share": conc["top1pct_share"],
        "top5_share": conc["top5_share"],
        "distinct_users": conc["distinct_users"],

        # 요청 가중 중앙값이 감별에 쓰는 값입니다. 계정당 1표인
        # interval_cv_unweighted 는 소수 매크로를 구조적으로 놓칩니다.
        "interval_cv": round(cv, 4) if cv is not None else None,
        "interval_cv_top": round(cv_top, 4) if cv_top is not None else None,
        "interval_cv_unweighted": round(cv_plain, 4) if cv_plain is not None else None,
        "interval_users": cv_users,
        "interval_top_users": cv_top_n,

        "ua_diversity": _ratio(sk.distinct_ua.estimate(), sk.ua_events),
        "ip_diversity": _ratio(sk.distinct_ip.estimate(), sk.n_business),

        "click_ratio": ratio,
        "click_detail": ratio_detail,

        "cache_hit_rate": _ratio(sk.cache_hit, cache_total),
        "cache_samples": cache_total,
        # 파드 하나만 무효화를 놓쳐도 service 평균엔 안 잡힌다(README 시나리오 1).
        # pod_name 이 있는 파드만 대상 — 이 값을 만들 pod_name 태그가 아직 없는
        # 봉투(SDK 구버전 등)에서 온 이벤트는 자연히 빠진다.
        "cache_hit_rate_by_pod": {
            pod: _ratio(
                sk.cache_hit_by_pod.get(pod, 0),
                sk.cache_hit_by_pod.get(pod, 0) + sk.cache_miss_by_pod.get(pod, 0),
            )
            for pod in set(sk.cache_hit_by_pod) | set(sk.cache_miss_by_pod)
        },

        "failure_rate": fail_rates,
        "failure_codes": fail_codes,
        # S1 정확 축. failure_codes 맵은 실패 사유 내부 분포라 차단률이 아니다.
        # 별도 scalar여야 Datadog Monitor와 Agent 검증 쿼리가 직접 읽을 수 있다.
        "channel_limited_rate": failure_code_rate(sk, "chat.send", "CHANNEL_LIMITED"),

        "pg_latency_ratio": sk.pg_ratio.quantile(0.5),
        "pg_samples": sk.pg_ratio.count,

        "version_fail_delta": vdelta,
        "version_detail": vdetail,

        # --- 사용자 경험 저하 ---
        # 여기부터는 인프라 지표가 전부 정상인 채로도 움직이는 값들입니다.
        # 응답이 200이고 p95 가 임계 안이어도 체감은 나빠질 수 있습니다.
        "latency_p50": sk.latency.quantile(0.5),
        "latency_p95": sk.latency.quantile(0.95),
        "latency_p99": sk.latency.quantile(0.99),
        "latency_samples": sk.latency.n,

        # 파드 하나만 느려도 service p95 는 나머지 파드에 희석돼 임계 안에
        # 머문다(README 시나리오 5의 재분석 근거). cache_hit_rate_by_pod 와
        # 같은 축·같은 이유다.
        #
        # 표본이 적은 파드는 뺀다. LogHistogram.quantile 은 표본 1개에도
        # 값을 내주는데, 그 값을 outlier 탐지에 넣으면 방금 뜬 파드의 첫
        # 요청 하나가 이상치로 잡힌다. 파드가 실제로 느린 것과 아직 덜
        # 데워진 것을 구분하지 못하면 재분석이 엉뚱한 파드를 지목한다.
        "latency_p95_by_pod": {
            pod: hist.quantile(0.95)
            for pod, hist in sk.latency_by_pod.items()
            if hist.n >= LATENCY_POD_MIN_SAMPLES
        },
        "latency_samples_by_pod": {pod: hist.n for pod, hist in sk.latency_by_pod.items()},

        # 사용자가 같은 동작을 반복했다는 것 자체가 체감 저하의 증거입니다.
        # 서버는 매번 성공했을 수 있습니다.
        "retry_rate": _ratio(sk.retry_events, sk.retry_base),
        "retry_per_event": _ratio(sk.retry_sum, sk.retry_base),
        "retry_samples": sk.retry_base,

        # 폴백 성공은 '성공'으로 기록되어 실패율에 잡히지 않습니다.
        "fallback_rate": _ratio(sk.fallback_used, cache_total),

        # 취소는 사후·비동기라 요청 시점 신호가 없습니다.
        "cancel_rate": _ratio(cancels, orders),
        "cancel_reasons": {
            k: round(v / cancel_total, 4)
            for k, v in sorted(sk.cancel_reasons.items(), key=lambda kv: -kv[1])
        } if cancel_total else {},
        "cancel_by": dict(sorted(sk.cancel_by.items(), key=lambda kv: -kv[1])),

        # 평균이 가리는 것을 드러냅니다.
        "overall_failure_rate": _ratio(failed, attempts),
        "segments": segment_view(sk),
        "segment_skew": segment_skew(sk, attempts, failed),

        # --- 부가 ---
        "top_contributors": [
            {"user_key": k, "count": c, "share": _ratio(c, sk.users.total)}
            for k, c in sk.users.top(TOP_CONTRIBUTORS)
        ],
        "updated_at": iso_now(),
        "rev": sk.n,
    }
    out["confidence"] = assess(sk, out, now=now, baseline_ready=baseline_ready)
    return out


# Datadog 으로 보낼 스칼라만 골라낸 목록.
# 맵·리스트는 커스텀 메트릭이 될 수 없고, 되더라도 고카디널리티라
# 보내면 안 됩니다. 이 경계가 설계의 핵심입니다.
DATADOG_SCALARS = (
    "rps",
    "rps_ratio",
    "top1pct_share",
    "top5_share",
    "interval_cv",
    "interval_cv_top",
    "ua_diversity",
    "ip_diversity",
    "click_ratio",
    "cache_hit_rate",
    "pg_latency_ratio",
    "version_fail_delta",
    "event_count",
    "distinct_users",
    # 사용자 경험 저하 — 인프라 임계로는 안 울리므로 별도 Monitor 가 필요합니다.
    "latency_p50",
    "latency_p95",
    # p99 는 오래 계산만 되고 보내지지 않았습니다. 명세 S2 의 1차 조치 검증이
    # p50·p95·**p99** 셋을 함께 보는 것을 전제하는데, Datadog 에는 둘뿐이라
    # 그 단계에서 읽을 값이 없었습니다.
    #
    # p95 로 대신할 수 없습니다. 파드 하나가 느린 상황에서 그 파드의 몫이
    # 전체의 5% 미만이면 **p95 는 안 움직이고 p99 만 움직입니다.** 조치가
    # 꼬리 끝을 건드렸는지는 p99 에서만 보입니다.
    "latency_p99",
    "retry_rate",
    "fallback_rate",
    "cancel_rate",
    "overall_failure_rate",
    "channel_limited_rate",
)
