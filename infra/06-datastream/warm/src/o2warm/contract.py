"""o2events 이벤트 계약 중 집계가 의존하는 부분.

## 왜 o2events 를 import 하지 않는가

`from o2events.schemas import EVENT_NAMES` 가 더 직접적으로 보이지만,
`o2events/__init__.py` 가 emit·emitter·sinks 를 전부 끌어옵니다. 집계
Lambda 가 이벤트 **발행** 코드를 싣고 다니게 되고, 그러면 앱 SDK 버전이
올라갈 때마다 집계기도 재배포해야 합니다.

그래서 값은 여기 두고, **드리프트는 테스트가 잡습니다.**
`tests/test_contract.py` 가 o2events 를 개발 의존성으로 불러와 이 파일의
모든 값이 실제 계약에 존재하는지 확인합니다. 필드명이 하나라도 바뀌면
배포 전에 시험이 깨집니다.

런타임 결합은 0, 드리프트 감지는 CI — 이 조합이 목적입니다.
"""

from __future__ import annotations

# --- 이벤트 이름 (schemas.EVENT_NAMES) -------------------------------

EVENT_COUPON = "coupon.issue"
EVENT_PAYMENT = "payment.process"
EVENT_INVENTORY = "inventory.check"
EVENT_ORDER_CREATE = "order.create"
EVENT_ORDER_CANCEL = "order.cancel"
EVENT_CLIENT = "client.action"

EVENT_NAMES = frozenset({
    EVENT_COUPON, EVENT_PAYMENT, EVENT_INVENTORY,
    EVENT_ORDER_CREATE, EVENT_ORDER_CANCEL, EVENT_CLIENT,
})

# 클라이언트 스트림으로 가는 이벤트. sinks._stream_for 와 같은 규칙입니다.
CLIENT_PREFIXES = ("client.", "live.")

# --- enum 값 ---------------------------------------------------------

RESULT_FAILED = "FAILED"        # COUPON_RESULT · PAYMENT_RESULT 공통
RESULT_SUCCESS = "SUCCESS"

ACTION_COUPON_CLICK = "COUPON_BUTTON_CLICK"
ACTION_CHECKOUT_CLICK = "CHECKOUT_CLICK"

# --- payload 필드 (emit.* 시그니처) ----------------------------------
# 이름이 바뀌면 해당 지표가 조용히 None 이 됩니다. 그래서 시험으로 묶습니다.

F_RESULT = "result"
F_FAILURE_CODE = "failure_code"
F_CACHE_HIT = "cache_hit"
F_PG_LATENCY = "pg_latency_ms"
F_TOTAL_LATENCY = "total_latency_ms"
F_ACTION = "action"
F_UA_KEY = "ua_key"

# --- 사용자 경험 저하 신호 ---
# 인프라 지표가 정상인 채로 체감만 나빠지는 상황을 잡는 필드들입니다.
# 응답이 200이고 에러율이 정상이어도 이 값들은 움직입니다.
F_LATENCY = "latency_ms"
F_FALLBACK_USED = "fallback_used"
F_IS_RETRY = "is_retry"
F_RETRY_COUNT = "retry_count"
F_REASON_CODE = "reason_code"
F_CANCELLED_BY = "cancelled_by"

# --- 세그먼트 축 ---
# "평균은 멀쩡한데 특정 구간만 죽는" 상황을 보려면 나눌 축이 필요합니다.
F_CAMPAIGN_ID = "campaign_id"
F_CHANNEL = "channel"
F_SOURCE = "source"
F_DEVICE_TYPE = "device_type"

# emit 함수별로 이 필드가 있어야 한다는 대응표. 시험이 이대로 검사합니다.
PAYLOAD_FIELDS = {
    "coupon_issue": [F_RESULT, F_FAILURE_CODE, F_LATENCY, F_IS_RETRY, F_CAMPAIGN_ID],
    "payment_process": [F_RESULT, F_FAILURE_CODE, F_PG_LATENCY, F_TOTAL_LATENCY,
                        F_RETRY_COUNT],
    "inventory_check": [F_CACHE_HIT, F_LATENCY, F_FALLBACK_USED, F_SOURCE],
    "order_create": [F_CHANNEL, F_LATENCY],
    "order_cancel": [F_REASON_CODE, F_CANCELLED_BY],
    "client_action": [F_ACTION, F_UA_KEY, F_DEVICE_TYPE],
}

# --- 봉투 필드 -------------------------------------------------------

E_EVENT_NAME = "event_name"
E_BROADCAST_ID = "broadcast_id"
E_SERVICE = "service"
E_SERVICE_VERSION = "service_version"
E_USER_KEY = "user_key"
E_CLIENT_IP_KEY = "client_ip_key"
E_RECEIVED_TS = "received_ts"
E_EVENT_TS = "event_ts"
E_PAYLOAD = "payload"

ENVELOPE_FIELDS = frozenset({
    E_EVENT_NAME, E_BROADCAST_ID, E_SERVICE, E_SERVICE_VERSION, E_USER_KEY,
    E_CLIENT_IP_KEY, E_RECEIVED_TS, E_EVENT_TS, E_PAYLOAD,
})

# 세그먼트 축과 값의 출처. "payload" 또는 "envelope".
#
# **비즈니스 이벤트에는 device_type 이 없습니다.** 계약상 클라이언트
# 이벤트에만 실리므로, "모바일 사용자만 결제가 실패한다"는 현재 계약으로
# 감지할 수 없습니다. 클릭 볼륨의 기기별 급감까지만 보입니다.
# 서버 이벤트에 device_type 을 추가하려면 계약 변경이 필요합니다.
SEGMENT_AXES = (
    (F_CAMPAIGN_ID, "payload"),
    (F_CHANNEL, "payload"),
    (F_SOURCE, "payload"),
    (F_DEVICE_TYPE, "payload"),
    (E_BROADCAST_ID, "envelope"),
)
