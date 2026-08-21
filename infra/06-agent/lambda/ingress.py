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
# ★ 대괄호가 아니라 .get() 이다. lambda_o2.tf 의 o2-dify-ingress 가 이 zip 을
#   공유하는데 그쪽에는 이 변수가 없다. 대괄호로 읽으면 그 함수가 import 에서
#   죽는다. 없으면 MTTR 기록만 꺼지고 중계는 그대로 돈다 — worker.py 와 같은 이유.
HISTORY_BUCKET = os.environ.get("HISTORY_BUCKET")

_lambda = boto3.client("lambda")
_s3 = boto3.client("s3")
_secrets = None


def _load_secrets():
    global _secrets
    if _secrets is None:
        raw = boto3.client("secretsmanager").get_secret_value(SecretId=SECRET_NAME)
        _secrets = json.loads(raw["SecretString"])
    return _secrets


def _record_recovery(body):
    """복구 시각만 S3 에 남긴다. MTTR 재료다.

    ★ incidents/ 의 기존 객체를 고치지 않고 **따로 쓴다.** 그쪽은 날짜로
      파티션되어 있어 고치려면 어느 날짜인지 먼저 찾아야 하고, 그러면 읽기가
      생긴다. 따로 쓰면 읽기가 없고 append-only 원칙도 지켜진다.
      MTTR 은 나중에 cycle_key 로 두 파일을 짝지어 빼면 나온다.

    ★ 무슨 일이 있어도 예외를 밖으로 내보내지 않는다. 이 함수의 실패로
      200 을 못 주면 Datadog 이 재시도하고, 그 재시도가 다시 여기로 온다.
      **지표 결손이 알림 파이프라인 교란보다 싸다.**
    """
    if not HISTORY_BUCKET:
        return

    cycle_key = body.get("cycle_key")
    if not cycle_key:
        # 스키마 검증이 아니다. 키가 없으면 짝지을 대상이 없을 뿐이다.
        print("recovery not recorded: no cycle_key")
        return

    try:
        _s3.put_object(
            Bucket=HISTORY_BUCKET,
            Key=f"resolutions/{cycle_key}.json",
            Body=json.dumps(
                {
                    "cycle_key": cycle_key,
                    "event_id": body.get("event_id", ""),
                    "monitor_id": body.get("monitor_id", ""),
                    "recovered_at": body.get("occurred_at", ""),
                },
                ensure_ascii=False,
            ).encode(),
            ContentType="application/json",
        )
        print("recovery recorded:", cycle_key)
    except Exception as e:  # noqa: BLE001 — 알림 경로를 막지 않는다
        print("recovery record failed:", type(e).__name__, e)


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
    #
    # **분석은 안 하지만 시각은 버리지 않는다.** Datadog 은 한 장애에 대해
    # Triggered 와 Recovered 를 두 번 보내고 cycle_key 가 그 둘을 묶는다.
    # 두 시각의 차가 곧 MTTR(장애 발생부터 복구까지)이고, 이 프로젝트의
    # 평가 지표다. 여기서 버리면 되찾을 방법이 없다.
    if body.get("alert_transition") == "Recovered":
        _record_recovery(body)
        print("skipped: recovered", body.get("event_id"))
        return {"statusCode": 200, "body": "skipped"}

    _lambda.invoke(
        FunctionName=WORKER_FUNCTION,
        InvocationType="Event",
        Payload=json.dumps(body).encode(),
    )
    print("queued:", body.get("event_id"))

    return {"statusCode": 200, "body": "queued"}
