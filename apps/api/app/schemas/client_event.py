"""클라이언트 행동 수집 요청 (contracts.md 2.5).

**자유 문자열을 받지 않는다.** 이 엔드포인트는 인터넷에 열려 있고, 여기로 들어온
값은 그대로 `client.action` 이 되어 에이전트가 읽는 저장소까지 간다. 본문을 실을
수 있게 하면 시청자 누구나 운영 에이전트에게 문장을 넣는 경로가 생긴다
(architecture.md 8.5 — `chat.send` 가 본문을 빼는 것과 같은 이유).

그래서 `action` 은 enum 이고 `target_id` 는 식별자 패턴으로 막는다. 둘 다
pydantic 이 400 으로 떨어뜨리므로 SDK 의 `SchemaError` 까지 가지 않는다.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

# SDK schemas.py 의 CLIENT_ACTION 과 같아야 한다. 값이 어긋나면 SDK 가
# SchemaError 를 내고 그 이벤트만 조용히 사라진다 — tests/test_client_events.py
# 의 드리프트 시험이 SDK 가 설치된 환경에서 이 집합을 비교한다.
ClientAction = Literal[
    "LIVE_ENTER",
    "LIVE_LEAVE",
    "COUPON_BUTTON_CLICK",
    "CHECKOUT_CLICK",
]

# sku_id·broadcast_id 같은 식별자만 담는다. 길이와 문자를 모두 좁힌다.
TargetId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class ClientActionIn(BaseModel):
    """행동 1건.

    `client_ts` 는 받지 않는다. 브라우저 시계는 조작할 수 있고, 집계는 어차피
    서버 도착 시각(`received_ts`)으로만 윈도우를 나눈다
    (`o2warm/windows.py` 머리말). 받아도 쓰이지 않는 값을 신뢰 경계 밖에서
    들여올 이유가 없다.
    """

    action: ClientAction
    target_id: TargetId | None = None


class ClientEventBatch(BaseModel):
    """한 요청에 여러 건.

    구매 버튼 한 번이 두 건(쿠폰·체크아웃)을 만들기 때문에 배열이 기본이다
    (contracts.md 5.2). 상한을 두는 것은 이 엔드포인트가 인증 없이 열려 있어서다.
    """

    events: Annotated[list[ClientActionIn], Field(min_length=1, max_length=20)]


class ClientEventAccepted(BaseModel):
    """발행에 성공한 건수. 요청 건수와 다를 수 있다 (services/client_event.py)."""

    accepted: int
