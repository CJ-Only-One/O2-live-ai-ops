"""GET /api/broadcasts/{broadcast_id} 응답 (contracts.md 2.1)."""

from pydantic import BaseModel

from app.schemas.common import (
    BroadcastId,
    BroadcastState,
    NonNegativeInt,
    ProductState,
    SkuId,
)


class ProductOut(BaseModel):
    # 계약상 문자열이다. 저장은 BIGINT 이므로 직렬화 시점에 바꾼다
    # (contracts.md 1.2).
    sku_id: SkuId
    name: str
    price: NonNegativeInt
    sale_price: NonNegativeInt

    # 표시용이며 주문 가부의 근거가 아니다. 판정은 항상 Valkey 의 DECR
    # 결과를 따른다 — "1개 남음" 이 몇 초 더 보이는 것은 정상 동작이다
    # (architecture.md 3.6).
    stock_display: NonNegativeInt

    # PENDING / ON_SALE / SOLD_OUT
    state: ProductState


class BroadcastOut(BaseModel):
    broadcast_id: BroadcastId

    # SCHEDULED / LIVE / ENDED
    state: BroadcastState

    # ISO 8601 UTC. 문자열로 담는 이유는 캐시에 넣는 값과 응답이
    # 같은 모양이어야 하기 때문이다.
    started_at: str | None
    hls_url: str | None
    products: list[ProductOut]
