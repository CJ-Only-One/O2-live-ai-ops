"""알림을 Dify 로 보내 분석하고, 복구되면 그 결과를 이력에 적재한다.

Ingress 가 InvocationType="Event" 로 깨우므로 `event` 는 Datadog 이 보낸
알림 dict 그대로다. HTTP 이벤트가 아니라 봉투가 없다.

VPC 안에 있어야 Dify 를 사설 IP 로 부를 수 있다. 동시성은 Dify 가 감당하는
수에 맞춘다 — 이 파이프라인의 처리량 상한은 Lambda 가 아니라 Dify 다.

경로가 둘이다. `alert_transition` 으로 갈린다.

  Triggered  분석. 임베딩 → 과거 사례 검색 → Dify → 저장
  Recovered  적재. 벡터에서 원본을 찾아 결과를 채운다. **Dify 를 부르지 않는다**

★ 실패했을 때 예외를 올리는지가 경로마다 다르다. 규칙이 아니라 결과로 정했다.

  Dify 호출 실패        → **올린다.** 비동기 호출에서 Lambda 는 반환값을 읽지
    않는다. `return {"statusCode": 502}` 는 성공으로 취급되고 재시도도 DLQ 도
    동작하지 않는다. 알림이 조용히 사라지는 경로다 — T-011

  과거 사례 검색 실패   → **안 올린다.** past_cases 만 비우고 진행한다. 보조
    정보 하나 때문에 알림 분석 전체를 잃는 것은 손해다

  Triggered 저장 실패   → **안 올린다.** 이 시점엔 Dify 가 이미 성공했다.
    재시도하면 LLM 비용이 두 배가 되고 같은 인시던트가 두 번 쌓인다

  Recovered 적재 실패   → **올린다.** 여기는 LLM 을 안 부르고 멱등하다
    (이미 닫힌 건은 건너뛴다). 재시도가 공짜이므로 막히면 알려야 한다

  세 번째와 네 번째가 정반대다. 헷갈려서 통일하지 마라 — 비싼 쪽을 재시도하지
  않고 싼 쪽만 재시도하는 것이 이 배치의 요점이다.
"""

import datetime
import json
import os
import re
import urllib.error
import urllib.request

import boto3

# 값이 아니라 "시크릿 이름"만 환경변수로 받는다. 값을 환경변수에 넣으면
# terraform state 에 평문으로 남는다 (06-datastream/warm-path.tf 와 같은 패턴).
SECRET_NAME = os.environ["ALERT_SECRET_NAME"]
DIFY_URL = os.environ["DIFY_URL"]

# ★ 이 넷만 대괄호가 아니라 .get() 이다. 실수가 아니다.
#   lambda_o2.tf 의 두 번째 파이프라인(o2-dify-ingress/o2-dify-worker)이
#   **이 파일의 zip 을 그대로 공유한다.** 이 넷을 os.environ["..."] 로 읽으면
#   이 변수가 없는 쪽에서 import 시점에 KeyError 가 나고 그 파이프라인이
#   통째로 죽는다 — 알림 경로 하나가 조용히 사라지는 사고다. 이 zip 을
#   공유하는 파이프라인이 앞으로 더 생겨도 같은 이유로 계속 .get() 이어야 한다.
#
#   O2 파이프라인은 2026-08-22 부터 이력 기록이 켜져 있다(history_o2.tf,
#   커밋 6d3a5ab7) — cycle_key 충돌을 피하려고 버킷/벡터인덱스를 원본과
#   완전히 분리한 전용 리소스로 켰다.
HISTORY_BUCKET = os.environ.get("HISTORY_BUCKET")
VECTOR_BUCKET = os.environ.get("VECTOR_BUCKET")
VECTOR_INDEX = os.environ.get("VECTOR_INDEX")
EMBED_MODEL_ID = os.environ.get("EMBED_MODEL_ID")

HISTORY_ENABLED = all([HISTORY_BUCKET, VECTOR_BUCKET, VECTOR_INDEX, EMBED_MODEL_ID])

SCHEMA_VERSION = "1.1"

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


# ── 검색 ─────────────────────────────────────────────────────────


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
    """알림 텍스트 → 1024차원 벡터."""
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
    skipped_unverified = 0
    for hit in res.get("vectors", []):
        if hit.get("distance", 99) > MAX_DISTANCE:
            continue
        meta = hit.get("metadata") or {}
        # 과거 사례의 유사도는 "같은 원인"의 증거가 아니다. 사람이 검증해
        # verified=True로 갱신한 사례만 Dify 입력에 넣는다. 구형·누락 메타데이터도
        # 안전하게 미검증으로 취급한다.
        if meta.get("verified") is not True:
            skipped_unverified += 1
            continue
        lines.append(f"- {meta.get('summary', '')}")

    print(
        "history: matched", len(lines), "of", len(res.get("vectors", [])),
        "skipped_unverified", skipped_unverified,
    )
    return "\n".join(lines)


# ── 이력 표현 ─────────────────────────────────────────────────────


def _incident_key(event):
    """cycle_key 가 Triggered 와 Recovered 를 묶는다. 비면 event_id 로 떨어진다."""
    return event.get("cycle_key") or event.get("event_id") or "unknown"


def _epoch_sec(value):
    """Datadog `$DATE_POSIX` 를 초로 맞춘다. 없으면 None.

    ★ 이 값이 초인지 밀리초인지는 문서로 확정되지 않는다. 잘못 읽으면 MTTR 이
      1000배 틀리는데 **그게 그럴듯한 숫자로 보여서** 아무도 눈치채지 못한다.
      단위를 가정하지 않고 크기로 가른다 — 지금 초는 약 1.7e9, 밀리초는 약 1.7e12 라
      1e11 로 깨끗하게 갈린다.
    """
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return None
    return n // 1000 if n > 10**11 else n


def _mttr_sec(occurred_at, recovered_at):
    """장애 발생부터 복구까지 초. 못 구하면 None."""
    start, end = _epoch_sec(occurred_at), _epoch_sec(recovered_at)
    if start is None or end is None or end < start:
        return None
    return end - start


def _ending(state, mttr_sec):
    """어떻게 끝났나를 한 조각으로."""
    if state == "unresolved":
        return "복구 미확인"
    if state == "false_alarm":
        return "오탐, 조치 없음"

    took = f"{mttr_sec // 60}분" if mttr_sec is not None else "시간 미상"
    return {
        "auto_recovered": f"{took} 뒤 자동복구",
        "human_fixed": f"사람이 조치 · {took}",
        "agent_fixed": f"에이전트 조치 · {took}",
    }.get(state, took)


# Datadog `$EVENT_TITLE` 이 앞에 붙이는 상태 딱지. 요약에서는 걷어낸다.
#
# ★ 걷어내는 이유가 토큰 절약만이 아니다. 이 줄은 "과거 사례"로 프롬프트에
#   들어가는데, `[Triggered] ... · 12분 뒤 자동복구` 는 **한 줄 안에서 서로
#   모순된다.** 상태는 우리가 붙이는 딱지([미검증]/[확인됨])가 말한다.
#
# `[TEST]` 나 `[O2]` 처럼 팀이 붙인 것은 건드리지 않는다.
_DD_TRANSITION = re.compile(
    r"^\s*(\[(triggered|re-triggered|recovered|warn|no data|renotify)\]\s*)+",
    re.IGNORECASE,
)


def _summary(title, outcome):
    """프롬프트에 그대로 들어가는 한 줄.

    ★ **검증되지 않은 사례는 원인을 말하지 않는다.** 사실만 남긴다 —
      "전에도 왔고 12분 뒤 저절로 돌아갔다" 까지다.

      에이전트 추측을 여기 넣으면 다음 알림에서 그것이 "과거 사례"로 다시 읽혀
      추측이 사실로 승격된다 (docs/architecture.md 7.4 "오판의 재학습").
      프롬프트에 "참고이지 정답이 아니다" 를 적어 두는 것보다, 애초에 넣지
      않는 편이 세다 — **규칙은 무시될 수 있지만 없는 데이터는 읽을 수 없다.**

      추측 전문은 S3 원본의 `agent.hypothesis` 에 그대로 남는다. 지우는 것이
      아니라 검색 코퍼스에서 빼는 것이다.
    """
    state = outcome.get("state", "unresolved")
    verified = bool(outcome.get("verified"))
    label = outcome.get("root_cause_label")

    if state == "false_alarm":
        head = "[오탐]"
    elif verified:
        head = "[확인됨]"
    elif state == "unresolved":
        head = "[진행중]"
    else:
        head = "[미검증]"

    clean = _DD_TRANSITION.sub("", title or "").strip()
    parts = [head, clean[:60]]
    if verified and label:
        parts.append(label)
    parts.append(_ending(state, outcome.get("mttr_sec")))
    return " · ".join(p for p in parts if p)


def _metadata(incident):
    """벡터에 붙일 메타데이터. **원본 하나에서만 만든다.**

    저장할 때와 복구를 적재할 때가 같은 함수를 쓰므로 두 경로가 어긋나지 않는다.

    ★ 값이 없는 키는 넣지 않는다. `-1` 같은 표식을 넣으면 나중에
      `mttr_sec > 0` 같은 필터가 그 표식까지 걸러야 한다.
    """
    ctx, trg, out = incident["context"], incident["trigger"], incident["outcome"]
    meta = {
        "monitor_id": str(trg.get("monitor_id", "")),
        "service": ctx.get("service", ""),
        "env": ctx.get("env", ""),
        "occurred_at": incident["started_at"][:10],
        "s3_key": incident["s3_key"],
        "outcome_state": out.get("state", "unresolved"),
        "verified": bool(out.get("verified")),
        "summary": _summary(ctx.get("signal_summary", ""), out),
    }
    if out.get("mttr_sec") is not None:
        meta["mttr_sec"] = out["mttr_sec"]
    if out.get("root_cause_label"):
        meta["root_cause_label"] = out["root_cause_label"]
    return {k: v for k, v in meta.items() if v != ""}


def _put_vector(key, data, incident):
    """벡터를 덮어쓴다. 키가 cycle_key 라 같은 인시던트는 늘 한 줄이다."""
    _, _, s3vectors = _clients()
    s3vectors.put_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=VECTOR_INDEX,
        vectors=[{"key": key, "data": data, "metadata": _metadata(incident)}],
    )


def _put_incident(incident):
    _, s3, _ = _clients()
    s3.put_object(
        Bucket=HISTORY_BUCKET,
        Key=incident["s3_key"],
        Body=json.dumps(incident, ensure_ascii=False).encode(),
        ContentType="application/json",
    )


# ── Triggered ────────────────────────────────────────────────────


def _last_action_taken(outputs):
    """final_report_json 의 attempt_log 마지막 항목에서 실행된 action_id 를 뽑는다.

    o2-aiops-workflow 가 조치(remediation)까지 하게 된 뒤에도 이 값은 계속
    "none" 으로 고정돼 있었다 — 이 함수를 만들기 전엔 diagnosis-only 시절
    가정이 그대로 남아 있었다. attempt_log 가 비어 있으면(예: 진단만 하고
    끝난 케이스) 여전히 "none" 이 맞는 값이다.
    """
    try:
        report = json.loads(outputs.get("final_report_json") or "{}")
    except (TypeError, ValueError):
        return "none"
    attempts = report.get("attempt_log") or []
    if not attempts:
        return "none"
    action_id = ((attempts[-1].get("action_result") or {}).get("action_id"))
    return action_id or "none"


def _build_incident(event, dify_data, past_cases):
    """스키마는 docs/architecture.md 7.3 을 따르되 outcome 만 다르다 — D-045."""
    now = datetime.datetime.now(datetime.timezone.utc)
    key = _incident_key(event)
    outputs = dify_data.get("outputs") or {}
    result = outputs.get("result", "")

    return {
        "schema_version": SCHEMA_VERSION,
        "incident_id": key,
        "trace_id": event.get("event_id", ""),
        "s3_key": f"incidents/dt={now:%Y-%m-%d}/{key}.json",
        "started_at": now.isoformat(),
        "occurred_at": event.get("occurred_at", ""),
        "recovered_at": None,
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
            # 검색 코퍼스에는 안 들어간다. 사람이 검증할 때 읽는 자리다.
            "hypothesis": result,
            "action_taken": _last_action_taken(outputs),
            "duration_ms": int(float(dify_data.get("elapsed_time") or 0) * 1000),
            "past_cases_used": bool(past_cases),
            "runbook": None,
        },
        "outcome": {
            # ★ 시작은 반드시 unresolved 다. 아직 복구 신호를 못 받았으니 사실이고,
            #   Recovered 가 영영 안 오면 그대로 남아 별도 청소 작업이 필요 없다.
            "state": "unresolved",
            "mttr_sec": None,
            # 아래 셋은 사람이 채운다 — scripts/verify.py
            "root_cause_label": None,
            "verified": False,
            "human_correction": None,
        },
    }


def _store(event, vector, dify_data, past_cases):
    incident = _build_incident(event, dify_data, past_cases)
    _put_incident(incident)
    _put_vector(_incident_key(event), {"float32": vector}, incident)
    print("history: stored", incident["s3_key"])


# ── Recovered ────────────────────────────────────────────────────


def _handle_recovery(event):
    """복구 결과를 이력에 적재한다. Dify 도 Bedrock 도 부르지 않는다.

    ★ 임베딩을 다시 하지 않는다. 저장할 때 메타데이터에 `s3_key` 를 넣어 뒀고
      `GetVectors` 가 벡터값까지 돌려주므로, cycle_key 하나로 원본과 벡터를
      모두 찾는다. 가장 비싼 구간(임베딩 약 1.4초)을 통째로 건너뛴다.
    """
    _, s3, s3vectors = _clients()
    key = _incident_key(event)

    got = s3vectors.get_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=VECTOR_INDEX,
        keys=[key],
        returnData=True,
        returnMetadata=True,
    )
    hits = got.get("vectors") or []
    if not hits:
        # Triggered 를 못 받았거나 이력을 켜기 전 사건이다. 오류가 아니다 —
        # 복구 시각은 ingress 가 resolutions/ 에 남겨 두므로 나중에 짝지을 수 있다.
        print("recovery: no incident for", key)
        return {"ok": True, "merged": False}

    hit = hits[0]
    meta = hit.get("metadata") or {}

    # ★ flapping. 한 장애에 Recovered 가 여러 번 오면 **첫 번째만** 센다.
    #   두 번째부터 덮어쓰면 MTTR 이 마지막 진동까지 포함해 부풀어 오른다.
    #   (옛 스키마에는 이 키가 없다. 그때는 아직 안 닫힌 것으로 본다.)
    if meta.get("outcome_state", "unresolved") != "unresolved":
        print("recovery: already closed", key, meta.get("outcome_state"))
        return {"ok": True, "merged": False}

    raw = s3.get_object(Bucket=HISTORY_BUCKET, Key=meta["s3_key"])["Body"].read()
    incident = json.loads(raw)

    recovered_at = event.get("occurred_at", "")
    incident["schema_version"] = SCHEMA_VERSION
    incident["s3_key"] = meta["s3_key"]
    incident["recovered_at"] = recovered_at

    out = incident.setdefault("outcome", {})
    # ★ 기본값은 반드시 auto_recovered 다. Datadog `Recovered` 는 "지표가 임계
    #   아래로 돌아왔다" 일 뿐, 누가 고쳤다는 뜻이 아니다. 지금 에이전트는
    #   action_taken="none" — 분석만 하고 아무것도 고치지 않는다. 이것을
    #   human_fixed 로 적으면 발표의 MTTR 숫자가 거짓이 된다. 사람이 조치했다면
    #   사람이 그렇게 표시한다 (scripts/verify.py).
    out["state"] = "auto_recovered"
    out["mttr_sec"] = _mttr_sec(incident.get("occurred_at"), recovered_at)
    out.pop("resolved", None)  # 1.0 의 boolean. state 가 대체한다
    out.pop("human_verified", None)  # 1.0 의 이름. verified 로 바뀌었다
    out.setdefault("root_cause_label", None)
    out.setdefault("verified", False)
    out.setdefault("human_correction", None)

    _put_incident(incident)
    _put_vector(key, hit["data"], incident)

    print("recovery: merged", key, "mttr", out["mttr_sec"])
    return {"ok": True, "merged": True}


# ── 진입점 ───────────────────────────────────────────────────────


def lambda_handler(event, context):
    if event.get("alert_transition") == "Recovered":
        if not HISTORY_ENABLED:
            print("recovery: history disabled")
            return {"ok": True, "merged": False}
        # ★ 여기서는 예외를 막지 않는다. LLM 을 안 부르고 멱등하므로 재시도가
        #   공짜다. 막히면 DLQ 로 가서 알려주는 편이 낫다.
        return _handle_recovery(event)

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

    # blocking 이라 워크플로가 끝날 때까지 기다린다. Hot Path/Runbook Lookup
    # API 붙고 나서 승인 없는 경로도 실측 40~60초대로 늘었고, Slack 승인이
    # 걸리면 Dify 쪽 노드 타임아웃(최대 600초)만큼 기다려야 한다.
    # ★ 이 값보다 함수 자체의 timeout(lambda_o2.tf)이 반드시 더 커야 한다 —
    #   짧으면 Lambda 런타임이 이 예외처리보다 먼저 강제 종료해서 DLQ 로그가
    #   훨씬 알아보기 어려운 형태로 남는다.
    #
    # 노드가 더 늘어 이 값을 자꾸 올려야 하는 상황이 오면, 이 호출을 콜백
    # 방식으로 바꾼다(설계 문서 참조) — Dify 워커 점유가 병목이 되기 시작한다는 신호다.
    try:
        with urllib.request.urlopen(req, timeout=820) as res:
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
