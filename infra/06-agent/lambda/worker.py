"""대기열에서 알림을 하나 받아 Dify 워크플로를 실행하고, 결과를 이력에 남긴다.

Ingress 가 InvocationType="Event" 로 깨우므로 `event` 는 Datadog 이 보낸
알림 dict 그대로다. HTTP 이벤트가 아니라 봉투가 없다.

VPC 안에 있어야 Dify 를 사설 IP 로 부를 수 있다. 동시성은 Dify 가 감당하는
수에 맞춘다 — 이 파이프라인의 처리량 상한은 Lambda 가 아니라 Dify 다.

순서는 넷이다.

  1. 알림 텍스트를 벡터로 바꾼다            (Bedrock Titan, 호출 1회)
  2. 그 벡터로 과거 인시던트를 찾는다        (S3 Vectors)
  3. 찾은 것을 past_cases 로 넘겨 Dify 실행
  4. 이번 건을 저장한다                     (S3 원본 + S3 Vectors)

★ 검색과 저장은 **절대 예외를 올리지 않는다.** 이유가 서로 다르다.

  검색 실패 → past_cases 만 비우고 그대로 진행한다. 과거 사례는 있으면
    좋은 보조 정보이지 필수 입력이 아니다. 그것 하나 때문에 알림 분석
    전체를 잃는 것은 손해다.

  저장 실패 → 로그만 남기고 성공으로 끝낸다. 이 함수의 예외는 재시도와
    DLQ 를 부르는데, 이 시점엔 Dify 가 이미 성공한 뒤다. 재실행하면
    LLM 비용이 두 배가 되고 같은 인시던트가 두 번 쌓인다.

  아래 "실패는 반드시 예외로" 규칙은 **Dify 호출에만** 해당한다.

★ Dify 호출 실패는 반드시 **예외로** 알려야 한다.
  비동기 호출에서 Lambda 는 반환값을 읽지 않는다. `return {"statusCode": 502}`
  는 성공으로 취급되고, 그러면 재시도도 DLQ 도 동작하지 않는다.
  알림이 조용히 사라지는 경로다 — docs/troubleshooting.md T-011.
"""

import datetime
import json
import os
import urllib.error
import urllib.request

import boto3

# 값이 아니라 "시크릿 이름"만 환경변수로 받는다. 값을 환경변수에 넣으면
# terraform state 에 평문으로 남는다 (06-datastream/warm-path.tf 와 같은 패턴).
SECRET_NAME = os.environ["ALERT_SECRET_NAME"]
DIFY_URL = os.environ["DIFY_URL"]

# ★ 이 넷만 대괄호가 아니라 .get() 이다. 실수가 아니다.
#   lambda_o2.tf 의 두 번째 파이프라인(o2-dify-ingress/o2-dify-worker)이
#   **이 파일의 zip 을 그대로 공유한다.** 그쪽에는 이 변수들이 없으므로
#   os.environ["..."] 로 읽으면 import 시점에 KeyError 가 나고 그 파이프라인이
#   통째로 죽는다 — 알림 경로 하나가 조용히 사라지는 사고다.
#
#   그래서 이력 기록은 **환경변수가 있는 파이프라인에서만 켜진다.** O2 쪽을
#   켜려면 lambda_o2.tf 에 같은 변수와 IAM 을 넣으면 되는데, 지금은 일부러
#   안 한다. 두 파이프라인이 같은 모니터를 받으면 cycle_key 가 겹쳐 서로의
#   인시던트를 덮어쓴다. 켤 때 키에 파이프라인 구분을 먼저 넣어야 한다.
HISTORY_BUCKET = os.environ.get("HISTORY_BUCKET")
VECTOR_BUCKET = os.environ.get("VECTOR_BUCKET")
VECTOR_INDEX = os.environ.get("VECTOR_INDEX")
EMBED_MODEL_ID = os.environ.get("EMBED_MODEL_ID")

HISTORY_ENABLED = all([HISTORY_BUCKET, VECTOR_BUCKET, VECTOR_INDEX, EMBED_MODEL_ID])

TOP_K = 3

# 코사인 거리. 0 이 같은 글, 2 가 정반대다.
#
# ★ 이 값은 근거 있는 상수가 아니라 **눈금**이다. 실제 알림으로 재보고 맞춘다.
#   느슨하면 상관없는 사례가 "과거 사례"로 프롬프트에 들어가 LLM 이 거기에
#   끌려간다 (docs/architecture.md 7.4 "오판의 재학습"). 빡빡하면 재발을 놓친다.
#   초기값은 보수적으로 잡았다 — 놓치는 쪽이 잘못 엮는 쪽보다 낫다.
MAX_DISTANCE = 0.35

_secrets = None
_bedrock = None
_s3 = None
_s3vectors = None


def _load_secrets():
    global _secrets
    if _secrets is None:
        raw = boto3.client("secretsmanager").get_secret_value(SecretId=SECRET_NAME)
        _secrets = json.loads(raw["SecretString"])
    return _secrets


def _clients():
    """무거운 클라이언트는 처음 쓸 때 만든다. 콜드스타트를 늘리지 않는다.

    ★ s3vectors 는 2025년에 추가된 서비스라 **런타임에 들어 있는 boto3 가
      낡으면 UnknownServiceError 가 난다.** 그때 로그에 boto3 버전이 찍히므로
      원인이 바로 보인다. 해결은 README "이력 저장소" 절 참고.
    """
    global _bedrock, _s3, _s3vectors
    if _s3 is None:
        _bedrock = boto3.client("bedrock-runtime")
        _s3 = boto3.client("s3")
        _s3vectors = boto3.client("s3vectors")
    return _bedrock, _s3, _s3vectors


def _alert_text(event):
    """임베딩 대상 텍스트.

    ★ Dify 의 판단문을 여기 섞지 않는다. 검색은 "들어온 알림" 대 "과거 알림"
      비교다. 저장 쪽에만 판단문을 붙이면 두 텍스트의 성격이 달라져 유사도가
      흐려진다. 판단 결과는 메타데이터와 S3 원본에만 넣는다.

      덕분에 검색용과 저장용이 같은 벡터라 Bedrock 호출이 알림당 한 번이다.
    """
    parts = [
        event.get("alert_title", ""),
        event.get("alert_body", ""),
        event.get("alert_query", ""),
        event.get("tags", ""),
    ]
    # titan-embed-text-v2 입력 상한은 8192 토큰이다. 문자 수로 넉넉히 자른다.
    return "\n".join(p for p in parts if p)[:8000]


def _embed(text):
    """알림 텍스트 → 1024차원 벡터. 실패하면 None."""
    bedrock, _, _ = _clients()
    res = bedrock.invoke_model(
        modelId=EMBED_MODEL_ID,
        body=json.dumps({"inputText": text, "dimensions": 1024, "normalize": True}),
    )
    return json.loads(res["body"].read())["embedding"]


def _search(vector):
    """비슷한 과거 인시던트를 찾아 프롬프트에 넣을 문장으로 만든다."""
    _, _, s3vectors = _clients()
    res = s3vectors.query_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=VECTOR_INDEX,
        queryVector={"float32": vector},
        topK=TOP_K,
        returnMetadata=True,
        returnDistance=True,
    )

    lines = []
    for hit in res.get("vectors", []):
        if hit.get("distance", 99) > MAX_DISTANCE:
            continue
        meta = hit.get("metadata") or {}
        lines.append(
            f"- [{meta.get('occurred_at', '?')}] {meta.get('service', '?')} "
            f"(monitor {meta.get('monitor_id', '?')})\n"
            f"  {meta.get('summary', '')}"
        )

    print("history: matched", len(lines), "of", len(res.get("vectors", [])))
    return "\n".join(lines)


def _incident_key(event):
    """cycle_key 가 Triggered 와 Recovered 를 묶는다. 비면 event_id 로 떨어진다."""
    return event.get("cycle_key") or event.get("event_id") or "unknown"


def _store(event, vector, dify_data, past_cases):
    """S3 에 원본, S3 Vectors 에 벡터. 스키마는 docs/architecture.md 7.3 이다."""
    _, s3, s3vectors = _clients()

    key = _incident_key(event)
    now = datetime.datetime.now(datetime.timezone.utc)
    result = (dify_data.get("outputs") or {}).get("result", "")
    s3_key = f"incidents/dt={now:%Y-%m-%d}/{key}.json"

    # 지금 채울 수 없는 필드도 키는 남긴다. 나중에 붙일 자리를 문서가 아니라
    # 데이터가 들고 있게 하려는 것이다 — 사후 구조화는 대부분 실패한다.
    incident = {
        "schema_version": "1.0",
        "incident_id": key,
        "trace_id": event.get("event_id", ""),
        "started_at": now.isoformat(),
        "occurred_at": event.get("occurred_at", ""),
        "trigger": {
            "source": "datadog_monitor",
            "monitor_id": event.get("monitor_id", ""),
            "severity": event.get("priority", ""),
            "link": event.get("link", ""),
        },
        "context": {
            "service": event.get("service", ""),
            "env": event.get("env", ""),
            "host": event.get("host", ""),
            "tags": event.get("tags", ""),
            "signal_summary": event.get("alert_title", ""),
            "alert_query": event.get("alert_query", ""),
            "alert_body": event.get("alert_body", ""),
        },
        "agent": {
            "steps": [],
            "hypothesis": result,
            "action_taken": "none",
            "total_tokens": None,
            "duration_ms": int(float(dify_data.get("elapsed_time") or 0) * 1000),
            "past_cases_used": bool(past_cases),
        },
        # resolved 와 mttr_sec 은 resolutions/ 와 짝지어 나중에 채운다.
        # human_verified 는 사람이 손으로 뒤집는다 — 여기서 true 로 시작하면
        # 검증이라는 말이 의미를 잃는다.
        "outcome": {
            "resolved": None,
            "mttr_sec": None,
            "root_cause_label": None,
            "human_verified": False,
            "human_correction": None,
        },
    }

    s3.put_object(
        Bucket=HISTORY_BUCKET,
        Key=s3_key,
        Body=json.dumps(incident, ensure_ascii=False).encode(),
        ContentType="application/json",
    )

    # 벡터 키도 cycle_key 다. 같은 인시던트가 두 번 들어와도 덮어써서
    # 중복이 안 쌓인다.
    s3vectors.put_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=VECTOR_INDEX,
        vectors=[
            {
                "key": key,
                "data": {"float32": vector},
                "metadata": {
                    "monitor_id": str(event.get("monitor_id", "")),
                    "service": event.get("service", ""),
                    "env": event.get("env", ""),
                    "occurred_at": now.strftime("%Y-%m-%d"),
                    "s3_key": s3_key,
                    "human_verified": False,
                    # 프롬프트에 그대로 들어가는 문장이다. 길면 다음 알림의
                    # 입력이 통째로 부풀어 토큰이 샌다.
                    "summary": f"{event.get('alert_title', '')} → {result}"[:600],
                },
            }
        ],
    )
    print("history: stored", s3_key)


def lambda_handler(event, context):
    secrets = _load_secrets()
    print("processing:", event.get("event_id"), event.get("alert_title"))

    # ── 1~2. 임베딩과 검색 ────────────────────────────────────────
    # 실패해도 진행한다. 여기서 멈추면 알림 분석 자체를 잃는다.
    vector = None
    past_cases = ""
    if not HISTORY_ENABLED:
        print("history: disabled (env not set)")
    else:
        try:
            vector = _embed(_alert_text(event))
            past_cases = _search(vector)
        except Exception as e:  # noqa: BLE001 — 무엇이 터지든 분석은 계속한다
            print("history search failed:", type(e).__name__, e, "boto3", boto3.__version__)

    # ── 3. Dify 실행 ──────────────────────────────────────────────
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
            # 첫 알림에서는 항상 빈 문자열이다. Dify 쪽에서 **선택** 변수여야
            # 한다 — 필수인데 비면 API 가 400 을 낸다.
            "past_cases": past_cases,
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

    # ── 4. 저장 ───────────────────────────────────────────────────
    # 여기서 예외를 올리면 이미 성공한 Dify 를 다시 부르게 된다. 로그만 남긴다.
    if vector is not None:
        try:
            _store(event, vector, data, past_cases)
        except Exception as e:  # noqa: BLE001 — Dify 는 이미 성공했다
            print("history store failed:", type(e).__name__, e)

    return {"ok": True}
