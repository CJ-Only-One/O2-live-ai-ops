"""이벤트 계약 드리프트 감지.

집계기는 o2events SDK 를 런타임에 import 하지 않습니다(이유는
`o2warm/contract.py` 첫머리). 대신 이 시험이 **개발 의존성으로** SDK 를
불러와, contract.py 의 모든 값이 실제 계약에 존재하는지 확인합니다.

앱 팀이 필드명을 바꾸거나 enum 을 지우면 여기서 먼저 깨집니다.
이것이 없으면 집계는 조용히 None 을 내고, Agent 는 "데이터가 정상이다"로
읽습니다. **틀린 값보다 나쁜 것이 조용히 빈 값입니다.**

SDK 가 설치돼 있지 않으면 건너뜁니다 — Lambda 배포 파이프라인은 SDK 를
필요로 하지 않으므로, 이 시험 때문에 배포가 막히면 안 됩니다.
CI 에서는 반드시 설치해 주세요.
"""

from __future__ import annotations

import inspect

import pytest
from o2warm import contract as C

o2schemas = pytest.importorskip(
    "o2events.schemas", reason="o2events 미설치 — 계약 검증을 건너뜁니다"
)
o2emit = pytest.importorskip("o2events.emit")


def test_event_names_exist_in_contract():
    unknown = C.EVENT_NAMES - o2schemas.EVENT_NAMES
    assert not unknown, f"계약에 없는 이벤트를 집계가 참조합니다: {sorted(unknown)}"


def test_contract_covers_every_published_event():
    """SDK 가 발행하는데 집계가 모르는 이벤트가 있으면 알려줍니다.

    실패해도 당장 깨지는 것은 아니지만, 새 이벤트가 추가됐는데 지표에
    반영되지 않았다는 뜻이라 확인이 필요합니다.
    """
    missing = o2schemas.EVENT_NAMES - C.EVENT_NAMES
    assert not missing, f"집계가 모르는 신규 이벤트: {sorted(missing)}"


def test_result_enums_exist():
    for enum_name in ("COUPON_RESULT", "PAYMENT_RESULT"):
        allowed = getattr(o2schemas, enum_name)
        assert C.RESULT_FAILED in allowed, f"{enum_name} 에 {C.RESULT_FAILED} 없음"
        assert C.RESULT_SUCCESS in allowed, f"{enum_name} 에 {C.RESULT_SUCCESS} 없음"


def test_click_actions_exist():
    for action in (C.ACTION_COUPON_CLICK, C.ACTION_CHECKOUT_CLICK):
        assert action in o2schemas.CLIENT_ACTION, (
            f"{action} 이 계약에서 사라졌습니다 — click_ratio 가 0 이 됩니다"
        )


@pytest.mark.parametrize("func_name,fields", sorted(C.PAYLOAD_FIELDS.items()))
def test_payload_fields_match_emit_signature(func_name, fields):
    """emit 함수 인자명이 곧 payload 키입니다.

    이름이 바뀌면 해당 지표가 조용히 None 이 됩니다.
    """
    func = getattr(o2emit, func_name, None)
    assert func is not None, f"emit.{func_name} 이 사라졌습니다"

    params = set(inspect.signature(func).parameters)
    missing = [f for f in fields if f not in params]
    assert not missing, (
        f"emit.{func_name} 에 {missing} 인자가 없습니다 — "
        f"집계가 참조하는 payload 필드입니다"
    )


def test_envelope_fields_match_sdk():
    """봉투 키 집합이 SDK 실제 출력과 어긋나면 여기서 깹니다.

    **이 시험이 없어서 실제로 한 번 놓쳤습니다.** SDK 0.3.0 이 봉투에
    `pod_name` 을 추가했는데, 이 파일의 `E_POD_NAME` 상수만 만들고
    `ENVELOPE_FIELDS` 집합에 넣지 않은 채로 아무 시험도 깨지지 않았습니다
    (`docs/troubleshooting.md` T-023).

    SDK 에는 봉투 필드 목록을 내보내는 상수가 없습니다(v0.3.1 기준). 그래서
    상수끼리 비교하지 못하고 `_envelope()` 을 직접 불러 실제 키를 봅니다 —
    위 `test_payload_fields_match_emit_signature` 가 `inspect.signature()` 로,
    `test_client_prefix_rule_matches_sdk_routing` 이 `sinks._stream_for()` 로
    하는 것과 같은 방식입니다. SDK 가 공개 상수를 내주면 그때 갈아탑니다.
    """
    actual = set(o2emit._envelope(C.EVENT_ORDER_CREATE, {"order_id": "O-1"}))

    missing = C.ENVELOPE_FIELDS - actual
    assert not missing, (
        f"집계가 참조하는데 봉투에 없는 필드: {sorted(missing)} — "
        f"해당 지표가 조용히 None 이 됩니다"
    )

    # 늘어난 쪽도 잡습니다. 빠진 필드보다 **새로 생긴 필드를 모르는 것**이
    # 실제로 우리를 문 경우였습니다 — 쓸지 말지 한 번은 정하게 만듭니다.
    unknown = actual - C.ENVELOPE_FIELDS - C.ENVELOPE_FIELDS_UNUSED
    assert not unknown, (
        f"봉투에 생겼는데 집계가 모르는 필드: {sorted(unknown)} — "
        f"쓸 것이면 ENVELOPE_FIELDS 에, 안 쓸 것이면 "
        f"ENVELOPE_FIELDS_UNUSED 에 넣으세요"
    )


def test_envelope_unused_fields_still_exist_in_sdk():
    """'안 쓴다'고 선언한 필드가 SDK 에서 사라졌으면 선언을 지워야 합니다.

    없어진 필드를 계속 예외로 두면 그 자리가 죽은 코드가 되고, 나중에 같은
    이름이 다른 뜻으로 되살아나도 시험이 안 깹니다.
    """
    actual = set(o2emit._envelope(C.EVENT_ORDER_CREATE, {"order_id": "O-1"}))

    stale = C.ENVELOPE_FIELDS_UNUSED - actual
    assert not stale, f"SDK 봉투에 없는데 예외로 남아 있는 필드: {sorted(stale)}"


def test_client_prefix_rule_matches_sdk_routing():
    """어떤 이벤트가 클라이언트 스트림으로 가는지에 대한 판단이 양쪽에서
    같아야 합니다. 어긋나면 클릭이 비즈니스 윈도우로 새거나 그 반대가 됩니다.
    """
    from o2events import sinks

    for name in o2schemas.EVENT_NAMES:
        env = {"event_name": name, "payload": {}}
        sdk_says_client = sinks._stream_for(env) == sinks.config.stream_client
        warm_says_client = name.startswith(C.CLIENT_PREFIXES)
        assert sdk_says_client == warm_says_client, (
            f"{name} 의 스트림 판정이 SDK 와 집계에서 다릅니다"
        )
