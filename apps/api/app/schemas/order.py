"""POST /api/orders 요청·응답 (contracts.md 2.2)."""

from pydantic import BaseModel, Field


class OrderCreate(BaseModel):
    broadcast_id: str
    # 계약상 문자열이다("88213"). 저장과 재고 키는 정수를 쓴다.
    sku_id: str
    qty: int = Field(ge=1)


class OrderAccepted(BaseModel):
    order_id: str
    # 이 시점의 상태는 항상 ACCEPTED 다. MySQL 기록은 워커가 하므로
    # CONFIRMED 는 여기서 나올 수 없다.
    state: str = "ACCEPTED"
