"""Dify 의 "11. Runbook Lookup" 노드가 부르는 동기 엔드포인트.

rca_type 하나를 받아 DynamoDB 를 대신 Query 한다 (Node 11 은 SigV4 를 못 해서
직접 못 두드린다 — D-043, decisions.md). 같은 rca_type 을 PK 로 갖는 아이템은
DEF 하나와 ACTION#{action_id} 여러 개뿐이라, PK 만으로 Query 하면 그 유형의
런북 전체(성공 판정 조건 + 가능한 조치 목록)가 한 번에 나온다.

요청: {"rca_type": "cache_invalidation_storm"}
응답: {
  "rca_type": "cache_invalidation_storm",
  "success_criteria": {...} | null,   # DEF 아이템이 없으면 null (아직 런북 없음)
  "actions": [...]                     # ACTION 아이템들. 없으면 빈 배열
}

★ unknown·other 는 애초에 이 테이블에 아이템이 없다 (labels.txt: Runbook 매칭
  대상 아님) — 그 경우도 에러가 아니라 success_criteria=null, actions=[] 로
  정상 응답한다. "런북 없음"과 "호출 실패"를 구분해야 Node 11 다음 단계가
  분기할 수 있다.
"""

import hashlib
import hmac
import json
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ["RUNBOOK_TABLE"]
SECRET_NAME = os.environ["RUNBOOK_SECRET_NAME"]
API_KEY_HEADER = "x-api-key"

_table = boto3.resource("dynamodb").Table(TABLE_NAME)
_secrets = None


def _load_secrets():
    global _secrets
    if _secrets is None:
        raw = boto3.client("secretsmanager").get_secret_value(SecretId=SECRET_NAME)
        _secrets = json.loads(raw["SecretString"])
    return _secrets


def _json_default(value):
    # threshold 같은 숫자 필드는 DynamoDB 에서 Decimal 로 돌아온다.
    # json 표준 인코더가 모르는 타입이라 여기서 int/float 로 내린다.
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"not JSON serializable: {value!r}")


def lambda_handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    secrets = _load_secrets()

    received = headers.get(API_KEY_HEADER) or ""
    expected = secrets["runbook-lookup-api-key"]

    # ★ hmac.compare_digest — slack_approval_request.py 는 평범한 != 비교라
    #   길이 차 나는 값에서 반환 시점이 미세하게 갈린다. 이 파일은 새로 쓰는
    #   김에 상수 시간 비교로 둔다 (slack_approval_request.py 는 이번 범위 밖).
    if not hmac.compare_digest(received, expected):
        # ★ 실제 값은 절대 로그에 남기지 않는다. 길이/공백/해시만 비교한다
        #   (slack_approval_request.py 와 같은 이유 — 원인 규명용 디버그 로그).
        print(
            "rejected: bad api key",
            "received_len=", len(received),
            "expected_len=", len(expected),
            "stripped_match=", received.strip() == expected.strip(),
            "received_sha256=", hashlib.sha256(received.encode()).hexdigest(),
            "expected_sha256=", hashlib.sha256(expected.encode()).hexdigest(),
        )
        return {"statusCode": 403, "body": json.dumps({"error": "forbidden"})}

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError as e:
        print("bad json:", e)
        return {"statusCode": 400, "body": json.dumps({"error": "bad json"})}

    rca_type = body.get("rca_type")
    if not rca_type:
        return {"statusCode": 400, "body": json.dumps({"error": "rca_type required"})}

    items = _table.query(KeyConditionExpression=Key("rca_type").eq(rca_type)).get(
        "Items", []
    )

    success_criteria = None
    actions = []
    for item in items:
        if item["sk"] == "DEF":
            success_criteria = item.get("success_criteria")
        elif item["sk"].startswith("ACTION#"):
            actions.append(item)

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "rca_type": rca_type,
                "success_criteria": success_criteria,
                "actions": actions,
            },
            default=_json_default,
        ),
    }
