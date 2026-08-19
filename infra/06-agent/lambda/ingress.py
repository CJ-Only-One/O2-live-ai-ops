"""Datadog webhook 을 받아 Worker 를 비동기로 깨우고 즉시 답한다.

이 함수는 **문지기**다. Dify 를 부르지 않으므로 응답이 밀리초 단위이고,
동시성 상한을 두지 않는다 — 여기서 막으면 문 앞에서 알림을 버리는 것이라
"알림을 잃지 않는다" 는 목표와 정반대가 된다.

왜 동기 호출을 그만뒀나:

    Function URL 은 동기라 대기열이 없다. Worker 동시성이 차 있으면
    Lambda 가 429 를 돌려주는데, Datadog 은 5XX 와 내부 오류에만 재시도한다.
    **429 는 재시도 대상이 아니다.** 그 알림은 영구히 사라진다.

    InvocationType="Event" 로 부르면 AWS 가 내부 대기열에 넣는다. 동시성
    초과는 소실이 아니라 지연이 되고, 재시도와 DLQ 가 따라온다.
    SQS 를 세우지 않고 같은 성질을 얻는다.

VPC 밖에 둔다. SQS 도 Dify 도 부르지 않고 Lambda API 와 Secrets Manager 만
쓰므로 ENI 가 필요 없고, 콜드스타트가 1초대에서 100밀리초대로 떨어진다.
"""

import json
import os

import boto3

SECRET_NAME = os.environ["ALERT_SECRET_NAME"]
WORKER_FUNCTION = os.environ["WORKER_FUNCTION"]

_lambda = boto3.client("lambda")
_secrets = None


def _load_secrets():
    global _secrets
    if _secrets is None:
        raw = boto3.client("secretsmanager").get_secret_value(SecretId=SECRET_NAME)
        _secrets = json.loads(raw["SecretString"])
    return _secrets


def lambda_handler(event, context):
    secrets = _load_secrets()

    # Function URL 은 헤더 이름을 소문자로 내려주지만, 대소문자에 기대지 않는다.
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if headers.get("x-dd-secret") != secrets["webhook-secret"]:
        print("rejected: bad secret")
        return {"statusCode": 403, "body": "forbidden"}

    # ★ 여기서 하는 일은 셋뿐이다. 스키마 검증을 넣지 마라.
    #   필드가 비었거나 모양이 달라도 그대로 흘려보낸다. 검증에 걸려
    #   버려지는 알림이 곧 소실이고, Datadog 이 템플릿을 바꾸면 파이프라인이
    #   조용히 죽는다. 이상한 알림을 분석하는 비용이 알림을 잃는 비용보다 싸다.
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError as e:
        print("bad json:", e)
        return {"statusCode": 400, "body": "bad json"}

    print("incoming:", json.dumps(body, ensure_ascii=False))

    # 복구 알림은 분석할 필요가 없다. 1차 필터는 Datadog Monitor 메시지의
    # {{#is_alert}} 이고, 이건 그 조건을 빠뜨린 모니터를 대비한 2차 방어선이다.
    # 여기서 걸러야 대기열과 재시도 횟수를 낭비하지 않는다.
    if body.get("alert_transition") == "Recovered":
        print("skipped: recovered", body.get("event_id"))
        return {"statusCode": 200, "body": "skipped"}

    _lambda.invoke(
        FunctionName=WORKER_FUNCTION,
        InvocationType="Event",
        Payload=json.dumps(body).encode(),
    )
    print("queued:", body.get("event_id"))

    return {"statusCode": 200, "body": "queued"}
