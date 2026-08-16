"""데모 데이터를 넣는다. 여러 번 돌려도 안전하다.

    python -m app.seed                                   # 로컬
    kubectl exec -n o2-dev deploy/api -- python -m app.seed   # 클러스터

MySQL 과 Valkey 두 곳에 넣는다. 재고의 원본은 Valkey 의 stock:{sku} 이고
MySQL 에는 재고 컬럼이 없기 때문이다 (D-07). MySQL 만 채우면 상품은 보이는데
주문이 -2(미초기화)로 실패한다.

**재고는 실행할 때마다 초기값으로 되돌아간다.** 시나리오를 반복 재현하려면
그래야 하고, 부하 테스트도 콜드 상태에서 시작해야 의미가 있다
(architecture.md 12.1). 방송 중에 실수로 부르지 말 것.
"""

from datetime import datetime, timezone

from sqlalchemy.dialects.mysql import insert

from app.db.session import SessionLocal
from app.db.valkey import valkey
from app.models.broadcast import Broadcast
from app.models.product import Product

BROADCAST_ID = "bc_1042"

# hls_url 은 05-media(MediaMTX·CloudFront)가 생기면 실제 값으로 바뀐다.
# 지금 넣는 것은 응답 모양을 확인하기 위한 자리다.
HLS_URL = "https://example.invalid/hls/bc_1042/index.m3u8"

# state 를 셋 다 넣는다. 하나만 있으면 PENDING·SOLD_OUT 분기를 화면에서도
# API 에서도 시험할 수 없다.
PRODUCTS = [
    # sku_id, 이름, 정가, 특가, 초기 재고, 상태
    (88213, "올리브영 수분 앰플 50ml", 24000, 12000, 120, "ON_SALE"),
    (88214, "데일리 선크림 SPF50+", 18000, 9900, 80, "PENDING"),
    (88215, "리페어 헤어 에센스", 32000, 15900, 0, "SOLD_OUT"),
]


def seed() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with SessionLocal() as db:
        # ON DUPLICATE KEY UPDATE 로 upsert 한다. 지우고 다시 넣으면 주문이
        # 참조하던 sku_id 가 잠깐 사라진다.
        db.execute(
            insert(Broadcast)
            .values(
                broadcast_id=BROADCAST_ID,
                state="LIVE",
                started_at=now,
                hls_url=HLS_URL,
            )
            .on_duplicate_key_update(state="LIVE", started_at=now, hls_url=HLS_URL)
        )

        for sku_id, name, price, sale_price, _stock, state in PRODUCTS:
            db.execute(
                insert(Product)
                .values(
                    sku_id=sku_id,
                    broadcast_id=BROADCAST_ID,
                    name=name,
                    price=price,
                    sale_price=sale_price,
                    state=state,
                )
                .on_duplicate_key_update(
                    broadcast_id=BROADCAST_ID,
                    name=name,
                    price=price,
                    sale_price=sale_price,
                    state=state,
                )
            )

        db.commit()

    # TTL 을 걸지 않는다. 만료되는 순간 재고가 소실된다 (contracts.md 4).
    # 축출도 막혀 있다 — Valkey 파라미터 그룹이 volatile-lru 라 TTL 없는 키는
    # 메모리 압박에도 살아남는다 (D-017).
    for sku_id, _name, _price, _sale, stock, _state in PRODUCTS:
        valkey.set(f"stock:{sku_id}", stock)

    print(f"seeded: {BROADCAST_ID}, products={[p[0] for p in PRODUCTS]}")
    for sku_id, *_ in PRODUCTS:
        print(f"  stock:{sku_id} = {valkey.get(f'stock:{sku_id}')}")


if __name__ == "__main__":
    seed()
