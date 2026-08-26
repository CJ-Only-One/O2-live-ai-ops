"""Agent 전달 계층.

## 왜 '한 번의 호출'이어야 하는가

진단 Agent는 §9 표의 재료를 전부 봐야 판단합니다. Agent가 지표·큐시트·
배포이력·정책·토폴로지를 각각 조회하게 만들면, 호출마다 시점이 어긋나
**서로 다른 순간의 재료로 하나의 결론을 내리게 됩니다.** 게다가 그 조회
순서를 Agent 팀이 구현해야 합니다.

그래서 `snapshot()` 하나가 판단 재료 전부를 한 번에 조립합니다.
이 반환값은 그대로 LLM 프롬프트에 실을 수 있는 형태이고, 그대로
`INCIDENT#<id>/SNAPSHOT#DETECT` 에 기록할 수 있는 형태입니다 —
"그 시점 Agent가 본 것"의 정의가 하나뿐이어야 재현과 평가가 가능합니다.

## 신선도는 읽을 때 다시 계산합니다

저장된 confidence 는 '쓸 때' 기준입니다. 40초 뒤에 읽으면 그 값은
거짓말이 됩니다. 검증 단계에서 오래된 지표를 최신으로 착각하면
복구되지 않은 상태를 복구로 판정합니다.
"""

from __future__ import annotations

import time

from .confidence import refresh
from .settings import settings
from .store import WarmStore
from .windows import iso_now, window_start

DEFAULT_WINDOWS = 6  # 10초 × 6 = 최근 1분


class WarmClient:
    """Agent 쪽에서 쓰는 조회 클라이언트.

    Python Agent 라면 이 클래스를 직접 쓰는 것이 가장 빠릅니다(HTTP 홉 없음).
    Dify 처럼 HTTP 만 되는 환경이면 serve/handler.py 가 이 클래스를 감쌉니다.
    """

    def __init__(self, store: WarmStore | None = None, **kwargs):
        self._store = store or WarmStore(**kwargs)

    # ------------------------------------------------------------ 지표
    def windows(self, service: str, count: int = DEFAULT_WINDOWS, now: float | None = None) -> list[dict]:
        """최근 N개 윈도우를 오래된 것부터 정렬해 돌려줍니다.

        Agent 프롬프트에 넣을 때 시간순이 아니면 추세를 읽지 못합니다.
        """
        now = now or time.time()
        items = self._store.recent_metrics(service, count)
        out = []
        for it in sorted(items, key=lambda i: i.get("window_start", 0)):
            it = {k: v for k, v in it.items() if k not in ("pk", "sk", "expires_at")}
            it["confidence"] = refresh(it.get("confidence"), it.get("window_end", 0), now)
            out.append(it)
        return out

    def latest(self, service: str, now: float | None = None) -> dict | None:
        """가장 최근의 **닫힌** 윈도우.

        ★ 열려 있는 윈도우를 주면 안 된다. 집계 Lambda 가 이벤트를 받는 대로
          DynamoDB 를 갱신하므로, 방금 시작한 창은 부분 집계 상태다. 그 값이
          Agent 의 복구 판정으로 그대로 간다 — 아직 실패가 안 담긴 창에서
          `channel_limited_rate = 0`, `failure_codes = {}` 가 나와 "정상 복귀"
          로 읽힌 사례가 있다(T-040).

          `window_end` 가 아직 안 지났으면 그 창은 진행 중이다. 닫힌 창이
          하나도 없으면 `None` 이다 — 부분값을 주느니 없다고 말한다.
        """
        now = now or time.time()
        for item in reversed(self.windows(service, DEFAULT_WINDOWS, now=now)):
            if item.get("window_end", 0) <= now:
                return item
        return None

    def range(self, service: str, start: int, end: int, now: float | None = None) -> list[dict]:
        now = now or time.time()
        out = []
        for it in self._store.metrics_between(service, window_start(start), window_start(end)):
            it = {k: v for k, v in it.items() if k not in ("pk", "sk", "expires_at")}
            it["confidence"] = refresh(it.get("confidence"), it.get("window_end", 0), now)
            out.append(it)
        return out

    # ------------------------------------------------------------ 판단 재료 번들
    def snapshot(
        self,
        service: str,
        *,
        count: int = DEFAULT_WINDOWS,
        broadcast_id: str | None = None,
        include: tuple[str, ...] = ("metrics", "deploy", "rundown", "policy", "topology"),
        now: float | None = None,
    ) -> dict:
        """이 시점 Agent가 볼 재료 전부."""
        now = now or time.time()
        bundle: dict = {
            "service": service,
            "as_of": iso_now(),
            "as_of_epoch": round(now, 3),
            "window_seconds": settings.window_seconds,
        }

        if "metrics" in include:
            series = self.windows(service, count, now=now)
            bundle["windows"] = series
            # windows 는 열린 창까지 그대로 준다(추세를 보려면 필요하다).
            # latest 는 판정에 쓰이므로 닫힌 창만 고른다 — 위 latest() 참고.
            bundle["latest"] = next(
                (it for it in reversed(series) if it.get("window_end", 0) <= now), None
            )
            bundle["trend"] = _trend(series)

        if "deploy" in include:
            bundle["deploy"] = self._store.deploy_context(service)
        if "rundown" in include and broadcast_id:
            # 큐시트가 없으면 예정된 쿠폰 발급 시각의 정상 급증을
            # 이상으로 오탐합니다.
            bundle["rundown"] = self._store.rundown(broadcast_id)
        if "policy" in include:
            bundle["policy"] = self._store.policy(service)
        if "topology" in include:
            bundle["topology"] = self._store.topology(service)

        bundle["gaps"] = _gaps(bundle, broadcast_id)
        return bundle

    # ------------------------------------------------------------ 인시던트
    def record_snapshot(
        self,
        incident_id: str,
        phase: str,
        service: str,
        extra: dict | None = None,
        broadcast_id: str | None = None,
    ) -> dict:
        """감지 시점 / 조치 직전 / 조치 직후를 인시던트에 못 박습니다.

        `PRE`·`POST` 는 지표만 남깁니다 — 복구 판정에 쓰이는 것이 지표뿐이고,
        나머지를 같이 넣으면 레코드만 무거워집니다.

        `DETECT` 는 번들 전체를 남깁니다. 지표 시계열은 TTL 7일이라 사후에도
        조회되지만 `confidence`·`gaps`·`rundown`·`policy` 는 **조회 시점 기준으로
        다시 계산**되므로, 지금 남기지 않으면 "그때 Agent 가 본 것"이 복원되지
        않습니다. 오판을 되짚을 때 필요한 것이 정확히 그 값들입니다.
        """
        phase = phase.upper()
        if phase == "DETECT":
            snap = self.snapshot(service, broadcast_id=broadcast_id)
        else:
            snap = self.snapshot(service, include=("metrics",))
        payload = {"service": service, "snapshot": snap}
        if extra:
            payload["extra"] = extra
        return self._store.put_snapshot(incident_id, phase, payload)

    def compare_snapshots(self, incident_id: str) -> dict | None:
        """조치 전후 비교. 검증 단계가 이 결과로 복구를 판정합니다.

        **인프라 지표만으로 판정하면 Silent Failure 를 복구로 오판합니다.**
        그래서 비즈니스 지표를 함께 비교합니다.
        """
        pre = self._store.get_snapshot(incident_id, "PRE")
        post = self._store.get_snapshot(incident_id, "POST")
        if not pre or not post:
            return None

        a = ((pre.get("snapshot") or {}).get("latest")) or {}
        b = ((post.get("snapshot") or {}).get("latest")) or {}
        keys = (
            "rps_ratio", "top1pct_share", "interval_cv", "click_ratio",
            "cache_hit_rate", "pg_latency_ratio", "version_fail_delta",
        )
        delta = {}
        for k in keys:
            if a.get(k) is not None and b.get(k) is not None:
                delta[k] = {"before": a[k], "after": b[k], "delta": round(b[k] - a[k], 4)}
        for event, rate in (b.get("failure_rate") or {}).items():
            before = (a.get("failure_rate") or {}).get(event)
            if before is not None and rate is not None:
                delta[f"failure_rate.{event}"] = {
                    "before": before, "after": rate, "delta": round(rate - before, 4)
                }
        return {"incident_id": incident_id, "before": a, "after": b, "delta": delta}


def _trend(series: list[dict]) -> dict:
    """첫 윈도우 대비 마지막 윈도우의 변화.

    Agent 가 값 하나만 보면 "0.71 이 높은가"를 알 수 없습니다.
    """
    if len(series) < 2:
        return {}
    first, last = series[0], series[-1]
    out = {}
    for k in ("rps", "rps_ratio", "top1pct_share", "interval_cv", "click_ratio",
              "cache_hit_rate", "pg_latency_ratio"):
        a, b = first.get(k), last.get(k)
        if a is None or b is None:
            continue
        out[k] = {"from": a, "to": b, "change": round(b - a, 4)}
    return out


def _gaps(bundle: dict, broadcast_id: str | None) -> list[str]:
    """빠진 재료를 명시합니다.

    Agent 가 없는 데이터를 '정상'으로 읽는 것이 가장 위험합니다.
    """
    gaps = []
    if not bundle.get("windows"):
        gaps.append("지표 윈도우 없음 — 해당 서비스의 이벤트가 들어오지 않았습니다")
    latest = bundle.get("latest") or {}
    for reason in (latest.get("confidence") or {}).get("reasons", []):
        gaps.append(reason)
    if "deploy" in bundle and not bundle.get("deploy"):
        gaps.append("배포 이력 없음 — 배포 장애 감별 불가")
    if broadcast_id and not bundle.get("rundown"):
        gaps.append("방송 큐시트 없음 — 예정된 급증을 이상으로 오탐할 수 있음")
    if "policy" in bundle and not bundle.get("policy"):
        gaps.append("정책 없음 — 조치 Agent 의 Guardrail 미동작")
    if "topology" in bundle and not bundle.get("topology"):
        gaps.append("토폴로지 없음 — blast radius 예측 불가")
    return gaps
