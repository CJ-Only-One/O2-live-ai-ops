"""주문 확정 워커.

api 가 재고를 깎고 큐에 넣은 주문을 MySQL 에 기록한다. 사용자 응답 경로에서
DB 쓰기를 떼어내 특가 오픈의 쓰기 부하를 큐가 흡수하게 하는 구조다
(architecture.md 3.6).

오류를 두 종류로 가른다. 이 구분이 이 파일의 핵심이다.

    일시적 오류   메시지를 삭제하지 않는다 → SQS 가 다시 준다
    영구적 오류   메시지를 삭제한다 → 재시도해도 같은 결과다

일시적 오류를 삭제하면 주문이 사라지고, 영구적 오류를 남기면 같은 메시지가
maxReceiveCount 까지 돌다 DLQ 로 간다.
"""

import json
import logging
import signal
import sys
import time

import boto3
from o2events import emit
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker

from worker.config import settings
from worker.models import Order

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("order-worker")

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    # 워커는 파드당 커넥션이 적어도 된다. 큐에서 순차로 꺼내 쓰기 때문이다.
    pool_size=2,
    max_overflow=2,
    connect_args={"connect_timeout": 5},
)
SessionLocal = sessionmaker(bind=engine)

sqs = boto3.client("sqs", region_name=settings.AWS_REGION)

# SIGTERM 을 받으면 새 메시지를 받지 않고, 처리 중인 배치만 끝내고 나간다.
# 중간에 끊으면 삭제되지 않은 메시지가 가시성 타임아웃만큼 묶인다.
_running = True


def _stop(signum, _frame):
    global _running
    logger.info("종료 신호 수신(%s). 처리 중인 배치를 끝내고 종료한다.", signum)
    _running = False


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


class PermanentError(Exception):
    """재시도해도 결과가 같은 오류. 메시지를 지우고 order.cancel 을 발행한다."""


def _parse(body: str) -> dict:
    try:
        msg = json.loads(body)
    except json.JSONDecodeError as exc:
        raise PermanentError(f"본문이 JSON 이 아니다: {exc}") from exc

    required = ("order_id", "idem_key", "broadcast_id", "sku_id", "user_key", "qty", "unit_price", "amount")
    missing = [k for k in required if msg.get(k) is None]
    if missing:
        raise PermanentError(f"필수 필드 누락: {', '.join(missing)}")
    return msg


def _persist(msg: dict) -> bool:
    """주문을 기록한다. 이미 있으면 False.

    금액을 다시 계산하지 않는다. api 가 접수 시점에 확정한 값을 그대로 쓴다.
    """
    with SessionLocal() as db:
        db.add(
            Order(
                order_id=msg["order_id"],
                idem_key=msg["idem_key"],
                broadcast_id=msg["broadcast_id"],
                sku_id=int(msg["sku_id"]),
                user_key=msg["user_key"],
                qty=int(msg["qty"]),
                unit_price=int(msg["unit_price"]),
                amount=int(msg["amount"]),
                state="CONFIRMED",
            )
        )
        try:
            db.commit()
            return True
        except IntegrityError as exc:
            db.rollback()
            # 중복은 유니크 키 위반일 때만이다. IntegrityError 를 통째로
            # 중복으로 삼키면 NOT NULL 위반 같은 실제 오류가 "이미 처리됨"
            # 으로 기록되고 주문이 조용히 사라진다.
            if "uk_idem" in str(exc) or "uk_order_id" in str(exc):
                return False
            raise


def _handle(record: dict) -> None:
    msg = _parse(record["Body"])
    started = time.perf_counter()

    inserted = _persist(msg)
    latency_ms = int((time.perf_counter() - started) * 1000)

    if inserted:
        logger.info("주문 확정: %s amount=%s (%sms)", msg["order_id"], msg["amount"], latency_ms)
    else:
        logger.info("이미 처리된 주문(중복 전달): %s", msg["order_id"])


def _emit_cancel(record: dict, reason: str) -> None:
    """최종 취소가 확정된 경우에만 발행한다.

    일시적 실패마다 발행하면 재시도 횟수만큼 취소 이벤트가 쌓여 통계가 망가진다.
    """
    try:
        body = json.loads(record["Body"])
        order_id = body.get("order_id", "unknown")
    except Exception:
        order_id = "unknown"

    try:
        # reason_code 와 cancelled_by 는 SDK 의 열거 안에서만 골라야 한다.
        # 계약 밖 값을 넣으면 SchemaError 가 난다.
        emit.order_cancel(order_id=order_id, reason_code=reason, cancelled_by="SYSTEM")
    except Exception:
        logger.exception("order.cancel 발행 실패")


def _poll_once() -> int:
    resp = sqs.receive_message(
        QueueUrl=settings.SQS_ORDER_QUEUE_URL,
        MaxNumberOfMessages=settings.SQS_BATCH_SIZE,
        WaitTimeSeconds=settings.SQS_WAIT_SECONDS,
    )
    records = resp.get("Messages", [])

    for record in records:
        try:
            _handle(record)
        except PermanentError as exc:
            # 재시도해도 같은 결과다. 큐에 남기면 DLQ 까지 도는 동안 처리량만 먹는다.
            logger.error("영구 오류, 메시지를 버린다: %s", exc)
            _emit_cancel(record, "SYSTEM_ERROR")
        except OperationalError:
            # DB 순단 같은 일시적 오류. 삭제하지 않아 SQS 가 다시 준다.
            logger.exception("일시적 DB 오류 — 메시지를 남긴다")
            continue
        except Exception:
            # 정체를 모르는 오류는 일시적으로 취급한다. 지우면 주문이 사라지고,
            # 남기면 maxReceiveCount 뒤 DLQ 로 가 사람이 볼 수 있다.
            logger.exception("알 수 없는 오류 — 메시지를 남긴다")
            continue

        sqs.delete_message(QueueUrl=settings.SQS_ORDER_QUEUE_URL, ReceiptHandle=record["ReceiptHandle"])

    return len(records)


def main() -> None:
    if not settings.SQS_ORDER_QUEUE_URL:
        logger.error("SQS_ORDER_QUEUE_URL 이 비어 있다. 큐 없이는 할 일이 없다.")
        sys.exit(1)

    logger.info("워커 시작: %s", settings.SQS_ORDER_QUEUE_URL)
    while _running:
        try:
            _poll_once()
        except Exception:
            # 폴링 자체가 실패하면(권한·네트워크) 잠깐 쉬고 다시 시도한다.
            logger.exception("폴링 실패 — 5초 후 재시도")
            time.sleep(5)

    logger.info("워커 종료")


if __name__ == "__main__":
    main()
