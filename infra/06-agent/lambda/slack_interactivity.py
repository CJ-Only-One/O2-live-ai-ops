"""Slack 이 버튼 클릭을 알려주는 콜백. Interactivity & Shortcuts 의
Request URL 에 이 함수의 Function URL 을 등록한다.

Slack 은 이 응답을 3초 안에 받아야 한다 — slack_approval_request.py 처럼
기다리는 함수가 아니다. 여기서 하는 일은 딱 셋이다: 서명 검증, DynamoDB
갱신, 원래 메시지 갱신. Dify 를 직접 부르지 않는다 — 결정을 기다리는 건
slack_approval_request.py 의 폴링 루프다.
"""

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request

import boto3

TABLE_NAME = os.environ["APPROVALS_TABLE"]
SECRET_NAME = os.environ["SLACK_SECRET_NAME"]

_table = boto3.resource("dynamodb").Table(TABLE_NAME)
_secrets = None


def _load_secrets():
    global _secrets
    if _secrets is None:
        raw = boto3.client("secretsmanager").get_secret_value(SecretId=SECRET_NAME)
        _secrets = json.loads(raw["SecretString"])
    return _secrets


def _verify_slack_signature(headers, raw_body, signing_secret):
    ts = headers.get("x-slack-request-timestamp")
    sig = headers.get("x-slack-signature")
    if not ts or not sig:
        return False
    # 5분 넘은 요청은 재생 공격으로 간주하고 버린다 (Slack 권장 값).
    if abs(time.time() - int(ts)) > 60 * 5:
        return False
    basestring = f"v0:{ts}:{raw_body}".encode()
    computed = "v0=" + hmac.new(signing_secret.encode(), basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, sig)


def _update_slack_message(response_url, result_text, original_text=""):
    if not response_url:
        return
    # response_url 은 별도 토큰 없이도 원본 메시지를 고칠 수 있게 Slack 이
    # 매번 새로 발급해주는 임시 주소다. 여기서는 버튼을 없애고 원본 내용(어떤
    # 인시던트의 어떤 조치였는지) 아래에 결과를 덧붙인다 — 원본 text를 그냥
    # result_text로 덮어쓰면(replace_original) 뭘 승인/거부했는지가 화면에서
    # 사라져서 사람이 다시 스크롤해서 찾아야 했다.
    text = f"{original_text}\n\n{result_text}" if original_text else result_text
    req = urllib.request.Request(
        response_url,
        data=json.dumps({"replace_original": "true", "text": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        # 메시지 갱신 실패는 치명적이지 않다 — 결정 자체는 이미 DynamoDB 에
        # 저장됐다. Slack UI 가 안 바뀌는 정도의 문제라 로그만 남긴다.
        print("slack message update failed:", e)


def lambda_handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    raw_body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode()

    secrets = _load_secrets()
    if not _verify_slack_signature(headers, raw_body, secrets["slack-signing-secret"]):
        print("rejected: bad signature")
        return {"statusCode": 403, "body": "forbidden"}

    # Slack interactivity 콜백은 x-www-form-urlencoded 로 오고, payload 필드
    # 안에 실제 JSON 이 문자열로 들어있다.
    form = urllib.parse.parse_qs(raw_body)
    try:
        payload = json.loads(form["payload"][0])
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print("bad payload:", e)
        return {"statusCode": 400, "body": "bad payload"}

    action = (payload.get("actions") or [{}])[0]
    approval_id, _, decision = action.get("value", "").partition("|")
    user = payload.get("user", {}).get("username", "unknown")
    response_url = payload.get("response_url")
    # 원본 승인 요청 메시지 텍스트(인시던트/원인/조치/위험도/영향범위) — Slack이
    # 버튼 클릭 payload에 원본 메시지를 그대로 실어 보내준다.
    original_text = (payload.get("message") or {}).get("text", "")

    if not approval_id or decision not in {"APPROVE", "REJECT", "RECONSIDER"}:
        print("bad button value:", action.get("value"))
        return {"statusCode": 200, "body": ""}

    try:
        _table.update_item(
            Key={"approval_id": approval_id},
            UpdateExpression="SET #s=:decided, decision=:d, decided_by=:u, decided_at=:t",
            ConditionExpression="#s=:pending",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":decided": "DECIDED",
                ":pending": "PENDING",
                ":d": decision,
                ":u": user,
                ":t": int(time.time()),
            },
        )
    except _table.meta.client.exceptions.ConditionalCheckFailedException:
        # 이미 누가 눌렀거나(동시 클릭), 폴링이 시간 초과로 이미 끝난 뒤다.
        # 두 번째 클릭은 무시한다 — 최초 결정이 이긴다.
        print("already decided, ignoring second click:", approval_id)
        _update_slack_message(response_url, "⚠️ 이미 처리된 요청입니다.", original_text)
        return {"statusCode": 200, "body": ""}

    label = {"APPROVE": "✅ 승인", "REJECT": "❌ 거부", "RECONSIDER": "🤔 재고"}[decision]
    _update_slack_message(response_url, f"{label} — @{user}", original_text)
    print("decided:", approval_id, decision, "by", user)
    return {"statusCode": 200, "body": ""}
