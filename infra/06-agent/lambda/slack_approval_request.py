"""Dify 의 "17. Slack Approval Request" 노드가 부르는 동기 엔드포인트.

Dify 는 이 호출이 끝날 때까지 최대 600초 blocking 으로 기다린다
(DSL 의 node timeout: max_read_timeout=600). 그래서 이 함수는:

  1. Slack 에 버튼 3개(승인/거부/재고) 달린 메시지를 보내고
  2. DynamoDB 에 결정이 기록될 때까지 폴링하다가
  3. 결정이 나오면(또는 시간 초과하면) 그 자리에서 바로 응답한다

버튼 클릭 자체는 별개 함수(slack_interactivity.py)가 Slack 으로부터 직접
받아서 DynamoDB 에 기록한다 — 이 함수는 그 값이 나타나길 기다릴 뿐이다.

★ Dify 의 이 HTTP 노드는 실패하면 500ms 뒤 한 번 재시도한다(retry_config,
  max_retries=1). 재시도가 오면 완전히 같은 body 가 다시 온다. incident_id
  와 action 내용을 해시해서 approval_id 를 만들면, 재시도가 와도 Slack 에
  메시지를 두 번 보내지 않고 이미 만든 요청을 그대로 이어서 기다릴 수 있다.

★ 응답 바디는 반드시 {"decision": "APPROVE"|"REJECT"|"RECONSIDER"} 형태여야
  한다. DSL 의 "17-B. CODE — Slack Response Parser" 가 이 키(decision/action/
  result 중 하나)만 읽고, 셋 중 하나로 안 떨어지는 값은 전부 RECONSIDER 로
  강등시킨다 — 다른 키 이름을 쓰면 Dify 가 조용히 무시하고 RECONSIDER 로
  흘러간다 (T-012 와 같은 함정).
"""

import hashlib
import json
import os
import time
import urllib.error
import urllib.request

import boto3

TABLE_NAME = os.environ["APPROVALS_TABLE"]
SECRET_NAME = os.environ["SLACK_SECRET_NAME"]
API_KEY_HEADER = "x-api-key"

# Dify 의 노드 타임아웃(600초)보다 여유를 두고 먼저 돌아온다.
# Function URL 자체 한도는 900초라 이 값이 병목은 아니다.
POLL_DEADLINE_SECONDS = 580
POLL_INTERVAL_SECONDS = 3

_table = boto3.resource("dynamodb").Table(TABLE_NAME)
_secrets = None


def _load_secrets():
    global _secrets
    if _secrets is None:
        raw = boto3.client("secretsmanager").get_secret_value(SecretId=SECRET_NAME)
        _secrets = json.loads(raw["SecretString"])
    return _secrets


def _approval_id(incident_id: str, action: dict) -> str:
    # 같은 요청(Dify 의 재시도 포함)은 항상 같은 id 로 떨어져야 한다.
    key = f"{incident_id}:{json.dumps(action, sort_keys=True, ensure_ascii=False)}"
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def _shorten(text, limit=150):
    # LLM이 낸 rca는 완결된 문장 여러 개로 길게 나올 때가 많다. Slack
    # 승인 메시지는 빠른 판단용이라 전문을 다 보여줄 필요가 없다 — 잘라도
    # 원문은 이력에 그대로 남는다(여기서 자르는 건 표시 전용).
    #
    # 글자 수로 그냥 자르면 단어 중간이 잘린다("...팬아웃 경로가 수용" 처럼).
    # 1순위: limit 안에서 끝나는 마지막 문장(".")까지만 보여준다 — 완결된
    #        문장이라 잘렸다는 티가 안 난다.
    # 2순위: 문장이 너무 짧거나(limit의 절반 미만) 아예 없으면, 마지막
    #        단어(공백) 경계에서 자르고 "…"를 붙인다.
    text = (text or "").strip()
    if len(text) <= limit:
        return text or "-"

    window = text[:limit]
    last_period = window.rfind(". ")
    if last_period == -1:
        last_period = window.rstrip().rfind(".")
    if last_period >= limit // 2:
        return window[: last_period + 1].strip()

    last_space = window.rfind(" ")
    cut = window[:last_space] if last_space > 0 else window
    return cut.rstrip() + "…"


def _post_slack_message(secrets, approval_id, incident_id, diagnosis, action, risk_level):
    # Dify 의 "diagnosis" 필드는 diagnosis_agg.output(= {"diagnosis": {...},
    # "context": {...}} 번들 전체)을 그대로 담아 보낸다 — 한 겹 더 감싸져
    # 있다. 그대로 diagnosis.get("rca")를 하면 항상 못 찾고 "원인: -"로
    # 뜬다. 감싸진 형태와 혹시 나중에 워크플로 쪽에서 안쪽 값만 바로
    # 보내도록 고쳐질 경우 둘 다 받아들이게 한 겹 벗긴다.
    if isinstance(diagnosis, dict) and isinstance(diagnosis.get("diagnosis"), dict):
        diagnosis = diagnosis["diagnosis"]
    rca = diagnosis.get("rca") if isinstance(diagnosis, dict) else None
    rca_short = _shorten(rca)
    action_id = action.get("action_id", "unknown")
    blast_radius = action.get("blast_radius", "-")

    # text는 Slack 알림·접근성용 폴백이라 blocks 내용과 별개로 항상 채운다.
    text = f"인시던트 승인 요청 — {incident_id} / 원인: {rca_short} / 조치: {action_id} (위험도 {risk_level})"

    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":rotating_light: *인시던트 승인 요청*\n`{incident_id}`"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*원인*\n{rca_short}"}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*조치*\n`{action_id}`"},
                {"type": "mrkdwn", "text": f"*위험도*\n{risk_level}"},
            ],
        },
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"영향 범위: {blast_radius}"}]},
        {
            "type": "actions",
            "block_id": "o2_approval_actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ 승인"},
                    "style": "primary",
                    "action_id": "o2_approve",
                    "value": f"{approval_id}|APPROVE",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ 거부"},
                    "style": "danger",
                    "action_id": "o2_reject",
                    "value": f"{approval_id}|REJECT",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🤔 재고"},
                    "action_id": "o2_reconsider",
                    "value": f"{approval_id}|RECONSIDER",
                },
            ],
        },
    ]

    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps(
            {"channel": secrets["slack-channel-id"], "text": text, "blocks": blocks}
        ).encode(),
        headers={
            "Authorization": f"Bearer {secrets['slack-bot-token']}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        result = json.loads(res.read())

    if not result.get("ok"):
        raise RuntimeError(f"slack postMessage failed: {result.get('error')}")

    return result["channel"], result["ts"]


def lambda_handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    secrets = _load_secrets()

    if headers.get(API_KEY_HEADER) != secrets["approval-api-key"]:
        # ★ 실제 값은 절대 로그에 남기지 않는다. 길이/공백/해시만 비교해서
        #   "뭐가 다른지"를 진단한다 (T: Dify 테스트 워크플로우에서 403 반복 —
        #   원인 규명용으로 임시로 추가, 안정화되면 제거해도 된다).
        received = headers.get(API_KEY_HEADER) or ""
        expected = secrets["approval-api-key"]
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

    incident_id = body.get("incident_id", "unknown")
    diagnosis = body.get("diagnosis") or {}
    action = body.get("action") or {}
    risk_level = body.get("risk_level", "-")

    approval_id = _approval_id(incident_id, action)
    item = _table.get_item(Key={"approval_id": approval_id}).get("Item")

    if item is None:
        # 처음 보는 요청 -> Slack 에 새로 메시지를 보낸다.
        try:
            channel, ts = _post_slack_message(
                secrets, approval_id, incident_id, diagnosis, action, risk_level
            )
        except (urllib.error.URLError, RuntimeError) as e:
            print("slack post failed:", e)
            return {"statusCode": 502, "body": json.dumps({"error": "slack post failed"})}

        _table.put_item(
            Item={
                "approval_id": approval_id,
                "status": "PENDING",
                "incident_id": incident_id,
                "slack_channel": channel,
                "slack_ts": ts,
                "created_at": int(time.time()),
                # 감사 로그 겸 보관. 7일 뒤 자동 삭제(TTL 은 테이블에 설정).
                "ttl": int(time.time()) + 7 * 24 * 3600,
            }
        )
        print("approval requested:", approval_id, incident_id)
    else:
        # Dify 의 500ms 재시도, 혹은 같은 조치가 정말로 다시 온 경우.
        # 이미 메시지를 보냈으므로 다시 보내지 않고 결과만 기다린다.
        print("approval already exists, resuming wait:", approval_id, item.get("status"))

    deadline = time.time() + POLL_DEADLINE_SECONDS
    while time.time() < deadline:
        item = _table.get_item(Key={"approval_id": approval_id}).get("Item") or {}
        if item.get("status") == "DECIDED":
            return {"statusCode": 200, "body": json.dumps({"decision": item["decision"]})}
        time.sleep(POLL_INTERVAL_SECONDS)

    # 시간 안에 아무도 안 눌렀다. RECONSIDER 로 떨어뜨린다 — APPROVE 로 자동
    # 확정하지 않는 게 안전하다 (승인 없는 위험 조치 실행을 막는 게 목적).
    print("approval timed out:", approval_id)
    return {"statusCode": 200, "body": json.dumps({"decision": "RECONSIDER"})}
