"""Dify 의 "11. Runbook Lookup" 노드가 부르는 동기 엔드포인트.

rca_type 하나를 받아 DynamoDB 를 대신 Query 한다 (Node 11 은 SigV4 를 못 해서
직접 못 두드린다 — D-043, decisions.md). 같은 rca_type 을 PK 로 갖는 아이템은
DEF 하나와 ACTION#{action_id} 여러 개다. `status=active` 인 DEF와 ACTION만
Agent에 돌려준다. draft·retired 항목은 같은 테이블에 보존되지만 자동
조회·실행에서는 제외한다(D-077).

요청: {"rca_type": "cache_invalidation_storm"}
응답: {
  "rca_type": "cache_invalidation_storm",
  "runbook_id": "..." | null,
  "runbook_status": "active|draft|retired|missing",
  "success_criteria": {...} | null,   # DEF 아이템이 없으면 null (아직 런북 없음)
  "actions": [...]                     # ACTION 아이템들. 없으면 빈 배열
}

★ unknown 또는 draft·retired RCA도 에러가 아니라 success_criteria=null,
  actions=[] 로 정상 응답한다. `runbook_status` 로 "없음"과 "승격 전"을
  구분한다. 호출 실패와도 구분돼야 Node 11 다음 단계가 안전하게 분기한다.
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


# 노브 카탈로그가 사는 PK. scripts/seed_runbook.py 의 KNOB_PARTITION 과 같아야
# 한다. rca_type 축이 아니라 노브 축이라 별도 파티션에 둔다 — 같은 노브가 여러
# rca_type 의 조치로 쓰이고, S3 처럼 런북 없이 조립하는 조치도 있기 때문이다.
KNOB_PARTITION = "KNOB"
KNOB_SK_PREFIX = "KNOB#"


def _knob(action_id):
    """조치 하나의 노브 정의를 가져온다. 없으면 None.

    없어도 조회를 실패시키지 않는다 — 노브가 빠진 것과 런북이 없는 것은 다른
    문제이고, 여기서 500 을 내면 진단 자체가 멈춘다. 대신 호출자가 `knob` 키의
    부재로 "게이트 판정 근거 없음" 을 알 수 있다.
    """
    if not action_id:
        return None
    got = _table.get_item(
        Key={"rca_type": KNOB_PARTITION, "sk": f"{KNOB_SK_PREFIX}{action_id}"}
    )
    return got.get("Item")


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

    definition = None
    action_items = []
    knobs = []
    for item in items:
        if item["sk"] == "DEF":
            definition = item
        elif item["sk"].startswith("ACTION#"):
            action_items.append(item)
        elif item["sk"].startswith(KNOB_SK_PREFIX):
            knobs.append(item)

    # 상태 필드 도입 전 시딩된 항목은 하위 호환을 위해 active 로 본다.
    # 새 시드 원본은 항상 status 를 명시하므로 전체 재시드 뒤에는 이 폴백이
    # 실제 운영 데이터에 남지 않는다.
    runbook_status = (definition or {}).get(
        "status", "active" if definition else "missing"
    )
    runbook_id = (definition or {}).get("runbook_id")
    active_definition = runbook_status == "active"
    success_criteria = (
        definition.get("success_criteria") if definition and active_definition else None
    )
    actions = [
        item
        for item in action_items
        if active_definition and item.get("status", "active") == "active"
    ]

    # 게이트 진입 판정은 LLM 이 아니라 이 값들로 한다 — knob_reversible ·
    # user_effect_reversible · preapproved_budget · preconditions. 조치마다
    # 노브를 붙여 보내야 호출자가 조회를 두 번 하지 않는다.
    for action in actions:
        knob = _knob(action.get("action_id"))
        if knob is not None:
            action["knob"] = knob

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "rca_type": rca_type,
                "runbook_id": runbook_id,
                "runbook_status": runbook_status,
                "success_criteria": success_criteria,
                "actions": actions,
                # rca_type="KNOB" 으로 부르면 카탈로그 전체가 여기 담긴다.
                "knobs": knobs,
            },
            default=_json_default,
        ),
    }
