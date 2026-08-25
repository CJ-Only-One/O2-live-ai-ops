"""방송 진입 스냅샷 조립.

읽기 경로는 architecture.md 3.5 를 따른다.

    로컬 캐시 (1초 + singleflight)
      ↓ 미스
    Valkey bcast:{id}:meta (30초)
      ↓ 미스
    MySQL 리드 리플리카 → Valkey 채움 → 로컬 채움

**재고는 이 캐시에 넣지 않는다.** stock:{sku} 는 Valkey 가 원본이고 주문마다
바뀐다 (D-07). 메타에 섞으면 DECR 한 번마다 방송 캐시를 무효화해야 하고,
그러면 캐시가 사실상 없는 것과 같아진다. 메타만 캐시하고 재고는 매 요청
MGET 으로 읽는다 — 왕복 한 번이 늘지만 표시값이 최신에 가까워진다.
"""

import json
import logging
import time

from o2events import emit
from sqlalchemy import select

from app.core.cache import get_or_load
from app.core.telemetry import telemetry
from app.db.session import ReaderSessionLocal
from app.db.valkey import valkey
from app.models.broadcast import Broadcast
from app.models.product import Product

logger = logging.getLogger(__name__)

LOCAL_TTL = 1.0  # architecture.md 3.4
VALKEY_TTL = 30  # architecture.md 3.9


def _meta_key(broadcast_id: str) -> str:
    return f"bcast:{broadcast_id}:meta"


def _load_from_db(broadcast_id: str) -> dict | None:
    """리드 리플리카에서 방송과 편성 상품을 읽어 메타를 만든다."""
    with ReaderSessionLocal() as db:
        broadcast = db.get(Broadcast, broadcast_id)
        if broadcast is None:
            return None

        products = db.scalars(
            select(Product)
            .where(Product.broadcast_id == broadcast_id)
            .order_by(Product.sku_id)
        ).all()

    return {
        "broadcast_id": broadcast.broadcast_id,
        "state": broadcast.state,
        # 컬럼은 naive UTC 다. 계약이 Z 접미사를 쓰므로 여기서 붙인다.
        "started_at": (
            broadcast.started_at.isoformat(timespec="seconds") + "Z"
            if broadcast.started_at
            else None
        ),
        "hls_url": broadcast.hls_url,
        "products": [
            {
                "sku_id": str(p.sku_id),
                "name": p.name,
                "price": p.price,
                "sale_price": p.sale_price,
                "state": p.state,
            }
            for p in products
        ],
    }


def _load_meta(broadcast_id: str, origin: dict) -> dict | None:
    """Valkey 를 보고, 없으면 DB 에서 읽어 Valkey 를 채운다.

    Valkey 가 죽어도 DB 경로로 응답한다. 캐시는 보조이지 원본이 아니다.

    origin 은 어느 계층이 응답했는지 호출자에게 돌려주는 자리다.
    이벤트의 cache_hit 이 트래픽 폭증과 캐시 미스 폭주를 가르는 유일한 근거라
    (SDK inventory_check 주석) 실제 값을 실어야 한다.
    """
    key = _meta_key(broadcast_id)

    try:
        cached = valkey.get(key)
        if cached:
            return json.loads(cached)
    except Exception:
        logger.exception("방송 메타 캐시 조회 실패, DB 로 우회한다")
        telemetry.fallback("broadcast.meta", True)

    origin["source"] = "DB_REPLICA"
    origin["cache_hit"] = False

    meta = _load_from_db(broadcast_id)
    if meta is None:
        return None

    try:
        valkey.set(key, json.dumps(meta), ex=VALKEY_TTL)
    except Exception:
        logger.exception("방송 메타 캐시 저장 실패")

    return meta


def warm_meta(broadcast_id: str) -> bool:
    """캐시만 채운다. cue-warmer(D-041 사전 확장)가 이걸 부른다.

    get_snapshot() 을 그대로 호출하지 않는다 — 그건 재고 MGET 과
    inventory.check 발행까지 같이 한다. 재고는 애초에 캐시 대상이 아니고
    (D-07), inventory.check 의 cache_hit·source 는 "실제 트래픽 폭증과
    캐시 미스 폭주를 가르는 유일한 근거"다(contracts.md 5.1). 워머가 그
    경로를 타면 진짜 시청자 요청과 안 갈리는 가짜 히트가 그 지표에 매
    tick 마다 섞여 들어간다 — M-009 가 재던 바로 그 신호가 오염된다.

    반환값은 방송이 존재해서 실제로 채웠는지 여부다. 없는 broadcast_id 를
    호출자가 조용히 넘기지 않게 한다.
    """
    return _load_meta(broadcast_id, origin={"source": "CACHE", "cache_hit": True}) is not None


def _stock_display(sku_ids: list[str]) -> dict[str, int]:
    """표시용 재고. 원본은 Valkey 이므로 캐시를 거치지 않고 직접 읽는다."""
    if not sku_ids:
        return {}
    try:
        values = valkey.mget([f"stock:{sku}" for sku in sku_ids])
    except Exception:
        logger.exception("재고 조회 실패, 0 으로 표시한다")
        telemetry.failure("inventory.check", "CACHE_READ_FAILED")
        telemetry.fallback("inventory.stock", True)
        return {sku: 0 for sku in sku_ids}

    # 키가 없으면(미초기화) 0 으로 보여준다. 주문은 어차피 DECR 결과를
    # 따르므로 표시값이 보수적인 편이 낫다.
    return {sku: int(v) if v is not None else 0 for sku, v in zip(sku_ids, values)}


def get_product(broadcast_id: str, sku_id: str) -> dict | None:
    """편성 상품 하나. 없으면 None.

    주문 접수가 판매가와 상태를 여기서 꺼낸다. 화면이 보는 것과 같은 캐시라
    "사용자가 본 것"과 "서버가 판정한 것"이 같은 출처가 된다. 별도 DB 조회도
    생기지 않는다 — 스냅샷 캐시에 이미 들어 있다.

    가격만 반환하지 않는 이유는, 가격과 상태를 따로 꺼내면 두 번 조회하거나
    둘이 다른 시점의 값이 될 수 있기 때문이다.
    """
    meta = get_or_load(
        _meta_key(broadcast_id), LOCAL_TTL, lambda: _load_meta(broadcast_id, {"source": "CACHE", "cache_hit": True})
    )
    if meta is None:
        return None
    for p in meta["products"]:
        if p["sku_id"] == sku_id:
            return p
    return None


def degraded_key(broadcast_id: str) -> str:
    """`app/api/routes/admin.py` 도 SET·DEL 할 때 이 함수를 그대로 쓴다 —
    키 포맷이 두 곳에 따로 있으면 한쪽만 바뀌었을 때 조용히 어긋난다."""
    return f"cfg:read_path_degraded:{broadcast_id}"


def _load_degraded_flag(broadcast_id: str) -> bool:
    """Valkey 가 죽어도 DB 경로처럼 안전한 기본값(평시)으로 응답한다 —
    `_load_meta` 와 같은 원칙이다. 노브 조회 실패가 읽기 경로 자체를
    죽이면 안 된다 — 특히 이 노브가 켜지는 시점(인시던트 중)일수록
    Valkey 가 불안정할 확률이 높다.

    `bool(...)` 는 None 을 안 돌려주므로 `get_or_load` 가 문제없이
    캐시한다(cache.py — loader 가 None 일 때만 캐시를 건너뛴다).
    """
    try:
        return bool(valkey.get(degraded_key(broadcast_id)))
    except Exception:
        logger.exception("read_path_degraded 노브 조회 실패, 평시로 간주한다")
        return False


def _read_path_degraded(broadcast_id: str) -> bool:
    """S3(scenario-experiment.md 0.7) 조치 노브. 켜져 있으면 요청당 부가
    작업(inventory.check 발행)을 건너뛴다 — 응답 내용은 안 바뀌므로 사용자
    차단은 0 그대로다.

    매 요청 Valkey 를 직접 보지 않는다 — 로컬 캐시(1초)로 감싸서, 평시
    수백 RPS 에서도 실제 Valkey 조회는 초당 1회로 묶인다.
    """
    return get_or_load(
        degraded_key(broadcast_id),
        LOCAL_TTL,
        lambda: _load_degraded_flag(broadcast_id),
    )


def _emit_inventory_check(meta: dict, stocks: dict[str, int], origin: dict, latency_ms: int) -> None:
    """스냅샷 조회 1건당 이벤트 1건 (contracts.md 5.1).

    상품마다 발행하지 않는다. 편성 상품이 전부 같은 캐시 블롭에서 나오므로
    상품별로 쪼개도 cache_hit 이 전부 같은 값이고, 볼륨만 상품 수만큼 늘어난다.
    대표 상품 하나로 방송 단위 조회를 기록한다.

    발행 실패가 사용자 요청을 실패시키면 안 된다 (contracts.md 5.1).
    SDK 는 전송을 논블로킹으로 처리하지만 계약 위반은 raise 하므로 여기서 막는다.
    """
    products = meta.get("products") or []
    if not products:
        return

    featured = products[0]
    telemetry.business_event("inventory.check", "success")
    telemetry.cache_access(origin["cache_hit"])
    telemetry.operation_duration("inventory.read", latency_ms)
    try:
        emit.inventory_check(
            product_id=featured["sku_id"],
            # 조회일 뿐 주문이 아니라 요청 수량이 없다.
            requested_qty=0,
            available_qty=stocks.get(featured["sku_id"], 0),
            source=origin["source"],
            cache_hit=origin["cache_hit"],
            latency_ms=latency_ms,
        )
    except Exception:
        logger.exception("inventory.check 발행 실패")


def get_snapshot(broadcast_id: str) -> dict | None:
    started = time.perf_counter()

    # 아래 loader 가 안 불리면 로컬 캐시가 응답한 것이다.
    origin = {"source": "CACHE", "cache_hit": True}

    meta = get_or_load(
        _meta_key(broadcast_id), LOCAL_TTL, lambda: _load_meta(broadcast_id, origin)
    )
    if meta is None:
        return None

    sku_ids = [p["sku_id"] for p in meta["products"]]
    stocks = _stock_display(sku_ids)

    latency_ms = int((time.perf_counter() - started) * 1000)
    if not _read_path_degraded(broadcast_id):
        _emit_inventory_check(meta, stocks, origin, latency_ms)

    # 캐시에 담긴 dict 를 그대로 고치면 다음 요청이 남의 재고를 본다.
    return {
        **meta,
        "products": [
            {**p, "stock_display": stocks.get(p["sku_id"], 0)}
            for p in meta["products"]
        ],
    }
