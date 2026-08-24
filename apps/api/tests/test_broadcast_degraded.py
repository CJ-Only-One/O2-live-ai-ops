"""S3 읽기 경로 CPU 감소 노브 — 서비스 쪽(broadcast.py)만 검증한다.

admin.py(라우트)는 test_admin.py 가 본다. 여기서는 두 가지를 확인한다 —
1) admin.py 와 broadcast.py 가 정말 같은 키 포맷을 쓰는가(degraded_key 공유)
2) Valkey 조회가 실패해도 읽기 경로가 죽지 않는가(코드 리뷰에서 나온
   버그 수정 — 이전에는 예외가 get_snapshot() 밖으로 새 나갔다).
"""

import pytest

from app.api.routes.admin import degraded_key as admin_degraded_key
from app.core import cache
from app.services import broadcast


@pytest.fixture(autouse=True)
def _clear_local_cache():
    # get_or_load 의 로컬 캐시는 프로세스 전역이다 — 테스트끼리 값이
    # 새지 않게 매번 비운다.
    cache.clear()
    yield
    cache.clear()


class _FakeValkey:
    def __init__(self, *, raise_on_get: bool = False):
        self.store: dict[str, str] = {}
        self.raise_on_get = raise_on_get

    def get(self, key):
        if self.raise_on_get:
            raise ConnectionError("valkey unreachable")
        return self.store.get(key)


def test_admin_route_and_service_agree_on_key_format():
    """admin.py 가 broadcast.py 의 degraded_key 를 그대로 import 해서 쓰는지
    — 리터럴 문자열을 각자 만들면 조용히 어긋날 수 있다(코드 리뷰 지적)."""
    assert admin_degraded_key is broadcast.degraded_key
    assert broadcast.degraded_key("bc_1042") == "cfg:read_path_degraded:bc_1042"


def test_set_flag_is_visible_to_read_path(monkeypatch):
    fake = _FakeValkey()
    fake.store["cfg:read_path_degraded:bc_1042"] = "1"
    monkeypatch.setattr(broadcast, "valkey", fake)

    assert broadcast._read_path_degraded("bc_1042") is True


def test_valkey_failure_degrades_to_false_not_exception(monkeypatch):
    """Valkey 가 죽어 있어도 _read_path_degraded()가 예외를 던지면 안 된다 —
    get_snapshot()이 이미 DB 폴백으로 성공시킨 응답을 500으로 만들면 안 되기
    때문이다(코드 리뷰 지적 — 이 노브가 켜지는 인시던트 상황일수록 Valkey가
    불안정할 확률이 높다)."""
    fake = _FakeValkey(raise_on_get=True)
    monkeypatch.setattr(broadcast, "valkey", fake)

    assert broadcast._read_path_degraded("bc_1042") is False
