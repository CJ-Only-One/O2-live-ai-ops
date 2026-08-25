"""S3(docs/scenario-experiment.md 0.7) 조치 실행 — 읽기 경로 CPU 감소 노브.

`cfg:read_path_degraded:{broadcast_id}` 를 SET(조치)·DEL(원복) 한다.
`app/services/broadcast.py` 의 `_read_path_degraded()` 가 이 키를 읽어
`get_snapshot()` 의 `inventory.check` 발행을 건너뛴다 — 응답 내용(재고·가격)은
전혀 안 바뀌므로 사용자 차단은 0 이다(S3 는 "안 고르고 버티기"가 성공 기준).

apps/chat-gateway 의 `/ws/admin/channel-limit`(S1, D-061)과 같은 이유로
별도 실행기를 안 만든다 — api 가 이미 이 Valkey 에 붙어 있고 이미 FastAPI
라우터가 있다. 인증도 같은 방식 — Secrets Manager 를 안 거치고
`READ_PATH_DEGRADED_ADMIN_KEY` 를 kubectl 로 직접 넣는다.

★ 키 포맷(`degraded_key`)은 `app/services/broadcast.py` 것을 그대로
  import 해서 쓴다. 여기서 따로 만들면 한쪽만 고쳤을 때 SET 은 되는데
  읽기 쪽은 못 찾는 조용한 불일치가 생긴다.
"""

from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, model_validator

from app.core.admin_auth import require_admin_key
from app.core.config import settings
from app.db.valkey import valkey
from app.schemas.common import BroadcastId
from app.services import payment
from app.services.broadcast import degraded_key

router = APIRouter()


class ReadPathDegradedIn(BaseModel):
    broadcast_id: BroadcastId
    action: Literal["set", "clear"]


class ReadPathDegradedOut(BaseModel):
    broadcast_id: str
    action: str
    previously_degraded: bool


class ReadPathDegradedStatusOut(BaseModel):
    broadcast_id: str
    read_path_degraded_active: bool


@router.get("/admin/read-path-degraded", response_model=ReadPathDegradedStatusOut)
def get_read_path_degraded(
    broadcast_id: BroadcastId,
    x_admin_key: str | None = Header(default=None),
):
    require_admin_key(settings.READ_PATH_DEGRADED_ADMIN_KEY, x_admin_key)
    return ReadPathDegradedStatusOut(
        broadcast_id=broadcast_id,
        read_path_degraded_active=bool(valkey.get(degraded_key(broadcast_id))),
    )


@router.post("/admin/read-path-degraded", response_model=ReadPathDegradedOut)
def set_read_path_degraded(
    body: ReadPathDegradedIn,
    x_admin_key: str | None = Header(default=None),
):
    require_admin_key(settings.READ_PATH_DEGRADED_ADMIN_KEY, x_admin_key)

    key = degraded_key(body.broadcast_id)
    # Precheck 재확인 — patch 전에 현재 값을 다시 읽어 응답에 같이 싣는다.
    previously_degraded = bool(valkey.get(key))

    if body.action == "set":
        valkey.set(key, "1")
    else:
        valkey.delete(key)

    return ReadPathDegradedOut(
        broadcast_id=body.broadcast_id,
        action=body.action,
        previously_degraded=previously_degraded,
    )


# S3 재설계(2026-08-25) 조치 — "외부 PG(결제 게이트웨이)가 느리다/안 붙는다"에
# 우리 쪽에서 할 수 있는 조치들이다. 아래 셋(circuit/timeout/retry)은 방어적
# 조치라 PG-A 자체가 느린 근본 원인은 못 고친다. 그래서 넷째로 pg-provider-switch
# 를 추가한다 — 실제 PG 연동을 새로 만드는 게 아니라(그건 architecture.md 0.2
# 스코프 밖 그대로다), 이미 있는 목업 PG 스텁(payment.py)의 활성 provider를
# PG-A에서 PG-B로 바꿔서 "다른 게이트웨이로 우회했다"를 재현한다(2026-08-25
# 회의 결정 — S3는 방어 조치만으로 끝나지 않고 재발 시 실제로 해결되는
# 시나리오로 간다). 결제 경로를 바꾸는 조치라 L3로 등록하고 Slack 승인 뒤에만
# 실행한다(seed_runbook.py).

class PgCircuitOpenIn(BaseModel):
    service: str
    action: Literal["set", "clear"]
    ttl_seconds: int = 60


class PgCircuitOpenOut(BaseModel):
    service: str
    action: str
    previously_open: bool


@router.post("/admin/pg-circuit-open", response_model=PgCircuitOpenOut)
def set_pg_circuit_open(
    body: PgCircuitOpenIn,
    x_admin_key: str | None = Header(default=None),
):
    require_admin_key(settings.READ_PATH_DEGRADED_ADMIN_KEY, x_admin_key)

    key = f"cfg:pg_circuit_open:{body.service}"
    previously_open = bool(valkey.get(key))

    if body.action == "set":
        valkey.set(key, "1", ex=body.ttl_seconds)
    else:
        valkey.delete(key)

    return PgCircuitOpenOut(
        service=body.service,
        action=body.action,
        previously_open=previously_open,
    )


class PgTimeoutTightenIn(BaseModel):
    service: str
    action: Literal["set", "clear"]
    timeout_ms: int = 800


class PgTimeoutTightenOut(BaseModel):
    service: str
    action: str
    previous_timeout_ms: int | None


@router.post("/admin/pg-timeout-tighten", response_model=PgTimeoutTightenOut)
def set_pg_timeout_tighten(
    body: PgTimeoutTightenIn,
    x_admin_key: str | None = Header(default=None),
):
    require_admin_key(settings.READ_PATH_DEGRADED_ADMIN_KEY, x_admin_key)

    key = f"cfg:pg_timeout_ms:{body.service}"
    raw = valkey.get(key)
    previous_timeout_ms = int(raw) if raw else None

    if body.action == "set":
        valkey.set(key, str(body.timeout_ms))
    else:
        valkey.delete(key)

    return PgTimeoutTightenOut(
        service=body.service,
        action=body.action,
        previous_timeout_ms=previous_timeout_ms,
    )


class PgRetryBackoffIn(BaseModel):
    service: str
    action: Literal["set", "clear"]
    backoff_ms: int = 2000


class PgRetryBackoffOut(BaseModel):
    service: str
    action: str
    previous_backoff_ms: int | None


@router.post("/admin/pg-retry-backoff", response_model=PgRetryBackoffOut)
def set_pg_retry_backoff(
    body: PgRetryBackoffIn,
    x_admin_key: str | None = Header(default=None),
):
    require_admin_key(settings.READ_PATH_DEGRADED_ADMIN_KEY, x_admin_key)

    key = f"cfg:pg_retry_backoff_ms:{body.service}"
    raw = valkey.get(key)
    previous_backoff_ms = int(raw) if raw else None

    if body.action == "set":
        valkey.set(key, str(body.backoff_ms))
    else:
        valkey.delete(key)

    return PgRetryBackoffOut(
        service=body.service,
        action=body.action,
        previous_backoff_ms=previous_backoff_ms,
    )


class PgProviderSwitchIn(BaseModel):
    action: Literal["set", "clear", "set_pg_b_ready"]
    pg_b_ready: bool | None = None

    @model_validator(mode="after")
    def validate_action_arguments(self):
        if self.action == "set_pg_b_ready" and self.pg_b_ready is None:
            raise ValueError("set_pg_b_ready requires pg_b_ready")
        if self.action != "set_pg_b_ready" and self.pg_b_ready is not None:
            raise ValueError("pg_b_ready is only valid for set_pg_b_ready")
        return self


class PgProviderSwitchOut(BaseModel):
    action: str
    previous_provider: str
    provider: str
    pg_b_ready: bool
    already_in_target_state: bool


class PgProviderSwitchStatusOut(BaseModel):
    provider: str
    pg_b_ready: bool
    pg_a_injection_active: bool


@router.get("/admin/pg-provider-switch", response_model=PgProviderSwitchStatusOut)
def get_pg_provider_switch(x_admin_key: str | None = Header(default=None)):
    require_admin_key(settings.READ_PATH_DEGRADED_ADMIN_KEY, x_admin_key)
    current = payment.get_config(authoritative=True)
    return PgProviderSwitchStatusOut(
        provider=current.active_provider,
        pg_b_ready=current.pg_b_ready,
        pg_a_injection_active=current.active,
    )


@router.post("/admin/pg-provider-switch", response_model=PgProviderSwitchOut)
def set_pg_provider_switch(
    body: PgProviderSwitchIn,
    x_admin_key: str | None = Header(default=None),
):
    require_admin_key(settings.READ_PATH_DEGRADED_ADMIN_KEY, x_admin_key)

    previous = payment.get_config(authoritative=True)
    already_in_target_state = False
    if body.action == "set_pg_b_ready":
        try:
            current = payment.set_pg_b_ready(body.pg_b_ready)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        already_in_target_state = previous.pg_b_ready == current.pg_b_ready
    elif body.action == "set":
        if not previous.pg_b_ready:
            raise HTTPException(status_code=409, detail="PG-B is not ready")
        if previous.active_provider == "PG-B":
            current = previous
            already_in_target_state = True
        elif previous.active_provider != "PG-A":
            raise HTTPException(status_code=409, detail="active provider is not PG-A")
        else:
            current = payment.set_active_provider("PG-B")
    else:
        if previous.active_provider == "PG-A":
            if previous.active:
                raise HTTPException(
                    status_code=409,
                    detail="cannot confirm rollback while PG-A injection is active",
                )
            current = previous
            already_in_target_state = True
        elif previous.active_provider != "PG-B":
            raise HTTPException(status_code=409, detail="active provider is not PG-B")
        elif previous.active:
            raise HTTPException(
                status_code=409,
                detail="cannot roll back while PG-A injection is active",
            )
        else:
            current = payment.clear_active_provider()

    return PgProviderSwitchOut(
        action=body.action,
        previous_provider=previous.active_provider,
        provider=current.active_provider,
        pg_b_ready=current.pg_b_ready,
        already_in_target_state=already_in_target_state,
    )
