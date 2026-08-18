"""REST 계약에서 공통으로 쓰는 식별자와 상태 타입."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints


BroadcastId = Annotated[
    str,
    StringConstraints(pattern=r"^bc_[0-9]+$"),
]
SkuId = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9]+$"),
]
OrderId = Annotated[
    str,
    StringConstraints(pattern=r"^od_[0-9A-HJKMNP-TV-Z]{26}$"),
]

BroadcastState = Literal["SCHEDULED", "LIVE", "ENDED"]
ProductState = Literal["PENDING", "ON_SALE", "SOLD_OUT"]
OrderState = Literal["ACCEPTED", "CONFIRMED", "CANCELLED"]

# 금액과 표시 재고는 음수가 될 수 없다. 주문 가능 여부는 stock_display 가 아니라
# 주문 API의 Valkey DECR 결과가 정한다.
NonNegativeInt = Annotated[int, Field(ge=0)]
