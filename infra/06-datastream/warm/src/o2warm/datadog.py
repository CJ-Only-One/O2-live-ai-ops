"""집계 결과를 Datadog 커스텀 메트릭으로 보냅니다.

## Datadog 은 여기서 '계산 주체'가 아니라 '감지용 싱크'입니다

담당 경계는 데이터 출처로 나눠져 있습니다 — 인프라에서 나온 것은 Datadog,
이벤트 스트림에서 나온 것은 이 파이프라인. 그래서 비즈니스 지표의 계산은
Lambda 한 곳에서만 일어나고, 같은 값이 두 시스템에 생기지 않습니다.

전송은 그와 별개 층위입니다. 감지가 Datadog 으로 일원화돼 있으므로
결과 중 스칼라만 그쪽으로 흘려보냅니다.

## 왜 DynamoDB 만으로는 안 되는가

감지는 Datadog 하나로 일원화돼 있습니다. 비즈니스 지표가 DynamoDB에만
있으면 "쿠폰 발급 성공률이 떨어졌다"를 감지할 별도 감시기를 또 만들어야
합니다. 계산은 한 번 하고 결과를 양쪽에 보냅니다.

- Datadog  → 알림 조건, 대시보드, 추세  (스칼라 1개)
- DynamoDB → Agent 판단용 상세          (분포·기여자 목록 포함)

## 무엇을 보내지 않는가

`failure_codes`, `top_contributors`, `version_detail` 은 보내지 않습니다.
맵이라 메트릭이 될 수 없고, 태그로 펼치면 user_key 수만큼 시계열이 생겨
커스텀 메트릭 요금이 폭발합니다. **이 경계가 Hot/Warm 분리의 실체입니다.**

## 실패해도 집계를 막지 않습니다

Datadog 전송은 부가 작업입니다. 여기서 예외가 나 Lambda 가 실패하면
Kinesis 배치가 재처리되고, 정작 중요한 DynamoDB 집계가 지연됩니다.
그래서 짧은 타임아웃 + 예외 삼킴으로 처리합니다.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

from . import secrets
from .metrics import DATADOG_SCALARS
from .settings import settings

GAUGE = 3  # Datadog series v2 의 gauge 타입 코드


def api_key() -> str:
    """키가 있는 곳에서 실행 시점에 읽습니다. 조회·캐시는 `secrets` 가 합니다.

    원본은 Secrets Manager `o2/dev/datadog` 이고, 04-platform 이 ESO 로
    Agent 에 넣는 것과 **같은 시크릿**입니다. 사본을 만들지 않으므로
    키를 회전할 때 Agent 와 이 Lambda 가 함께 바뀝니다. 한쪽만 바뀌면
    인프라 지표는 정상인데 비즈니스 지표만 조용히 멈춥니다.
    """
    return secrets.datadog_api_key()


def build_series(metrics: dict, *, prefix: str | None = None, env: str | None = None) -> list[dict]:
    """지표 아이템에서 스칼라만 뽑아 series 페이로드로 만듭니다."""
    prefix = prefix if prefix is not None else settings.dd_prefix
    tags = [
        f"service:{metrics['service']}",
        f"env:{env if env is not None else settings.dd_env}",
    ]
    ts = int(metrics["window_start"])

    series = [
        {
            "metric": f"{prefix}{name}",
            "type": GAUGE,
            "points": [{"timestamp": ts, "value": float(metrics[name])}],
            "tags": tags,
        }
        for name in DATADOG_SCALARS
        if metrics.get(name) is not None
    ]

    # 실패율은 이벤트 종류별로 갈라야 알림 조건을 세울 수 있습니다.
    # event_name 은 값의 종류가 고정이라 태그로 안전합니다.
    for event, rate in (metrics.get("failure_rate") or {}).items():
        if rate is None:
            continue
        series.append(
            {
                "metric": f"{prefix}failure_rate",
                "type": GAUGE,
                "points": [{"timestamp": ts, "value": float(rate)}],
                "tags": tags + [f"event:{event}"],
            }
        )

    # rps 는 service 단위 합산이라 event.confirm 정지 같은 것을 못 봅니다.
    # failure_rate 와 같은 이유로 event 태그로 갈라 보냅니다 — metrics.py
    # 의 derive() 가 이미 known EVENT_NAMES 로만 제한해 뒀습니다.
    for event, rate in (metrics.get("event_rate") or {}).items():
        if rate is None:
            continue
        series.append(
            {
                "metric": f"{prefix}event_rate",
                "type": GAUGE,
                "points": [{"timestamp": ts, "value": float(rate)}],
                "tags": tags + [f"event:{event}"],
            }
        )

    # 파드 하나만 캐시 무효화를 놓쳐도 service 단위 cache_hit_rate 평균에는
    # 안 잡힙니다(README 시나리오 1). 같은 메트릭 이름에 pod_name 태그만 얹어
    # 보냅니다 — 위 DATADOG_SCALARS 루프가 이미 보낸 service 단위 값과
    # 시계열이 다르게 잡혀 outlier 탐지 쿼리(`by {pod_name}`)가 이 태그가
    # 있는 시계열만 골라 씁니다. pod_name 은 K8s 가 정하는 값이라 카디널리티가
    # 입력값에 안 좌우됩니다(failure_rate/event_rate 와 같은 이유).
    for pod, rate in (metrics.get("cache_hit_rate_by_pod") or {}).items():
        if rate is None:
            continue
        series.append(
            {
                "metric": f"{prefix}cache_hit_rate",
                "type": GAUGE,
                "points": [{"timestamp": ts, "value": float(rate)}],
                "tags": tags + [f"pod_name:{pod}"],
            }
        )

    conf = metrics.get("confidence") or {}
    if conf.get("score") is not None:
        series.append(
            {
                "metric": f"{prefix}confidence",
                "type": GAUGE,
                "points": [{"timestamp": ts, "value": float(conf["score"])}],
                "tags": tags,
            }
        )
    return series


def submit(series: list[dict]) -> bool:
    """series v2 로 전송. 성공 여부만 돌려주고 예외는 던지지 않습니다."""
    if not series:
        return True
    key = api_key()
    if not key:
        return False

    url = f"https://api.{settings.dd_site}/api/v2/series"
    body = json.dumps({"series": series}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "DD-API-KEY": key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=settings.dd_timeout) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        _warn(f"Datadog {e.code}: {e.read()[:200]!r}")
    except Exception as e:  # 네트워크·타임아웃 전부 여기로
        _warn(f"Datadog 전송 실패: {e}")
    return False


def publish(metrics_list: list[dict]) -> int:
    """여러 윈도우를 한 번의 호출로 보냅니다.

    윈도우마다 따로 부르면 Lambda 실행 시간이 호출 수만큼 늘어납니다.
    """
    series: list[dict] = []
    for m in metrics_list:
        series.extend(build_series(m))
    return len(series) if submit(series) else 0


def _warn(msg: str) -> None:
    sys.stderr.write(f"[o2warm] {msg}\n")
