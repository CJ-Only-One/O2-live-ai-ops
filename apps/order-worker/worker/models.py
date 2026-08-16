"""orders 테이블 매핑.

**스키마 원본이 아니다.** 테이블 정의와 마이그레이션은 apps/api 가 소유하고,
여기는 INSERT 에 필요한 만큼만 적어둔 매핑이다. 그래서 이 서비스에서는
alembic autogenerate 를 돌리지 않는다 — 돌리면 여기 없는 컬럼을 DROP 하는
마이그레이션이 만들어진다.

공용 패키지로 빼지 않은 이유는 CI 의 빌드 컨텍스트가 apps/<service> 라
서비스가 남의 폴더를 못 보기 때문이다. 파이썬 서비스가 셋째가 되거나 스키마
변경이 잦아지면 그때 뽑는다.
"""

from sqlalchemy import CHAR, BigInteger, Column, Integer, String, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import declarative_base

Base = declarative_base()

DT3 = DATETIME(fsp=3)

# DB 의 DEFAULT CURRENT_TIMESTAMP(3) 를 모델에도 적어야 한다. 안 적으면
# SQLAlchemy 가 컬럼을 INSERT 문에 넣고 NULL 을 명시적으로 보내, 서버
# 기본값이 적용되지 않고 "cannot be null" 로 거부된다.
NOW3 = text("CURRENT_TIMESTAMP(3)")


class Order(Base):
    __tablename__ = "orders"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(String(32), nullable=False)

    # 워커 재처리 시 중복 주문을 막는 최종 방어선. SQS Standard 는 최소 1회
    # 전달이라 같은 메시지를 두 번 받는 것이 정상 동작 범위다.
    idem_key = Column(CHAR(36), nullable=False)

    broadcast_id = Column(String(32), nullable=False)
    sku_id = Column(BigInteger, nullable=False)
    user_key = Column(String(64), nullable=False)
    qty = Column(Integer, nullable=False)

    # 접수 시점에 API 가 확정한 값이다. 여기서 다시 조회하지 않는다 —
    # 큐가 밀린 사이 가격이 바뀌면 사용자가 본 금액과 달라진다.
    unit_price = Column(Integer, nullable=False)
    amount = Column(Integer, nullable=False)

    state = Column(String(16), nullable=False)
    created_at = Column(DT3, nullable=False, server_default=NOW3)
