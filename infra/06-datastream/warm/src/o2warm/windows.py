"""10초 윈도우 계산과 봉투 해석.

**시각은 항상 received_ts 를 씁니다.** event_ts 는 발행 측 시계이고
client_ts 는 브라우저 시계라 조작될 수 있습니다. 요청 간격의 규칙성으로
매크로를 감별하는 지표에 조작 가능한 시계를 쓸 수는 없습니다.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from . import contract as C
from .settings import settings

WINDOW_SECONDS = settings.window_seconds
CLIENT_PREFIXES = C.CLIENT_PREFIXES


def parse_ts(value: str | None) -> float | None:
    """ISO8601 밀리초 UTC → epoch 초. 계약 밖 형식이면 None."""
    if not value:
        return None
    try:
        # 'Z' 는 fromisoformat 이 3.11 부터만 받으므로 직접 치환합니다.
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        ).timestamp()
    except (ValueError, TypeError):
        return None


def event_epoch(env: dict) -> float:
    """윈도우 배정에 쓸 시각. received_ts → event_ts → 현재 순으로 내려갑니다."""
    return (
        parse_ts(env.get(C.E_RECEIVED_TS))
        or parse_ts(env.get(C.E_EVENT_TS))
        or time.time()
    )


def window_start(epoch: float, size: int = WINDOW_SECONDS) -> int:
    return int(epoch // size) * size


def is_client(env: dict) -> bool:
    return str(env.get(C.E_EVENT_NAME, "")).startswith(CLIENT_PREFIXES)


def service_of(env: dict) -> str:
    """이 이벤트를 어느 서비스의 윈도우에 넣을 것인가.

    비즈니스 이벤트는 발행 서비스 그대로입니다.
    클라이언트 이벤트는 '뒤이어 호출될 서비스'로 보냅니다 — 그래야 클릭과
    서버 요청이 같은 윈도우에 모여 click_ratio 가 계산됩니다.
    """
    if not is_client(env):
        return str(env.get(C.E_SERVICE) or "unknown")

    action = (env.get(C.E_PAYLOAD) or {}).get(C.F_ACTION)
    return settings.click_route.get(action) or settings.client_service


def iso_now() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def iso_from_epoch(epoch: float) -> str:
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def group_by_window(envelopes: list[dict]) -> dict[tuple[str, int], list[dict]]:
    """(service, window_start) 로 이벤트를 묶습니다.

    한 Lambda 배치가 윈도우 경계를 걸치는 것은 정상이며, 그때는 두 개의
    그룹이 나옵니다. 각각 별도 아이템에 병합됩니다.
    """
    out: dict[tuple[str, int], list[dict]] = {}
    for env in envelopes:
        key = (service_of(env), window_start(event_epoch(env)))
        out.setdefault(key, []).append(env)
    return out
