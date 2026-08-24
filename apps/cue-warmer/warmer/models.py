"""cue_sheets 테이블 매핑. 읽기 전용.

**스키마 원본이 아니다.** 테이블 정의와 마이그레이션은 apps/api 가 소유하고
(apps/api/app/models/cue_sheet.py), 여기는 SELECT 에 필요한 컬럼만 적어둔
매핑이다. 공용 패키지로 빼지 않은 이유는 order-worker 의 models.py 와 같다
— CI 빌드 컨텍스트가 apps/<service> 라 서비스가 남의 폴더를 못 본다.
"""

from sqlalchemy import Column, String
from sqlalchemy.dialects.mysql import DATETIME, JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()

DT3 = DATETIME(fsp=3)


class CueSheet(Base):
    __tablename__ = "cue_sheets"

    broadcast_id = Column(String(32), primary_key=True)
    scheduled_at = Column(DT3, nullable=False)
    ends_at = Column(DT3, nullable=True)
    body = Column(JSON, nullable=False)
