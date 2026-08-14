from sqlalchemy import BigInteger, Column, Index, Integer, String

from app.db.session import Base
from app.models.types import DT3, NOW3


class Product(Base):
    """판매 상품.

    재고 컬럼이 없는 것은 누락이 아니다. 재고의 원본은 Valkey 의
    stock:{sku} 이고 MySQL 은 그것을 갖지 않는다 (D-07, architecture.md 4.5).
    응답의 stock_display 는 Valkey 에서 읽는다.
    """

    __tablename__ = "products"

    # 계약상 JSON 에서는 문자열이지만("88213") 저장은 정수다.
    # 직렬화 시점에 문자열로 바꾼다 (contracts.md 1.2).
    sku_id = Column(BigInteger, primary_key=True, autoincrement=False)

    # 어느 방송에 편성됐는지. 외래 키를 걸지 않는다 — 방송당 상품이 수십 건
    # 수준이라 참조 무결성보다 인덱스 하나가 싸고, orders 쪽과 규약을 맞춘다.
    broadcast_id = Column(String(32), nullable=False)

    name = Column(String(255), nullable=False)

    # 원가와 특가. 통화 단위는 원이라 소수점이 없어 정수로 둔다.
    # DECIMAL 이 필요해지면 그때 바꾼다.
    price = Column(Integer, nullable=False)
    sale_price = Column(Integer, nullable=False)

    # PENDING / ON_SALE / SOLD_OUT
    state = Column(String(16), nullable=False)

    created_at = Column(DT3, nullable=False, server_default=NOW3)

    # 스냅샷 조회가 방송 단위로만 들어온다 (contracts.md 2.1).
    __table_args__ = (Index("idx_broadcast", "broadcast_id"),)
