"""13-A 종료 사유 분기 자체 점검. `python3 dify/test_no_candidate_action.py` 로 돈다.

S3 1차 실행(scenario-experiment.md 0.7 Phase 2)이 성립하는 조건 하나를 본다 —
active 런북이 없으면 재진단 루프를 도는 게 아니라 ESCALATED + NO_ACTIVE_RUNBOOK
으로 멈추는가. 이게 깨지면 1차가 다른 종료 사유로 끝나고 "지식이 없어 멈췄다"는
S3의 주장 자체가 사라진다. 조용히 틀리는 종류라 눈으로는 안 잡힌다.

DSL 원본에서 코드를 꺼내 그대로 실행한다 — 복사본을 두면 DSL만 바뀌었을 때
테스트가 통과해버린다. YAML 파서 없이 도는 이유는 이 저장소의 다른 자체 점검과
같다(표준 라이브러리만 쓴다).
"""

import json
import os
import sys

WORKFLOW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "o2-aiops-workflow.yml")


def node_code(node_id):
    """`id: <node_id>` 바로 앞에 있는 code 스칼라를 꺼낸다.

    Dify DSL 의 code 는 한 줄짜리 큰따옴표 스칼라라 JSON 문자열과 이스케이프
    규칙이 같다. 그래서 json.loads 로 푼다.
    """
    with open(WORKFLOW, encoding="utf-8") as f:
        text = f.read()
    marker = "\n      id: %s\n" % node_id
    end = text.index(marker)
    start = text.rindex('        code: "', 0, end) + len("        code: ")
    return json.loads(text[start : text.index('"\n', start) + 1])


def load(node_id):
    namespace = {}
    exec(node_code(node_id), namespace)
    return namespace["main"]


def main():
    shape = load("runbook_shape")
    event = load("ev_candidates_exhausted")

    # 11-B 가 runbook_status 를 흘려보내야 13-A 가 판단할 수 있다.
    shaped = shape(
        rca_category="pg_external_failure",
        http_body=json.dumps({"runbook_status": "draft", "actions": []}),
    )["runbook_json"]
    assert json.loads(shaped)["runbook_status"] == "draft", shaped

    # 응답에 status 가 아예 없는 구형 경로도 active 로 오인하면 안 된다.
    legacy = shape(rca_category="other", http_body="{}")["runbook_json"]
    assert json.loads(legacy)["runbook_status"] == "missing", legacy

    def reason(status):
        payload = json.dumps({"runbook_status": status}) if status else "{}"
        return json.loads(event(runbook_json=payload)["event_json"])

    # S3 1차 — draft 뿐이라 실행 가능한 조치가 없다. 멈춘다.
    assert reason("draft") == {"type": "MANUAL_REQUIRED", "reason": "NO_ACTIVE_RUNBOOK"}
    assert reason("missing") == {"type": "MANUAL_REQUIRED", "reason": "NO_ACTIVE_RUNBOOK"}
    assert reason("retired") == {"type": "MANUAL_REQUIRED", "reason": "NO_ACTIVE_RUNBOOK"}
    assert reason(None) == {"type": "MANUAL_REQUIRED", "reason": "NO_ACTIVE_RUNBOOK"}

    # S3 2차·S1·S2 — 런북이 있는데 후보만 소진된 경우는 종전대로 재진단한다.
    assert reason("active") == {"type": "REDIAGNOSE", "reason": "CANDIDATES_EXHAUSTED"}
    # S2 실전 시연의 한정 draft 허용도 "런북이 있는" 쪽이다.
    assert reason("experiment") == {"type": "REDIAGNOSE", "reason": "CANDIDATES_EXHAUSTED"}

    print("ok")


if __name__ == "__main__":
    sys.exit(main())
