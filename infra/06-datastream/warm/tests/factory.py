"""시나리오 재현용 합성 이벤트 생성기.

감별표의 각 행을 실제 이벤트 흐름으로 만들어 봐야, 지표 조합이 정말로
그 행들을 갈라내는지 확인할 수 있습니다. 표만 보고 "구분된다"고 믿는 것과
계산해서 확인하는 것은 다릅니다.
"""

from __future__ import annotations

import random

from o2warm.windows import iso_from_epoch

BASE = 1786000000  # 10으로 나누어떨어지는 고정 시각 — 윈도우 경계가 흔들리지 않게


BROADCAST = "LIVE-20260813-01"


def envelope(name, ts, *, service="coupon-api", user=None, ip=None,
             version="v1.4.2", payload=None, session=None, broadcast=BROADCAST):
    return {
        "event_id": f"E{int(ts * 1000)}{random.randint(0, 999999)}",
        "event_name": name,
        "schema_version": "1.0",
        "event_ts": iso_from_epoch(ts),
        "received_ts": iso_from_epoch(ts),
        "service": service,
        "service_version": version,
        "trace_id": f"t{random.randint(0, 10**12)}",
        "broadcast_id": broadcast,
        "user_key": user,
        "client_ip_key": ip,
        "session_id": session or user,
        "payload": payload or {},
    }


def coupon(ts, user, ip, *, result="SUCCESS", code=None, version="v1.4.2",
           campaign="LIVE-FLASH-01", latency=87, is_retry=False):
    p = {"coupon_id": "CP-8821", "campaign_id": campaign,
         "result": result, "latency_ms": latency, "is_retry": is_retry}
    if code:
        p["failure_code"] = code
    return envelope("coupon.issue", ts, user=user, ip=ip, version=version, payload=p)


def click(ts, user, ua, *, action="COUPON_BUTTON_CLICK", device="MOBILE_APP"):
    return envelope(
        "client.action", ts,
        service="web-collector", user=user,
        payload={"action": action, "device_type": device, "ua_key": ua},
    )


def order_create(ts, user, ip, *, channel="LIVE", latency=140):
    return envelope(
        "order.create", ts, service="order-api", user=user, ip=ip,
        payload={"order_id": f"O{int(ts*1000)}{random.randint(0,999)}",
                 "items": [{"product_id": "SKU-1", "qty": 1}],
                 "total_amount": 25000, "channel": channel, "latency_ms": latency},
    )


def order_cancel(ts, user, ip, *, reason="CUSTOMER_REQUEST", by="CUSTOMER"):
    return envelope(
        "order.cancel", ts, service="order-api", user=user, ip=ip,
        payload={"order_id": f"O{int(ts*1000)}{random.randint(0,999)}",
                 "reason_code": reason, "cancelled_by": by, "stage": "FULFILLMENT"},
    )


def payment(ts, user, ip, *, result="SUCCESS", code=None, pg_ms=40, total_ms=200,
            version="v1.4.2", retry_count=0):
    p = {"order_id": f"O{int(ts*1000)}", "payment_id": f"P{int(ts*1000)}",
         "amount": 25000, "result": result, "retry_count": retry_count,
         "pg_latency_ms": pg_ms, "total_latency_ms": total_ms}
    if code:
        p["failure_code"] = code
    return envelope("payment.process", ts, service="payment-api", user=user, ip=ip,
                    version=version, payload=p)


def inventory(ts, user, ip, *, cache_hit=True, fallback=False, latency=12):
    return envelope(
        "inventory.check", ts, service="coupon-api", user=user, ip=ip,
        payload={"product_id": "SKU-1", "requested_qty": 1, "available_qty": 5,
                 "source": "CACHE" if cache_hit else "DB_PRIMARY",
                 "cache_hit": cache_hit, "fallback_used": fallback,
                 "latency_ms": latency},
    )


# ---------------------------------------------------------------- 시나리오

def normal(n_users=200, per_user=3, rng=None):
    """평시. 사용자가 많고 간격은 제각각이며 클릭이 요청에 앞섭니다."""
    rng = rng or random.Random(1)
    out = []
    for u in range(n_users):
        user, ip, ua = f"u_{u:04d}", f"ip_{u:04d}", f"ua_{u % 40}"
        t = BASE + rng.random() * 2
        for _ in range(per_user):
            out.append(click(t - 0.15, user, ua))
            out.append(coupon(t, user, ip))
            t += rng.uniform(0.8, 3.5)  # 사람의 간격은 들쭉날쭉합니다
    return out


def traffic_surge(rng=None):
    """트래픽 폭증 — 사용자 수 자체가 늘어난 경우."""
    return normal(n_users=1200, per_user=3, rng=rng or random.Random(2))


def macro(rng=None):
    """매크로 — 소수 계정이 클릭 없이 일정 간격으로 두드립니다."""
    rng = rng or random.Random(3)
    out = normal(n_users=120, per_user=2, rng=random.Random(4))  # 배경의 정상 사용자
    for u in range(6):
        user, ip = f"bot_{u}", f"ipbot_{u}"
        t = BASE + u * 0.01
        for _ in range(300):
            out.append(coupon(t, user, ip, result="FAILED", code="SOLD_OUT"))
            t += 0.03 + rng.uniform(-0.001, 0.001)  # 기계적으로 일정한 간격
    return out


def cache_miss_storm(rng=None):
    """캐시 미스 폭주 — 트래픽은 평시인데 캐시가 안 듣습니다."""
    rng = rng or random.Random(5)
    out = normal(n_users=200, per_user=3, rng=random.Random(1))
    for i in range(600):
        u = f"u_{i % 200:04d}"
        out.append(inventory(BASE + rng.random() * 9, u, f"ip_{i % 200:04d}",
                             cache_hit=(i % 20 == 0)))
    return out


def pg_outage(rng=None):
    """PG 장애 — 결제 실패가 PG_* 로 몰리고 지연이 PG 구간에 쏠립니다."""
    rng = rng or random.Random(6)
    out = []
    for i in range(400):
        u, ip = f"u_{i % 300:04d}", f"ip_{i % 300:04d}"
        t = BASE + rng.random() * 9
        if i % 10 < 6:
            out.append(payment(t, u, ip, result="FAILED", code="PG_TIMEOUT",
                               pg_ms=2900, total_ms=3000))
        else:
            out.append(payment(t, u, ip, pg_ms=60, total_ms=220))
    return out


def db_outage(rng=None):
    """DB 장애 — 실패율은 PG 장애와 같지만 사유와 지연 구간이 다릅니다."""
    rng = rng or random.Random(7)
    out = []
    for i in range(400):
        u, ip = f"u_{i % 300:04d}", f"ip_{i % 300:04d}"
        t = BASE + rng.random() * 9
        if i % 10 < 6:
            out.append(payment(t, u, ip, result="FAILED", code="DB_TIMEOUT",
                               pg_ms=55, total_ms=3000))
        else:
            out.append(payment(t, u, ip, pg_ms=60, total_ms=220))
    return out


# ------------------------------------------------- 사용자 경험 저하 시나리오
#
# 공통점: **인프라 지표는 전부 정상입니다.**
# 응답은 200이고, 에러율도 p95도 임계 안입니다. 그런데 사용자는 불편합니다.

def campaign_outage(rng=None):
    """캠페인 하나만 죽음.

    전체 실패율은 임계에 안 걸리는 수준인데 특정 캠페인 사용자는
    거의 전원이 실패합니다. 평균이 가리는 전형적인 형태입니다.
    """
    rng = rng or random.Random(41)
    out = []
    for i in range(600):  # 정상 캠페인
        u = f"u_{i % 400:04d}"
        out.append(coupon(BASE + rng.random() * 9, u, f"ip_{i % 400:04d}",
                          campaign="LIVE-FLASH-01"))
    for i in range(100):  # 망가진 캠페인
        u = f"u_{i % 90:04d}"
        failed = i % 20 != 0  # 95%
        out.append(coupon(
            BASE + rng.random() * 9, u, f"ip_{i % 90:04d}",
            campaign="LIVE-FLASH-02",
            result="FAILED" if failed else "SUCCESS",
            code="INTERNAL_ERROR" if failed else None,
        ))
    return out


def retry_storm(rng=None):
    """전부 성공하는데 사용자가 계속 다시 누름.

    실패율 0, 지연 정상. 그런데 같은 사람이 반복 시도한다는 것은
    무언가 기대대로 동작하지 않았다는 뜻입니다.
    """
    rng = rng or random.Random(42)
    out = []
    for i in range(500):
        u = f"u_{i % 150:04d}"
        out.append(coupon(BASE + rng.random() * 9, u, f"ip_{i % 150:04d}",
                          is_retry=(i % 10 >= 4)))  # 60%
    return out


def cancel_surge(rng=None):
    """주문은 정상 생성되는데 뒤에서 취소가 쏟아짐.

    요청 시점에는 아무 신호가 없습니다. 취소는 비동기·사후에 일어납니다.
    """
    rng = rng or random.Random(43)
    out = []
    for i in range(200):
        u = f"u_{i % 150:04d}"
        out.append(order_create(BASE + rng.random() * 9, u, f"ip_{i % 150:04d}"))
    for i in range(70):
        u = f"u_{i % 60:04d}"
        out.append(order_cancel(BASE + rng.random() * 9, u, f"ip_{i % 60:04d}",
                                reason="INVENTORY_SHORTAGE", by="SYSTEM"))
    return out


def fallback_degradation(rng=None):
    """캐시가 죽어 폴백으로 처리됨. **실패가 하나도 없습니다.**

    inventory.check 에는 result 필드 자체가 없어 실패율로는 절대 안 잡힙니다.
    폴백 비율과 지연 분포만이 근거입니다.
    """
    rng = rng or random.Random(44)
    out = []
    for i in range(500):
        u = f"u_{i % 200:04d}"
        degraded = i % 10 < 8  # 80%
        out.append(inventory(
            BASE + rng.random() * 9, u, f"ip_{i % 200:04d}",
            cache_hit=not degraded,
            fallback=degraded,
            latency=420 if degraded else 12,
        ))
    return out


def tail_latency(rng=None):
    """p50 은 멀쩡한데 꼬리만 무너짐.

    평균과 중앙값으로는 안 보입니다. 그런데 12%의 사용자는 3초를 기다립니다.
    """
    rng = rng or random.Random(45)
    out = []
    for i in range(500):
        u = f"u_{i % 200:04d}"
        slow = i % 25 < 3  # 12%
        out.append(coupon(BASE + rng.random() * 9, u, f"ip_{i % 200:04d}",
                          latency=3200 if slow else int(rng.uniform(60, 110))))
    return out


def healthy(rng=None):
    """대조군. 위 지표들이 전부 조용해야 합니다."""
    rng = rng or random.Random(46)
    out = []
    for i in range(500):
        u = f"u_{i % 300:04d}"
        out.append(coupon(BASE + rng.random() * 9, u, f"ip_{i % 300:04d}",
                          latency=int(rng.uniform(60, 120))))
    for i in range(300):
        u = f"u_{i % 200:04d}"
        out.append(inventory(BASE + rng.random() * 9, u, f"ip_{i % 200:04d}",
                             cache_hit=(i % 50 != 0)))
    return out


def bad_deploy(rng=None):
    """배포 장애 — 신 버전에서만 실패합니다. 전체 실패율만 보면 애매합니다."""
    rng = rng or random.Random(8)
    out = []
    for i in range(400):
        u, ip = f"u_{i % 300:04d}", f"ip_{i % 300:04d}"
        t = BASE + rng.random() * 9
        new = i % 2 == 0
        version = "v1.5.0" if new else "v1.4.2"
        failed = new and (i % 10 < 6)
        out.append(payment(
            t, u, ip, version=version,
            result="FAILED" if failed else "SUCCESS",
            code="INTERNAL_ERROR" if failed else None,
            pg_ms=60, total_ms=220,
        ))
    return out
