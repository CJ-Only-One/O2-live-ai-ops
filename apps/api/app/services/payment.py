"""S3 외부 결제 게이트웨이 장애를 재현하는 목업 PG.

실제 결제 인프라나 외부 네트워크 호출은 만들지 않는다. 주문 접수 경로가
Valkey의 ``cfg:pg:*`` 설정을 읽고, 설정된 시간만큼 동기 대기한 뒤 결정론적으로
실패시킨다. 같은 결제 멱등키는 같은 결과를 내므로 클라이언트 재시도가 결제
결과를 뒤집지 않는다.

이벤트 발행은 관측 경로일 뿐이다. SDK 또는 Kinesis 전송 실패가 결제 결과를
바꾸면 계측 장애가 구매 장애가 되므로 예외를 요청 경로 밖으로 내보내지 않는다.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from dataclasses import dataclass

from o2events import emit

from app.core import cache
from app.core.telemetry import telemetry
from app.db.valkey import valkey

logger = logging.getLogger(__name__)

PG_DELAY_KEY = "cfg:pg:delay_ms"
PG_FAIL_RATE_KEY = "cfg:pg:fail_rate"
# S3 조치 — PG-A 장애를 우리가 못 고치니 PG-B로 우회한다(2026-08-25 회의 결정,
# S3는 방어 조치만으로 끝나지 않고 실제로 해결되는 시나리오로 간다). 이 키가
# 있는 동안은 process_payment가 PG_DELAY_KEY/PG_FAIL_RATE_KEY 주입을 완전히
# 무시한다 — "이미 다른 게이트웨이로 갔다"는 전제라 PG-A 장애가 안 보여야 한다.
PG_ACTIVE_PROVIDER_KEY = "cfg:pg:active_provider"
PROVIDERS = ("PG-A", "PG-B")

# 직접 Valkey를 수정해도 한 파드에서 최대 1초 뒤에는 반영된다. 평시 주문마다
# Valkey 왕복 두 건을 추가하지 않으면서 재배포 없는 장애 주입을 유지하는 경계다.
_CONFIG_CACHE_KEY = "local:pg-stub-config"
_CONFIG_CACHE_TTL_SECONDS = 1.0

# 성능 기준이나 권장 주입값이 아니라, 오타 하나가 워커 스레드를 무기한 점유하지
# 못하게 하는 하드 안전 상한이다. 실제 시나리오 강도는 measurements.md 실측 뒤
# 별도로 정한다.
MAX_DELAY_MS = 30_000


@dataclass(frozen=True)
class PgStubConfig:
    delay_ms: int = 0
    fail_rate: float = 0.0
    active_provider: str = "PG-A"

    @property
    def active(self) -> bool:
        return self.delay_ms > 0 or self.fail_rate > 0


@dataclass(frozen=True)
class PaymentResult:
    succeeded: bool
    payment_id: str
    failure_code: str | None
    pg_latency_ms: int
    total_latency_ms: int
    retry_count: int = 0


def _text(value) -> str | None:
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else str(value)


def _parse_config(values) -> PgStubConfig:
    delay_raw, fail_rate_raw = values
    delay_ms = int(_text(delay_raw) or "0")
    fail_rate = float(_text(fail_rate_raw) or "0")

    if not 0 <= delay_ms <= MAX_DELAY_MS:
        raise ValueError(f"delay_ms must be between 0 and {MAX_DELAY_MS}")
    if not math.isfinite(fail_rate) or not 0 <= fail_rate <= 1:
        raise ValueError("fail_rate must be between 0 and 1")
    if fail_rate > 0 and delay_ms == 0:
        raise ValueError("PG_TIMEOUT injection requires delay_ms greater than 0")
    return PgStubConfig(delay_ms=delay_ms, fail_rate=fail_rate)


def _parse_provider(value) -> str:
    provider = _text(value) or "PG-A"
    if provider not in PROVIDERS:
        raise ValueError(f"active_provider must be one of {PROVIDERS}")
    return provider


def _load_config() -> PgStubConfig:
    try:
        delay_raw, fail_rate_raw, provider_raw = valkey.mget(
            [PG_DELAY_KEY, PG_FAIL_RATE_KEY, PG_ACTIVE_PROVIDER_KEY]
        )
        base = _parse_config([delay_raw, fail_rate_raw])
        return PgStubConfig(
            delay_ms=base.delay_ms,
            fail_rate=base.fail_rate,
            active_provider=_parse_provider(provider_raw),
        )
    except Exception:
        # 이 노브는 장애 실험용이다. Valkey 장애나 잘못된 수동 입력이 실제 주문
        # 장애를 추가로 만들지 않도록 평시 설정으로 fail-open 한다.
        logger.exception("PG 스텁 설정 조회 실패, 평시 설정으로 간주합니다")
        return PgStubConfig()


def set_active_provider(provider: str) -> PgStubConfig:
    valkey.set(PG_ACTIVE_PROVIDER_KEY, _parse_provider(provider))
    cache.delete(_CONFIG_CACHE_KEY)
    return get_config(authoritative=True)


def clear_active_provider() -> PgStubConfig:
    valkey.delete(PG_ACTIVE_PROVIDER_KEY)
    cache.delete(_CONFIG_CACHE_KEY)
    return get_config(authoritative=True)


def get_config(*, authoritative: bool = False) -> PgStubConfig:
    if authoritative:
        return _load_config()
    return cache.get_or_load(
        _CONFIG_CACHE_KEY,
        _CONFIG_CACHE_TTL_SECONDS,
        _load_config,
    )


def set_config(*, delay_ms: int, fail_rate: float) -> PgStubConfig:
    # HTTP 모델 밖에서 호출하더라도 같은 안전 경계를 통과하게 한다.
    desired = _parse_config([delay_ms, fail_rate])
    valkey.mset(
        {
            PG_DELAY_KEY: str(desired.delay_ms),
            PG_FAIL_RATE_KEY: format(desired.fail_rate, ".12g"),
        }
    )
    cache.delete(_CONFIG_CACHE_KEY)
    return desired


def clear_config() -> PgStubConfig:
    valkey.delete(PG_DELAY_KEY, PG_FAIL_RATE_KEY)
    cache.delete(_CONFIG_CACHE_KEY)
    return PgStubConfig()


def _payment_id(idempotency_key: str) -> str:
    # 원문 UUID를 이벤트에 다시 싣지 않는다. 같은 키의 재시도는 같은 결제 ID를
    # 가져 downstream에서 중복을 식별할 수 있다.
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:24]
    return f"pay_{digest}"


def _fails(idempotency_key: str, fail_rate: float) -> bool:
    if fail_rate <= 0:
        return False
    if fail_rate >= 1:
        return True

    # 난수를 다시 뽑으면 동일 멱등키 재시도가 성공/실패를 뒤집는다. 해시를
    # [0, 1) 표본으로 바꿔 전체 요청에서는 fail_rate 분포를 만들되 같은 결제는
    # 언제나 같은 결과를 내게 한다.
    sample = int(hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:13], 16)
    return sample / float(16**13) < fail_rate


def process_payment(
    *, order_id: str, idempotency_key: str, amount: int
) -> PaymentResult:
    config = get_config()
    started = time.perf_counter()

    if config.active_provider == "PG-B":
        # 사람이 승인해 PG-A에서 전환한 뒤다 — 이미 다른 게이트웨이로 갔다는
        # 전제이므로 PG-A용으로 주입된 delay_ms/fail_rate를 재현하지 않는다.
        failed = False
    else:
        if config.delay_ms:
            time.sleep(config.delay_ms / 1000)
        failed = _fails(idempotency_key, config.fail_rate)
    pg_latency_ms = int((time.perf_counter() - started) * 1000)
    result = "FAILED" if failed else "SUCCESS"
    failure_code = "PG_TIMEOUT" if failed else None
    payment_id = _payment_id(idempotency_key)

    telemetry.business_event("payment.process", result.lower())
    telemetry.operation_duration("payment.process", pg_latency_ms)
    if failure_code:
        telemetry.failure("payment.process", failure_code)

    try:
        emit.payment_process(
            order_id=order_id,
            payment_id=payment_id,
            amount=amount,
            result=result,
            failure_code=failure_code,
            failure_stage="PG_CALL" if failed else None,
            # PG-B 전환 후에는 provider 이름 자체가 판단 근거다(Agent 조치의
            # 성공 여부를 provider별 성공 이벤트로 확인해야 하므로) — PG-A일
            # 때는 여전히 PG 구간 지연·실패 코드가 우선 근거다.
            pg_provider=config.active_provider,
            pg_response_code="TIMEOUT" if failed else "OK",
            pg_latency_ms=pg_latency_ms,
            total_latency_ms=pg_latency_ms,
            retry_count=0,
        )
    except Exception:
        logger.exception("payment.process 발행 실패")

    return PaymentResult(
        succeeded=not failed,
        payment_id=payment_id,
        failure_code=failure_code,
        pg_latency_ms=pg_latency_ms,
        total_latency_ms=pg_latency_ms,
    )
