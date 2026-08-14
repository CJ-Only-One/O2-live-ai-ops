from sqlalchemy import (
    CHAR,
    BigInteger,
    Column,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from app.db.session import Base
from app.models.types import DT3, NOW3


class Order(Base):
    """주문.

    architecture.md 4.4 의 정의를 계약(contracts.md 2.2·2.3)이 요구하는 만큼
    넓힌 것이다. 4.4 에는 state·order_id·broadcast_id 가 없는데 계약이 셋 다
    쓴다. AGENTS.md 규약대로 계약을 기준으로 맞췄다.

    외래 키를 걸지 않는다. 특가 오픈에 600 RPS 가 몰리는 경로라 부모 행에
    잠금이 잡히는 것을 피한다 (architecture.md 4.5 가 같은 이유로 MySQL 재고
    차감을 금지한다).
    """

    __tablename__ = "orders"

    # 내부 PK. architecture.md 4.4 의 정의를 그대로 둔다.
    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # 계약이 정한 공개 식별자 (od_ + ULID, contracts.md 1.2).
    # 내부 PK 를 노출하면 주문량이 밖에서 세어진다.
    order_id = Column(String(32), nullable=False)

    # 멱등 키. 클라이언트가 만든 UUID v4 다 (contracts.md 2.2).
    # SQS Standard 는 최소 1회 전달이라 워커 재처리가 정상 동작 범위이고,
    # 이 유니크 제약이 그때 중복 주문을 막는 최종 방어선이다. Valkey 의
    # idem:{key} 는 1차 방어선일 뿐 최종 판정은 여기서 난다.
    # UUID v4 는 길이가 고정이라 CHAR 다 (architecture.md 4.4).
    idem_key = Column(CHAR(36), nullable=False)

    broadcast_id = Column(String(32), nullable=False)
    sku_id = Column(BigInteger, nullable=False)

    # 로그인이 없다. 클라이언트가 만든 세션 토큰에서 파생한 HMAC 을 담는다 —
    # 이벤트 봉투의 user_key 와 같은 값이라 원본 식별자가 저장되지 않는다.
    user_key = Column(String(64), nullable=False)

    qty = Column(Integer, nullable=False)

    # ACCEPTED / CONFIRMED / CANCELLED (contracts.md 2.3).
    # POST /api/orders 가 202 로 돌려주는 시점은 ACCEPTED 이고,
    # CONFIRMED 로 바꾸는 것은 order-worker 다.
    state = Column(String(16), nullable=False)

    created_at = Column(DT3, nullable=False, server_default=NOW3)

    __table_args__ = (
        UniqueConstraint("idem_key", name="uk_idem"),
        UniqueConstraint("order_id", name="uk_order_id"),
        Index("idx_sku_created", "sku_id", "created_at"),
    )
