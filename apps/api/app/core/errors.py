"""계약이 정한 오류 봉투 (contracts.md 1.3).

    { "error": { "code": "SOLD_OUT", "message": "품절되었습니다" } }

FastAPI 의 HTTPException 을 그대로 쓰면 본문이 {"detail": ...} 로 감싸져
이 모양이 되지 않는다. code 는 기계가 읽고 message 는 사람이 읽는다 —
클라이언트는 message 로 분기하지 않으므로 문구는 바뀌어도 된다.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

# 계약이 정한 코드와 상태 코드의 대응. 여기 없는 코드를 쓰지 않는다.
STATUS = {
    "SOLD_OUT": 409,
    "NOT_STARTED": 409,
    "RATE_LIMITED": 429,
    "INVALID_REQUEST": 400,
    "INTERNAL_ERROR": 500,
}


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

    상태 코드는 STATUS 를 따르되, 라우트가 덮어쓰는 경우(없는 리소스에
    INVALID_REQUEST 를 404 로 내는 것)는 튜플로 적는다.

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
