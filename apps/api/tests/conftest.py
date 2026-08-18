"""SDK 가 설치되지 않은 환경에서도 시험이 돌게 한다.

`o2events` 는 비공개 저장소에서 토큰으로 설치된다 (apps/api/Dockerfile).
CI 의 테스트 스텝에는 그 토큰이 없어 `requirements.txt` 만 깔리므로, SDK 를
그대로 import 하면 **수집 단계에서 모든 시험이 깨진다.** 시험이 없는 것보다
나쁜 것은 항상 깨져 있어 아무도 안 보는 시험이다.

그래서 SDK 가 없으면 최소 대역을 `sys.modules` 에 넣는다. 대역으로 도는 동안
검증되는 것은 **우리 코드**(경로·입력 검증·발행 인자)이고, 계약 자체는 SDK 가
설치된 곳에서 `test_sdk_contract.py` 가 확인한다 (그쪽은 없으면 skip 한다).
둘이 한 쌍이라야 의미가 있다 — 대역만 있으면 계약이 바뀌어도 초록이 뜬다.
"""

import hashlib
import sys
import time
import types


def _install_stub() -> None:
    package = types.ModuleType("o2events")
    package.__path__ = []  # 하위 모듈을 가질 수 있는 패키지로 취급되게 한다

    emit = types.ModuleType("o2events.emit")
    emit.calls = []

    def _recorder(name):
        def _call(**kwargs):
            emit.calls.append((name, kwargs))

        return _call

    for fn in (
        "client_action",
        "coupon_issue",
        "inventory_check",
        "order_create",
        "order_cancel",
        "payment_process",
    ):
        setattr(emit, fn, _recorder(fn))

    core = types.ModuleType("o2events.core")

    def hash_key(prefix: str, raw: str | None) -> str | None:
        """진짜는 HMAC 이다 (SDK core.py). 여기서는 모양만 같으면 된다 —
        시험이 보는 것은 '가명화된 값이 실렸는가'이지 해시 알고리즘이 아니다."""
        if not raw:
            return None
        return f"{prefix}_{hashlib.sha256(str(raw).encode()).hexdigest()[:16]}"

    def ulid() -> str:
        """order_id 의 뒷부분. 계약이 정한 모양(Crockford base32 26자)만 지킨다
        — 시간순 정렬 같은 성질은 SDK 의 몫이고 여기서 흉내 내지 않는다."""
        alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
        raw = hashlib.sha256(str(time.time_ns()).encode()).digest()
        return "".join(alphabet[b % 32] for b in raw[:26])

    core.hash_key = hash_key
    core.ulid = ulid

    middleware = types.ModuleType("o2events.middleware")
    middleware.installed = {}

    def install_fastapi(app, *, user_id_getter=None, broadcast_id_getter=None):
        # 미들웨어를 실제로 붙이지는 않는다. 봉투를 만드는 것은 SDK 의 몫이고,
        # 여기서 흉내 내면 '대역이 통과시키는 시험'이 되어 버린다.
        # 대신 무엇이 배선됐는지만 남겨 시험이 확인할 수 있게 한다.
        middleware.installed = {
            "user_id_getter": user_id_getter,
            "broadcast_id_getter": broadcast_id_getter,
        }

    middleware.install_fastapi = install_fastapi

    package.emit = emit
    package.core = core
    package.middleware = middleware

    sys.modules["o2events"] = package
    sys.modules["o2events.emit"] = emit
    sys.modules["o2events.core"] = core
    sys.modules["o2events.middleware"] = middleware


try:  # pragma: no cover - 어느 쪽이 도는지는 환경이 정한다
    import o2events  # noqa: F401

    SDK_INSTALLED = True
except ModuleNotFoundError:
    _install_stub()
    SDK_INSTALLED = False
