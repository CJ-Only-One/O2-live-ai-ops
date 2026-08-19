from typing import Annotated

from fastapi import APIRouter, Header, Response

from app.core.errors import openapi_errors
from app.schemas.client_event import ClientEventAccepted, ClientEventBatch
from app.schemas.common import BroadcastId
from app.services import client_event as client_event_service

router = APIRouter()


@router.post(
    "/broadcasts/{broadcast_id}/events",
    response_model=ClientEventAccepted,
    status_code=202,
    responses=openapi_errors("INVALID_REQUEST", "INTERNAL_ERROR"),
)
def collect_client_events(
    broadcast_id: BroadcastId,
    body: ClientEventBatch,
    response: Response,
    user_agent: Annotated[str | None, Header()] = None,
):
    """클라이언트 행동 수집 (contracts.md 2.5).

    `broadcast_id` 를 경로에 두는 이유는 이벤트 봉투 때문이다. 봉투의
    `broadcast_id` 는 미들웨어가 **요청 경로에서** 뽑아 넣는다 — 본문을 읽는
    시점에는 컨텍스트가 이미 정해져 있어야 한다 (main.py 참고). 그래서 이
    인자는 여기서 쓰이지 않지만, 형식 검증과 OpenAPI 명세를 위해 선언한다.

    202 인 이유는 발행이 비동기이기 때문이다. 응답의 `accepted` 는 "발행을
    시도해 계약 검증까지 통과한 건수"이고, 스트림 도착을 보장하지 않는다.
    """
    accepted = client_event_service.collect(body.events, user_agent)
    response.status_code = 202
    return ClientEventAccepted(accepted=accepted)
