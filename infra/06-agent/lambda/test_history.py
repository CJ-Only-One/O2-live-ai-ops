"""이력 기능 자체 점검. 프레임워크 없이 `python3 lambda/test_history.py` 로 돈다.

여기서 보는 것은 셋뿐이다 — 틀리면 조용히 잘못 동작하는 것들이다.

  1. 거리 임계값 필터. 느슨하면 상관없는 사례가 프롬프트에 들어간다
  2. 환경변수 없는 파이프라인(lambda_o2.tf)에서 import 가 죽지 않는가
  3. 키 폴백. cycle_key 가 비어도 저장 경로가 만들어지는가

★ archive_file 이 worker.py/ingress.py 만 zip 에 넣으므로 이 파일은
  Lambda 에 올라가지 않는다.
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# CI Runner에는 AWS region/credential이 없다. ingress.py는 import 시점에 Lambda와
# S3 client를 만들기 때문에, 이 값이 없으면 테스트가 AWS를 호출하기도 전에
# NoRegionError로 죽는다(T-028). 전부 테스트용 가짜 값이고 네트워크 호출은 하지 않는다.
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-northeast-2")
os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")

# boto3 는 Lambda 런타임에만 있다. 이 점검은 AWS 를 부르지 않으므로,
# 로컬에 없으면 가짜를 끼워 넣는다. 설치를 요구하면 아무도 안 돌린다.
try:
    import boto3  # noqa: F401
except ModuleNotFoundError:
    _BOTO3_STUBBED = True
    sys.modules["boto3"] = types.SimpleNamespace(
        client=lambda *a, **k: None, __version__="stub"
    )
else:
    _BOTO3_STUBBED = False

# worker 는 이 둘만 필수로 읽는다. 이력 관련 변수는 일부러 비워 둔다 —
# O2 파이프라인은 2026-08-22 부터 실제로는 이력이 켜져 있지만(history_o2.tf),
# 이 zip 을 공유하는 파이프라인이 그 변수 없이도 안 죽어야 한다는 것 자체를
# 이 점검이 보장한다.
os.environ.setdefault("ALERT_SECRET_NAME", "dummy")
os.environ.setdefault("DIFY_URL", "http://127.0.0.1/v1/workflows/run")
os.environ.setdefault("WORKER_FUNCTION", "dummy")


import ingress  # noqa: E402
import worker  # noqa: E402

# unittest discovery는 같은 process에서 다음 test module을 import한다. 로컬 stub을
# 남기면 importlib.find_spec("boto3")가 __spec__ 없는 객체를 만나 ValueError를 낸다.
# ingress/worker는 이미 자기 module namespace에 참조를 잡았으므로 전역 cache만 치운다.
if _BOTO3_STUBBED:
    sys.modules.pop("boto3", None)


def test_import_survives_without_history_env():
    """이 점검은 이력 변수를 일부러 안 준다. 대괄호로 읽으면 여기서 죽는다."""
    assert worker.HISTORY_ENABLED is False
    assert worker.HISTORY_BUCKET is None


def test_ingress_import_survives_without_history_env():
    """o2-dify-ingress 도 같은 zip 이다. 여기가 죽으면 중계가 통째로 멈춘다."""
    assert ingress.HISTORY_BUCKET is None


def test_recovery_record_is_noop_without_bucket():
    """버킷이 없으면 S3 를 부르지 않고 그냥 돌아와야 한다."""

    class Boom:
        def put_object(self, **kwargs):
            raise AssertionError("버킷이 없는데 S3 를 불렀다")

    ingress._s3 = Boom()
    ingress._record_recovery({"cycle_key": "c1"})


def test_alert_text_skips_empty_and_truncates():
    text = worker._alert_text(
        {"alert_title": "제목", "alert_body": "", "alert_query": "q", "tags": "env:dev"}
    )
    assert text == "제목\nq\nenv:dev", text
    assert len(worker._alert_text({"alert_title": "가" * 20000})) == 8000


def test_search_drops_far_hits():
    """임계값보다 먼 사례는 프롬프트에 들어가면 안 된다."""

    class FakeVectors:
        def query_vectors(self, **kwargs):
            return {
                "vectors": [
                    {"distance": 0.1, "metadata": {"summary": "검증됨", "service": "api", "verified": True}},
                    {"distance": 0.1, "metadata": {"summary": "미검증", "service": "api", "verified": False}},
                    {"distance": 0.9, "metadata": {"summary": "멂", "service": "api", "verified": True}},
                ]
            }

    worker._clients = lambda: (None, None, FakeVectors())
    out = worker._search([0.0] * 1024)

    assert "검증됨" in out
    assert "미검증" not in out, "검증 전 사례가 실행 근거로 새어 나왔다"
    assert "멂" not in out, "임계값을 넘은 사례가 새어 나왔다"


def test_search_returns_empty_when_all_far():
    class FakeVectors:
        def query_vectors(self, **kwargs):
            return {"vectors": [{"distance": 1.5, "metadata": {"summary": "무관"}}]}

    worker._clients = lambda: (None, None, FakeVectors())
    assert worker._search([0.0] * 1024) == ""


def test_incident_key_falls_back():
    assert worker._incident_key({"cycle_key": "c1", "event_id": "e1"}) == "c1"
    assert worker._incident_key({"cycle_key": "", "event_id": "e1"}) == "e1"
    assert worker._incident_key({}) == "unknown"


def test_last_action_taken_reads_final_attempt():
    """조치가 실행된 인시던트는 action_taken 이 'none'으로 고정되면 안 된다."""
    import json as _json

    outputs = {
        "final_report_json": _json.dumps(
            {
                "attempt_log": [
                    {"status": "NO_RECOVERY", "action_result": {"action_id": "isolate_slow_pod"}},
                    {"status": "RESOLVED", "action_result": {"action_id": "limit_channel_volume"}},
                ]
            }
        )
    }
    assert worker._last_action_taken(outputs) == "limit_channel_volume"


def test_last_action_taken_defaults_to_none():
    """진단만 하고 조치가 없었던 인시던트(빈 attempt_log)는 여전히 'none'이 맞다."""
    assert worker._last_action_taken({"final_report_json": '{"attempt_log":[]}'}) == "none"
    assert worker._last_action_taken({}) == "none"


# ── 복구 결과 적재 ────────────────────────────────────────────────


def test_epoch_sec_tells_seconds_from_millis():
    """단위를 틀리면 MTTR 이 1000배 어긋나는데 숫자가 그럴듯해서 안 보인다."""
    assert worker._epoch_sec(1787312904) == 1787312904        # 초
    assert worker._epoch_sec(1787312904000) == 1787312904     # 밀리초
    assert worker._epoch_sec("1787312904") == 1787312904      # 문자열로 온다
    assert worker._epoch_sec("") is None
    assert worker._epoch_sec(None) is None


def test_mttr_rejects_nonsense():
    assert worker._mttr_sec(1787312904, 1787313624) == 720
    assert worker._mttr_sec(1787312904, 1787312904000) == 0   # 단위가 섞여도 맞춘다
    assert worker._mttr_sec(1787313624, 1787312904) is None   # 복구가 발생보다 앞
    assert worker._mttr_sec(None, 1787312904) is None


def test_summary_hides_cause_until_verified():
    """★ 이 파일에서 가장 중요한 검사다.

    검증 안 된 사례가 원인을 말하면 에이전트 추측이 다음 판단의 '과거 사례'가
    되어 사실로 승격된다. 그 경로를 코드로 막았는지 본다.
    """
    out = {
        "state": "auto_recovered",
        "mttr_sec": 720,
        "root_cause_label": "db_lock_contention",
        "verified": False,
    }
    unverified = worker._summary("주문 생성 지연", out)
    assert "db_lock_contention" not in unverified, unverified
    assert "[미검증]" in unverified
    assert "12분 뒤 자동복구" in unverified

    out["verified"] = True
    verified = worker._summary("주문 생성 지연", out)
    assert "db_lock_contention" in verified
    assert "[확인됨]" in verified


def test_summary_strips_datadog_transition_prefix():
    """`[Triggered] ... 12분 뒤 자동복구` 는 한 줄 안에서 모순된다."""
    out = {"state": "auto_recovered", "mttr_sec": 720, "verified": False}
    got = worker._summary("[Triggered] [TEST] [O2] 주문 확정 큐가 밀린다", out)

    assert "[Triggered]" not in got, got
    assert "[TEST]" in got, "팀이 붙인 딱지는 건드리지 않는다"
    assert "[미검증]" in got
    assert got.startswith("[미검증] · [TEST]"), got

    # 여러 개가 겹쳐 오거나 대소문자가 달라도 걷어낸다
    assert "[" not in worker._summary("[Recovered][Warn] 큐", out).split("·")[1]


def test_summary_marks_open_and_false_alarm():
    open_case = worker._summary("x", {"state": "unresolved", "verified": False})
    assert "[진행중]" in open_case and "복구 미확인" in open_case

    bogus = worker._summary("x", {"state": "false_alarm", "verified": True})
    assert "[오탐]" in bogus


def _incident(**outcome):
    base = {
        "state": "unresolved",
        "mttr_sec": None,
        "root_cause_label": None,
        "verified": False,
    }
    return {
        "s3_key": "incidents/dt=2026-08-21/k.json",
        "started_at": "2026-08-21T11:48:37+00:00",
        "trigger": {"monitor_id": 21940247},
        "context": {"service": "api", "env": "dev", "signal_summary": "주문 생성 지연"},
        "outcome": {**base, **outcome},
    }


def test_metadata_omits_unknown_values():
    """빈 값에 -1 이나 '' 를 넣으면 나중에 필터가 그 표식까지 걸러야 한다."""
    meta = worker._metadata(_incident())
    assert "mttr_sec" not in meta
    assert "root_cause_label" not in meta
    assert meta["outcome_state"] == "unresolved"
    assert meta["verified"] is False
    assert meta["occurred_at"] == "2026-08-21"

    filled = worker._metadata(_incident(mttr_sec=720, root_cause_label="cache_cold_start",
                                        verified=True, state="auto_recovered"))
    assert filled["mttr_sec"] == 720
    assert filled["root_cause_label"] == "cache_cold_start"


def test_recovery_skips_already_closed_incident():
    """flapping. Recovered 가 또 와도 MTTR 을 마지막 진동으로 덮어쓰지 않는다."""

    class Vectors:
        def get_vectors(self, **kw):
            return {"vectors": [{"key": "k", "data": {"float32": []},
                                 "metadata": {"outcome_state": "auto_recovered"}}]}

        def put_vectors(self, **kw):
            raise AssertionError("이미 닫힌 건을 다시 썼다")

    worker._clients = lambda: (None, None, Vectors())
    assert worker._handle_recovery({"cycle_key": "k"}) == {"ok": True, "merged": False}


def test_recovery_without_incident_is_not_an_error():
    """Triggered 를 놓친 경우. 예외로 올리면 DLQ 가 쓰레기로 찬다."""

    class Vectors:
        def get_vectors(self, **kw):
            return {"vectors": []}

    worker._clients = lambda: (None, None, Vectors())
    assert worker._handle_recovery({"cycle_key": "없는키"})["merged"] is False


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all passed")
