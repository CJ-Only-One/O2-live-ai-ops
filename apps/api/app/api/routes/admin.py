"""S3(docs/scenario-experiment.md 0.7) 조치 실행 — 읽기 경로 CPU 감소 노브.

`cfg:read_path_degraded:{broadcast_id}` 를 SET(조치)·DEL(원복) 한다.
`app/services/broadcast.py` 의 `_read_path_degraded()` 가 이 키를 읽어
`get_snapshot()` 의 `inventory.check` 발행을 건너뛴다 — 응답 내용(재고·가격)은
전혀 안 바뀌므로 사용자 차단은 0 이다(S3 는 "안 고르고 버티기"가 성공 기준).

apps/chat-gateway 의 `/ws/admin/channel-limit`(S1, D-061)과 같은 이유로
별도 실행기를 안 만든다 — api 가 이미 이 Valkey 에 붙어 있고 이미 FastAPI
라우터가 있다. 인증도 같은 방식 — Secrets Manager 를 안 거치고
`READ_PATH_DEGRADED_ADMIN_KEY` 를 kubectl 로 직접 넣는다.
"""

import hmac

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.db.valkey import valkey

router = APIRouter()


class ReadPathDegradedIn(BaseModel):
    broadcast_id: str
    action: str  # "set" | "clear"


class ReadPathDegradedOut(BaseModel):
    broadcast_id: str
    action: str
    previously_degraded: bool
    degraded: bool


def _degraded_key(broadcast_id: str) -> str:
    return f"cfg:read_path_degraded:{broadcast_id}"


def _authorize(x_admin_key: str | None) -> None:
    expected = settings.READ_PATH_DEGRADED_ADMIN_KEY
    if not expected or not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=403, detail="forbidden")


@router.post("/admin/read-path-degraded", response_model=ReadPathDegradedOut)
def set_read_path_degraded(
    body: ReadPathDegradedIn,
    x_admin_key: str | None = Header(default=None),
):
    _authorize(x_admin_key)

    if body.action not in ("set", "clear"):
        raise HTTPException(status_code=400, detail="action must be 'set' or 'clear'")

    key = _degraded_key(body.broadcast_id)
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
        degraded=body.action == "set",
    )
