"""조치 상태 머신 자체 점검. `python3 lambda/test_action_state.py` 로 돈다.

판정 로직만 본다 — DynamoDB 왕복은 대역으로 막고, **틀리면 조용히 잘못
판정하는 것**들만 확인한다.

  1. 절대 SLO 만 통과하고 기준선 조건이 없으면 통과로 세지 않는가
     (없는 것을 만족으로 세면 자연 회복이 조치 효과가 된다)
  2. S2 1차 검증 — 개선됐지만 미달이면 되돌리지 않고 재분석으로 가는가
  3. 악화하면 오염 여부와 무관하게 즉시 되돌리는가
  4. 재분석 1회를 넘기면 사람에게 넘기는가
  5. 실행 락이 두 번째 조치를 막는가
  6. 원복 값이 조치 뒤 재시도에 덮어써지지 않는가
     (덮어쓰면 원복이 조치 상태로 되돌린다 — 되돌린 줄 알고 넘어간다)

★ archive_file 이 action_state.py 만 zip 에 넣으므로 이 파일은 Lambda 에
  올라가지 않는다.
"""

import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("INCIDENT_STATE_TABLE", "dummy")
os.environ.setdefault("ACTION_STATE_SECRET_NAME", "dummy")


class _FakeTable:
    class _Exc(Exception):
        pass

    def __init__(self):
        self.items = {}
        client = types.SimpleNamespace(
            exceptions=types.SimpleNamespace(ConditionalCheckFailedException=self._Exc)
        )
        self.meta = types.SimpleNamespace(client=client)

    def get_item(self, Key=None, **_):
        item = self.items.get(Key["pk"])
        return {"Item": item} if item else {}

    def put_item(self, Item=None, ConditionExpression=None, ExpressionAttributeValues=None, **_):
        if ConditionExpression:
            held = self.items.get(Item["pk"])
            same = held and held.get("idempotency_key") == (ExpressionAttributeValues or {}).get(":k")
            if held and not same:
                raise self._Exc("locked")
        self.items[Item["pk"]] = Item

    def delete_item(self, Key=None, **_):
        self.items.pop(Key["pk"], None)


def _load():
    fake = _FakeTable()
    sys.modules.setdefault(
        "boto3",
        types.SimpleNamespace(
            resource=lambda *a, **k: types.SimpleNamespace(Table=lambda n: fake),
            client=lambda *a, **k: None,
        ),
    )
    sys.modules.pop("action_state", None)
    import action_state

    action_state._table = fake
    action_state._secrets = {"action-state-api-key": "k"}
    return action_state, fake


def _call(mod, body):
    res = mod.lambda_handler({"headers": {"x-api-key": "k"}, "body": json.dumps(body)}, None)
    return res["statusCode"], json.loads(res["body"])


CRITERIA = {
    "conditions": [{"metric": "p95_ms", "comparison": "<=", "threshold": 800}],
    "baseline_conditions": [
        {"metric": "p95_ms", "comparison": "<=", "relative_to": "baseline_p95_ms"}
    ],
}


def _baseline(mod, metrics, action_id="isolate_slow_pod", revision=1):
    return _call(
        mod,
        {"op": "baseline", "incident_id": "inc1", "action_id": action_id,
         "revision": revision, "metrics": metrics},
    )


def test_missing_baseline_value_is_not_a_pass():
    mod, _ = _load()
    # 기준값에 baseline_p95_ms 가 없다 — 절대 SLO 는 통과하지만 기준선 조건은
    # 판정할 근거가 없다. 이걸 통과로 세면 자연 회복이 조치 효과가 된다.
    _baseline(mod, {"p95_ms": 900})
    status, body = _call(
        mod,
        {"op": "judge", "incident_id": "inc1", "action_id": "isolate_slow_pod",
         "metrics": {"p95_ms": 700}, "success_criteria": CRITERIA},
    )
    assert status == 200, body
    assert body["verdict"] != "RESOLVED", body
    assert any(f.get("reason") == "MISSING_BASELINE" for f in body["failed"]), body


def test_improved_but_short_keeps_and_reanalyzes():
    mod, _ = _load()
    # S2 1차 검증 — 증설로 나아졌지만 계약 기준에는 못 미친다. 무해하므로
    # 되돌리지 않고 그대로 두고 재분석한다(0.6).
    _baseline(mod, {"p95_ms": 2000, "baseline_p95_ms": 2000})
    status, body = _call(
        mod,
        {"op": "judge", "incident_id": "inc1", "action_id": "isolate_slow_pod",
         "metrics": {"p95_ms": 1200, "baseline_p95_ms": 2000},
         "success_criteria": CRITERIA, "diagnostic_contamination": True},
    )
    assert body["verdict"] == "KEEP_AND_REANALYZE", body
    assert body["reanalysis_count"] == 1, body


def test_worse_rolls_back():
    mod, _ = _load()
    _baseline(mod, {"p95_ms": 1000, "baseline_p95_ms": 1000})
    _, body = _call(
        mod,
        {"op": "judge", "incident_id": "inc1", "action_id": "isolate_slow_pod",
         "metrics": {"p95_ms": 1600, "baseline_p95_ms": 1000},
         "success_criteria": CRITERIA, "diagnostic_contamination": False},
    )
    assert body["verdict"] == "ROLLBACK_NOW" and body["reason"] == "WORSENED", body


def test_second_failure_escalates():
    mod, fake = _load()
    _baseline(mod, {"p95_ms": 2000, "baseline_p95_ms": 2000})
    judge_body = {
        "op": "judge", "incident_id": "inc1", "action_id": "isolate_slow_pod",
        "metrics": {"p95_ms": 1200, "baseline_p95_ms": 2000},
        "success_criteria": CRITERIA, "diagnostic_contamination": True,
    }
    _call(mod, judge_body)          # 1회차 — 재분석
    _, body = _call(mod, judge_body)  # 2회차 — 상한 초과
    assert body["verdict"] == "ESCALATED", body
    assert body["reason"] == "REANALYSIS_EXHAUSTED", body


def test_lock_blocks_second_action():
    mod, _ = _load()
    _baseline(mod, {"p95_ms": 1000})
    status, body = _baseline(mod, {"p95_ms": 1000}, action_id="limit_channel_volume")
    assert status == 409 and body["error"] == "ACTION_IN_PROGRESS", body
    assert body["holder"] == "isolate_slow_pod", body


def _restore(mod, restore, action_id="isolate_slow_pod"):
    return _call(
        mod,
        {"op": "record_restore", "incident_id": "inc1", "action_id": action_id,
         "restore": restore},
    )


def test_restore_value_survives_to_judge():
    mod, _ = _load()
    _baseline(mod, {"p95_ms": 1000, "baseline_p95_ms": 1000})
    # 조치 실행기가 patch 직전에 읽은 값. 이걸 안 남기면 Argo replica 예외
    # 때문에 git 도 안 되돌려 주므로 되돌릴 대상을 아무도 모른다.
    status, body = _restore(mod, {"replicas": 2})
    assert status == 200 and body["restore"] == {"replicas": 2}, body

    _, judged = _call(
        mod,
        {"op": "judge", "incident_id": "inc1", "action_id": "isolate_slow_pod",
         "metrics": {"p95_ms": 1600, "baseline_p95_ms": 1000},
         "success_criteria": CRITERIA},
    )
    assert judged["verdict"] == "ROLLBACK_NOW", judged
    # 되돌리라고 판정했으면 무엇으로 되돌릴지가 같은 응답에 있어야 한다.
    assert judged["restore"] == {"replicas": 2}, judged


def test_restore_first_write_wins():
    mod, _ = _load()
    _baseline(mod, {"p95_ms": 1000})
    _restore(mod, {"replicas": 2})
    # 조치 뒤 재시도가 지금 값(0)을 다시 보낸다. 덮어쓰면 원복이 0 으로 간다.
    status, body = _restore(mod, {"replicas": 0})
    assert status == 409 and body["error"] == "RESTORE_ALREADY_RECORDED", body
    assert body["recorded"] == {"replicas": 2}, body


def test_restore_without_baseline_is_rejected():
    mod, _ = _load()
    status, body = _restore(mod, {"replicas": 2})
    assert status == 409 and body["error"] == "NO_BASELINE", body


def test_same_action_same_revision_is_idempotent():
    mod, _ = _load()
    _baseline(mod, {"p95_ms": 1000})
    status, body = _baseline(mod, {"p95_ms": 4242})
    assert status == 200 and body["status"] == "ALREADY_RECORDED", body
    # 재시도가 기준값을 덮어쓰면 "조치 직전" 이 조치 이후 값으로 바뀐다.
    assert body["baseline"]["p95_ms"] == 1000, body


if __name__ == "__main__":
    # 건수를 하드코딩하지 않는다. 시험을 늘렸는데 출력이 그대로면
    # 늘어난 줄 모르고 지나간다(T-027 이 그 사고였다).
    ran = 0
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_"):
            _fn()
            ran += 1
    print(f"✓ 조치 상태 머신 {ran}건 통과")
