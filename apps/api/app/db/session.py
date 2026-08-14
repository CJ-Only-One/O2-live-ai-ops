from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

# 풀 상한을 명시한다. 기본값(5 + overflow 10)이면 파드 하나가 최대 15개를 잡고,
# 파드가 늘어나면 db.t4g.micro 의 max_connections 에 먼저 닿는다 (R-06).
#
# connect_timeout 이 없으면 DB 가 응답하지 않을 때 연결 시도가 그대로 매달린다.
# readyz 는 동기 핸들러라 스레드풀을 물고 있게 되고, 그 고갈은 health 까지
# 같이 죽여 liveness 가 파드를 재시작시킨다 — readiness/liveness 를 나눈 의미가
# 사라지므로 짧게 끊는다.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    connect_args={"connect_timeout": 2},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
