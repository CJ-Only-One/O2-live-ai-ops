import logging

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.db.session import engine
from app.db.valkey import valkey

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health():
    """liveness. 프로세스 생존만 본다.

    여기서 의존성을 검사하면 DB 가 잠깐 끊겼을 때 전 파드가 재시작 루프에
    빠진다 (docs/architecture.md 9.4-4). 검사는 readyz 가 한다.
    """
    return {"status": "ok"}


@router.get("/readyz")
def readyz(response: Response):
    """readiness. 의존성이 닿는지 본다. 하나라도 실패하면 503.

    이 경로는 ALB 를 통해 인터넷에서 호출된다 (ingress 가 /api 를 통째로
    넘긴다). 그래서 호스트명이나 예외 문구를 응답에 담지 않는다 —
    어느 의존성인지만 불리언으로 알린다. 원인은 로그에 남긴다.
    """
    checks = {"mysql": False, "valkey": False}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["mysql"] = True
    except Exception:
        logger.exception("readyz: MySQL 연결 실패")

    try:
        valkey.ping()
        checks["valkey"] = True
    except Exception:
        logger.exception("readyz: Valkey 연결 실패")

    if not all(checks.values()):
        response.status_code = 503
        return {"status": "degraded", **checks}

    return {"status": "ok", **checks}
