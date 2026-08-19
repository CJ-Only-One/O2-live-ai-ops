"""Datadog webhook 을 받아 Dify 워크플로를 실행한다.

Datadog 은 SaaS 라 우리 VPC 안으로 직접 들어올 수 없다. 그래서 퍼블릭 HTTPS
입구가 하나 필요한데, ALB 를 세우는 대신 이 Lambda 의 Function URL 을 쓴다.
이유는 세 가지다 (자세한 비교는 노션-초안/공유_Datadog-Dify-알림-파이프라인.md):

  - VPC 에 인바운드 구멍을 내지 않는다. 이 함수가 안쪽에서 Dify 를 호출한다.
  - 알림이 0건인 달에도 ALB 는 시간당 과금이 붙는다. 여기는 요청당이다.
  - 방송 시작 시 알림이 한꺼번에 터진다. 그때 걸러낼 자리가 필요하다.

인증은 Function URL 의 AuthType 이 NONE 이라 아래 x-dd-secret 헤더 비교가
유일한 방어선이다. 이 검사를 무력화하지 말 것.
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

# 모듈 스코프에 캐시한다. 웜 컨테이너에서는 Secrets Manager 를 다시 부르지
# 않는다. 회전 후 즉시 반영이 필요하면 함수를 한 번 업데이트해 콜드스타트를
# 강제한다 — 알림 경로라 몇 분 지연은 문제가 되지 않는다.
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

    body = json.loads(event.get("body") or "{}")
    print("incoming:", json.dumps(body, ensure_ascii=False))

    # 복구 알림은 분석할 필요가 없다. 1차 필터는 Datadog Monitor 메시지의
    # {{#is_alert}} 이고, 이건 그 조건을 빠뜨린 모니터를 대비한 2차 방어선이다.
    #
    # 제목 문자열 매칭이 아니라 alert_transition 을 쓴다. 제목은 모니터마다
    # 자유 형식이라 매칭이 조용히 어긋난다.
    if body.get("alert_transition") == "Recovered":
        print("skipped: recovered")
        return {"statusCode": 200, "body": "skipped"}

    # Datadog 은 15필드를 보내지만 Dify 에는 LLM 이 읽는 것만 넘긴다.
    # event_id·cycle_key·monitor_id·occurred_at·env·service 는 여기서 소비하고
    # 끝낸다 (계약: infra/06-agent/dify/README.md 1절).
    #
    # ★ Dify 는 모르는 입력 키를 조용히 무시한다. 400 을 내지 않는다.
    #   즉 아래 이름이 Dify 시작 노드 변수와 어긋나면 그 값이 그냥 사라지고
    #   워크플로는 succeeded 로 끝난다. 이름을 바꿀 때는 양쪽을 같이 고친다.
    #
    # 수동 이벤트(api/v1/events)로 테스트하면 host·priority·alert_query 가
    # 비어서 온다. Dify 시작 노드에서 이것들을 필수로 두면 안 되는 이유다.
    payload = {
        "inputs": {
            "alert_title": body.get("alert_title", ""),
            "alert_body": body.get("alert_body", ""),
            "alert_query": body.get("alert_query", ""),
            "priority": body.get("priority", ""),
            "host": body.get("host", ""),
            "tags": body.get("tags", ""),
            "link": body.get("link", ""),
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
    # 워크플로가 무거워져 30초를 넘기면 Datadog 이 먼저 타임아웃 내고
    # 재시도해 같은 알림을 두 번 분석할 수 있다. 그때는 이 호출을
    # 비동기(자기 자신을 InvocationType='Event' 로 재호출)로 바꾼다.
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

    # ★ Dify 는 워크플로가 실패해도 HTTP 200 을 준다. 상태는 본문 안에 있다.
    #   상태 코드만 보면 실패가 성공으로 보고되고, 그러면 Datadog 재시도도
    #   (비동기로 바꾼 뒤에는 대기열 재시도와 DLQ 도) 동작하지 않는다.
    #   알림이 조용히 사라지는 경로다 — docs/troubleshooting.md T-011.
    data = result.get("data", {})
    if data.get("status") != "succeeded":
        raise RuntimeError(
            f"dify workflow {data.get('status')}: {data.get('error')}"
        )

    print("dify ok:", data.get("elapsed_time"), "s")

    return {"statusCode": 200, "body": "ok"}
