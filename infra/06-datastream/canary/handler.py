"""파이프라인 생존 카나리 — 1분마다 합성 이벤트를 하나 넣습니다.

## 왜 필요한가

이 경로는 **전 구간이 실패를 삼키도록** 설계돼 있습니다. SDK 의 `_send()`,
chat-gateway 의 `send()`, 집계기의 `datadog.submit()` 이 전부 예외를 먹고
stderr 로만 남기는데, `04-platform` 의 `logs.enabled = false` 라 그 stderr 는
Datadog 에 오지 않습니다. **파이프라인이 통째로 멈춰도 대시보드는 조용합니다.**

가용성을 위해서는 옳은 선택입니다 — 이벤트 발행 실패가 주문이나 채팅을
막으면 안 되니까요. 대신 **밖에서 살아 있음을 확인해 줄 무언가**가 필요합니다.

## 왜 비즈니스 지표로는 안 되는가

`o2.warm.event_count` 같은 실제 지표에 no-data 를 걸면 **트래픽이 없을 때
장애와 구분되지 않습니다.** 이건 가정이 아니라 겪은 일입니다 —
`order_latency_p95` 의 `notify_no_data` 가 08-19~08-21 사흘 동안 No Data 와
Recovered 를 7번 왕복해서 결국 꺼졌습니다(`05-datadog/monitor.tf` 주석).

실측(M-014)에서도 48시간 중 42시간이 6시간당 5건 수준이었고, 나머지가
6시간에 164,581건이었습니다. **이 환경은 원래 간헐적입니다.**

그래서 생존 신호는 **스스로 트래픽을 만들어야** 합니다. 그것이 카나리입니다.

## 무엇을 증명하나

이 함수가 넣은 레코드가 `o2.warm.rps{service:o2-canary}` 로 나오면
**Kinesis → 이벤트 소스 매핑 → 집계 Lambda → 윈도우 계산 → Datadog 전송**
이 전부 살아 있다는 뜻입니다. 한 구간이라도 죽으면 그 시계열이 끊깁니다.

구간별 지표(`aws.lambda.errors` 등)는 **어디가** 끊겼는지 알려주고, 이
카나리는 **끊겼다는 사실 자체**를 알려줍니다. 둘 다 필요하고, 순서는
이쪽이 먼저입니다 — 어디가 문제인지는 끊긴 걸 안 다음의 질문입니다.

## 남기는 흔적

`service:o2-canary` 하나로 격리됩니다. 실제 서비스 윈도우와 섞이지 않는
이유는 집계기가 `service` 로 윈도우를 가르기 때문입니다(`windows.service_of`).

**다만 두 곳에 흔적이 남습니다.**

- DynamoDB — `o2-canary` 서비스의 윈도우 아이템. TTL 로 만료됩니다
- **S3 데이터 레이크** — Firehose 가 같은 스트림을 읽으므로 합성 레코드가
  그대로 적재됩니다. Athena 쿼리에서 `service <> 'o2-canary'` 로 빼야 합니다

에이전트가 읽는 지표를 조회할 때도 이 서비스를 빼야 합니다. 명세 8절의
"주입은 Agent 가 읽는 저장소에 흔적을 남기지 않는다" 와 맞물리는 지점이라,
**서비스 이름 하나로 걸러지도록** 일부러 전용 이름을 씁니다.

## 이벤트 이름을 `canary.ping` 으로 둔 이유

계약에 없는 이름이라 `event_rate` 태그로 안 펼쳐집니다(집계기가 `EVENT_NAMES`
로 제한합니다). 그러면서 `client.`/`live.` 접두어가 아니라 비즈니스 이벤트로
세어져 `rps` 와 `event_count` 에는 잡힙니다. **생존 확인에 필요한 것만
남기고 나머지 지표는 건드리지 않는** 조합입니다.
"""

from __future__ import annotations

import json
import os
import random
import string
import time
from datetime import datetime, timezone

import boto3

STREAM = os.environ["CANARY_STREAM"]
SERVICE = os.environ.get("CANARY_SERVICE", "o2-canary")
EVENT_NAME = "canary.ping"

_kinesis = boto3.client("kinesis")
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _iso_now() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _ulid() -> str:
    """SDK core.py 의 ulid() 와 같은 모양. 앞 10자가 밀리초 타임스탬프다.

    수집단이 정렬·중복 제거 키로 쓰므로 여기만 UUID 를 내면 카나리 레코드의
    정렬이 깨진다. 깨져도 아무도 에러를 내지 않아 늦게 발견된다.
    """
    ms = int(time.time() * 1000)
    head = ""
    for _ in range(10):
        head = _CROCKFORD[ms & 31] + head
        ms >>= 5
    tail = "".join(random.choice(_CROCKFORD) for _ in range(16))
    return head + tail


def _envelope() -> dict:
    now = _iso_now()
    return {
        "event_id": _ulid(),
        "event_name": EVENT_NAME,
        "schema_version": "1.0",
        "event_ts": now,
        "received_ts": now,
        "service": SERVICE,
        "service_version": "canary",
        "trace_id": None,
        "broadcast_id": None,
        # 사용자 키를 매번 새로 만들지 않는다. distinct_users 와 간격 통계가
        # 카나리 때문에 움직이면 안 된다 — 이 서비스는 어차피 분리돼 있지만,
        # 고정 키가 "합성" 이라는 것을 데이터에서도 읽히게 한다.
        "user_key": "u_canary",
        "session_id": None,
        "client_ip_key": None,
        "pod_name": None,
        "payload": {"emitted_at": now},
    }


def handler(event, context):
    env = _envelope()
    resp = _kinesis.put_record(
        StreamName=STREAM,
        PartitionKey=env["event_id"],
        Data=(json.dumps(env) + "\n").encode("utf-8"),
    )
    # 실패는 삼키지 않는다. 이 함수까지 조용히 실패하면 카나리를 둔 의미가
    # 없다 — Lambda 오류로 올려서 aws.lambda.errors 에 잡히게 한다.
    print(f"[canary] shard={resp['ShardId']} seq={resp['SequenceNumber'][-8:]}")
    return {"ok": True, "event_id": env["event_id"]}
