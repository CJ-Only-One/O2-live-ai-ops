"""S3 목업 PG 장애 주입 제어면.

인터넷에 노출되는 ``/api`` 경로 아래에 있으므로 별도 ``x-admin-key`` 없이는
항상 거부한다. 설정은 모든 api 파드가 공유하는 Valkey에 저장하며, 비밀값이나
실제 결제 정보는 다루지 않는다.
"""

from typing import Literal

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field, model_validator

from app.core.admin_auth import require_admin_key
from app.core.config import settings
from app.services import payment

router = APIRouter()


class PgStubConfigOut(BaseModel):
    delay_ms: int
    fail_rate: float
    active: bool


class PgStubChangeIn(BaseModel):
    action: Literal["set", "clear"]
    delay_ms: int | None = Field(default=None, ge=0, le=payment.MAX_DELAY_MS)
    fail_rate: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def require_set_values(self):
        if self.action == "set" and (self.delay_ms is None or self.fail_rate is None):
            raise ValueError("set requires delay_ms and fail_rate")
        if self.action == "set" and self.fail_rate > 0 and self.delay_ms == 0:
            raise ValueError("PG_TIMEOUT injection requires delay_ms greater than 0")
        return self


class PgStubChangeOut(BaseModel):
    action: str
    previous: PgStubConfigOut
    current: PgStubConfigOut


def _out(config: payment.PgStubConfig) -> PgStubConfigOut:
    return PgStubConfigOut(
        delay_ms=config.delay_ms,
        fail_rate=config.fail_rate,
        active=config.active,
    )


@router.get("/admin/pg-stub", response_model=PgStubConfigOut)
def get_pg_stub(x_admin_key: str | None = Header(default=None)):
    require_admin_key(settings.PG_STUB_ADMIN_KEY, x_admin_key)
    # 운영 확인은 캐시가 아니라 Valkey 원본을 읽는다.
    return _out(payment.get_config(authoritative=True))


@router.post("/admin/pg-stub", response_model=PgStubChangeOut)
def change_pg_stub(
    body: PgStubChangeIn,
    x_admin_key: str | None = Header(default=None),
):
    require_admin_key(settings.PG_STUB_ADMIN_KEY, x_admin_key)
    previous = payment.get_config(authoritative=True)

    if body.action == "set":
        current = payment.set_config(
            delay_ms=body.delay_ms,
            fail_rate=body.fail_rate,
        )
    else:
        current = payment.clear_config()

    return PgStubChangeOut(
        action=body.action,
        previous=_out(previous),
        current=_out(current),
    )
