"""예상 부하 → 목표 파드 수 변환.

분모(API_RPS_PER_POD·CHAT_ITEMS_PER_POD)는 실측값이라 여기서 다시 검증하지
않는다. 이 파일이 보는 것은 나눗셈과 올림, 그리고 값이 없을 때 조용히 0 을
만들지 않고 None 을 돌려주는지다.
"""

from warmer import capacity


def test_api_pods_uses_density_not_headcount():
    # 같은 12,000명이어도 진입 창이 다르면 필요한 파드 수가 다르다.
    # 30초에 몰리면 400 RPS -> 300 으로 나눠 올림 = 2
    assert capacity.api_pods(12_000, 30) == 2
    # 5분에 걸치면 40 RPS = 1
    assert capacity.api_pods(12_000, 300) == 1


def test_api_pods_rounds_up():
    # 301 RPS 는 파드 하나로 못 받는다 — 내림하면 포화 상태로 둔다.
    assert capacity.api_pods(301, 1) == 2


def test_api_pods_needs_both_values():
    assert capacity.api_pods(12_000, None) is None
    assert capacity.api_pods(None, 30) is None
    # 0 은 계산이 안 되는 값이다(0으로 나누기). None 과 같이 취급한다.
    assert capacity.api_pods(12_000, 0) is None


def test_chat_pods_multiplies():
    # 팬아웃 총량 = 시청자 x 채팅율. 4,000 x 10 = 40,000 items/s
    # 파드당 10,000 이므로 4파드.
    assert capacity.chat_pods(4_000, 10.0) == 4
    # 같은 인원이어도 채팅율이 낮으면 적게 든다.
    assert capacity.chat_pods(4_000, 2.0) == 1


def test_chat_pods_needs_both_values():
    assert capacity.chat_pods(4_000, None) is None
    assert capacity.chat_pods(None, 3.0) is None


def test_targets_omits_uncomputable_services():
    # entry_window_s 가 없으면 api 는 계산이 안 된다 — 키 자체가 없어야 한다.
    # 0 을 넣으면 호출자가 "0개로 줄이라" 로 읽는다.
    out = capacity.targets({"concurrent": 4_000, "chat_rate": 10.0})
    assert "api" not in out
    assert out["chat-gateway"] == 4


def test_targets_empty_expected():
    assert capacity.targets({}) == {}


def test_targets_both_services():
    out = capacity.targets(
        {"concurrent": 12_000, "entry_window_s": 30, "chat_rate": 5.0}
    )
    assert out == {"api": 2, "chat-gateway": 6}


def test_merge_takes_max_not_sum():
    # 방송 시작과 게스트 등장이 같은 시각이어도 시청자는 한 무리다.
    # 합치면 같은 인원을 두 번 세게 된다.
    a = {"api": 2, "chat-gateway": 1}
    b = {"api": 1, "chat-gateway": 6}
    assert capacity.merge(a, b) == {"api": 2, "chat-gateway": 6}


def test_merge_keeps_service_only_in_one_side():
    assert capacity.merge({"api": 2}, {"chat-gateway": 3}) == {
        "api": 2,
        "chat-gateway": 3,
    }
