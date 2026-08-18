"""이벤트 계약 드리프트 감지.

`test_client_events.py` 는 SDK 대역으로도 돌기 때문에, 그것만으로는 계약이
바뀐 것을 못 잡는다 — 대역은 무엇을 넘겨도 받아준다. 이 파일이 나머지 절반이다.

SDK 가 없으면 통째로 건너뛴다. CI 의 테스트 스텝에는 비공개 저장소 토큰이 없어
설치되지 않지만, 이미지 안(=실제로 도는 곳)에서는 설치돼 있다. 배포 전에
`kubectl exec ... pytest` 로 한 번 돌리면 여기가 진짜 계약을 본다.
"""

import inspect
from typing import get_args

import pytest

from app.schemas.client_event import ClientAction
from app.services.client_event import device_type_of

o2schemas = pytest.importorskip(
    "o2events.schemas", reason="o2events 미설치 — 계약 검증을 건너뜁니다"
)
o2emit = pytest.importorskip("o2events.emit")
o2sinks = pytest.importorskip("o2events.sinks")


def test_our_actions_match_the_contract():
    """계약에 없는 값을 받으면 SDK 가 SchemaError 를 내고 그 이벤트만 사라진다."""
    ours = set(get_args(ClientAction))
    assert ours == o2schemas.CLIENT_ACTION, (
        f"우리만 아는 값: {sorted(ours - o2schemas.CLIENT_ACTION)} / "
        f"계약에만 있는 값: {sorted(o2schemas.CLIENT_ACTION - ours)}"
    )


def test_device_types_are_in_the_contract():
    produced = {
        device_type_of(ua)
        for ua in (None, "", "Android 14 Mobile", "Macintosh; Intel Mac OS X")
    }
    assert produced <= o2schemas.DEVICE_TYPE


def test_emit_accepts_the_arguments_we_pass():
    """인자 이름이 바뀌면 TypeError 로 죽는다 — 우리는 그것을 삼키므로
    (services/client_event.py) 이벤트만 조용히 사라진다."""
    params = set(inspect.signature(o2emit.client_action).parameters)
    assert {"action", "target_id", "device_type", "ua_key"} <= params


def test_client_events_are_routed_to_the_client_stream():
    """이 엔드포인트의 존재 이유. `client.` 접두사가 목적지를 정한다."""
    stream = o2sinks._stream_for({"event_name": "client.action"})
    # sinks 가 들고 있는 설정 인스턴스를 그대로 본다. o2events.config 는
    # 패키지가 같은 이름의 인스턴스로 가려 놓아 모듈로 접근하면 헷갈린다.
    assert stream == o2sinks.config.stream_client
    assert stream != o2sinks.config.stream_business
