"""needs_warming() 의 시간 창 계산 — 이 파일에서 유일하게 틀리기 쉬운 로직.

DB·HTTP 는 여기서 안 본다(order-worker·api 의 다른 서비스 시험과 같은 결 —
실환경에서만 왕복을 확인한다). CACHE_LEAD_S 를 10초로 고정해 경계값 계산이
쉽게 검증되게 한다.
"""

from datetime import datetime, timedelta, timezone

import pytest

from warmer.config import settings
from warmer.main import needs_warming


@pytest.fixture(autouse=True)
def _lead_10s(monkeypatch):
    monkeypatch.setattr(settings, "CACHE_LEAD_S", 10)


AT = "2026-08-24T20:00:00+09:00"  # UTC 11:00:00
AT_UTC = datetime(2026, 8, 24, 11, 0, 0)


def _segment(entry_window_s=60, at=AT):
    return {"at": at, "expected": {"entry_window_s": entry_window_s, "concurrent": 1000}}


def test_no_segments():
    assert needs_warming({"segments": []}, AT_UTC) is False


def test_missing_segments_key():
    assert needs_warming({}, AT_UTC) is False


def test_segment_without_expected_is_ignored():
    body = {"segments": [{"at": AT, "what": "설명 구간"}]}
    assert needs_warming(body, AT_UTC - timedelta(seconds=5)) is False


def test_expected_without_entry_window_s_is_ignored():
    # EVENT_ANNOUNCE·SALE_CLOSING 같은, 신규 진입이 없는 세그먼트.
    body = {"segments": [{"at": AT, "expected": {"chat_rate": 8.0}}]}
    assert needs_warming(body, AT_UTC - timedelta(seconds=5)) is False


def test_well_before_window_is_false():
    body = {"segments": [_segment()]}
    now = AT_UTC - timedelta(seconds=30)  # lead=10 보다 훨씬 이전
    assert needs_warming(body, now) is False


def test_window_start_is_inclusive():
    body = {"segments": [_segment()]}
    now = AT_UTC - timedelta(seconds=10)  # lead 경계
    assert needs_warming(body, now) is True


def test_just_before_at_is_true():
    body = {"segments": [_segment()]}
    now = AT_UTC - timedelta(seconds=1)
    assert needs_warming(body, now) is True


def test_at_itself_is_true():
    # at 은 진입이 "시작되는" 시각이지 끝나는 시각이 아니다 — 그 순간에도
    # 계속 데워야 한다.
    body = {"segments": [_segment(entry_window_s=60)]}
    assert needs_warming(body, AT_UTC) is True


def test_still_warming_during_entry_window():
    # entry_window_s=60 인데 30초 지점에서 멈추면 안 된다 — 값 자체를
    # 구간 계산에 써야 하는 이유가 이 시험이다.
    body = {"segments": [_segment(entry_window_s=60)]}
    now = AT_UTC + timedelta(seconds=30)
    assert needs_warming(body, now) is True


def test_stops_exactly_when_entry_window_elapses():
    body = {"segments": [_segment(entry_window_s=60)]}
    assert needs_warming(body, AT_UTC + timedelta(seconds=59)) is True
    assert needs_warming(body, AT_UTC + timedelta(seconds=60)) is False


def test_well_after_entry_window_is_false():
    body = {"segments": [_segment(entry_window_s=60)]}
    now = AT_UTC + timedelta(seconds=120)
    assert needs_warming(body, now) is False


def test_negative_entry_window_s_is_ignored():
    # save_cue_sheet 는 이 값을 검증하지 않는다(D-065) — 스키마의
    # minimum:1 을 우회한 값이 그대로 들어올 수 있다.
    body = {"segments": [_segment(entry_window_s=-5)]}
    assert needs_warming(body, AT_UTC) is False


def test_non_numeric_entry_window_s_is_ignored():
    body = {"segments": [_segment(entry_window_s="soon")]}
    assert needs_warming(body, AT_UTC) is False


def test_one_of_several_segments_matches():
    body = {
        "segments": [
            {"at": AT, "expected": {"chat_rate": 8.0}},  # entry_window_s 없음
            _segment(at="2026-08-24T20:30:00+09:00"),  # UTC 11:30, 아직 멀었음
            _segment(at=AT),  # 이게 걸려야 한다
        ]
    }
    now = AT_UTC - timedelta(seconds=2)
    assert needs_warming(body, now) is True


def test_offsetless_timestamp_is_skipped_not_crashed():
    # save_cue_sheet() 가 저장 시점에 이미 오프셋을 강제하지만(D-065),
    # 워머는 별도 프로세스라 방어적으로 파싱한다 — 예외로 tick 전체가
    # 죽으면 안 된다.
    body = {"segments": [_segment(at="2026-08-24T20:00:00")]}
    assert needs_warming(body, AT_UTC - timedelta(seconds=5)) is False


def test_malformed_segment_does_not_crash_other_segments():
    body = {
        "segments": [
            _segment(at="not-a-timestamp"),
            _segment(at=AT),
        ]
    }
    now = AT_UTC - timedelta(seconds=2)
    assert needs_warming(body, now) is True


def test_segments_not_a_list_is_false_not_crashed():
    # save_cue_sheet() 는 세그먼트 형태를 검사하지 않는다(D-065) — DB 에서
    # 읽어온 body 가 이런 모양일 수 있다는 걸 코드 리뷰가 지적했다.
    assert needs_warming({"segments": "oops"}, AT_UTC) is False
    assert needs_warming({"segments": 5}, AT_UTC) is False
    assert needs_warming({"segments": None}, AT_UTC) is False


def test_non_dict_segment_items_are_skipped():
    body = {"segments": ["not-a-dict", 123, None, _segment(at=AT)]}
    now = AT_UTC - timedelta(seconds=2)
    assert needs_warming(body, now) is True


def test_non_dict_expected_is_ignored():
    body = {"segments": [{"at": AT, "expected": "not-a-dict"}]}
    assert needs_warming(body, AT_UTC - timedelta(seconds=2)) is False
