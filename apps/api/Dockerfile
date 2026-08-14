FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
