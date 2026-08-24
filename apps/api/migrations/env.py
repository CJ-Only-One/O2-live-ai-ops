from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.core.config import settings
from app.db.session import Base

# 모델을 import 해야 Base.metadata 에 테이블이 등록된다.
# 빠뜨리면 autogenerate 가 "지울 테이블"로 인식해 DROP 을 만들어낸다.
from app.models import broadcast, cue_sheet, order, product  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    """항상 writer 로 붙는다. 마이그레이션은 DDL 이라 리플리카로 갈 수 없다."""
    return settings.database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # 마이그레이션은 Job 으로 한 번 돌고 끝나므로 풀을 쓰지 않는다.
    # 애플리케이션의 엔진을 재사용하면 그 풀 설정(상한 5)에 묶인다.
    connectable = create_engine(_url(), poolclass=None, connect_args={"connect_timeout": 5})

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
