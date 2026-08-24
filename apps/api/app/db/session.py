from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings
from app.core.telemetry import telemetry

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

# 읽기 전용 조회용. 리드 리플리카가 없는 동안에는 writer 와 같은 주소가 오므로
# 지금은 커넥션만 나뉜다. 리플리카를 켜는 순간 코드를 안 고쳐도 읽기가 분산된다
# (architecture.md 4.2).
#
# 쓰기 직후 조회는 여기로 보내지 않는다. 리플리카는 비동기 복제라
# "주문 없음" 이 나갈 수 있다.
reader_engine = create_engine(
    settings.reader_database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    connect_args={"connect_timeout": 2},
)
ReaderSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=reader_engine)


def _observe_pool(pool, role: str) -> None:
    telemetry.db_pool(
        role,
        active=pool.checkedout(),
        idle=pool.checkedin(),
        overflow=pool.overflow(),
    )


for _engine, _role in ((engine, "writer"), (reader_engine, "reader")):
    event.listen(_engine.pool, "checkout", lambda *args, p=_engine.pool, r=_role: _observe_pool(p, r))
    event.listen(_engine.pool, "checkin", lambda *args, p=_engine.pool, r=_role: _observe_pool(p, r))

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_reader_db():
    db = ReaderSessionLocal()
    try:
        yield db
    finally:
        db.close()
