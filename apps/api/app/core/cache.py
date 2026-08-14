"""인프로세스 로컬 캐시와 singleflight.

계층 구조에서 효과가 가장 큰 자리다 (architecture.md 3.3). 로컬 1초 캐시가
방송 메타·상품 조회의 90% 이상을 흡수하는 것이 목표다 (3.10).

singleflight 가 로컬 미스 지점에 있는 것이 핵심이다. 없으면 방송 시작 순간
파드 하나에서만 초당 수백 건의 중복 조회가 하위 계층으로 누출된다 (3.5).

동기 구현인 이유: 라우트가 동기 함수라 uvicorn 의 스레드풀에서 돌기 때문이다.
asyncio 가 아니라 threading 으로 맞춰야 실제로 합쳐진다.
"""

import threading
import time
from collections import OrderedDict
from typing import Any, Callable

# 엔트리 수 상한이 있어야 한다. 무제한이면 방송·상품이 늘어날수록 파드가
# OOM 으로 죽는다 (리스크 R-10).
_MAX_ENTRIES = 512

_store: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
_store_lock = threading.Lock()

# 진행 중인 로드. 같은 키를 동시에 요청한 스레드는 여기 편승한다.
_inflight: dict[str, threading.Event] = {}
_inflight_lock = threading.Lock()

# 리더가 죽었을 때 팔로워가 영원히 기다리지 않도록 상한을 둔다.
# 하위 계층 타임아웃(2초)보다 넉넉해야 정상 로드를 중간에 포기하지 않는다.
_WAIT_TIMEOUT = 5.0


def _get_fresh(key: str) -> Any:
    now = time.monotonic()
    with _store_lock:
        entry = _store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= now:
            del _store[key]
            return None
        _store.move_to_end(key)
        return value


def _put(key: str, value: Any, ttl: float) -> None:
    with _store_lock:
        _store[key] = (time.monotonic() + ttl, value)
        _store.move_to_end(key)
        while len(_store) > _MAX_ENTRIES:
            _store.popitem(last=False)


def get_or_load(key: str, ttl: float, loader: Callable[[], Any]) -> Any:
    """로컬 캐시에서 읽고, 없으면 loader 를 한 번만 실행한다.

    같은 키를 동시에 요청한 다른 스레드는 그 결과를 기다린다.
    """
    hit = _get_fresh(key)
    if hit is not None:
        return hit

    with _inflight_lock:
        event = _inflight.get(key)
        is_leader = event is None
        if is_leader:
            event = threading.Event()
            _inflight[key] = event

    if not is_leader:
        event.wait(timeout=_WAIT_TIMEOUT)
        hit = _get_fresh(key)
        if hit is not None:
            return hit
        # 리더가 실패했거나 시간 안에 못 채웠다. 직접 읽는다 —
        # 여기서 None 을 반환하면 리더 하나의 실패가 대기 중인 전부의
        # 실패가 된다.
        return loader()

    try:
        value = loader()
        if value is not None:
            _put(key, value, ttl)
        return value
    finally:
        with _inflight_lock:
            _inflight.pop(key, None)
        event.set()


def clear() -> None:
    """테스트와 자체 점검용."""
    with _store_lock:
        _store.clear()
