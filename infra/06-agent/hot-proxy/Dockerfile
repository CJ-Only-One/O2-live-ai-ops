# boto3 하나만 필요하다. 서명과 자격증명 갱신에 쓴다(app.py 머리말).
FROM python:3.12-slim

RUN pip install --no-cache-dir boto3==1.35.36

WORKDIR /app
COPY app.py .

# 루트로 돌리지 않는다. 숫자 UID 로 준다 — 이름으로 주면 k8s 에서
# CreateContainerConfigError 가 나는 것과 같은 계열의 문제를 피한다
# (여기는 compose 라 당장은 무해하지만 규칙을 맞춘다).
USER 10001

EXPOSE 8788
CMD ["python", "-u", "app.py"]
