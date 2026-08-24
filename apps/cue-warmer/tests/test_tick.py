"""tick() 이 방송 하나의 문제로 나머지 방송까지 밀리지 않는지.

candidate_broadcasts() 와 warm() 을 대역으로 갈아끼운다 — DB·HTTP 없이
tick() 자체의 방송 간 격리만 본다.
"""

import warmer.main as main


def test_one_bad_body_does_not_block_others(monkeypatch):
    good = {"broadcast_id": "bc_good", "segments": []}
    bad = {"broadcast_id": "bc_bad"}  # segments 자체가 없는 깨진 body

    monkeypatch.setattr(main, "candidate_broadcasts", lambda db, now: [bad, good])

    def fake_needs_warming(body, now):
        if body is bad:
            raise TypeError("깨진 body — 실제로는 여기서 무슨 예외든 날 수 있다")
        return True

    monkeypatch.setattr(main, "needs_warming", fake_needs_warming)

    warmed_ids = []

    def fake_warm(client, broadcast_id):
        warmed_ids.append(broadcast_id)
        return True

    monkeypatch.setattr(main, "warm", fake_warm)

    warmed = main.tick(db=None, client=None)

    # bad 때문에 예외가 났어도 good 은 그대로 워밍됐어야 한다.
    assert warmed == 1
    assert warmed_ids == ["bc_good"]


def test_failed_warm_is_not_counted(monkeypatch):
    # warm() 이 403·404·네트워크 오류로 실패해도 예외를 안 던지고 False 만
    # 돌려준다 — tick() 이 그 신호를 무시하고 세면, 실패가 "이번 tick
    # 워밍: N건" INFO 로그 뒤에 영원히 숨는다.
    body = {"broadcast_id": "bc_1042", "segments": []}
    monkeypatch.setattr(main, "candidate_broadcasts", lambda db, now: [body])
    monkeypatch.setattr(main, "needs_warming", lambda b, now: True)
    monkeypatch.setattr(main, "warm", lambda client, broadcast_id: False)

    assert main.tick(db=None, client=None) == 0
