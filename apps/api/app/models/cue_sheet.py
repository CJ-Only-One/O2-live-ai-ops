from sqlalchemy import Column, Index, Integer, String
from sqlalchemy.dialects.mysql import JSON

from app.db.session import Base
from app.models.types import DT3, NOW3


class CueSheet(Base):
    """방송 진행 대본. 언제 무슨 일이 있고 얼마나 몰릴지를 담아
    사전 확장(캐시 워밍·파드 증설)의 입력이 된다 (D-041, contracts/cue-sheet-v1).

    세그먼트를 테이블로 정규화하지 않는다. 워머가 실제로 던지는 질의는
    "앞으로 N분 안에 시작하는 세그먼트" 하나뿐이고, 세그먼트 스키마가
    아직 안 굳었다. 질의가 둘 이상 생기면 그때 뽑는다.
    """

    __tablename__ = "cue_sheets"

    # 방송당 큐시트 하나. broadcasts 와 외래 키를 걸지 않는다 —
    # products·orders 와 같은 저장소 규약(FK 대신 인덱스).
    broadcast_id = Column(String(32), primary_key=True)

    # 큐시트를 고칠 때마다 애플리케이션이 올린다. 신선도 판정의 근거다.
    cue_version = Column(Integer, nullable=False)

    # body 안에도 같은 값이 있다. 여기 따로 두는 이유는 워머가 매 tick
    # JSON 을 파싱하지 않고 이 컬럼으로 바로 "다가오는 방송" 을 거르기
    # 위해서다. api 가 유일한 쓰기 경로라 이중 값이 어긋날 위험이 없다.
    # 원본은 항상 body — 여기는 색인이지 진실이 아니다.
    scheduled_at = Column(DT3, nullable=False)
    ends_at = Column(DT3, nullable=True)

    # 큐시트 전체(contracts/cue-sheet-v1.schema.json). segments·baseline·
    # interpretation 을 통째로 담는다.
    body = Column(JSON, nullable=False)

    updated_at = Column(DT3, nullable=False, server_default=NOW3)

    # 워머의 유일한 질의 — 지금부터 N분 안에 시작하는 방송을 찾는다.
    __table_args__ = (Index("idx_scheduled_at", "scheduled_at"),)
