"""클라이언트 행동을 `client.action` 으로 발행한다 (contracts.md 2.5 · 5.1).

브라우저가 Kinesis 에 직접 쓸 수는 없다 — 자격증명을 번들에 넣어야 하기 때문이다.
그래서 api 가 수집 지점이 된다. SDK 의 `_stream_for()` 가 `client.*` 를
`stream-client` 로 보내므로, 여기서 스트림 이름을 다루지 않는다.

**봉투는 미들웨어가 채운다.** `user_key`(X-Session-Key), `client_ip_key`,
`broadcast_id`(경로) 는 `main.py` 의 `install_fastapi` 가 요청 컨텍스트에
넣어둔 값이 실린다. 여기서 넘기는 것은 payload 뿐이다.
"""

import logging
import re

from o2events import emit
from o2events.core import hash_key

from app.schemas.client_event import ClientActionIn

logger = logging.getLogger(__name__)

# 기기 구분은 서버가 판정한다. 클라이언트가 보낸 값을 그대로 실으면 세그먼트
# 축(device_type)이 조작 가능해지고, "모바일만 실패한다" 같은 판단이 흔들린다.
_MOBILE = re.compile(r"Android|iPhone|iPad|iPod|Windows Phone|Mobile", re.IGNORECASE)


def device_type_of(user_agent: str | None) -> str:
    """SDK schemas.py 의 DEVICE_TYPE 중 하나.

    `MOBILE_APP` 은 쓰지 않는다. 앱이 없고, 웹에서 앱을 구분할 방법도 없다.
    UA 가 없으면(헤더 누락) 데스크톱으로 본다 — 판정 불가를 나타내는 값이
    계약에 없어서, 없는 값을 만드는 대신 다수 쪽으로 떨어뜨린다.
    """
    if user_agent and _MOBILE.search(user_agent):
        return "MOBILE_WEB"
    return "PC_WEB"


def collect(events: list[ClientActionIn], user_agent: str | None) -> int:
    """발행하고 성공 건수를 돌려준다.

    발행 실패가 사용자 요청을 실패시키면 안 된다 (contracts.md 5.1). 화면에서
    보면 이 호출은 계측일 뿐이고, 계측이 화면을 죽이는 것은 언제나 손해다.
    """
    device_type = device_type_of(user_agent)

    # ua_diversity 의 분자다. 원본 UA 는 스트림에 넣지 않는다 — 사용자 키·IP 와
    # 같은 salt·같은 방식으로 가명화한다 (SDK core.hash_key).
    ua_key = hash_key("ua", user_agent)

    accepted = 0
    for event in events:
        try:
            emit.client_action(
                action=event.action,
                target_id=event.target_id,
                device_type=device_type,
                ua_key=ua_key,
            )
        except Exception:
            logger.exception("client.action 발행 실패 (action=%s)", event.action)
            continue
        accepted += 1

    return accepted
