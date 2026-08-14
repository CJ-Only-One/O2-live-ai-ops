from sqlalchemy import Column, String

from app.db.session import Base
from app.models.types import DT3, NOW3


class Broadcast(Base):
    """방송 편성. contracts.md 2.1 진입 스냅샷의 상위 객체다."""

    __tablename__ = "broadcasts"

    # 계약이 정한 공개 식별자를 그대로 PK 로 쓴다 (bc_ + 숫자, contracts.md 1.2).
    # URL 에 드러나는 값이고 바뀌지 않으므로 내부 PK 를 따로 둘 이유가 없다.
    broadcast_id = Column(String(32), primary_key=True)

    # SCHEDULED / LIVE / ENDED. ENUM 을 쓰지 않는 이유는 값이 늘 때마다
    # MySQL 이 테이블을 다시 쓰기 때문이다. 검증은 애플리케이션이 한다.
    state = Column(String(16), nullable=False)

    started_at = Column(DT3, nullable=True)

    # MediaMTX 가 리패키징한 HLS 를 CloudFront 가 서빙한다 (architecture.md 2.1).
    # 도메인이 바뀔 수 있으므로 전체 URL 을 담는다.
    hls_url = Column(String(512), nullable=True)

    created_at = Column(DT3, nullable=False, server_default=NOW3)
