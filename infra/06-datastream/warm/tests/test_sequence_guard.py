"""샤드 sequence number 가드의 전제를 고정합니다.

`WindowSketch.already_applied()` 는 샤드별 **최댓값 하나**로 재시도를
걸러냅니다. 이 방식은 "한 샤드를 한 번에 하나씩 처리한다" 를 전제하는데,
그 전제는 Terraform 쪽 설정(`parallelization_factor`)에 달려 있습니다.

**전제가 깨지면 예외가 아니라 건수가 줄어듭니다.** 집계가 조용히 틀리는
가장 나쁜 모양이라, 그 성질을 시험으로 못 박아 둡니다. 누군가 지연을
줄이려고 `parallelization_factor` 를 올릴 때 이 파일이 왜 안 되는지를
설명해 주는 것이 목적입니다.

근거·결정은 D-058.
"""

from __future__ import annotations

import factory
from o2warm.sketch import WindowSketch, build
from o2warm.windows import window_start

W = window_start(factory.BASE)
SHARD_A = "stream-business:shardId-000000000000"
SHARD_B = "stream-business:shardId-000000000001"


def _batch(source, seq_hi, n, tag):
    """한 Lambda 호출이 만든 부분 집계 하나."""
    events = [
        factory.order_create(factory.BASE + i, f"{tag}{i}", "1.1.1.1", latency=50)
        for i in range(n)
    ]
    s = build("order-api", W, events)
    s.note_source(source, seq_hi)
    return s


def test_sequential_batches_all_land():
    """순차 처리(parallelization_factor = 1) — 지금 설정이다."""
    acc = WindowSketch("order-api", W)
    acc.merge(_batch(SHARD_A, "100", 10, "a"))
    acc.merge(_batch(SHARD_A, "200", 10, "b"))

    assert acc.n == 20


def test_retry_of_the_same_batch_is_dropped():
    """같은 배치가 두 번 오면 한 번만 세야 한다 — 가드의 본래 목적."""
    acc = WindowSketch("order-api", W)
    acc.merge(_batch(SHARD_A, "100", 10, "a"))
    acc.merge(_batch(SHARD_A, "100", 10, "a"))

    assert acc.n == 10


def test_out_of_order_batch_on_the_same_shard_is_silently_lost():
    """**이 시험은 결함을 고정한 것이 아니라 제약을 고정한 것이다.**

    같은 샤드의 배치가 뒤바뀌어 도착하면 앞선 배치가 통째로 버려진다.
    가드가 최댓값 하나만 들고 있어 재시도와 구분할 수 없기 때문이다.

    이 동작을 고치려면 번호를 구간이나 집합으로 들어야 하는데, 그러면
    저장 형식이 바뀌고 마이그레이션이 필요하다. 그래서 **고치는 대신
    이 상황을 만들지 않는 쪽**을 택했다 — parallelization_factor 를 1로
    두고, 지연은 샤드 수로 푼다(D-058).

    이 시험이 깨진다면 누군가 가드를 고쳤다는 뜻이고, 그때는 D-058 의
    제약도 같이 풀렸는지 확인해야 한다.
    """
    acc = WindowSketch("order-api", W)
    acc.merge(_batch(SHARD_A, "200", 10, "b"))   # 나중 배치가 먼저 끝남
    acc.merge(_batch(SHARD_A, "100", 10, "a"))   # 앞선 배치가 뒤늦게 도착

    assert acc.n == 10, "순서가 뒤바뀌면 10건이 유실된다 — 이것이 제약이다"


def test_different_shards_are_independent():
    """샤드가 다르면 순서와 무관하게 전부 남는다 — 샤드 수로 푸는 근거."""
    for order in ((SHARD_A, SHARD_B), (SHARD_B, SHARD_A)):
        acc = WindowSketch("order-api", W)
        acc.merge(_batch(order[0], "200", 10, "x"))
        acc.merge(_batch(order[1], "100", 10, "y"))

        assert acc.n == 20, order


def test_out_of_order_drop_is_reported_to_stderr(capsys):
    """조용히 버리지는 않는다.

    되돌릴 방법은 없지만, 최소한 CloudWatch 로그에 흔적이 남아야
    "왜 건수가 줄었지" 를 추적할 수 있다.
    """
    acc = WindowSketch("order-api", W)
    acc.merge(_batch(SHARD_A, "200", 10, "b"))
    capsys.readouterr()

    acc.merge(_batch(SHARD_A, "100", 10, "a"))
    err = capsys.readouterr().err

    assert "순서가 뒤바뀐 배치" in err
    assert "parallelization_factor" in err


def test_plain_retry_does_not_warn(capsys):
    """재시도는 정상이므로 경고를 내면 안 된다 — 로그가 쓸모없어진다."""
    acc = WindowSketch("order-api", W)
    acc.merge(_batch(SHARD_A, "100", 10, "a"))
    capsys.readouterr()

    acc.merge(_batch(SHARD_A, "100", 10, "a"))
    err = capsys.readouterr().err

    assert err == ""
