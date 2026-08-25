from typing import Annotated

from fastapi import APIRouter, Header, Response
from o2events.core import hash_key
from pydantic import UUID4

from app.core.errors import ApiError, openapi_errors
from app.schemas.common import OrderId
from app.schemas.order import OrderAccepted, OrderCreate, OrderStatus
from app.services import order as order_service

router = APIRouter()


@router.post(
    "/orders",
    response_model=OrderAccepted,
    status_code=202,
    responses=openapi_errors(
        "SOLD_OUT",
        "NOT_STARTED",
        "REQUEST_IN_PROGRESS",
        "PAYMENT_FAILED",
        "INVALID_REQUEST",
        "INTERNAL_ERROR",
    ),
)
def create_order(
    body: OrderCreate,
    response: Response,
    idempotency_key: Annotated[UUID4, Header(alias="Idempotency-Key")],
    session_key: Annotated[UUID4, Header(alias="X-Session-Key")],
):
    """주문 접수 (contracts.md 2.2).

    202 인 이유는 이 시점에 확정된 것이 재고 차감까지이기 때문이다.
    MySQL 기록은 SQS 를 거쳐 워커가 한다.
    """
    # 이벤트 SDK 미들웨어와 같은 함수·salt 로 파생한다. 원본 세션 키를 SQS나
    # MySQL에 넣으면 이벤트의 user_key와 조인할 수 없고 원본 식별자도 남는다.
    user_key = hash_key("u", str(session_key))
    if user_key is None:  # UUID4 검증을 통과했다면 일어날 수 없는 방어 분기다.
        raise ApiError("INTERNAL_ERROR", "사용자 식별자를 만들 수 없습니다")

    result = order_service.create_order(body, str(idempotency_key), user_key)
    response.status_code = 202
    return result


@router.get(
    "/orders/{order_id}",
    response_model=OrderStatus,
    responses=openapi_errors("INVALID_REQUEST", "NOT_FOUND", "INTERNAL_ERROR"),
)
def get_order(order_id: OrderId):
    """주문 상태 조회 (contracts.md 2.3).

    캐싱하지 않는다. 상태가 ACCEPTED 에서 CONFIRMED 로 바뀌는 구간을
    보는 것이 이 엔드포인트의 목적인데, 캐시가 그 변화를 가린다.
    """
    order = order_service.get_order(order_id)
    if order is None:
        raise ApiError("NOT_FOUND", "주문을 찾을 수 없습니다")
    return order
