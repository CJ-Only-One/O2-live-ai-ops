"""대기열에서 알림을 하나 받아 Dify 워크플로를 실행한다.

Ingress 가 InvocationType="Event" 로 깨우므로 `event` 는 Datadog 이 보낸
알림 dict 그대로다. HTTP 이벤트가 아니라 봉투가 없다.

VPC 안에 있어야 Dify 를 사설 IP 로 부를 수 있다. 동시성은 Dify 가 감당하는
수에 맞춘다 — 이 파이프라인의 처리량 상한은 Lambda 가 아니라 Dify 다.

★ 실패는 반드시 **예외로** 알려야 한다.
  비동기 호출에서 Lambda 는 반환값을 읽지 않는다. `return {"statusCode": 502}`
  는 성공으로 취급되고, 그러면 재시도도 DLQ 도 동작하지 않는다.
  알림이 조용히 사라지는 경로다 — docs/troubleshooting.md T-011.
"""

import json
import os
import urllib.error
import urllib.request

import boto3

# 값이 아니라 "시크릿 이름"만 환경변수로 받는다. 값을 환경변수에 넣으면
# terraform state 에 평문으로 남는다 (06-datastream/warm-path.tf 와 같은 패턴).
SECRET_NAME = os.environ["ALERT_SECRET_NAME"]
DIFY_URL = os.environ["DIFY_URL"]

_secrets = None


def _load_secrets():
    global _secrets
    if _secrets is None:
        raw = boto3.client("secretsmanager").get_secret_value(SecretId=SECRET_NAME)
        _secrets = json.loads(raw["SecretString"])
    return _secrets


def lambda_handler(event, context):
    secrets = _load_secrets()
    print("processing:", event.get("event_id"), event.get("alert_title"))

    # Datadog 은 15필드를 보내지만 Dify 에는 LLM 이 읽는 것만 넘긴다.
    # event_id·cycle_key·monitor_id·occurred_at·env·service 는 라우팅용이라
    # 여기서 소비하고 끝낸다 (계약: infra/06-agent/dify/README.md 1절).
    #
    # ★ Dify 는 모르는 입력 키를 조용히 무시한다. 400 을 내지 않는다.
    #   아래 이름이 Dify 시작 노드 변수와 어긋나면 그 값이 그냥 사라지고
    #   워크플로는 succeeded 로 끝난다 — T-012. 이름은 양쪽을 같이 고친다.
    payload = {
        "inputs": {
            "alert_title": event.get("alert_title", ""),
            "alert_body": event.get("alert_body", ""),
            "alert_query": event.get("alert_query", ""),
            "priority": event.get("priority", ""),
            "host": event.get("host", ""),
            "tags": event.get("tags", ""),
            "link": event.get("link", ""),
        },
        "response_mode": "blocking",
        "user": "datadog",
    }

    req = urllib.request.Request(
        DIFY_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {secrets['dify-api-key']}",
            "Content-Type": "application/json",
        },
    )

    # blocking 이라 워크플로가 끝날 때까지 기다린다. 현재 2~3초다.
    # 노드가 늘어 30초를 넘기기 시작하면 Dify 워커 점유가 병목이 되므로,
    # 그때는 이 호출을 콜백 방식으로 바꾼다(설계 문서 참조).
    try:
        with urllib.request.urlopen(req, timeout=55) as res:
            result = json.loads(res.read())
    except urllib.error.HTTPError as e:
        # 본문을 통째로 찍지 않는다. Dify 오류 응답에 입력이 되비쳐 나온다.
        print("dify error:", e.code, e.read().decode()[:500])
        raise
    except urllib.error.URLError as e:
        # 대부분 보안그룹이나 DIFY_URL 의 IP 문제다. 포트는 80 이어야 한다
        # (17080 은 SSM 터널이 만드는 각자 로컬 포트이지 서버 포트가 아니다).
        print("dify unreachable:", e.reason)
        raise

    # ★ Dify 는 워크플로가 실패해도 HTTP 200 을 준다. 상태는 본문 안에 있다 — T-011.
    data = result.get("data", {})
    if data.get("status") != "succeeded":
        raise RuntimeError(f"dify workflow {data.get('status')}: {data.get('error')}")

    print("dify ok:", data.get("elapsed_time"), "s")
    return {"ok": True}
