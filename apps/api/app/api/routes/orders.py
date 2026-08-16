from fastapi import APIRouter, Header, Request, Response

from app.core.errors import ApiError
from app.schemas.order import OrderAccepted, OrderCreate, OrderStatus
from app.services import order as order_service

router = APIRouter()


@router.post("/orders", response_model=OrderAccepted, status_code=202)
def create_order(
    body: OrderCreate,
    request: Request,
    response: Response,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
):
    """주문 접수 (contracts.md 2.2).

    202 인 이유는 이 시점에 확정된 것이 재고 차감까지이기 때문이다.
    MySQL 기록은 SQS 를 거쳐 워커가 한다.
    """
    if not idempotency_key:
        # 서버가 만들어주지 않는다. 서버가 만들면 클라이언트가 재시도할 때
        # 같은 키를 다시 보낼 수 없어 멱등성이 성립하지 않는다
        # (contracts.md 1.2).
        raise ApiError("INVALID_REQUEST", "Idempotency-Key 헤더가 필요합니다")

    # 로그인이 없다. 클라이언트가 만든 데모 세션 키로 사용자를 구분한다.
    user_key = request.headers.get("x-session-key", "")

    result = order_service.create_order(body, idempotency_key, user_key)
    response.status_code = 202
    return result


@router.get("/orders/{order_id}", response_model=OrderStatus)
def get_order(order_id: str):
    """주문 상태 조회 (contracts.md 2.3).

    캐싱하지 않는다. 상태가 ACCEPTED 에서 CONFIRMED 로 바뀌는 구간을
    보는 것이 이 엔드포인트의 목적인데, 캐시가 그 변화를 가린다.
    """
    order = order_service.get_order(order_id)
    if order is None:
        raise ApiError("INVALID_REQUEST", "주문을 찾을 수 없습니다", status_code=404)
    return order
