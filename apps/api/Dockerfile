FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# 숫자 UID로 실행 (비root, K8s securityContext의 runAsNonRoot와 매칭)
RUN useradd -u 10001 -r appuser
USER 10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
