# ── 의존성 빌더 ──────────────────────────────────────────────
# 스테이지를 나누는 이유는 git 때문이다. 이벤트 SDK 가 private 저장소에 있고,
# fine-grained PAT 은 codeload(github.com/.../archive/…)의 basic auth 를
# 받아주지 않아 404 가 난다. 문서가 보장하는 경로는 git over HTTPS 뿐이다.
#
# git 을 런타임 이미지에 두면 쓰지도 않는 도구가 취약점 표면으로 남으므로,
# 여기서만 설치하고 결과물만 넘긴다.
FROM python:3.12-slim AS deps

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# 토큰을 ARG 나 ENV 로 받지 않는다. 그렇게 하면 이미지 히스토리에 남아
# `docker history` 로 읽힌다. BuildKit 시크릿은 이 RUN 동안만 파일로
# 마운트되고 레이어에 기록되지 않는다.
#
# 커밋 SHA 로 고정한다. 저장소에 태그가 없어 브랜치로 두면 SDK 가 바뀔 때마다
# 우리 빌드 결과가 조용히 달라진다.
ARG SDK_REF=0f26876
RUN --mount=type=secret,id=sdk_token \
    pip install --no-cache-dir --prefix=/install \
    "o2events @ git+https://x-access-token:$(cat /run/secrets/sdk_token)@github.com/CJ-Only-One/o2-sdk-for-event.git@${SDK_REF}"

# ── 런타임 ───────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# 설치된 패키지와 콘솔 스크립트(uvicorn, alembic)를 통째로 가져온다.
# SDK 설치는 빌더 스테이지에서 끝났다 — 여기서 다시 받지 않는다.
COPY --from=deps /install /usr/local

COPY app ./app

# 마이그레이션은 같은 이미지로 K8s Job 이 돌린다 (alembic upgrade head).
# 이미지를 따로 만들면 파드가 쓰는 모델과 마이그레이션이 갈릴 수 있다.
COPY alembic.ini .
COPY migrations ./migrations

# 숫자 UID로 실행 (비root, K8s securityContext의 runAsNonRoot와 매칭)
RUN useradd -u 10001 -r appuser
USER 10001

EXPOSE 8000

# ddtrace-run 이 임포트를 가로채 FastAPI·SQLAlchemy·redis·boto3 를 계측한다.
# 코드에 임포트를 넣지 않는 이유는, 넣으면 계측을 끄려 할 때 이미지를 다시
# 빌드해야 하기 때문이다. 이 방식은 DD_TRACE_ENABLED=false 로 끌 수 있다.
#
# 에이전트에 못 붙어도 애플리케이션은 그대로 뜬다. 트레이스만 버려진다.
CMD ["ddtrace-run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
