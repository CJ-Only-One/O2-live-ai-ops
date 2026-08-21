"""Hot Path 설정.

o2warm/settings.py 와 같은 규칙이다 — 값이 아니라 **출처 이름**만 담는다.
값을 환경변수로 넘기면 Lambda 콘솔과 Terraform state 에 평문으로 남는다.
조회는 secrets.py 가 실행 시점에 한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class HotSettings:
    region: str = field(
        default_factory=lambda: os.environ.get("AWS_REGION", "ap-northeast-2")
    )

    # --- Datadog ---
    # o2warm/o2-agg 가 읽는 것과 같은 시크릿(기본 o2/dev/datadog-new)이다.
    # 사본을 만들지 않는다 — 회전 때 한쪽만 바뀌면 증상을 알아채기 어렵다
    # (o2warm/secrets.py 모듈 docstring 참고).
    dd_secret: str = field(default_factory=lambda: os.environ.get("O2_DD_SECRET", ""))
    dd_secret_api_property: str = field(
        default_factory=lambda: os.environ.get("O2_DD_SECRET_API_PROPERTY", "api-key")
    )
    dd_secret_app_property: str = field(
        default_factory=lambda: os.environ.get("O2_DD_SECRET_APP_PROPERTY", "app-key")
    )
    # api-key 의 대안 경로. Secrets Manager 를 못 쓸 때만. app-key 는 대안이
    # 없다 — 이미 있는 시크릿에 두 속성이 함께 있어 새 파라미터를 또 만들
    # 이유가 없다.
    dd_api_param: str = field(default_factory=lambda: os.environ.get("O2_DD_API_PARAM", ""))
    dd_site: str = field(
        default_factory=lambda: os.environ.get("DD_SITE", "datadoghq.com")
    )
    dd_timeout: float = field(default_factory=lambda: _float("O2_DD_TIMEOUT", 8.0))

    # 조회 API 자체 인증은 없다 — Function URL 이 AWS_IAM(SigV4) 이라 AWS 가
    # Lambda 를 부르기 전에 이미 검증한다. handlers/serve.py 머리말 참고.


settings = HotSettings()
