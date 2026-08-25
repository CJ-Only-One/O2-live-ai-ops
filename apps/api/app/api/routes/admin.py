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

from fastapi import APIRouter, Header
from pydantic import BaseModel

from app.core.admin_auth import require_admin_key
from app.core.config import settings
from app.db.valkey import valkey
from app.schemas.common import BroadcastId
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


# S3 재설계(2026-08-25) 조치 3개 — "외부 PG(결제 게이트웨이)가 느리다/안 붙는다"에
# 우리 쪽에서 방어적으로 할 수 있는 조치만 담는다. 결제 게이트웨이 연동 자체는
# architecture.md 0.2 "이 문서가 다루지 않는 것"으로 스코프 밖이라, PG 자체를
# 실제로 고치는 조치(예: 리드 리플리카 failover)는 만들지 않는다 — 우리가
# 소유하지 않은 인프라라 개념적으로 성립하지 않는다. 여기 셋은 real Valkey
# 노브라 실제로 켜지고 원복되지만, 읽는 실제 결제 호출 경로가 없어서 근본
# 원인(PG 자체가 느림)은 못 고친다 — 그게 이 시나리오의 요지다.

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
