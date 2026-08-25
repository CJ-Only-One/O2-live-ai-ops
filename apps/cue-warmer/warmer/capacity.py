"""큐시트의 예상 부하를 서비스별 목표 파드 수로 옮긴다.

여기 있는 나눗셈의 분모는 **전부 실측값**이다(docs/measurements.md). 추정치를
쓰지 않는 것이 이 파일의 규칙이다 — 안 잰 축은 아예 계산하지 않고 None 을
돌려 호출자가 "모른다" 를 그대로 다루게 한다.

서비스마다 쓰는 필드가 다르다. api·chat-gateway 는 Deployment 의 replicas 를
직접 잡고, order-worker 는 그 필드를 KEDA 가 소유하므로
(order-worker-scaledobject.yaml) ScaledObject 의 minReplicaCount 만 올린다.
여기서 내는 것은 어느 쪽이든 "목표 파드 수" 하나이고, 그 값을 어느 필드에
쓸지는 main.reconcile_scale 이 정한다.
"""

import math

# ── 실측 분모 ────────────────────────────────────────────────
#
# M-009: api 파드 하나가 계약 기준(p95 < 800ms)을 지키는 최대 읽기 처리량.
# 300 RPS 에서 p95 314ms 로 통과했고 400 RPS 에서 1,352ms 로 깨졌다.
API_RPS_PER_POD = 300

# M-010: chat-gateway 2파드 안전선 20,000 아이템/s 를 파드 수로 나눈 값.
#
# **선형 가정이 들어 있다.** 2파드만 쟀고 4·8파드는 안 쟀다. 게다가 M-010
# 해석 2 가 "같은 아이템/s 라도 연결이 많을수록 나쁘다"(프레임마다 직렬화가
# 도는 구조)고 했으므로 실제로는 선형보다 나쁠 수 있다. 파드를 늘려 재면
# 그 값으로 바꾼다.
CHAT_ITEMS_PER_POD = 10_000

# M-014: order-worker 파드 하나가 SQS 에서 빼 MySQL 에 넣는 주문 처리량.
# 1 → 12 파드에서 47~49/s 로 평평했고 꺾이는 지점을 못 찾았다(12파드
# 588.9/s 에서도 RDS CPU 18.2%). 보수적으로 아래쪽을 쓴다.
ORDER_PER_POD = 47


def api_pods(concurrent: int | None, entry_window_s: int | None) -> int | None:
    """진입 스냅샷은 1회성이라 인원이 아니라 밀도가 RPS 를 정한다.

    12,000명이 30초에 걸쳐 들어오면 400 RPS 이고 5분에 걸치면 40 RPS 다 —
    같은 인원이어도 필요한 파드 수가 10배 다르다.
    """
    if not concurrent or not entry_window_s:
        return None
    rps = concurrent / entry_window_s
    return math.ceil(rps / API_RPS_PER_POD)


def chat_pods(concurrent: int | None, chat_rate: float | None) -> int | None:
    """팬아웃 총량은 시청자 × 채팅율이다 — 채팅 한 건이 접속자 전원에게 가므로
    (M-010). 둘 중 하나만 알면 아이템/s 를 못 구한다."""
    if not concurrent or not chat_rate:
        return None
    items_per_s = concurrent * chat_rate
    return math.ceil(items_per_s / CHAT_ITEMS_PER_POD)


def order_pods(order_rate: float | None) -> int | None:
    """특가 오픈·마감의 주문 폭주를 큐 소비 파드 수로 옮긴다.

    order-worker 의 파드 수는 KEDA 가 SQS 큐 길이로 소유한다. 워머가 그
    소유권을 뺏지 않는다 — ScaledObject 의 minReplicaCount(바닥)만 올리고,
    KEDA 는 그 위에서 큐 길이를 보고 계속 조절한다. 워머가 미리 올려둔
    것으로도 부족하면 KEDA 가 더 올린다(D-041 의 층 구조 — 사전 확장이
    주력, KEDA 가 2차 보정).
    """
    if not order_rate:
        return None
    return math.ceil(order_rate / ORDER_PER_POD)


def targets(expected: dict) -> dict[str, int]:
    """세그먼트 하나의 expected 에서 서비스별 목표 파드 수를 낸다.

    값이 없어 계산이 안 되는 서비스는 키 자체를 안 넣는다 — 0 을 넣으면
    호출자가 "0개로 줄이라" 로 읽을 수 있다.
    """
    out: dict[str, int] = {}

    api = api_pods(expected.get("concurrent"), expected.get("entry_window_s"))
    if api is not None:
        out["api"] = api

    chat = chat_pods(expected.get("concurrent"), expected.get("chat_rate"))
    if chat is not None:
        out["chat-gateway"] = chat

    order = order_pods(expected.get("order_rate"))
    if order is not None:
        out["order-worker"] = order

    return out


def merge(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    """겹치는 세그먼트의 목표를 합친다 — 같은 서비스면 큰 쪽을 쓴다.

    합(sum)이 아니라 max 인 이유: 세그먼트 둘이 같은 시각에 걸쳐 있어도
    시청자는 한 무리다. 방송 시작(진입 밀도)과 게스트 등장(연결 수)이 같은
    시각이면 concurrent 를 두 번 세는 게 아니라 각자 계산한 요구 중 큰 쪽을
    맞추면 된다.
    """
    out = dict(a)
    for service, pods in b.items():
        out[service] = max(out.get(service, 0), pods)
    return out
