"""cue sheets

Revision ID: e22d7e31dc84
Revises: ccdd5120aa51
Create Date: 2026-08-24 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = 'e22d7e31dc84'
down_revision: Union[str, None] = 'ccdd5120aa51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cue_sheets',
        sa.Column('broadcast_id', sa.String(length=32), nullable=False),
        sa.Column('cue_version', sa.Integer(), nullable=False),
        # scheduled_at·ends_at 은 body 안에도 있다. 여기 따로 두는 이유는
        # "다가오는 세그먼트" 질의 하나 때문이다 — 워머가 매 tick JSON 을
        # 파싱해 방송을 거르지 않고 이 컬럼으로 바로 걸러낸다. api 만 쓰는
        # 유일한 인입 경로라 이중 쓰기 위험이 없다(schema.md 1절과 다른
        # 이유의 예외).
        sa.Column('scheduled_at', mysql.DATETIME(fsp=3), nullable=False),
        sa.Column('ends_at', mysql.DATETIME(fsp=3), nullable=True),
        # 큐시트 전체(segments·baseline·interpretation 포함). 세그먼트를
        # 테이블로 정규화하지 않는다 — 질의가 하나뿐이고 세그먼트 스키마가
        # 아직 안 굳었다.
        sa.Column('body', mysql.JSON(), nullable=False),
        sa.Column('updated_at', mysql.DATETIME(fsp=3), server_default=sa.text('CURRENT_TIMESTAMP(3)'), nullable=False),
        sa.PrimaryKeyConstraint('broadcast_id'),
    )
    op.create_index('idx_scheduled_at', 'cue_sheets', ['scheduled_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_scheduled_at', table_name='cue_sheets')
    op.drop_table('cue_sheets')
