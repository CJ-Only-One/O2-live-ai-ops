"""조치 상태 머신의 결정론적 절반. Dify 가 두 지점에서 부른다.

`scenario-experiment.md` 0.4 의 상태 머신에서 **LLM 이 만들면 안 되는 판정**만
여기로 뺐다. 조치안을 고르고 설명을 쓰는 것은 LLM 이 하고, 아래 넷은 값으로
정한다.

  Baseline   실행 락 · 기준값 기록 · 멱등 키 · 런북 반복 금지
  Restore    원복에 쓸 조치 직전 설정값 보관
  Judging    검증 판정 · 세 갈래 · 재분석 1회 상한

왜 나눴나. 게이트 진입을 노브 카탈로그 조회로 정하기로 한 것(D-067)과 같은
이유다 — 같은 상황에서 같은 답이 나와야 실험이 반복 가능하고, 녹화도 테이크마다
달라지지 않는다.

저장은 `incident_state` 테이블을 그대로 쓴다. pk 규약이 하나 는다:

    SIGNAL#{digest}                  correlator 의 source 신호 claim
    INCIDENT#{incident_id}           correlator 의 인시던트 스냅샷
    ACTION#{incident_id}#{action_id} 여기서 만드는 조치 시도 기록
    LOCK#{incident_id}               인시던트당 하나뿐인 실행 락

요청/응답은 JSON 하나다. `op` 로 갈린다.
"""

import hashlib
import hmac
import json
import os
import time

import boto3

TABLE_NAME = os.environ["INCIDENT_STATE_TABLE"]
SECRET_NAME = os.environ["ACTION_STATE_SECRET_NAME"]
API_KEY_HEADER = "x-api-key"

# 조치 기록은 인시던트가 끝나도 한동안 남겨 재분석 이력을 본다. correlator 의
# 신호 claim 보다 길게 잡되 무한은 아니다 — 테이블은 상태 저장소이지 이력
# 저장소가 아니다. 이력의 원본은 history.tf 의 S3 다.
RECORD_TTL_SECONDS = 7 * 24 * 3600

# 재분석은 1회다. 초과하면 사람에게 넘긴다(`scenario-experiment.md` 0.6).
MAX_REANALYSIS = 1

_table = boto3.resource("dynamodb").Table(TABLE_NAME)
_secrets = None


def _load_secrets():
    global _secrets
    if _secrets is None:
        raw = boto3.client("secretsmanager").get_secret_value(SecretId=SECRET_NAME)
        _secrets = json.loads(raw["SecretString"])
    return _secrets


def _err(status, code, **extra):
    return {"statusCode": status, "body": json.dumps({"error": code, **extra})}


def _ok(body):
    return {"statusCode": 200, "body": json.dumps(body, default=str)}


def _action_key(incident_id, action_id):
    return f"ACTION#{incident_id}#{action_id}"


def _lock_key(incident_id):
    return f"LOCK#{incident_id}"


# ── 판정 ────────────────────────────────────────────────────────────────

_COMPARISONS = {
    "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
}


def _check(conditions, metrics, baseline=None):
    """조건 목록을 전부 판정한다. (통과여부, 미달목록)

    `relative_to` 가 있으면 절대 임계가 아니라 기준값과 비교한다 — 자연 회복을
    조치 효과로 세지 않기 위해서다(D-054). 기준값이 없으면 **통과로 치지 않고
    미달로 센다.** 없는 것을 만족으로 세면 기준선 검사가 조용히 사라진다.
    """
    failed = []
    for cond in conditions or []:
        metric = cond["metric"]
        observed = metrics.get(metric)
        compare = _COMPARISONS.get(cond["comparison"])
        if observed is None or compare is None:
            failed.append({"metric": metric, "reason": "MISSING_OBSERVATION"})
            continue
        if "relative_to" in cond:
            threshold = (baseline or {}).get(cond["relative_to"])
            if threshold is None:
                failed.append({"metric": metric, "reason": "MISSING_BASELINE"})
                continue
        else:
            threshold = cond["threshold"]
        if not compare(float(observed), float(threshold)):
            failed.append({"metric": metric, "observed": observed, "threshold": threshold})
    return (not failed), failed


def _direction(metrics, baseline, verification_metrics):
    """조치 전후를 비교해 악화 / 개선 / 변화없음 중 하나를 고른다.

    검증 지표는 전부 "작을수록 좋다" 축이다(p95·오류율·차단률). 다른 축이
    생기면 노브 카탈로그에 방향을 실어야 한다 — 지금은 그런 지표가 없다.

    5% 는 측정 잡음 폭이 아니라 **자리값**이다. 실측 전까지 이 값으로 판정이
    뒤집히는 경우는 사람이 본다(`scenario-experiment.md` 1.1 원칙 셋째).
    """
    worse = better = 0
    for metric in verification_metrics or []:
        before, after = baseline.get(metric), metrics.get(metric)
        if before is None or after is None:
            continue
        before, after = float(before), float(after)
        if before == 0:
            continue
        delta = (after - before) / abs(before)
        if delta > 0.05:
            worse += 1
        elif delta < -0.05:
            better += 1
    if worse:
        return "WORSE"
    if better:
        return "BETTER"
    return "FLAT"


def judge(record, metrics, success_criteria, diagnostic_contamination):
    """검증 결과를 네 갈래 중 하나로 정한다.

    갈래를 `diagnostic_contamination` 하나로 정하지 않는다. 세 노브가 전부
    오염 참이라(D-067) 그것만 보면 KeepAndReanalyze 가 영영 안 나오고, S2 의
    "1차 증설은 무해하니 그대로 두고 재분석한다"(0.6) 가 성립하지 않는다.
    **먼저 악화 여부를 보고, 그다음에 오염을 본다.**
    """
    baseline = record.get("baseline") or {}
    criteria = success_criteria or {}
    absolute_ok, absolute_failed = _check(criteria.get("conditions"), metrics)
    relative_ok, relative_failed = _check(
        criteria.get("baseline_conditions"), metrics, baseline
    )

    # 절대 SLO 복귀 AND 기준선 대비 개선. 둘 다 요구한다(D-054).
    if absolute_ok and relative_ok:
        return {"verdict": "RESOLVED", "failed": []}

    failed = absolute_failed + relative_failed
    if int(record.get("reanalysis_count") or 0) >= MAX_REANALYSIS:
        return {"verdict": "ESCALATED", "failed": failed, "reason": "REANALYSIS_EXHAUSTED"}

    direction = _direction(metrics, baseline, criteria.get("verification_metrics") or [
        cond["metric"] for cond in (criteria.get("conditions") or [])
    ])
    if direction == "WORSE":
        return {"verdict": "ROLLBACK_NOW", "failed": failed, "reason": "WORSENED"}
    if direction == "FLAT" and diagnostic_contamination:
        # 효과도 없는데 다음 진단 지표를 흐린다. 남길 이유가 없다.
        return {"verdict": "ROLLBACK_NOW", "failed": failed, "reason": "NO_EFFECT_AND_CONTAMINATES"}
    return {"verdict": "KEEP_AND_REANALYZE", "failed": failed, "reason": direction}


# ── 연산 ────────────────────────────────────────────────────────────────


def _op_baseline(body):
    incident_id = body["incident_id"]
    action_id = body["action_id"]
    revision = int(body["revision"])
    idempotency_key = f"incident:{incident_id}:revision:{revision}:action:{action_id}"
    now = int(time.time())

    existing = _table.get_item(Key={"pk": _action_key(incident_id, action_id)}).get("Item")
    if existing:
        # 같은 조치를 같은 revision 에서 다시 부르면 같은 답을 준다. 재시도가
        # 기준값을 덮어쓰면 "조치 직전" 이 조치 이후 값으로 바뀐다.
        if existing.get("idempotency_key") == idempotency_key:
            return _ok({"status": "ALREADY_RECORDED", **_public(existing)})
        # 런북 반복 금지 — 같은 절차가 이미 검증에 실패했다(0.4 불변조건).
        if existing.get("status") == "VERIFY_FAILED":
            return _err(409, "RUNBOOK_REPEAT_FORBIDDEN", action_id=action_id)

    # 인시던트당 실행 락 하나. correlator 가 revision 을 직렬화해도 조치는
    # 별개다 — 승인 대기 중에 다른 조치가 들어오면 기준값이 섞인다.
    try:
        _table.put_item(
            Item={
                "pk": _lock_key(incident_id),
                "action_id": action_id,
                "idempotency_key": idempotency_key,
                "acquired_at": now,
                "expires_at": now + RECORD_TTL_SECONDS,
            },
            ConditionExpression="attribute_not_exists(pk) OR idempotency_key = :k",
            ExpressionAttributeValues={":k": idempotency_key},
        )
    except _table.meta.client.exceptions.ConditionalCheckFailedException:
        held = _table.get_item(Key={"pk": _lock_key(incident_id)}).get("Item") or {}
        return _err(409, "ACTION_IN_PROGRESS", holder=held.get("action_id"))

    record = {
        "pk": _action_key(incident_id, action_id),
        "incident_id": incident_id,
        "action_id": action_id,
        "revision": revision,
        "idempotency_key": idempotency_key,
        "status": "ACTING",
        "baseline": body.get("metrics") or {},
        "reanalysis_count": int((existing or {}).get("reanalysis_count") or 0),
        "recorded_at": now,
        "expires_at": now + RECORD_TTL_SECONDS,
    }
    _table.put_item(Item=record)
    return _ok({"status": "BASELINE_RECORDED", **_public(record)})


def _op_judge(body):
    incident_id = body["incident_id"]
    action_id = body["action_id"]
    record = _table.get_item(Key={"pk": _action_key(incident_id, action_id)}).get("Item")
    if not record:
        # 기준값 없이 판정하면 자연 회복을 조치 효과로 적게 된다.
        return _err(409, "NO_BASELINE", action_id=action_id)

    result = judge(
        record,
        body.get("metrics") or {},
        body.get("success_criteria"),
        bool(body.get("diagnostic_contamination")),
    )
    verdict = result["verdict"]

    record["status"] = "RESOLVED" if verdict == "RESOLVED" else "VERIFY_FAILED"
    record["verdict"] = verdict
    if verdict == "KEEP_AND_REANALYZE":
        record["reanalysis_count"] = int(record.get("reanalysis_count") or 0) + 1
    _table.put_item(Item=record)

    # 락은 조치가 끝난 시점에 푼다. 재분석은 새 조치를 고르는 단계라 락을
    # 쥔 채로 두면 다음 조치가 못 들어온다.
    _table.delete_item(Key={"pk": _lock_key(incident_id)})

    return _ok({**result, **_public(record)})


def _op_record_restore(body):
    """원복에 쓸 조치 직전 설정값을 조치 기록에 붙인다.

    왜 `baseline` 과 따로인가. 값을 아는 시점이 다르다 — Deployment 의 이전
    replicas 는 조치 실행기가 patch 직전에 읽어야 알 수 있고, 그때는 이미
    `baseline` 이 끝난 뒤다. 실행기가 직접 쓰게 하면 그쪽에 DynamoDB 권한을
    줘야 해서 `deployments/scale` 만 주기로 한 경계(D-059)가 넓어진다.

    **먼저 쓴 값이 이긴다.** 조치 뒤에 재시도가 같은 op 를 다시 부르면 그때
    읽은 값은 이미 조치 후 값이라, 덮어쓰면 원복이 조치 상태로 되돌린다.
    `baseline` 의 기준값을 안 덮어쓰는 것과 같은 이유다.
    """
    incident_id = body["incident_id"]
    action_id = body["action_id"]
    restore = body["restore"]
    if not isinstance(restore, dict) or not restore:
        return _err(400, "RESTORE_MUST_BE_NON_EMPTY_OBJECT")

    key = _action_key(incident_id, action_id)
    record = _table.get_item(Key={"pk": key}).get("Item")
    if not record:
        return _err(409, "NO_BASELINE", action_id=action_id)

    existing = record.get("restore")
    if existing:
        if existing != restore:
            return _err(409, "RESTORE_ALREADY_RECORDED", recorded=existing)
        return _ok({"status": "ALREADY_RECORDED", **_public(record)})

    record["restore"] = restore
    _table.put_item(Item=record)
    return _ok({"status": "RESTORE_RECORDED", **_public(record)})


def _public(record):
    return {
        "incident_id": record.get("incident_id"),
        "action_id": record.get("action_id"),
        "revision": record.get("revision"),
        "idempotency_key": record.get("idempotency_key"),
        "action_status": record.get("status"),
        "baseline": record.get("baseline"),
        # 원복 경로가 읽는 값. 없으면 되돌릴 대상을 모른다는 뜻이라,
        # 호출자가 키의 부재로 그것을 구분할 수 있어야 한다.
        "restore": record.get("restore"),
        "reanalysis_count": int(record.get("reanalysis_count") or 0),
        "max_reanalysis": MAX_REANALYSIS,
    }


_OPS = {"baseline": _op_baseline, "record_restore": _op_record_restore, "judge": _op_judge}


def lambda_handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    expected = _load_secrets()["action-state-api-key"]
    if not hmac.compare_digest(headers.get(API_KEY_HEADER) or "", expected):
        return _err(403, "forbidden")

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _err(400, "bad json")

    op = _OPS.get(body.get("op"))
    if op is None:
        return _err(400, "unknown op", allowed=sorted(_OPS))
    try:
        return op(body)
    except KeyError as e:
        return _err(400, "missing field", field=str(e).strip("'"))
