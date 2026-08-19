"""데모 데이터를 넣는다. 여러 번 돌려도 안전하다.

    python -m app.seed                                   # 로컬
    kubectl exec -n o2-dev deploy/api -- python -m app.seed   # 클러스터

MySQL 과 Valkey 두 곳에 넣는다. 재고의 원본은 Valkey 의 stock:{sku} 이고
MySQL 에는 재고 컬럼이 없기 때문이다 (D-07). MySQL 만 채우면 상품은 보이는데
주문이 -2(미초기화)로 실패한다.

**재고는 실행할 때마다 초기값으로 되돌아간다.** 시나리오를 반복 재현하려면
그래야 하고, 부하 테스트도 콜드 상태에서 시작해야 의미가 있다
(architecture.md 12.1). 방송 중에 실수로 부르지 말 것.

방송을 LIVE·SCHEDULED·ENDED 로 여러 개 둔다. 하나만 있으면 로비의 탭과
상태별 화면을 시험할 수 없다.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.mysql import insert

from app.db.session import SessionLocal
from app.db.valkey import valkey
from app.models.broadcast import Broadcast
from app.models.product import Product


def _hls(broadcast_id: str) -> str:
    # 07-media(MediaMTX·CloudFront)가 생기면 실제 값으로 바뀐다.
    return f"https://example.invalid/hls/{broadcast_id}/index.m3u8"


# broadcast_id, 상태, 시작 시각 오프셋(분)
BROADCASTS = [
    ("bc_1042", "LIVE", -25),
    ("bc_1043", "LIVE", -8),
    ("bc_1050", "SCHEDULED", 180),
    ("bc_1051", "SCHEDULED", 1500),
    ("bc_1030", "ENDED", -2880),
]

# broadcast_id, sku_id, 이름, 정가, 특가, 초기 재고, 상태
#
# 상태를 셋 다 넣는다. 하나만 있으면 PENDING·SOLD_OUT 분기를 화면에서도
# API 에서도 시험할 수 없다.
PRODUCTS = [
    ("bc_1042", 88213, "올리브영 수분 앰플 50ml", 24000, 12000, 120, "ON_SALE"),
    ("bc_1042", 88214, "데일리 선크림 SPF50+", 18000, 9900, 80, "ON_SALE"),
    ("bc_1042", 88215, "리페어 헤어 에센스 100ml", 32000, 15900, 0, "SOLD_OUT"),
    ("bc_1042", 88216, "딥클렌징 오일 200ml", 26000, 13900, 45, "PENDING"),
    ("bc_1043", 88220, "비타민 C 세럼 30ml", 38000, 19900, 60, "ON_SALE"),
    ("bc_1043", 88221, "수분 크림 80ml", 29000, 14500, 30, "ON_SALE"),
    ("bc_1050", 88230, "프로틴 쉐이크 1kg", 54000, 32900, 200, "PENDING"),
    ("bc_1051", 88240, "유산균 30포", 45000, 24900, 150, "PENDING"),
    ("bc_1030", 88250, "마스크팩 30매", 30000, 12900, 0, "SOLD_OUT"),
]


def seed() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with SessionLocal() as db:
        # ON DUPLICATE KEY UPDATE 로 upsert 한다. 지우고 다시 넣으면 주문이
        # 참조하던 sku_id 가 잠깐 사라진다.
        for broadcast_id, state, offset_min in BROADCASTS:
            started = now + timedelta(minutes=offset_min)
            hls = _hls(broadcast_id)
            db.execute(
                insert(Broadcast)
                .values(
                    broadcast_id=broadcast_id,
                    state=state,
                    started_at=started,
                    hls_url=hls,
                )
                .on_duplicate_key_update(state=state, started_at=started, hls_url=hls)
            )

        for broadcast_id, sku_id, name, price, sale_price, _stock, state in PRODUCTS:
            db.execute(
                insert(Product)
                .values(
                    sku_id=sku_id,
                    broadcast_id=broadcast_id,
                    name=name,
                    price=price,
                    sale_price=sale_price,
                    state=state,
                )
                .on_duplicate_key_update(
                    broadcast_id=broadcast_id,
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
    for _broadcast_id, sku_id, _name, _price, _sale, stock, _state in PRODUCTS:
        valkey.set(f"stock:{sku_id}", stock)

    print(f"seeded: 방송 {len(BROADCASTS)}개, 상품 {len(PRODUCTS)}개")
    for broadcast_id, state, _ in BROADCASTS:
        skus = [p[1] for p in PRODUCTS if p[0] == broadcast_id]
        print(f"  {broadcast_id:<10} {state:<10} 상품 {skus}")


if __name__ == "__main__":
    seed()
