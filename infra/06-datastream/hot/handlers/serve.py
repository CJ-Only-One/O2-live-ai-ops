"""Lambda o2-hot-api — Datadog Hot Path 시계열 지표 역쿼리 게이트웨이.

Dify 가 `@webhook-dify` 알림을 받은 뒤 "지금 수치가 얼마인가"를 Datadog 에
직접 되물을 때 쓴다. docs/DatadogMcpQueryInstruction.md 의 구현안
A(HTTP REST API Gateway)를 따른다.

Hot/Warm/Cold 이름 정리는 그 지침서 3절 표를 참고 — Hot 은 이 API, Warm 은
`o2-warm-api`, Cold(원시 로그 SQL)는 지금 `o2-warm-api` 의 `/v1/warm/athena`
가 겸하고 있다(표에 있는 별도 `o2-cold-api` 는 아직 없다).

## 엔드포인트

    POST /v1/hot/datadog/query   {"query": "...", "from_ts": ..., "to_ts": ...}
        → Datadog v1 /query 역쿼리. from_ts/to_ts 생략 시 최근 10분.

    GET  /v1/hot/health

## 인증

`o2-warm-api` 의 X-O2-Key 공유 시크릿과 다르다. Function URL 이
`authorization_type = "AWS_IAM"` 이라 **인증은 이 코드가 아니라 AWS 가
Lambda 를 부르기 전에 SigV4 서명으로 이미 끝낸다.** 서명이 없거나
`aws_lambda_permission.hot_api_invoker` 가 허용하지 않은 주체면 이 핸들러
자체가 실행되지 않는다 — 그래서 여기 `_authorized()` 가 없다.

왜 X-O2-Key 를 안 쓰는지는 `../../hot-path.tf` 머리말(D-031)을 참고한다 —
이 계정은 Organizations 멤버 계정이라 공개(`NONE`) Function URL 이
조직 밖 정책에 403 으로 막혀서 그 패턴을 못 썼다.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from o2hot.datadog import DatadogKeyError, query  # noqa: E402
from o2hot.metric_catalog import MetricRequestError, read_metric  # noqa: E402


def _resp(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False, default=str),
    }


def _caller_arn(event: dict) -> str:
    """감사 로그용. AWS_IAM Function URL 이벤트는 서명 검증을 이미 마친
    호출자 정보를 requestContext.authorizer.iam 에 담아 준다.
    """
    iam_ctx = ((event.get("requestContext") or {}).get("authorizer") or {}).get("iam") or {}
    return iam_ctx.get("userArn", "unknown")


def _route(event: dict) -> tuple[str, str]:
    http = (event.get("requestContext") or {}).get("http") or {}
    method = http.get("method") or event.get("httpMethod") or "GET"
    path = http.get("path") or event.get("rawPath") or event.get("path") or "/"
    return method.upper(), path.rstrip("/") or "/"


def handler(event, context):
    method, path = _route(event)
    if method == "OPTIONS":
        return _resp(200, {})

    print(f"[o2hot] caller={_caller_arn(event)} {method} {path}")

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        body = {}

    try:
        return _dispatch(method, path, body)
    except ValueError as e:
        return _resp(400, {"error": str(e)})
    except DatadogKeyError as e:
        return _resp(500, {"error": "datadog_key_unavailable", "detail": str(e)})
    except Exception as e:
        traceback.print_exc()
        return _resp(500, {"error": "internal", "detail": str(e)})


def _dispatch(method: str, path: str, body: dict):
    if path.endswith("/health"):
        return _resp(200, {"ok": True, "ts": time.time(), "path_type": "HOT_PATH"})

    if path.endswith("/datadog/query"):
        if method != "POST":
            raise ValueError("POST 메서드만 지원합니다")

        query_str = body.get("query")
        if not query_str:
            raise ValueError("query 파라미터가 필요합니다")

        now = int(time.time())
        from_ts = int(body.get("from_ts", now - 600))
        to_ts = int(body.get("to_ts", now))

        try:
            result = query(query_str, from_ts, to_ts)
        except DatadogKeyError:
            raise
        except Exception as ex:
            return _resp(500, {"error": "datadog_api_call_failed", "detail": str(ex)})

        return _resp(200, {"path_type": "HOT_PATH", **result})

    if path.endswith("/datadog/metric"):
        if method != "POST":
            raise MetricRequestError("POST method required")
        return _resp(200, {"path_type": "HOT_PATH", **read_metric(body)})

    raise ValueError(f"지원하지 않는 경로입니다: {method} {path}")
