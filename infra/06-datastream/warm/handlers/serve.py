"""Lambda o2-warm-api — Agent 조회 엔드포인트.

Agent 실행 환경이 Dify 로 정해지면 HTTP 만 가능하므로 이 계층이 필요합니다.
Python Agent 라면 `WarmClient` 를 직접 쓰는 편이 홉이 하나 줄어 빠릅니다.
**이 핸들러는 WarmClient 를 얇게 감싸기만 합니다** — 로직이 두 곳에
나뉘면 HTTP 로 본 값과 SDK 로 본 값이 달라집니다.

## 엔드포인트

    GET  /v1/warm/snapshot?service=coupon-api&windows=6&broadcast_id=...
         → 판단 재료 전부 (지표 추세 + 배포 + 큐시트 + 정책 + 토폴로지 + 결측 목록)

    GET  /v1/warm/metrics?service=coupon-api&windows=6
         → 지표 윈도우만

    POST /v1/warm/incidents/<id>/snapshot   {"phase":"PRE","service":"coupon-api"}
         → 조치 전/후 스냅샷 기록
           비즈니스 지표는 이 API 가 자동으로 채웁니다.
           **인프라 지표(p95·에러율·CPU)는 Agent 가 Datadog 에서 조회해
           `extra` 로 첨부해야 합니다.** 담당 경계가 그렇게 나뉘어 있고,
           인시던트 레코드만은 두 출처를 합쳐야 완결됩니다.
           비어 있어도 통과시킵니다 — 조치 직전 기록을 막는 편이 더
           위험하기 때문입니다. 대신 레코드 품질 문제로 남습니다.

    GET  /v1/warm/incidents/<id>/compare
         → 조치 전후 비교 (검증 단계용)

    GET  /v1/warm/health

## 인증

공유 시크릿 헤더 `X-O2-Key` 입니다. SigV4 를 요구하면 Dify 같은 범용
Agent 런타임에서 호출이 어렵기 때문입니다. Function URL 을 VPC 나
IAM 으로 닫을 수 있는 환경이라면 그쪽이 더 낫습니다.
"""

from __future__ import annotations

import hmac
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from o2warm import secrets  # noqa: E402
from o2warm.client import WarmClient  # noqa: E402
from o2warm.settings import settings  # noqa: E402

_client: WarmClient | None = None

MAX_WINDOWS = 60


def client() -> WarmClient:
    global _client
    if _client is None:
        _client = WarmClient()
    return _client


def _resp(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False, default=str),
    }


def _authorized(event: dict) -> bool:
    """키 조회 실패는 '키 없음'이 아니라 '거절'입니다.

    이 함수는 인터넷에 바로 노출된 Function URL 앞에 있습니다
    (`authorization_type = "NONE"`). 조회 실패를 미설정과 같이 처리하면
    SSM 이 흔들리는 동안 엔드포인트가 그대로 열립니다. `secrets` 가
    두 경우를 다른 값으로 돌려주는 이유입니다.
    """
    expected = secrets.warm_api_key()

    if expected is None:
        return False  # 사유는 secrets 가 이미 stderr 에 남깁니다
    if not expected:
        return True  # 출처 미지정 = 로컬/사설망 운영. 배포 시 반드시 설정하세요.

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    given = headers.get("x-o2-key") or ""
    return hmac.compare_digest(given, expected)


def _int_param(params: dict, name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(params.get(name, default))))
    except (TypeError, ValueError):
        return default


def _route(event: dict) -> tuple[str, str]:
    http = (event.get("requestContext") or {}).get("http") or {}
    method = http.get("method") or event.get("httpMethod") or "GET"
    path = http.get("path") or event.get("rawPath") or event.get("path") or "/"
    return method.upper(), path.rstrip("/") or "/"


def handler(event, context):
    method, path = _route(event)
    if method == "OPTIONS":
        return _resp(200, {})
    if not _authorized(event):
        return _resp(401, {"error": "unauthorized"})

    params = event.get("queryStringParameters") or {}
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        body = {}

    try:
        return _dispatch(method, path, params, body)
    except ValueError as e:
        return _resp(400, {"error": str(e)})
    except Exception as e:
        traceback.print_exc()
        return _resp(500, {"error": "internal", "detail": str(e)})


def _dispatch(method: str, path: str, params: dict, body: dict):
    if path.endswith("/health"):
        return _resp(200, {"ok": True, "ts": time.time(), "table": settings.table})

    parts = [p for p in path.split("/") if p]

    # /v1/warm/incidents/<id>/...
    if "incidents" in parts:
        i = parts.index("incidents")
        if len(parts) <= i + 1:
            raise ValueError("incident_id 가 필요합니다")
        incident_id = parts[i + 1]
        tail = parts[i + 2] if len(parts) > i + 2 else ""

        if tail == "snapshot" and method == "POST":
            service = body.get("service") or params.get("service")
            phase = (body.get("phase") or "PRE").upper()
            if not service:
                raise ValueError("service 가 필요합니다")
            if phase not in ("PRE", "POST"):
                raise ValueError("phase 는 PRE 또는 POST 여야 합니다")
            return _resp(201, client().record_snapshot(
                incident_id, phase, service, extra=body.get("extra")
            ))

        if tail == "compare" and method == "GET":
            result = client().compare_snapshots(incident_id)
            if result is None:
                # 비교 대상이 없다는 것은 조치 전 스냅샷을 남기지 않았다는
                # 뜻입니다. 조용히 빈 값을 주면 복구로 오판합니다.
                return _resp(409, {
                    "error": "snapshot_incomplete",
                    "detail": "PRE 또는 POST 스냅샷이 없어 복구를 판정할 수 없습니다",
                })
            return _resp(200, result)

        raise ValueError(f"지원하지 않는 경로입니다: {method} {path}")

    if method != "GET":
        raise ValueError(f"지원하지 않는 메서드입니다: {method}")

    service = params.get("service")
    if not service:
        raise ValueError("service 쿼리 파라미터가 필요합니다")
    count = _int_param(params, "windows", 6, 1, MAX_WINDOWS)

    if path.endswith("/metrics"):
        return _resp(200, {"service": service, "windows": client().windows(service, count)})

    if path.endswith("/snapshot"):
        include = tuple(
            (params.get("include") or "metrics,deploy,rundown,policy,topology").split(",")
        )
        return _resp(200, client().snapshot(
            service,
            count=count,
            broadcast_id=params.get("broadcast_id"),
            include=include,
        ))

    raise ValueError(f"지원하지 않는 경로입니다: {method} {path}")
