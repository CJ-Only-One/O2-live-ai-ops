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
ARG SDK_REF=4792fca
RUN --mount=type=secret,id=sdk_token \
    pip install --no-cache-dir --prefix=/install \
    "o2events @ git+https://x-access-token:$(cat /run/secrets/sdk_token)@github.com/CJ-Only-One/o2-sdk-for-event.git@${SDK_REF}"

# ── 런타임 ───────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

COPY --from=deps /install /usr/local

COPY worker ./worker

# 숫자 UID로 실행 (비root, K8s securityContext의 runAsNonRoot와 매칭)
RUN useradd -u 10001 -r appuser
USER 10001

# HTTP 서버가 아니라 큐 소비자다. 포트를 열지 않는다.
CMD ["ddtrace-run", "python", "-m", "worker.main"]
