FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY warmer ./warmer

# 숫자 UID로 실행 (비root, K8s securityContext의 runAsNonRoot와 매칭 —
# 이름으로 두면 kubelet이 root 여부를 검증 못 해 CreateContainerConfigError로
# 죽는다. decisions.md의 함정).
RUN useradd -u 10001 -r appuser
USER 10001

# HTTP 서버가 아니라 폴링 루프다. 포트를 열지 않는다.
CMD ["ddtrace-run", "python", "-m", "warmer.main"]
