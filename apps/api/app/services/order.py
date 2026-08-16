"""주문 접수.

재고를 깎는 유일한 지점이다. 판정은 Valkey 에서 끝나고 MySQL 은 워커가 쓴다
(architecture.md 3.6). 그래서 응답이 200 이 아니라 202 다 — 이 시점에 확정된
것은 재고 차감까지이고, 200 을 주면 클라이언트가 "저장됐다" 로 읽는다.
"""

import json
import logging
import time
from pathlib import Path

import boto3
from sqlalchemy import select
from o2events import emit
from o2events.core import ulid

from app.core.config import settings
from app.core.errors import ApiError
from app.db.session import SessionLocal
from app.db.valkey import valkey
from app.models.order import Order
from app.services import broadcast as broadcast_service

logger = logging.getLogger(__name__)

# 멱등키 보관 기간. 클라이언트 재시도가 이 안에 들어오면 재고를 다시 깎지
# 않는다. 최종 방어선은 MySQL 의 uk_idem 이다 (contracts.md 2.2).
IDEM_TTL_SECONDS = 600

_SCRIPT_PATH = Path(__file__).with_name("reserve_stock.lua")

# 스크립트를 미리 등록해 매 요청 본문을 보내지 않는다.
_reserve = valkey.register_script(_SCRIPT_PATH.read_text())

_sqs = boto3.client("sqs", region_name=settings.AWS_REGION) if settings.SQS_ORDER_QUEUE_URL else None


def _publish(order_id: str, req, idem_key: str, user_key: str, unit_price: int, amount: int) -> None:
    """주문 확정 요청을 큐에 넣는다. 실제 기록은 order-worker 가 한다.

    idem_key 를 메시지에 실어 보낸다. SQS Standard 는 최소 1회 전달이라
    워커가 같은 메시지를 두 번 받을 수 있고, 그때 MySQL 의 uk_idem 이
    중복을 흡수한다.
    """
    if _sqs is None:
        # 로컬에는 큐가 없다. 발행을 건너뛰되 조용히 넘어가지는 않는다.
        logger.warning("SQS_ORDER_QUEUE_URL 이 비어 있어 발행을 건너뜁니다: %s", order_id)
        return

    _sqs.send_message(
        QueueUrl=settings.SQS_ORDER_QUEUE_URL,
        MessageBody=json.dumps(
            {
                "order_id": order_id,
                "idem_key": idem_key,
                "broadcast_id": req.broadcast_id,
                "sku_id": req.sku_id,
                "user_key": user_key,
                "qty": req.qty,
                # 접수 시점에 확정한 금액이다. 워커는 이 값을 그대로 저장하고
                # 다시 조회하지 않는다.
                "unit_price": unit_price,
                "amount": amount,
            }
        ),
    )


def _mark_accepted(order_id: str, req) -> None:
    """접수 상태를 조회할 수 있게 표식을 남긴다.

    응답 캐시가 아니다. 202 를 받은 직후에는 MySQL 에 아직 행이 없고
    (워커가 나중에 쓴다), 계약은 그 구간을 ACCEPTED 로 정의한다
    (contracts.md 2.2·2.3). 그 상태를 담을 곳이 여기밖에 없다.

    TTL 은 멱등키와 같다. 그 안에 워커가 기록하지 못했다면 DLQ 로 갔거나
    영구 오류라, 표식이 남아 있어 봐야 사실과 다른 상태를 보여줄 뿐이다.
    """
    try:
        valkey.set(
            f"order:{order_id}",
            json.dumps({"sku_id": req.sku_id, "qty": req.qty, "state": "ACCEPTED"}),
            ex=IDEM_TTL_SECONDS,
        )
    except Exception:
        # 실패해도 주문 자체는 성사됐다. 조회가 잠깐 404 가 될 뿐이다.
        logger.exception("접수 표식 저장 실패: %s", order_id)


def get_order(order_id: str) -> dict | None:
    """주문 상태 조회 (contracts.md 2.3).

    MySQL 을 먼저 본다. 워커가 기록했다면 그것이 최종 상태이고, Valkey 를
    먼저 보면 확정된 뒤에도 ACCEPTED 를 돌려주게 된다.

    리플리카가 아니라 writer 로 간다. 주문 직후 조회가 대부분인데 리플리카는
    비동기 복제라 "주문 없음" 이 나갈 수 있다 (architecture.md 4.2).
    """
    with SessionLocal() as db:
        row = db.execute(
            select(Order).where(Order.order_id == order_id)
        ).scalar_one_or_none()

    if row is not None:
        return {
            "order_id": row.order_id,
            "state": row.state,
            "sku_id": str(row.sku_id),
            "qty": row.qty,
        }

    try:
        marker = valkey.get(f"order:{order_id}")
    except Exception:
        logger.exception("접수 표식 조회 실패: %s", order_id)
        marker = None

    if not marker:
        return None

    data = json.loads(marker)
    return {"order_id": order_id, **data}


def _compensate(idem_key: str, sku_id: str, qty: int) -> None:
    """발행이 실패했을 때 예약을 되돌린다.

    되돌리지 않으면 재고는 줄었는데 주문이 없는 상태가 남는다. 멱등키까지
    지워야 같은 키의 재시도가 처음부터 다시 시도할 수 있다.

    파드가 이 사이에 죽으면 재고가 묶인 채 남는다. 그 창을 없애려면 예약을
    durable 하게 만들어야 하는데, 이 규모에서는 방송 종료 배치의 정합성
    확인으로 흡수한다.
    """
    try:
        valkey.delete(f"idem:{idem_key}")
        valkey.incrby(f"stock:{sku_id}", qty)
    except Exception:
        logger.exception("예약 복원 실패 — 재고가 묶인 채 남는다: sku=%s qty=%s", sku_id, qty)


def create_order(req, idem_key: str, user_key: str) -> dict:
    started = time.perf_counter()
    order_id = f"od_{ulid()}"

    # 가격은 접수 시점에 확정한다. 화면이 보는 것과 같은 캐시에서 꺼내므로
    # 사용자가 본 금액과 청구 금액이 어긋나지 않는다.
    unit_price = broadcast_service.get_sale_price(req.broadcast_id, req.sku_id)
    if unit_price is None:
        raise ApiError("INVALID_REQUEST", "편성에 없는 상품입니다")
    amount = unit_price * req.qty

    code, value = _reserve(
        keys=[f"idem:{idem_key}", f"stock:{req.sku_id}"],
        args=[order_id, req.qty, IDEM_TTL_SECONDS],
    )
    code = int(code)
    value = value.decode() if isinstance(value, bytes) else value

    if code == 1:
        # 같은 멱등키의 재요청. 재고를 다시 깎지 않고 첫 응답을 그대로 준다.
        return {"order_id": value, "state": "ACCEPTED"}

    latency_ms = int((time.perf_counter() - started) * 1000)

    if code == -1:
        _emit_issue(req, "FAILED", "SOLD_OUT", latency_ms)
        raise ApiError("SOLD_OUT", "품절되었습니다")

    if code == -2:
        # 재고 키가 없다. 시드가 안 돌았거나 방송 종료 배치가 지운 것이다.
        # 이것을 SOLD_OUT 으로 응답하면 운영 실수가 정상 품절로 묻힌다.
        logger.error("재고 키 미초기화: stock:%s", req.sku_id)
        # failure_code 는 SDK 의 COUPON_FAILURE 안에서만 골라야 한다.
        # 계약 밖 값을 넣으면 SchemaError 로 요청이 죽는다.
        _emit_issue(req, "FAILED", "INTERNAL_ERROR", latency_ms)
        raise ApiError("INTERNAL_ERROR", "주문을 처리할 수 없습니다")

    try:
        _publish(order_id, req, idem_key, user_key, unit_price, amount)
    except Exception:
        logger.exception("주문 큐 발행 실패: %s", order_id)
        _compensate(idem_key, req.sku_id, req.qty)
        raise ApiError("INTERNAL_ERROR", "주문을 접수하지 못했습니다")

    _mark_accepted(order_id, req)

    latency_ms = int((time.perf_counter() - started) * 1000)
    _emit_issue(req, "SUCCESS", None, latency_ms, remaining=int(value))
    _emit_create(order_id, req, amount, latency_ms)

    return {"order_id": order_id, "state": "ACCEPTED"}


# ── 이벤트 ────────────────────────────────────────────────────
# 성공만 발행하면 매크로 트래픽이 통계에서 통째로 사라진다. 대부분이
# SOLD_OUT 이나 RATE_LIMITED 로 실패하기 때문이다 (contracts.md 5.1).
#
# 발행 실패가 사용자 요청을 실패시키면 안 되므로 전부 감싼다.

def _emit_issue(req, result: str, failure_code: str | None, latency_ms: int, remaining: int | None = None) -> None:
    """SDK 의 이벤트 이름은 쿠폰 도메인 기준이고 우리는 특가 판매다.
    대응은 contracts.md 5.2 가 정한다.
    """
    try:
        emit.coupon_issue(
            coupon_id=req.sku_id,
            campaign_id=req.broadcast_id,
            result=result,
            failure_code=failure_code,
            remaining_qty=remaining,
            latency_ms=latency_ms,
        )
    except Exception:
        logger.exception("coupon.issue 발행 실패")


def _emit_create(order_id: str, req, amount: int, latency_ms: int) -> None:
    try:
        emit.order_create(
            order_id=order_id,
            items=[{"sku_id": req.sku_id, "qty": req.qty}],
            total_amount=amount,
            channel="LIVE",
            latency_ms=latency_ms,
        )
    except Exception:
        logger.exception("order.create 발행 실패")
