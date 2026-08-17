from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from o2events.middleware import install_fastapi

from app.api.routes import broadcasts, health, orders
from app.core import errors
from app.core.config import settings

# 문서 경로도 /api 아래에 둔다. FastAPI 기본값은 /docs 인데, ALB 가 그 경로를
# 프론트엔드로 보내기 때문에 SPA 의 index.html 이 대신 나온다.
app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "라이브커머스 주문·조회 API. 이 문서는 코드에서 생성된다.\n\n"
        "설계 계약(왜 이런 모양인지, WebSocket·캐시 키·이벤트 규격)은 "
        "`docs/contracts.md` 가 원본이고, 어긋나면 그쪽이 맞다."
    ),
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

# 계약의 오류 봉투로 응답하게 한다 (contracts.md 1.3).
errors.register(app)

# 이벤트 봉투에 사용자·IP·trace 를 자동으로 담게 한다. 서비스당 한 번이면 되고,
# 이후 emit 호출은 도메인 값만 넘긴다.
#
# 로그인이 없으므로 사용자 식별은 클라이언트가 만든 데모 세션 키를 쓴다.
# SDK 가 이 값을 그대로 저장하지 않고 HMAC 으로 바꿔 봉투에 담는다.
install_fastapi(app, user_id_getter=lambda r: r.headers.get("x-session-key"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우트는 /api 접두사 아래에만 둔다. ALB 하나를 프론트엔드와 공유하는데,
# ALB는 nginx와 달리 경로를 벗겨내지 않고 그대로 넘기기 때문이다.
# 규약은 docs/contracts.md 1.1.
app.include_router(health.router, prefix="/api")
app.include_router(broadcasts.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
