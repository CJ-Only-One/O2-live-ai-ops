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


def register(app) -> None:
    @app.exception_handler(ApiError)
    def _handle(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
