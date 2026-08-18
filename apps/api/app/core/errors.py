"""계약이 정한 오류 봉투 (contracts.md 1.3).

    { "error": { "code": "SOLD_OUT", "message": "품절되었습니다" } }

FastAPI 의 HTTPException 을 그대로 쓰면 본문이 {"detail": ...} 로 감싸져
이 모양이 되지 않는다. code 는 기계가 읽고 message 는 사람이 읽는다 —
클라이언트는 message 로 분기하지 않으므로 문구는 바뀌어도 된다.
"""

import logging
from typing import Literal

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

ErrorCode = Literal[
    "SOLD_OUT",
    "NOT_STARTED",
    "RATE_LIMITED",
    "INVALID_REQUEST",
    "NOT_FOUND",
    "INTERNAL_ERROR",
]

# 계약이 정한 코드와 상태 코드의 대응. 여기 없는 코드를 쓰지 않는다.
STATUS = {
    "SOLD_OUT": 409,
    "NOT_STARTED": 409,
    "RATE_LIMITED": 429,
    "INVALID_REQUEST": 400,
    "NOT_FOUND": 404,
    "INTERNAL_ERROR": 500,
}


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code or STATUS.get(code, 500)
        super().__init__(message)


def openapi_errors(*codes: str | tuple[str, int]) -> dict:
    """라우트가 낼 수 있는 오류를 OpenAPI 명세에 실어준다.

    ApiError 는 FastAPI 가 아는 예외가 아니라서, 적어주지 않으면 생성된
    명세에 200 응답만 남는다. 클라이언트가 분기하는 근거는 code 인데
    (contracts.md 1.3) 그것이 명세에서 통째로 빠지는 셈이다.

    상태 코드는 STATUS 를 따른다. 계약에 없는 일회성 응답을 문서화해야 할 때만
    (code, status) 튜플로 덮어쓸 수 있다.

    상태 코드별로 묶는다 — 같은 409 라도 SOLD_OUT 과 NOT_STARTED 는
    다른 뜻이므로 둘 다 예시에 남긴다.
    """
    grouped: dict[int, list[str]] = {}
    for entry in codes:
        code, status = entry if isinstance(entry, tuple) else (entry, STATUS[entry])
        grouped.setdefault(status, []).append(code)

    return {
        status: {
            "description": " / ".join(group),
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "examples": {
                        code: {"value": {"error": {"code": code, "message": "..."}}}
                        for code in group
                    }
                }
            },
        }
        for status, group in grouped.items()
    }


def register(app) -> None:
    @app.exception_handler(ApiError)
    def _handle(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    def _handle_validation(_: Request, __: RequestValidationError) -> JSONResponse:
        # FastAPI 기본값은 422 + {"detail": ...} 이다. 계약은 형식 오류를
        # 400 INVALID_REQUEST 로 고정하므로 여기서 한 번에 변환한다.
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "요청 형식이 올바르지 않습니다",
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    def _handle_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            code = "NOT_FOUND"
        elif exc.status_code >= 500:
            code = "INTERNAL_ERROR"
        else:
            code = "INVALID_REQUEST"
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": str(exc.detail)}},
        )

    @app.exception_handler(Exception)
    def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # 알 수 없는 예외도 계약 봉투 밖으로 새지 않게 한다. 구체적인 예외
        # 문구는 내부 정보일 수 있으므로 응답에는 넣지 않고 로그에만 남긴다.
        logger.exception("처리되지 않은 API 예외", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "요청을 처리할 수 없습니다",
                }
            },
        )
