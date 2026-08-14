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

from sqlalchemy import select

from app.core.cache import get_or_load
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


def _load_meta(broadcast_id: str) -> dict | None:
    """Valkey 를 보고, 없으면 DB 에서 읽어 Valkey 를 채운다.

    Valkey 가 죽어도 DB 경로로 응답한다. 캐시는 보조이지 원본이 아니다.
    """
    key = _meta_key(broadcast_id)

    try:
        cached = valkey.get(key)
        if cached:
            return json.loads(cached)
    except Exception:
        logger.exception("방송 메타 캐시 조회 실패, DB 로 우회한다")

    meta = _load_from_db(broadcast_id)
    if meta is None:
        return None

    try:
        valkey.set(key, json.dumps(meta), ex=VALKEY_TTL)
    except Exception:
        logger.exception("방송 메타 캐시 저장 실패")

    return meta


def _stock_display(sku_ids: list[str]) -> dict[str, int]:
    """표시용 재고. 원본은 Valkey 이므로 캐시를 거치지 않고 직접 읽는다."""
    if not sku_ids:
        return {}
    try:
        values = valkey.mget([f"stock:{sku}" for sku in sku_ids])
    except Exception:
        logger.exception("재고 조회 실패, 0 으로 표시한다")
        return {sku: 0 for sku in sku_ids}

    # 키가 없으면(미초기화) 0 으로 보여준다. 주문은 어차피 DECR 결과를
    # 따르므로 표시값이 보수적인 편이 낫다.
    return {sku: int(v) if v is not None else 0 for sku, v in zip(sku_ids, values)}


def get_snapshot(broadcast_id: str) -> dict | None:
    meta = get_or_load(
        _meta_key(broadcast_id), LOCAL_TTL, lambda: _load_meta(broadcast_id)
    )
    if meta is None:
        return None

    sku_ids = [p["sku_id"] for p in meta["products"]]
    stocks = _stock_display(sku_ids)

    # 캐시에 담긴 dict 를 그대로 고치면 다음 요청이 남의 재고를 본다.
    return {
        **meta,
        "products": [
            {**p, "stock_display": stocks.get(p["sku_id"], 0)}
            for p in meta["products"]
        ],
    }
