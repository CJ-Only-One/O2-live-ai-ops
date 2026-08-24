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
         → 감지 시점(DETECT) / 조치 전(PRE) / 조치 후(POST) 스냅샷 기록
           DETECT 는 번들 전체를, PRE·POST 는 지표만 남깁니다.
           복구 판정에 쓰이는 것은 PRE·POST 뿐입니다.
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
from o2warm.store import SNAPSHOT_PHASES  # noqa: E402

_client: WarmClient | None = None

MAX_WINDOWS = 60

# 파이프라인 생존 카나리의 service 태그. `06-datastream` 의
# `local.canary_service` / `output.canary_service_tag` 와 같은 값이다.
#
# 이 값을 바꿔야 할 일이 생기면 두 곳을 같이 고친다. 여기만 고치면 카나리가
# 다시 새어 나오고, 저쪽만 고치면 이 API 가 실재하는 서비스를 막는다.
CANARY_SERVICE = os.getenv("O2_CANARY_SERVICE", "o2-canary")


def _reject_canary(service: str) -> None:
    """카나리를 실제 서비스인 것처럼 조회하는 것을 막습니다.

    카나리는 **파이프라인이 살아 있음을 증명하려고 스스로 만든 트래픽**
    입니다(D-052). 지표가 실재하기 때문에 `service=o2-canary` 로 물으면
    그럴듯한 답이 나오는데, 그 답에는 사용자가 없습니다 — rps 는 항상 0.1,
    실패율은 항상 0, 지연은 항상 합성값입니다.

    **조용히 빈 답을 주지 않고 400 으로 거절합니다.** 빈 답은 "이 서비스는
    지금 한산하다" 와 구분되지 않고, 에이전트는 그걸 정상으로 읽습니다.
    막힌 이유가 응답에 적혀 있어야 다음 질문이 달라집니다.

    명세 §08 *"주입은 Agent 가 읽는 저장소에 흔적을 남기지 않는다"* 와
    맞물리는 지점입니다. Athena 쪽 대응은 `business_events` 뷰가 합니다.
    """
    if service and service.strip().lower() == CANARY_SERVICE:
        raise ValueError(
            f"'{CANARY_SERVICE}' 는 파이프라인 생존 카나리이지 실제 서비스가 "
            "아닙니다. 이 지표는 관측 경로가 살아 있는지만 말해 주고 사용자 "
            "트래픽을 뜻하지 않습니다 — 장애 판단의 근거로 쓸 수 없습니다. "
            "파이프라인 자체를 의심한다면 Datadog 의 "
            "'[O2][파이프라인] warm 경로 끊김' Monitor 를 보십시오."
        )


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


def _emit_athena_metrics(*, result: str, duration_ms: float, scanned_bytes: int = 0) -> None:
    payload = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": "O2/WarmApi",
                "Dimensions": [["FunctionName", "Environment", "Result"]],
                "Metrics": [
                    {"Name": "AthenaQuery", "Unit": "Count"},
                    {"Name": "AthenaDurationMs", "Unit": "Milliseconds"},
                    {"Name": "AthenaScannedBytes", "Unit": "Bytes"},
                ],
            }],
        },
        "FunctionName": "o2-warm-api",
        "Environment": settings.dd_env,
        "Result": result,
        "AthenaQuery": 1,
        "AthenaDurationMs": duration_ms,
        "AthenaScannedBytes": scanned_bytes,
    }
    print(json.dumps(payload, separators=(",", ":")))


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

    # /v1/warm/athena (Athena SQL 쿼리 실행)
    if path.endswith("/athena"):
        if method != "POST":
            raise ValueError("athena 엔드포인트는 POST 메서드만 지원합니다")
        query_sql = body.get("query")
        if not query_sql:
            raise ValueError("query 파라미터(SQL 문)가 필요합니다")
        
        import boto3
        bucket = os.getenv("O2_DATA_LAKE_BUCKET", "o2-data-lake-066107819912")
        athena_client = boto3.client("athena", region_name=os.getenv("AWS_REGION", "ap-northeast-2"))
        
        try:
            start_resp = athena_client.start_query_execution(
                QueryString=query_sql,
                QueryExecutionContext={"Database": "o2_data_lake"},
                ResultConfiguration={"OutputLocation": f"s3://{bucket}/athena-results/"}
            )
            execution_id = start_resp["QueryExecutionId"]
            
            start_t = time.time()
            state = "RUNNING"
            while time.time() - start_t < 25:
                status_res = athena_client.get_query_execution(QueryExecutionId=execution_id)
                state = status_res["QueryExecution"]["Status"]["State"]
                if state in ["SUCCEEDED", "FAILED", "CANCELLED"]:
                    break
                time.sleep(0.5)
            
            if state != "SUCCEEDED":
                _emit_athena_metrics(
                    result=state.lower(),
                    duration_ms=(time.time() - start_t) * 1000,
                )
                reason = status_res["QueryExecution"]["Status"].get("StateChangeReason", "Unknown error")
                return _resp(500, {"error": "athena_query_failed", "state": state, "reason": reason})

            statistics = status_res["QueryExecution"].get("Statistics") or {}
            _emit_athena_metrics(
                result="success",
                duration_ms=float(statistics.get("EngineExecutionTimeInMillis", (time.time() - start_t) * 1000)),
                scanned_bytes=int(statistics.get("DataScannedInBytes", 0)),
            )
            
            results = athena_client.get_query_results(QueryExecutionId=execution_id)
            rows = results["ResultSet"]["Rows"]
            if not rows:
                return _resp(200, {"query_id": execution_id, "columns": [], "rows": []})
            
            col_names = [c.get("VarCharValue", "") for c in rows[0].get("Data", [])]
            data_rows = []
            for r in rows[1:]:
                row_dict = {}
                for idx, val in enumerate(r.get("Data", [])):
                    col_name = col_names[idx] if idx < len(col_names) else f"col_{idx}"
                    row_dict[col_name] = val.get("VarCharValue")
                data_rows.append(row_dict)
            
            return _resp(200, {
                "query_id": execution_id,
                "count": len(data_rows),
                "columns": col_names,
                "rows": data_rows
            })
        except Exception as ex:
            _emit_athena_metrics(result="error", duration_ms=0)
            return _resp(500, {"error": "athena_execution_error", "detail": str(ex)})

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
            _reject_canary(service)
            if phase not in SNAPSHOT_PHASES:
                raise ValueError("phase 는 DETECT, PRE, POST 중 하나여야 합니다")
            return _resp(201, client().record_snapshot(
                incident_id,
                phase,
                service,
                extra=body.get("extra"),
                broadcast_id=body.get("broadcast_id") or params.get("broadcast_id"),
            ))

        if tail == "compare" and method == "GET":
            result = client().compare_snapshots(incident_id)
            if result is None:
                # 비교 대상이 없다는 것은 조치 전 스냅샷을 남기지 않았다는
                # 뜻입니다. 조용히 빈 값을 주면 복구로 오판합니다.
                # DETECT 는 여기 끼지 않습니다 — 감지 시점과 비교하면
                # 대기 중 자기악화분까지 조치 성과로 잡힙니다.
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
    _reject_canary(service)
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
