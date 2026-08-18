"""o2warm — Warm Path 집계 계층.

Hot(Datadog) / Warm(이 패키지) / Cold(S3) 중 가운데를 담당합니다.

    Kinesis 2 스트림 ─▶ Lambda o2-agg ─▶ DynamoDB METRIC#<service>/TS#<10초>
                                     └─▶ Datadog 커스텀 메트릭

Agent는 감지 알림을 받은 뒤 WarmClient.snapshot() 한 번으로
그 시점의 판단 재료 전부를 가져갑니다.

## 의존 관계

계산부(contract, windows, sketch, metrics, confidence, baseline)는 **표준
라이브러리만 씁니다.** 감별 로직을 로컬에서 그대로 돌려 검증할 수 있어야
하기 때문이며, 실제로 tests/ 가 AWS 없이 6개 시나리오를 재현합니다.
boto3 가 필요한 것은 store 와 client 뿐입니다.

o2events SDK 는 **런타임에 import 하지 않습니다.** 이벤트 계약은
contract.py 에 값으로 두고, 드리프트는 tests/test_contract.py 가 잡습니다.
이유는 contract.py 첫머리에 적어 두었습니다.
"""

from __future__ import annotations

from .metrics import derive
from .sketch import WindowSketch
from .windows import WINDOW_SECONDS, service_of, window_start

__version__ = "0.1.0"
__all__ = [
    "WINDOW_SECONDS",
    "WindowSketch",
    "derive",
    "service_of",
    "window_start",
]
