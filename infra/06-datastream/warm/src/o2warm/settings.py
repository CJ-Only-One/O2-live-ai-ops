"""Warm Path 설정.

SDK쪽 config와 분리했습니다. 이벤트를 '보내는' 쪽과 '집계하는' 쪽은
배포 단위가 다르고, 서비스 파드에 Datadog 키나 DynamoDB 테이블명이
들어갈 이유가 없기 때문입니다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from . import contract as C


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _json(name: str, default):
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


# 클릭이 어느 서비스의 요청으로 이어지는가.
#
# 클라이언트 이벤트는 수집 Lambda가 발행하므로 envelope의 service가
# 'web-collector' 같은 값이 됩니다. 그대로 두면 클릭과 서버 요청이
# 서로 다른 윈도우 아이템에 들어가 click_ratio를 계산할 수 없습니다.
# 그래서 action을 보고 대상 서비스로 라우팅합니다.
CLICK_ROUTE_DEFAULT = {
    C.ACTION_COUPON_CLICK: "coupon-api",
    C.ACTION_CHECKOUT_CLICK: "order-api",
}

# click_ratio 를 만드는 (클릭 action, 서버 이벤트) 짝.
CLICK_PAIRS = {
    "coupon": (C.ACTION_COUPON_CLICK, C.EVENT_COUPON),
    "checkout": (C.ACTION_CHECKOUT_CLICK, C.EVENT_ORDER_CREATE),
}


@dataclass
class WarmSettings:
    # --- 저장소 ---
    table: str = field(
        default_factory=lambda: os.environ.get("O2_WARM_TABLE", "o2-agent-context")
    )
    region: str = field(
        default_factory=lambda: os.environ.get("AWS_REGION", "ap-northeast-2")
    )

    # --- 윈도우 ---
    window_seconds: int = field(default_factory=lambda: _int("O2_WARM_WINDOW", 10))
    metric_ttl_days: int = field(default_factory=lambda: _int("O2_WARM_METRIC_TTL_DAYS", 7))
    sketch_ttl_minutes: int = field(
        default_factory=lambda: _int("O2_WARM_SKETCH_TTL_MIN", 60)
    )

    # --- 부분 집계 상한 ---
    # 아이템 400KB 한도와 Lambda 128MiB 안에서 안전한 크기입니다.
    # 넘치면 잘라내되 confidence.completeness 를 떨어뜨려 알립니다.
    user_capacity: int = field(default_factory=lambda: _int("O2_WARM_USER_CAP", 256))
    interval_capacity: int = field(default_factory=lambda: _int("O2_WARM_IV_CAP", 256))
    distinct_capacity: int = field(default_factory=lambda: _int("O2_WARM_DISTINCT_CAP", 512))
    # 세그먼트 축 하나당 보관할 값의 개수.
    #
    # 다른 절단 구조와 달리 이건 **늦게 나타난 값을 통째로 버립니다**
    # (Space-Saving 처럼 큰 것을 살리지 않습니다). 그래서 상한을 넉넉히
    # 잡습니다 — 12,000 이벤트·캠페인 30개 실측에서 아이템이 8.4KB,
    # DynamoDB 한도의 2% 수준이라 여유가 큽니다.
    segment_capacity: int = field(default_factory=lambda: _int("O2_WARM_SEGMENT_CAP", 48))

    # --- 세그먼트 편차 판정 ---
    # 표본이 적으면 비율이 노이즈라 편차로 보지 않습니다.
    segment_min_samples: int = field(default_factory=lambda: _int("O2_WARM_SEG_MIN_N", 20))
    segment_min_lift: float = field(default_factory=lambda: _float("O2_WARM_SEG_MIN_LIFT", 1.8))

    # --- 평시 기준 ---
    baseline_alpha: float = field(default_factory=lambda: _float("O2_WARM_EWMA_ALPHA", 0.05))
    baseline_min_samples: int = field(
        default_factory=lambda: _int("O2_WARM_BASELINE_MIN", 30)
    )

    # --- 클라이언트 이벤트 라우팅 ---
    client_service: str = field(
        default_factory=lambda: os.environ.get("O2_WARM_CLIENT_SERVICE", "live-web")
    )
    click_route: dict = field(
        default_factory=lambda: _json("O2_WARM_CLICK_ROUTE", CLICK_ROUTE_DEFAULT)
    )

    # --- 세그먼트 축 ---
    # [[축 이름, "payload" 또는 "envelope"], ...] 형태로 재정의 가능합니다.
    segment_axes: tuple = field(
        default_factory=lambda: tuple(
            tuple(a) for a in _json("O2_WARM_SEGMENT_AXES", list(C.SEGMENT_AXES))
        )
    )

    # --- Datadog ---
    # 아래 셋은 **키가 어디 있는지**만 담습니다. 값 자체를 환경변수로 주면
    # Terraform state 와 Lambda 콘솔에 평문으로 남습니다. 조회는 secrets.py 가
    # 실행 시점에 합니다.
    dd_api_key: str = field(
        default_factory=lambda: os.environ.get("O2_DD_API_KEY")
        or os.environ.get("DD_API_KEY", "")
    )
    # 이 저장소의 원본. 04-platform 이 ESO 로 Agent 에 넣는 것과 같은 시크릿이라
    # 사본이 생기지 않고, 회전하면 Agent 와 Lambda 가 함께 바뀝니다.
    dd_secret: str = field(default_factory=lambda: os.environ.get("O2_DD_SECRET", ""))
    dd_secret_property: str = field(
        default_factory=lambda: os.environ.get("O2_DD_SECRET_PROPERTY", "api-key")
    )
    # 대안 경로. Secrets Manager 를 쓸 수 없을 때만 씁니다.
    dd_param: str = field(default_factory=lambda: os.environ.get("O2_DD_PARAM", ""))
    dd_site: str = field(
        default_factory=lambda: os.environ.get("DD_SITE", "datadoghq.com")
    )
    dd_prefix: str = field(
        default_factory=lambda: os.environ.get("O2_DD_PREFIX", "o2.warm.")
    )
    dd_timeout: float = field(default_factory=lambda: _float("O2_DD_TIMEOUT", 2.0))
    dd_env: str = field(default_factory=lambda: os.environ.get("DD_ENV", "prod"))

    # --- 조회 API ---
    # 값을 직접 넣는 경로(api_key)는 남겨 두지만 배포에는 쓰지 않습니다.
    # Function URL 은 인터넷에 바로 붙으므로 이 키가 state 에 남으면
    # state 를 읽을 수 있는 주체가 곧 엔드포인트 권한을 갖습니다.
    api_key: str = field(default_factory=lambda: os.environ.get("O2_WARM_API_KEY", ""))
    api_key_param: str = field(
        default_factory=lambda: os.environ.get("O2_WARM_API_KEY_PARAM", "")
    )
    max_windows: int = field(default_factory=lambda: _int("O2_WARM_MAX_WINDOWS", 60))

    @property
    def datadog_configured(self) -> bool:
        return bool(self.dd_api_key or self.dd_secret or self.dd_param)

    @property
    def api_auth_configured(self) -> bool:
        return bool(self.api_key or self.api_key_param)


settings = WarmSettings()
