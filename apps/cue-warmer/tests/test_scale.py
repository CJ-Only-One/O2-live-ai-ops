"""파드 사전 확장과 방송 종료 후 원복.

k8s API 는 대역으로 갈아끼운다 — 실제 patch 는 클러스터에서만 확인한다
(다른 서비스 시험과 같은 결). 여기서 보는 것은 "언제 늘리고, 언제 안 늘리고,
언제 되돌리는가" 판정이다.
"""

from datetime import datetime, timedelta, timezone

import pytest

import warmer.main as main
from warmer.config import settings

AT = "2026-08-24T20:00:00+09:00"  # UTC 11:00:00
AT_UTC = datetime(2026, 8, 24, 11, 0, 0)


@pytest.fixture(autouse=True)
def _scale_on(monkeypatch):
    monkeypatch.setattr(settings, "SCALE_ENABLED", True)
    monkeypatch.setattr(settings, "SCALE_LEAD_S", 60)
    monkeypatch.setattr(settings, "MAX_REPLICAS", 6)
    monkeypatch.setattr(settings, "REVERT_COOLDOWN_S", 600)


class _FakeK8s:
    """현재 replicas 를 들고 있는 가짜 클러스터."""

    def __init__(self, state: dict[str, int]):
        self.state = state
        self.patches: list[tuple[str, int]] = []

    def get_replicas(self, ns, deployment):
        return self.state.get(deployment)

    def set_replicas(self, ns, deployment, replicas):
        self.state[deployment] = replicas
        self.patches.append((deployment, replicas))
        return True


@pytest.fixture
def fake_k8s(monkeypatch):
    def _install(state):
        fake = _FakeK8s(state)
        monkeypatch.setattr(main.k8s, "get_replicas", fake.get_replicas)
        monkeypatch.setattr(main.k8s, "set_replicas", fake.set_replicas)
        return fake

    return _install


def _body(at=AT, ends_at=None, duration_s=60, **expected):
    exp = {"concurrent": 12_000, "entry_window_s": 30, "by": "operator"}
    exp.update(expected)
    body = {
        "broadcast_id": "bc_1042",
        "segments": [{"seq": 1, "at": at, "duration_s": duration_s, "expected": exp}],
    }
    if ends_at:
        body["ends_at"] = ends_at
    return body


# ── 확장 창 ──────────────────────────────────────────────────


def test_scales_up_before_segment():
    # 12,000명 / 30초 = 400 RPS -> api 2파드
    body = _body()
    now = AT_UTC - timedelta(seconds=30)  # lead 60초 안
    assert main.desired_replicas(body, now) == {"api": 2}


def test_not_yet_in_window():
    body = _body()
    now = AT_UTC - timedelta(seconds=120)  # lead 60초보다 이전
    assert main.desired_replicas(body, now) == {}


def test_still_in_window_during_duration():
    body = _body(duration_s=60)
    now = AT_UTC + timedelta(seconds=30)
    assert main.desired_replicas(body, now) == {"api": 2}


def test_window_ends_after_duration():
    body = _body(duration_s=60)
    now = AT_UTC + timedelta(seconds=61)
    assert main.desired_replicas(body, now) == {}


def test_duration_falls_back_to_entry_window():
    # duration_s 가 없으면 entry_window_s 를 쓴다.
    body = {
        "broadcast_id": "bc_1042",
        "segments": [
            {"at": AT, "expected": {"concurrent": 12_000, "entry_window_s": 30}}
        ],
    }
    assert main.desired_replicas(body, AT_UTC + timedelta(seconds=20)) == {"api": 2}
    assert main.desired_replicas(body, AT_UTC + timedelta(seconds=40)) == {}


# ── 늘리기만 ─────────────────────────────────────────────────


def test_scales_up_when_below_target(fake_k8s):
    k = fake_k8s({"api": 1})
    body = _body()
    changed = main.reconcile_scale([body], AT_UTC - timedelta(seconds=30))
    assert changed == 1
    assert k.patches == [("api", 2)]


def test_does_not_scale_down_during_broadcast(fake_k8s):
    # 에이전트가 S2 조치로 늘려둔 상태(5) — 워머 목표(2)보다 크다.
    # 방송 중에는 되돌리지 않는다.
    k = fake_k8s({"api": 5})
    body = _body()
    changed = main.reconcile_scale([body], AT_UTC - timedelta(seconds=30))
    assert changed == 0
    assert k.patches == []


def test_idempotent_when_already_at_target(fake_k8s):
    k = fake_k8s({"api": 2})
    body = _body()
    assert main.reconcile_scale([body], AT_UTC - timedelta(seconds=30)) == 0
    assert k.patches == []


def test_max_replicas_caps_target(fake_k8s):
    # 큐시트가 과하게 적혀도 비용 상한에서 막힌다.
    k = fake_k8s({"api": 1})
    body = _body(concurrent=1_000_000, entry_window_s=1)
    main.reconcile_scale([body], AT_UTC - timedelta(seconds=30))
    assert k.patches == [("api", settings.MAX_REPLICAS)]


def test_disabled_does_nothing(fake_k8s, monkeypatch):
    monkeypatch.setattr(settings, "SCALE_ENABLED", False)
    k = fake_k8s({"api": 1})
    assert main.reconcile_scale([_body()], AT_UTC - timedelta(seconds=30)) == 0
    assert k.patches == []


def test_unreadable_current_skips_service(fake_k8s):
    # get_replicas 가 None 이면(RBAC 없음·API 오류) 그 서비스만 건너뛴다.
    k = fake_k8s({})
    assert main.reconcile_scale([_body()], AT_UTC - timedelta(seconds=30)) == 0
    assert k.patches == []


# ── 방송 종료 후 원복 ────────────────────────────────────────


def _ends(delta_s):
    return (
        datetime(2026, 8, 24, 11, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=delta_s)
    ).isoformat()


def test_reverts_after_cooldown(fake_k8s):
    k = fake_k8s({"api": 6, "chat-gateway": 4})
    body = _body(ends_at=_ends(0))
    now = AT_UTC + timedelta(seconds=601)  # cooldown 600초 지남
    changed = main.reconcile_scale([body], now)
    assert changed == 2
    assert sorted(k.patches) == [("api", 2), ("chat-gateway", 2)]


def test_does_not_revert_before_cooldown(fake_k8s):
    k = fake_k8s({"api": 6})
    body = _body(ends_at=_ends(0))
    now = AT_UTC + timedelta(seconds=300)  # 아직 cooldown 안 지남
    assert main.reconcile_scale([body], now) == 0
    assert k.patches == []


def test_revert_is_idempotent(fake_k8s):
    # 이미 baseline 이면 patch 를 안 보낸다 — 후보로 남아 있는 동안
    # 여러 tick 이 돌아도 안전해야 한다.
    k = fake_k8s({"api": 2, "chat-gateway": 2})
    body = _body(ends_at=_ends(0))
    assert main.reconcile_scale([body], AT_UTC + timedelta(seconds=601)) == 0
    assert k.patches == []


def test_no_ends_at_never_reverts(fake_k8s):
    # 언제 끝났는지 모르는 방송을 임의로 줄이지 않는다.
    k = fake_k8s({"api": 6})
    body = _body()  # ends_at 없음
    far_future = AT_UTC + timedelta(days=7)
    main.reconcile_scale([body], far_future)
    assert k.patches == []


# ── 방송이 여럿일 때 ─────────────────────────────────────────


def test_live_broadcast_blocks_revert_of_ended_one(fake_k8s):
    """끝난 방송의 원복이 진행 중인 방송의 확장을 되돌리면 안 된다.

    파드 수는 방송별이 아니라 클러스터가 공유하는 값이라, 방송마다 따로
    조정하면 매 tick 마다 한쪽이 올리고 다른 쪽이 내리기를 반복한다.
    """
    k = fake_k8s({"api": 1})
    ended = _body(ends_at=_ends(0))
    live = _body(at="2026-08-24T20:20:00+09:00")  # UTC 11:20, 지금 창 안

    now = datetime(2026, 8, 24, 11, 19, 30)  # ended 는 cooldown 지남
    main.reconcile_scale([ended, live], now)

    # live 의 요구(2)로 올라가야지 ended 의 baseline(2)으로 내려가면 안 된다.
    assert k.patches == [("api", 2)]

    # 한 번 더 돌려도 진동하지 않는다.
    k.patches.clear()
    main.reconcile_scale([ended, live], now)
    assert k.patches == []


def test_reverts_only_when_all_ended(fake_k8s):
    k = fake_k8s({"api": 6})
    ended = _body(ends_at=_ends(0))
    still_running = _body(ends_at=_ends(100_000))  # 아직 안 끝남

    now = AT_UTC + timedelta(seconds=601)
    assert main.reconcile_scale([ended, still_running], now) == 0
    assert k.patches == []


def test_no_candidates_reverts_to_baseline(fake_k8s):
    # 큐시트가 하나도 없으면 예정된 방송이 없다는 뜻이다 — baseline 이 정답.
    k = fake_k8s({"api": 5, "chat-gateway": 4})
    changed = main.reconcile_scale([], AT_UTC)
    assert changed == 2
    assert sorted(k.patches) == [("api", 2), ("chat-gateway", 2)]


def test_two_live_broadcasts_take_max(fake_k8s):
    # 같은 시각에 방송 둘이 돌면 각자 요구 중 큰 쪽을 맞춘다.
    k = fake_k8s({"api": 1})
    small = _body(concurrent=3_000, entry_window_s=30)   # 100 RPS -> 1
    big = _body(concurrent=12_000, entry_window_s=30)    # 400 RPS -> 2
    main.reconcile_scale([small, big], AT_UTC - timedelta(seconds=30))
    assert k.patches == [("api", 2)]


# ── order-worker 는 ScaledObject 를 만진다 ──────────────────


class _FakeKeda:
    """ScaledObject 의 minReplicaCount 를 들고 있는 가짜."""

    def __init__(self, mins: dict[str, int]):
        self.mins = mins
        self.patches: list[tuple[str, int]] = []

    def get_min_replicas(self, ns, name):
        return self.mins.get(name)

    def set_min_replicas(self, ns, name, replicas):
        self.mins[name] = replicas
        self.patches.append((name, replicas))
        return True


@pytest.fixture
def fake_keda(monkeypatch):
    def _install(mins):
        fake = _FakeKeda(mins)
        monkeypatch.setattr(main.k8s, "get_min_replicas", fake.get_min_replicas)
        monkeypatch.setattr(main.k8s, "set_min_replicas", fake.set_min_replicas)
        return fake

    return _install


def _sale_body(at=AT, ends_at=None, order_rate=200.0):
    return {
        "broadcast_id": "bc_1042",
        "segments": [
            {
                "seq": 1, "at": at, "duration_s": 300,
                "segment_type": "SALE_OPEN", "sku_id": "88213",
                "expected": {"order_rate": order_rate, "by": "operator"},
            }
        ],
        **({"ends_at": ends_at} if ends_at else {}),
    }


def test_order_worker_uses_scaledobject_not_deployment(fake_k8s, fake_keda):
    """Deployment 의 replicas 를 만지면 KEDA 가 다음 조절 주기에 되돌린다.
    ScaledObject 의 minReplicaCount 로 가야 한다."""
    dep = fake_k8s({"order-worker": 1})   # Deployment 쪽 — 안 건드려야 함
    keda = fake_keda({"order-worker": 1})  # ScaledObject 쪽 — 여기로 가야 함

    main.reconcile_scale([_sale_body()], AT_UTC - timedelta(seconds=30))

    assert dep.patches == []
    assert keda.patches == [("order-worker", 5)]  # 200/47 -> 5


def test_order_worker_only_raises_floor(fake_k8s, fake_keda):
    # KEDA 가 이미 큐를 보고 min 을 올려둔 상태라면 내리지 않는다.
    fake_k8s({})
    keda = fake_keda({"order-worker": 8})
    main.reconcile_scale([_sale_body()], AT_UTC - timedelta(seconds=30))
    assert keda.patches == []


def test_order_worker_reverts_to_baseline_min(fake_k8s, fake_keda):
    fake_k8s({"api": 2, "chat-gateway": 2})
    keda = fake_keda({"order-worker": 5})
    body = _sale_body(ends_at=_ends(0))
    main.reconcile_scale([body], AT_UTC + timedelta(seconds=601))
    assert keda.patches == [("order-worker", 1)]
