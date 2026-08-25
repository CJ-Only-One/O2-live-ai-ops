"""노브 카탈로그 조회 자체 점검. `python3 lambda/test_runbook_lookup.py` 로 돈다.

여기서 보는 것은 셋뿐이다 — 틀리면 조용히 잘못 동작하는 것들이다.

  1. 조치에 노브가 붙는가. 안 붙으면 게이트가 판정 근거를 못 찾는데,
     응답은 200 이라 호출자가 눈치채기 어렵다
  2. 노브가 없는 조치에서 죽지 않는가. 런북에만 있고 카탈로그에 아직
     없는 조치가 진단 전체를 멈추면 안 된다
  3. draft·retired 런북이 자동 실행 후보에서 빠지는가
  4. rca_type="KNOB" 조회가 카탈로그 전체를 주는가

★ archive_file 이 runbook_lookup.py 만 zip 에 넣으므로 이 파일은 Lambda 에
  올라가지 않는다.
"""

import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("RUNBOOK_TABLE", "dummy")
os.environ.setdefault("RUNBOOK_SECRET_NAME", "dummy")


class _FakeTable:
    """PK 로 묶인 아이템 목록만 돌려주는 최소 대역."""

    def __init__(self, items):
        self._items = items

    def query(self, KeyConditionExpression=None, **_):
        # 이 점검은 Key 조건식을 파싱하지 않는다 — 호출당 파티션 하나만
        # 쓰므로 생성자가 받은 목록이 곧 그 파티션이다.
        return {"Items": self._items.get("query", [])}

    def get_item(self, Key=None, **_):
        item = self._items.get("knobs", {}).get(Key["sk"])
        return {"Item": item} if item is not None else {}


def _load(fake):
    sys.modules.setdefault(
        "boto3",
        types.SimpleNamespace(
            resource=lambda *a, **k: types.SimpleNamespace(Table=lambda n: fake),
            client=lambda *a, **k: None,
        ),
    )
    sys.modules.setdefault(
        "boto3.dynamodb", types.ModuleType("boto3.dynamodb")
    )
    cond = types.ModuleType("boto3.dynamodb.conditions")
    cond.Key = lambda name: types.SimpleNamespace(eq=lambda v: ("eq", name, v))
    sys.modules.setdefault("boto3.dynamodb.conditions", cond)

    sys.modules.pop("runbook_lookup", None)
    import runbook_lookup

    runbook_lookup._table = fake
    runbook_lookup._secrets = {"runbook-lookup-api-key": "k"}
    return runbook_lookup


def _call(mod, rca_type):
    res = mod.lambda_handler(
        {"headers": {"x-api-key": "k"}, "body": json.dumps({"rca_type": rca_type})},
        None,
    )
    assert res["statusCode"] == 200, res
    return json.loads(res["body"])


KNOB = {
    "rca_type": "KNOB",
    "sk": "KNOB#isolate_slow_pod",
    "action_id": "isolate_slow_pod",
    "knob_reversible": True,
    "user_effect_reversible": True,
    "preapproved_budget": None,
    "measured": False,
    "preconditions": [{"check": "target_is_not_the_only_capacity"}],
}


def test_action_carries_knob():
    fake = _FakeTable(
        {
            "query": [
                {"rca_type": "pod_load_skew", "sk": "DEF", "success_criteria": {"logic": "AND"}},
                {"rca_type": "pod_load_skew", "sk": "ACTION#isolate_slow_pod", "action_id": "isolate_slow_pod"},
            ],
            "knobs": {"KNOB#isolate_slow_pod": KNOB},
        }
    )
    body = _call(_load(fake), "pod_load_skew")
    knob = body["actions"][0]["knob"]
    # 게이트가 실제로 읽는 넷. 하나라도 빠지면 판정이 LLM 자유 서술로 돌아간다.
    for field in ("knob_reversible", "user_effect_reversible", "preapproved_budget", "preconditions"):
        assert field in knob, field
    assert knob["measured"] is False


def test_missing_knob_does_not_break_lookup():
    fake = _FakeTable(
        {
            "query": [
                {
                    "rca_type": "pod_load_skew",
                    "sk": "DEF",
                    "status": "active",
                    "success_criteria": {"logic": "AND"},
                },
                {"rca_type": "pod_load_skew", "sk": "ACTION#not_in_catalog", "action_id": "not_in_catalog"},
            ],
            "knobs": {},
        }
    )
    body = _call(_load(fake), "pod_load_skew")
    # 200 이되 knob 키가 없다 — 호출자가 "판정 근거 없음" 을 구분할 수 있어야 한다.
    assert "knob" not in body["actions"][0]


def test_draft_runbook_is_seeded_but_not_returned_for_execution():
    fake = _FakeTable(
        {
            "query": [
                {
                    "rca_type": "pod_resource_exhaustion",
                    "sk": "DEF",
                    "runbook_id": "RB-API-LATENCY-001",
                    "status": "draft",
                    "success_criteria": {"logic": "AND"},
                },
                {
                    "rca_type": "pod_resource_exhaustion",
                    "sk": "ACTION#scale_api_one_step",
                    "action_id": "scale_api_one_step",
                    "status": "draft",
                },
            ],
            "knobs": {},
        }
    )
    body = _call(_load(fake), "pod_resource_exhaustion")
    assert body["runbook_id"] == "RB-API-LATENCY-001"
    assert body["runbook_status"] == "draft"
    assert body["success_criteria"] is None
    assert body["actions"] == []


def test_retired_action_is_filtered_from_active_runbook():
    fake = _FakeTable(
        {
            "query": [
                {
                    "rca_type": "chat_channel_overload",
                    "sk": "DEF",
                    "status": "active",
                    "success_criteria": {"logic": "AND"},
                },
                {
                    "rca_type": "chat_channel_overload",
                    "sk": "ACTION#current",
                    "action_id": "current",
                    "status": "active",
                },
                {
                    "rca_type": "chat_channel_overload",
                    "sk": "ACTION#old",
                    "action_id": "old",
                    "status": "retired",
                },
            ],
            "knobs": {},
        }
    )
    body = _call(_load(fake), "chat_channel_overload")
    assert [action["action_id"] for action in body["actions"]] == ["current"]


def test_knob_partition_lists_catalog():
    fake = _FakeTable({"query": [KNOB], "knobs": {}})
    body = _call(_load(fake), "KNOB")
    # S3 는 런북이 없어서 이 경로로만 노브를 찾는다.
    assert [k["action_id"] for k in body["knobs"]] == ["isolate_slow_pod"]
    assert body["actions"] == []


if __name__ == "__main__":
    # 건수를 하드코딩하지 않는다. 시험을 늘렸는데 출력이 그대로면
    # 늘어난 줄 모르고 지나간다(T-027 이 그 사고였다).
    ran = 0
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_"):
            _fn()
            ran += 1
    print(f"✓ 노브 카탈로그 조회 {ran}건 통과")
