from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import broadcasts, health
from app.core import errors
from app.core.config import settings

app = FastAPI(title=settings.APP_NAME)

# 계약의 오류 봉투로 응답하게 한다 (contracts.md 1.3).
errors.register(app)

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
