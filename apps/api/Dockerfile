FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 이벤트 SDK 는 private 저장소에 있어 requirements.txt 로 못 받는다.
#
# 토큰을 ARG 나 ENV 로 받지 않는다. 그렇게 하면 이미지 히스토리에 남아
# `docker history` 로 읽힌다. BuildKit 시크릿은 이 RUN 동안만 파일로
# 마운트되고 레이어에 기록되지 않는다.
#
# git+https 대신 tarball 을 받는 이유는 slim 이미지에 git 이 없기 때문이다.
# git 을 설치하면 런타임 이미지에 그대로 남아 취약점 표면만 넓어진다.
#
# 커밋 SHA 로 고정한다. 저장소에 태그가 없어 브랜치로 두면 SDK 가 바뀔 때마다
# 우리 빌드 결과가 조용히 달라진다.
ARG SDK_REF=0f26876
RUN --mount=type=secret,id=sdk_token \
    pip install --no-cache-dir \
    "https://x-access-token:$(cat /run/secrets/sdk_token)@github.com/CJ-Only-One/o2-sdk-for-event/archive/${SDK_REF}.tar.gz"

COPY app ./app

# 마이그레이션은 같은 이미지로 K8s Job 이 돌린다 (alembic upgrade head).
# 이미지를 따로 만들면 파드가 쓰는 모델과 마이그레이션이 갈릴 수 있다.
COPY alembic.ini .
COPY migrations ./migrations

# 숫자 UID로 실행 (비root, K8s securityContext의 runAsNonRoot와 매칭)
RUN useradd -u 10001 -r appuser
USER 10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
