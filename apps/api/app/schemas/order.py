"""POST /api/orders 요청·응답 (contracts.md 2.2)."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import BroadcastId, OrderId, OrderState, SkuId


class OrderCreate(BaseModel):
    broadcast_id: BroadcastId
    # 계약상 문자열이다("88213"). 저장과 재고 키는 정수를 쓴다.
    sku_id: SkuId
    qty: int = Field(ge=1)


class OrderAccepted(BaseModel):
    order_id: OrderId
    # 이 시점의 상태는 항상 ACCEPTED 다. MySQL 기록은 워커가 하므로
    # CONFIRMED 는 여기서 나올 수 없다.
    state: Literal["ACCEPTED"] = "ACCEPTED"


class OrderStatus(BaseModel):
    order_id: OrderId
    # ACCEPTED / CONFIRMED / CANCELLED
    state: OrderState
    sku_id: SkuId
    qty: int = Field(ge=1)
