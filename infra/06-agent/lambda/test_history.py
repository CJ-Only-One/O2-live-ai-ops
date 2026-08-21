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

# boto3 는 Lambda 런타임에만 있다. 이 점검은 AWS 를 부르지 않으므로,
# 로컬에 없으면 가짜를 끼워 넣는다. 설치를 요구하면 아무도 안 돌린다.
try:
    import boto3  # noqa: F401
except ModuleNotFoundError:
    sys.modules["boto3"] = types.SimpleNamespace(
        client=lambda *a, **k: None, __version__="stub"
    )

# worker 는 이 둘만 필수로 읽는다. 이력 관련 변수는 일부러 비워 둔다 —
# 그게 O2 파이프라인의 상태이고, import 가 죽지 않아야 한다.
os.environ.setdefault("ALERT_SECRET_NAME", "dummy")
os.environ.setdefault("DIFY_URL", "http://127.0.0.1/v1/workflows/run")
os.environ.setdefault("WORKER_FUNCTION", "dummy")

import ingress  # noqa: E402
import worker  # noqa: E402


def test_import_survives_without_history_env():
    """O2 파이프라인은 이 변수들이 없다. 대괄호로 읽으면 여기서 죽는다."""
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
                    {"distance": 0.1, "metadata": {"summary": "가까움", "service": "api"}},
                    {"distance": 0.9, "metadata": {"summary": "멂", "service": "api"}},
                ]
            }

    worker._clients = lambda: (None, None, FakeVectors())
    out = worker._search([0.0] * 1024)

    assert "가까움" in out
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


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all passed")
