"""데이터 신뢰도.

Agent가 지표를 믿고 판단할지, 판단을 보류할지 결정하는 근거입니다.
**지표가 없는 것과 지표가 0인 것은 다릅니다.** 그 차이를 숫자와 사유
문자열로 함께 내보내, LLM 프롬프트에 그대로 실을 수 있게 합니다.

두 축으로 봅니다.

- freshness   — 얼마나 최근 윈도우인가. 읽는 시점마다 달라지므로
                조회할 때 재계산합니다.
- completeness — 판단에 필요한 재료가 다 들어왔는가.
                 스트림 누락, 부분 집계 잘림, 평시 기준 부재.

점수는 두 값의 **최솟값**입니다. 곱하면 각각은 멀쩡한데 합쳐서
낮아지는 일이 생겨 사유 설명과 어긋납니다.
"""

from __future__ import annotations

from . import contract as C
from .settings import settings

# 윈도우가 닫힌 뒤 이만큼 지나면 신선도 0으로 봅니다.
STALE_AFTER = 6  # 윈도우 크기의 배수 → 기본 60초


def freshness(window_end: int, now: float) -> float:
    age = now - window_end
    if age <= settings.window_seconds:
        return 1.0
    limit = settings.window_seconds * STALE_AFTER
    if age >= limit:
        return 0.0
    return round(1.0 - (age - settings.window_seconds) / (limit - settings.window_seconds), 3)


def assess(sk, metrics: dict, *, now: float, baseline_ready: bool) -> dict:
    reasons: list[str] = []
    completeness = 1.0

    if sk.n_business == 0:
        completeness -= 0.5
        reasons.append("비즈니스 이벤트 없음 — 서비스 지표 전부 미산출")

    # 클라이언트 이벤트가 기대되는 서비스인지는 라우팅 표로 판단합니다.
    client_expected = sk.service in set(settings.click_route.values())
    if client_expected and sk.n_client == 0:
        completeness -= 0.3
        reasons.append("클라이언트 이벤트 없음 — click_ratio·ua_diversity 미산출")

    if sk.users.truncated:
        completeness -= 0.15
        reasons.append(f"상위 기여자 상한 초과 (축출 {sk.users.evictions}건)")

    if sk.intervals.dropped:
        completeness -= 0.1
        reasons.append(f"요청 간격 표본 상한 초과 (누락 {sk.intervals.dropped}명)")

    if sk.distinct_users.approximate:
        reasons.append("고유 사용자 수는 표본 추정값")

    if sk.segments.dropped:
        # 다른 절단 구조와 달리 세그먼트는 '늦게 나타난 값'을 통째로 버립니다.
        # 그 구간에서 벌어지는 저하는 아예 안 보이므로 반드시 알려야 합니다.
        completeness -= 0.15
        reasons.append(
            f"세그먼트 축 상한 초과 (미집계 {sk.segments.dropped}건) — "
            "일부 구간의 편차가 보이지 않습니다"
        )

    if not baseline_ready:
        completeness -= 0.2
        reasons.append("평시 기준 미확보 — rps_ratio 미산출")

    if metrics.get("pg_samples", 0) == 0 and C.EVENT_PAYMENT in sk.by_event:
        reasons.append(f"{C.F_PG_LATENCY} 미기록 — PG·DB 장애 감별 불가")

    completeness = round(max(0.0, completeness), 3)
    fresh = freshness(metrics["window_end"], now)

    return {
        "score": round(min(fresh, completeness), 3),
        "freshness": fresh,
        "completeness": completeness,
        "reasons": reasons,
        "evaluated_at": round(now, 3),
    }


def refresh(conf: dict, window_end: int, now: float) -> dict:
    """조회 시점 기준으로 신선도만 다시 계산합니다.

    저장된 값은 '쓸 때' 기준이라 30초 뒤에 읽으면 실제보다 후하게 나옵니다.
    검증 단계에서 오래된 스냅샷을 최신으로 착각하면 복구를 오판합니다.
    """
    out = dict(conf or {})
    fresh = freshness(window_end, now)
    out["freshness"] = fresh
    out["score"] = round(min(fresh, out.get("completeness", 1.0)), 3)
    out["evaluated_at"] = round(now, 3)
    return out
