"""병합 가능한 부분 집계.

## 왜 '병합 가능'이어야 하는가

Lambda 배치(batch — Kinesis 가 한 번에 넘겨주는 레코드 묶음) 경계와
10초 윈도우는 일치하지 않습니다. 게다가 같은 윈도우에 비즈니스 스트림과
클라이언트 스트림이 **서로 다른 호출로** 도착합니다.
그래서 배치마다 완성된 지표를 만들 수 없고, 대신 배치 단위 부분 집계를
만들어 DynamoDB에서 합칩니다.

병합이 성립하려면 모든 통계량이 결합법칙을 만족해야 합니다. 평균이나
표준편차를 그대로 들고 다닐 수 없고 합·제곱합 형태로 보관하는 이유입니다.

## 상한이 있는 이유

user_key 는 고카디널리티라 전부 담으면 아이템 400KB를 넘깁니다.
- 상위 기여자: Space-Saving — 잘려도 **큰 것은 살아남습니다.**
- 고유 개수: 적응 표본추출 — 잘려도 **추정값이 편향되지 않습니다.**

두 구조 모두 잘림 사실을 기록하고, 그것이 confidence.completeness 로
Agent에게 전달됩니다. 조용히 부정확해지는 것이 가장 나쁩니다.
"""

from __future__ import annotations

import hashlib
import math
import sys
from typing import Any

from . import contract as C
from .settings import settings
from .windows import event_epoch, is_client

PG_BUCKETS = 20  # pg_latency / total_latency 히스토그램 해상도


def _h64(key: str) -> int:
    return int.from_bytes(hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest(), "big")


def _median(pairs: list[tuple[float, int]]) -> float | None:
    """가중 중앙값. weight 를 전부 1로 주면 보통의 중앙값입니다."""
    if not pairs:
        return None
    pairs = sorted(pairs)
    half = sum(w for _, w in pairs) / 2
    acc = 0
    for value, w in pairs:
        acc += w
        if acc >= half:
            return value
    return pairs[-1][0]


# ---------------------------------------------------------------- 상위 기여자

class SpaceSaving:
    """상한이 있는 상위 K 카운터.

    자리가 없으면 가장 작은 항목을 쫓아내고 그 카운트를 새 항목이 물려받습니다.
    이 상속 때문에 상위 항목의 카운트는 과소평가되지 않습니다 —
    top1pct_share 처럼 '큰 쪽'만 보는 지표에 정확히 맞는 성질입니다.
    """

    __slots__ = ("capacity", "counts", "total", "evictions")

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.counts: dict[str, int] = {}
        self.total = 0
        self.evictions = 0

    def add(self, key: str, count: int = 1) -> None:
        self.total += count
        if key in self.counts:
            self.counts[key] += count
            return
        if len(self.counts) < self.capacity:
            self.counts[key] = count
            return
        victim = min(self.counts, key=self.counts.__getitem__)
        inherited = self.counts.pop(victim)
        self.counts[key] = inherited + count
        self.evictions += 1

    def merge(self, other: "SpaceSaving") -> "SpaceSaving":
        self.evictions += other.evictions
        base_total = self.total
        for k, v in other.counts.items():
            self.add(k, v)
        # add() 가 올린 total 을 되돌리고 정확한 합으로 덮습니다.
        # other 의 total 에는 쫓겨난 항목의 몫도 들어 있기 때문입니다.
        self.total = base_total + other.total
        return self

    def top(self, n: int) -> list[tuple[str, int]]:
        return sorted(self.counts.items(), key=lambda kv: -kv[1])[:n]

    @property
    def truncated(self) -> bool:
        return self.evictions > 0

    def to_dict(self) -> dict:
        return {"c": self.counts, "t": self.total, "e": self.evictions}

    @classmethod
    def from_dict(cls, d: dict, capacity: int) -> "SpaceSaving":
        s = cls(capacity)
        s.counts = dict(d.get("c") or {})
        s.total = int(d.get("t") or 0)
        s.evictions = int(d.get("e") or 0)
        return s


# ---------------------------------------------------------------- 고유 개수

class DistinctCounter:
    """적응 표본추출 기반 고유 개수 추정.

    해시가 임계값 아래인 키만 보관하고, 가득 차면 임계값을 절반으로 내리며
    솎아냅니다. 보관 비율이 2^-level 이므로 추정값은 |보관| * 2^level 입니다.

    상한 안에서 동작하면서도 병합이 되는 것이 핵심입니다. 두 부분 집계를
    합칠 때는 더 낮은 임계값 기준으로 맞추면 그만입니다.
    """

    __slots__ = ("capacity", "level", "keys")

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.level = 0
        self.keys: set[str] = set()

    def _keep(self, key: str) -> bool:
        return _h64(key) < (1 << (64 - self.level))

    def add(self, key: str) -> None:
        if not self._keep(key):
            return
        self.keys.add(key)
        self._shrink()

    def _shrink(self) -> None:
        while len(self.keys) > self.capacity:
            self.level += 1
            self.keys = {k for k in self.keys if self._keep(k)}

    def merge(self, other: "DistinctCounter") -> "DistinctCounter":
        self.level = max(self.level, other.level)
        self.keys = {k for k in (self.keys | other.keys) if self._keep(k)}
        self._shrink()
        return self

    def estimate(self) -> int:
        return len(self.keys) << self.level

    @property
    def approximate(self) -> bool:
        return self.level > 0

    def to_dict(self) -> dict:
        return {"l": self.level, "k": sorted(self.keys)}

    @classmethod
    def from_dict(cls, d: dict, capacity: int) -> "DistinctCounter":
        c = cls(capacity)
        c.level = int(d.get("l") or 0)
        c.keys = set(d.get("k") or ())
        return c


# ---------------------------------------------------------------- 요청 간격

class IntervalStats:
    """user_key 별 요청 간격의 변동계수(CV).

    사람은 간격이 들쭉날쭉하고 매크로는 일정합니다. 그래서 CV 가 낮으면
    매크로 신호입니다. 단일 지표로는 결론이 안 나지만 트래픽 폭증과
    매크로를 가르는 두 축 중 하나입니다.

    사용자별로 (첫 시각, 마지막 시각, 건수, 간격합, 간격제곱합)만 들고 다닙니다.
    부분 집계를 합칠 때 **경계에서 끊긴 간격 하나**를 이어 붙여야 하는데,
    첫 시각과 마지막 시각을 보관하는 이유가 그것입니다.
    """

    __slots__ = ("capacity", "u", "dropped")

    def __init__(self, capacity: int):
        self.capacity = capacity
        # key -> [first, last, count, sum_diff, sumsq_diff]
        self.u: dict[str, list[float]] = {}
        self.dropped = 0

    def add(self, key: str, ts: float) -> None:
        rec = self.u.get(key)
        if rec is None:
            if len(self.u) >= self.capacity:
                self.dropped += 1
                return
            self.u[key] = [ts, ts, 1, 0.0, 0.0]
            return
        # 샤드 안에서는 순서가 보장되지만 두 스트림이 섞이면 역전될 수 있어
        # 절댓값으로 처리합니다.
        d = abs(ts - rec[1])
        rec[1] = max(rec[1], ts)
        rec[0] = min(rec[0], ts)
        rec[2] += 1
        rec[3] += d
        rec[4] += d * d

    def merge(self, other: "IntervalStats") -> "IntervalStats":
        self.dropped += other.dropped
        for k, o in other.u.items():
            mine = self.u.get(k)
            if mine is None:
                if len(self.u) >= self.capacity:
                    self.dropped += 1
                    continue
                self.u[k] = list(o)
                continue
            early, late = (mine, o) if mine[0] <= o[0] else (o, mine)
            seam = max(0.0, late[0] - early[1])  # 경계에서 끊긴 간격 하나
            self.u[k] = [
                early[0],
                max(mine[1], o[1]),
                mine[2] + o[2],
                mine[3] + o[3] + seam,
                mine[4] + o[4] + seam * seam,
            ]
        return self

    def samples(self, min_events: int = 3) -> list[tuple[str, float, int]]:
        """(user_key, CV, 간격 수). 간격이 2개 이상이어야 산포를 말할 수 있습니다."""
        out = []
        for key, (_f, _l, c, s, q) in self.u.items():
            n = c - 1
            if c < min_events or n <= 1 or s <= 0:
                continue
            mean = s / n
            var = max(0.0, q / n - mean * mean)
            out.append((key, math.sqrt(var) / mean, n))
        return out

    def cv_median(self, min_events: int = 3) -> tuple[float | None, int]:
        """계정 하나를 한 표로 세는 중앙값.

        문서(§3)의 정의 그대로입니다. 다만 **이 값만으로는 매크로가 잡히지
        않습니다** — 매크로는 요청의 다수를 차지하면서 계정 수로는 소수라,
        중앙값은 배경의 정상 사용자를 가리킵니다. 참고용으로만 둡니다.
        """
        s = self.samples(min_events)
        return (_median([(cv, 1) for _, cv, _ in s]), len(s))

    def cv_weighted_median(self, min_events: int = 3) -> tuple[float | None, int]:
        """요청 수로 가중한 중앙값 — 매크로 감별에 실제로 쓰는 값.

        "이 서비스에 들어온 **요청들**이 얼마나 규칙적이었는가"를 묻습니다.
        소수 계정이 대량으로 두드리면 가중치가 그쪽으로 쏠려 값이 내려갑니다.
        """
        s = self.samples(min_events)
        return (_median([(cv, w) for _, cv, w in s]), len(s))

    def cv_of(self, keys: set[str], min_events: int = 3) -> tuple[float | None, int]:
        """지정한 계정들만의 CV 중앙값.

        top1pct_share 가 지목한 상위 기여 계정에 이것을 적용하면
        "가장 많이 때린 계정들이 기계적으로 규칙적인가"에 바로 답합니다.
        """
        s = [(cv, 1) for k, cv, _ in self.samples(min_events) if k in keys]
        return (_median(s), len(s))

    def to_dict(self) -> dict:
        return {"u": {k: [round(v[0], 3), round(v[1], 3), v[2], round(v[3], 4), round(v[4], 4)]
                      for k, v in self.u.items()},
                "d": self.dropped}

    @classmethod
    def from_dict(cls, d: dict, capacity: int) -> "IntervalStats":
        s = cls(capacity)
        s.u = {k: [float(v[0]), float(v[1]), int(v[2]), float(v[3]), float(v[4])]
               for k, v in (d.get("u") or {}).items()}
        s.dropped = int(d.get("d") or 0)
        return s


# ---------------------------------------------------------------- 히스토그램

class LogHistogram:
    """로그 스케일 히스토그램 — 지연 분포용 (DDSketch 축약형).

    지연은 상한이 없어서 [0,1] 고정 버킷을 못 씁니다. 대신 **상대 오차가
    일정한** 로그 버킷을 씁니다. 87ms 든 8700ms 든 같은 비율의 오차를
    갖는 것이 지연 분석에 맞습니다.

    p95 를 보는 것이 핵심입니다. **사용자 경험 저하는 평균이 아니라
    꼬리에서 먼저 나타납니다.** p50 이 멀쩡한 채 p95 만 무너지는 상황이
    "지표는 정상인데 체감이 나쁜" 전형입니다.
    """

    GAMMA = 1.15  # 상대 오차 약 7%. 감지 임계에는 충분합니다.
    _LOG_GAMMA = math.log(GAMMA)

    __slots__ = ("b", "n", "zero")

    def __init__(self):
        self.b: dict[int, int] = {}  # 희소 저장 — 실제로 쓰이는 버킷만
        self.n = 0
        self.zero = 0

    def add(self, value: float) -> None:
        self.n += 1
        if value <= 0:
            self.zero += 1
            return
        i = int(math.ceil(math.log(value) / self._LOG_GAMMA))
        self.b[i] = self.b.get(i, 0) + 1

    def merge(self, other: "LogHistogram") -> "LogHistogram":
        for i, c in other.b.items():
            self.b[i] = self.b.get(i, 0) + c
        self.n += other.n
        self.zero += other.zero
        return self

    def quantile(self, q: float) -> float | None:
        if self.n == 0:
            return None
        target = q * self.n
        if self.zero >= target:
            return 0.0
        seen = self.zero
        for i in sorted(self.b):
            seen += self.b[i]
            if seen >= target:
                return round(self.GAMMA**i, 2)
        return round(self.GAMMA ** max(self.b), 2)

    def to_dict(self) -> dict:
        return {"b": {str(k): v for k, v in self.b.items()}, "n": self.n, "z": self.zero}

    @classmethod
    def from_dict(cls, d: dict) -> "LogHistogram":
        h = cls()
        h.b = {int(k): int(v) for k, v in (d.get("b") or {}).items()}
        h.n = int(d.get("n") or 0)
        h.zero = int(d.get("z") or 0)
        return h


class SegmentStats:
    """축별·값별 시도/실패 카운터.

    "평균은 멀쩡한데 특정 구간만 죽는" 상황을 잡습니다. 전체 실패율 3%가
    사실 캠페인 하나에서 95%, 나머지에서 0%인 경우 — 전체 값만 보면
    임계에 걸리지 않습니다.

    축별 값 수에 상한을 둡니다. campaign_id 처럼 늘어날 수 있는 축이
    아이템을 키우면 안 되기 때문입니다. 넘치면 버리고 세어 둡니다.
    """

    __slots__ = ("capacity", "axes", "dropped")

    def __init__(self, capacity: int = 24):
        self.capacity = capacity
        # axis -> value -> [n, failed]
        self.axes: dict[str, dict[str, list[int]]] = {}
        self.dropped = 0

    def add(self, axis: str, value: str, failed: bool) -> None:
        values = self.axes.setdefault(axis, {})
        rec = values.get(value)
        if rec is None:
            if len(values) >= self.capacity:
                self.dropped += 1
                return
            rec = values[value] = [0, 0]
        rec[0] += 1
        if failed:
            rec[1] += 1

    def merge(self, other: "SegmentStats") -> "SegmentStats":
        self.dropped += other.dropped
        for axis, values in other.axes.items():
            mine = self.axes.setdefault(axis, {})
            for value, (n, f) in values.items():
                rec = mine.get(value)
                if rec is None:
                    if len(mine) >= self.capacity:
                        self.dropped += 1
                        continue
                    rec = mine[value] = [0, 0]
                rec[0] += n
                rec[1] += f
        return self

    def to_dict(self) -> dict:
        return {"a": {k: {v: list(c) for v, c in vals.items()}
                      for k, vals in self.axes.items()},
                "d": self.dropped}

    @classmethod
    def from_dict(cls, d: dict, capacity: int = 24) -> "SegmentStats":
        s = cls(capacity)
        s.axes = {k: {v: [int(c[0]), int(c[1])] for v, c in vals.items()}
                  for k, vals in (d.get("a") or {}).items()}
        s.dropped = int(d.get("d") or 0)
        return s


class Histogram:
    """[0, 1] 고정 버킷 히스토그램. 중앙값을 병합 가능하게 얻으려는 용도입니다.

    개별 값을 다 들고 있으면 정확하지만 병합이 안 되고 아이템이 커집니다.
    pg_latency_ratio 는 '0.1인가 0.9인가' 수준의 구분이면 충분합니다.
    """

    __slots__ = ("buckets", "count")

    def __init__(self, n: int = PG_BUCKETS):
        self.buckets = [0] * (n + 1)  # 마지막 칸은 1.0 초과분
        self.count = 0

    def add(self, value: float) -> None:
        n = len(self.buckets) - 1
        idx = n if value >= 1.0 else max(0, int(value * n))
        self.buckets[idx] += 1
        self.count += 1

    def merge(self, other: "Histogram") -> "Histogram":
        self.buckets = [a + b for a, b in zip(self.buckets, other.buckets)]
        self.count += other.count
        return self

    def quantile(self, q: float) -> float | None:
        if self.count == 0:
            return None
        n = len(self.buckets) - 1
        target = q * self.count
        seen = 0
        for i, c in enumerate(self.buckets):
            if seen + c >= target:
                if i >= n:
                    return 1.0
                frac = (target - seen) / c if c else 0.0
                return round((i + frac) / n, 4)
            seen += c
        return 1.0

    def to_dict(self) -> dict:
        return {"b": self.buckets, "n": self.count}

    @classmethod
    def from_dict(cls, d: dict) -> "Histogram":
        h = cls(len(d.get("b") or [0] * (PG_BUCKETS + 1)) - 1)
        h.buckets = list(d.get("b") or h.buckets)
        h.count = int(d.get("n") or 0)
        return h


# ---------------------------------------------------------------- 윈도우 집계

class WindowSketch:
    """한 (service, 10초 윈도우) 의 부분 집계.

    add() 로 이벤트를 쌓고, merge() 로 다른 부분 집계와 합칩니다.
    merge 는 other 를 변경하지 않습니다 — DynamoDB 낙관적 잠금이 실패하면
    같은 부분 집계로 재시도해야 하기 때문입니다.
    """

    def __init__(self, service: str, window_start: int):
        self.service = service
        self.window_start = int(window_start)

        self.n = 0
        self.n_business = 0
        self.n_client = 0
        self.by_event: dict[str, int] = {}

        self.users = SpaceSaving(settings.user_capacity)
        self.distinct_users = DistinctCounter(settings.distinct_capacity)
        self.distinct_ua = DistinctCounter(settings.distinct_capacity)
        self.distinct_ip = DistinctCounter(settings.distinct_capacity)
        self.intervals = IntervalStats(settings.interval_capacity)

        self.cache_hit = 0
        self.cache_miss = 0
        # 파드별 캐시 히트/미스. 무효화 유실이 파드 하나에만 나는 장애는
        # service 단위 평균에 묻힌다(파드 3개 중 1개만 고장이어도 평균 75%는
        # 멀쩡해 보인다) — pod_name 축이 있어야만 그 파드 하나만 잡아낼 수
        # 있다. pod_name 은 K8s 가 정하는 축이라(사용자 입력이 아니다)
        # SegmentStats 처럼 상한을 두지 않는다 — 파드 수는 원래 작다.
        self.cache_hit_by_pod: dict[str, int] = {}
        self.cache_miss_by_pod: dict[str, int] = {}

        # "event_name|CODE" 형태로 눌러 담습니다. 중첩 맵은 병합만 번거롭습니다.
        self.results: dict[str, int] = {}
        self.failures: dict[str, int] = {}
        self.clicks: dict[str, int] = {}
        self.versions: dict[str, list[int]] = {}  # ver -> [n, fail]

        self.pg_ratio = Histogram()
        self.ua_events = 0  # ua_key 를 실을 수 있는 이벤트 수 (분모)

        # --- 사용자 경험 저하 신호 ---
        # 전부 "응답은 200인데 체감은 나쁜" 상황에서만 움직입니다.
        self.latency = LogHistogram()
        # 파드별 지연 분포. cache_hit_by_pod 와 같은 이유다 — 파드 3개 중
        # 하나만 느려도 service 단위 p95 는 나머지 둘에 희석돼 임계 안에
        # 머문다. 그 하나를 집어내려면 pod_name 축이 있어야 한다.
        #
        # 카운터가 아니라 히스토그램을 파드 수만큼 든다. LogHistogram 은
        # 희소 dict 라 실제로 쓰인 버킷만 남고(파드당 수십 개 정수),
        # pod_name 은 K8s 가 정하는 축이라 파드 수가 원래 작다.
        self.latency_by_pod: dict[str, LogHistogram] = {}
        self.retry_events = 0      # is_retry=true 또는 retry_count>0
        self.retry_sum = 0         # retry_count 합
        self.retry_base = 0        # 재시도 여부를 실을 수 있는 이벤트 수 (분모)
        self.fallback_used = 0
        self.cancel_reasons: dict[str, int] = {}
        self.cancel_by: dict[str, int] = {}
        self.segments = SegmentStats(settings.segment_capacity)

        self.first_ts: float | None = None
        self.last_ts: float | None = None

        # 이 윈도우에 이미 반영한 (스트림:샤드) 별 최대 sequence number.
        # Kinesis 재시도로 같은 배치가 두 번 오면 이중 집계되므로 필요합니다.
        self.seq: dict[str, str] = {}

    # ------------------------------------------------------------ 적재
    def add(self, env: dict) -> None:
        name = str(env.get(C.E_EVENT_NAME) or "unknown")
        payload = env.get(C.E_PAYLOAD) or {}
        ts = event_epoch(env)
        client = is_client(env)

        self.n += 1
        self.by_event[name] = self.by_event.get(name, 0) + 1
        if client:
            self.n_client += 1
        else:
            self.n_business += 1

        self.first_ts = ts if self.first_ts is None else min(self.first_ts, ts)
        self.last_ts = ts if self.last_ts is None else max(self.last_ts, ts)

        user = env.get(C.E_USER_KEY)
        if user:
            self.users.add(user)
            self.distinct_users.add(user)
            # 간격은 서버 도착 시각 기준입니다. 클라이언트가 보낸 시각을
            # 쓰면 매크로가 그 값을 흔들어 감별을 피할 수 있습니다.
            self.intervals.add(user, ts)

        ip = env.get(C.E_CLIENT_IP_KEY)
        if ip:
            self.distinct_ip.add(ip)

        version = env.get(C.E_SERVICE_VERSION)
        if version and not client:
            v = self.versions.setdefault(version, [0, 0])
            v[0] += 1

        if client:
            self._add_client(payload)
        else:
            self._add_business(name, payload, version, env.get(C.E_POD_NAME))

        self._add_segments(payload, env, payload.get(C.F_RESULT) == C.RESULT_FAILED)

    def _add_segments(self, payload: dict, env: dict, failed: bool) -> None:
        """세그먼트 축별로 시도·실패를 나눠 셉니다.

        축마다 값이 있을 때만 셉니다. 없는 축은 분모에도 안 들어가야
        "이 축에서는 판단 불가"와 "이 축은 정상"이 구분됩니다.
        """
        for axis, origin in settings.segment_axes:
            value = payload.get(axis) if origin == "payload" else env.get(axis)
            if value:
                self.segments.add(axis, str(value), failed)

    def _add_client(self, payload: dict) -> None:
        action = payload.get(C.F_ACTION)
        if action:
            self.clicks[action] = self.clicks.get(action, 0) + 1
        ua = payload.get(C.F_UA_KEY)
        self.ua_events += 1
        if ua:
            self.distinct_ua.add(ua)

    def _add_business(self, name: str, payload: dict, version: str | None, pod_name: str | None = None) -> None:
        result = payload.get(C.F_RESULT)
        if result:
            self.results[f"{name}|{result}"] = self.results.get(f"{name}|{result}", 0) + 1

        code = payload.get(C.F_FAILURE_CODE)
        if code:
            key = f"{name}|{code}"
            self.failures[key] = self.failures.get(key, 0) + 1

        if result == C.RESULT_FAILED and version:
            self.versions.setdefault(version, [0, 0])[1] += 1

        # 응답 지연. 성공하면서 느려지는 것이 가장 잡기 어려운 저하입니다.
        latency = payload.get(C.F_LATENCY)
        if isinstance(latency, (int, float)):
            self.latency.add(latency)
            if pod_name:
                self.latency_by_pod.setdefault(pod_name, LogHistogram()).add(latency)

        # 재시도. 사용자가 같은 동작을 반복한다는 것은 그 자체로
        # 체감이 나빴다는 신호입니다. 서버는 매번 성공했을 수 있습니다.
        if C.F_IS_RETRY in payload or C.F_RETRY_COUNT in payload:
            self.retry_base += 1
            count = payload.get(C.F_RETRY_COUNT)
            if payload.get(C.F_IS_RETRY) is True or (isinstance(count, int) and count > 0):
                self.retry_events += 1
            if isinstance(count, int):
                self.retry_sum += count

        if name == C.EVENT_INVENTORY:
            hit = payload.get(C.F_CACHE_HIT)
            if hit is True:
                self.cache_hit += 1
                if pod_name:
                    self.cache_hit_by_pod[pod_name] = self.cache_hit_by_pod.get(pod_name, 0) + 1
            elif hit is False:
                self.cache_miss += 1
                if pod_name:
                    self.cache_miss_by_pod[pod_name] = self.cache_miss_by_pod.get(pod_name, 0) + 1
            # 폴백은 '성공했지만 정상 경로가 아니었다'는 뜻입니다.
            # 결과가 SUCCESS 라 실패율에는 전혀 안 잡힙니다.
            if payload.get(C.F_FALLBACK_USED) is True:
                self.fallback_used += 1

        if name == C.EVENT_ORDER_CANCEL:
            # 취소는 비동기·사후에 일어나 요청 시점 신호가 없습니다.
            # 사유 없이는 '취소가 늘었다'까지만 알 수 있습니다.
            reason = payload.get(C.F_REASON_CODE)
            if reason:
                self.cancel_reasons[reason] = self.cancel_reasons.get(reason, 0) + 1
            by = payload.get(C.F_CANCELLED_BY)
            if by:
                self.cancel_by[by] = self.cancel_by.get(by, 0) + 1

        if name == C.EVENT_PAYMENT:
            pg = payload.get(C.F_PG_LATENCY)
            total = payload.get(C.F_TOTAL_LATENCY)
            # PG 장애와 DB 장애는 실패율이 똑같이 보입니다.
            # 이 비율만이 '느린 구간이 어디인가'에 답합니다.
            if isinstance(pg, (int, float)) and isinstance(total, (int, float)) and total > 0:
                self.pg_ratio.add(pg / total)

    def note_source(self, source: str, sequence_number: str | None) -> None:
        """이 부분 집계가 어느 샤드의 어디까지를 담았는지 기록합니다."""
        if not sequence_number:
            return
        cur = self.seq.get(source)
        if cur is None or int(sequence_number) > int(cur):
            self.seq[source] = str(sequence_number)

    # ------------------------------------------------------------ 병합
    def already_applied(self, other: "WindowSketch") -> bool:
        """other 가 이미 반영된 배치인지.

        한 Lambda 호출은 한 샤드의 연속 구간만 받으므로 other 의 source 는
        많아야 하나입니다. 그 구간의 끝 번호가 이미 기록돼 있으면
        같은 배치의 재시도입니다.

        ## 이 가드는 "샤드당 한 번에 하나" 를 전제로 합니다 — 지켜야 합니다

        번호를 **최댓값 하나**로만 들고 있습니다. 그래서 같은 샤드의 배치가
        **뒤바뀌어** 들어오면 앞선 배치를 재시도로 오인해 통째로 버립니다.
        예외도 오류도 나지 않고 건수만 조용히 줄어듭니다.

        Kinesis 이벤트 소스 매핑의 `parallelization_factor` 를 1보다 크게
        하면 **정확히 그 상황이 됩니다.** 같은 샤드를 동시에 여러 배치가
        처리하고, 늦게 시작한 배치가 먼저 끝날 수 있습니다.

        **집계기가 밀릴 때 `parallelization_factor` 로 푸는 것은 그래서 안
        됩니다. 샤드 수를 늘려야 합니다** — 샤드가 다르면 `source` 키가
        갈리고(`_source_of()` 가 스트림+샤드로 만듭니다) 번호를 서로
        독립적으로 비교하므로 안전합니다. 근거와 실측은 D-058.

        `tests/test_sequence_guard.py` 가 이 성질을 고정해 둡니다.
        """
        for src, hi in other.seq.items():
            cur = self.seq.get(src)
            if cur is None:
                continue
            if int(cur) < int(hi):
                continue

            # cur == hi 는 같은 배치의 재시도입니다. 정상이고 조용히 버립니다.
            #
            # cur > hi 는 다릅니다 — **이미 더 뒤까지 반영했는데 그보다 앞선
            # 배치가 지금 도착했다**는 뜻이고, 순차 처리에서는 일어나지
            # 않습니다. 버리는 동작 자체는 유지하되(여기서 순서를 되돌릴
            # 방법이 없습니다) 조용히 지나가지는 않게 합니다.
            if int(cur) > int(hi):
                print(
                    f"[o2warm] 순서가 뒤바뀐 배치를 버립니다 — source={src} "
                    f"기록={cur} 도착={hi}. parallelization_factor 가 1보다 "
                    f"크면 이 일이 상시로 일어나고 집계가 조용히 줄어듭니다(D-058).",
                    file=sys.stderr,
                )
            return True
        return False

    def merge(self, other: "WindowSketch") -> "WindowSketch":
        if other.n == 0:
            return self
        if self.already_applied(other):
            return self

        self.n += other.n
        self.n_business += other.n_business
        self.n_client += other.n_client
        self.ua_events += other.ua_events
        self.cache_hit += other.cache_hit
        self.cache_miss += other.cache_miss
        self.retry_events += other.retry_events
        self.retry_sum += other.retry_sum
        self.retry_base += other.retry_base
        self.fallback_used += other.fallback_used

        for src, table in (
            (other.by_event, self.by_event),
            (other.results, self.results),
            (other.failures, self.failures),
            (other.clicks, self.clicks),
            (other.cancel_reasons, self.cancel_reasons),
            (other.cancel_by, self.cancel_by),
            (other.cache_hit_by_pod, self.cache_hit_by_pod),
            (other.cache_miss_by_pod, self.cache_miss_by_pod),
        ):
            for k, v in src.items():
                table[k] = table.get(k, 0) + v

        for ver, (n, f) in other.versions.items():
            cur = self.versions.setdefault(ver, [0, 0])
            cur[0] += n
            cur[1] += f

        self.users.merge(other.users)
        self.distinct_users.merge(other.distinct_users)
        self.distinct_ua.merge(other.distinct_ua)
        self.distinct_ip.merge(other.distinct_ip)
        self.intervals.merge(other.intervals)
        self.pg_ratio.merge(other.pg_ratio)
        self.latency.merge(other.latency)
        for pod, hist in other.latency_by_pod.items():
            self.latency_by_pod.setdefault(pod, LogHistogram()).merge(hist)
        self.segments.merge(other.segments)

        if other.first_ts is not None:
            self.first_ts = other.first_ts if self.first_ts is None else min(self.first_ts, other.first_ts)
        if other.last_ts is not None:
            self.last_ts = other.last_ts if self.last_ts is None else max(self.last_ts, other.last_ts)

        for src, hi in other.seq.items():
            cur = self.seq.get(src)
            if cur is None or int(hi) > int(cur):
                self.seq[src] = hi

        return self

    # ------------------------------------------------------------ 직렬화
    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "window_start": self.window_start,
            "n": self.n,
            "nb": self.n_business,
            "nc": self.n_client,
            "by_event": self.by_event,
            "users": self.users.to_dict(),
            "du": self.distinct_users.to_dict(),
            "dua": self.distinct_ua.to_dict(),
            "dip": self.distinct_ip.to_dict(),
            "iv": self.intervals.to_dict(),
            "cache": [self.cache_hit, self.cache_miss],
            "cache_pod": [self.cache_hit_by_pod, self.cache_miss_by_pod],
            "results": self.results,
            "failures": self.failures,
            "clicks": self.clicks,
            "versions": self.versions,
            "pg": self.pg_ratio.to_dict(),
            "ua_events": self.ua_events,
            "lat": self.latency.to_dict(),
            "lat_pod": {pod: h.to_dict() for pod, h in self.latency_by_pod.items()},
            "retry": [self.retry_events, self.retry_sum, self.retry_base],
            "fallback": self.fallback_used,
            "cancel_reasons": self.cancel_reasons,
            "cancel_by": self.cancel_by,
            "seg": self.segments.to_dict(),
            "first_ts": self.first_ts,
            "last_ts": self.last_ts,
            "seq": self.seq,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WindowSketch":
        s = cls(d.get("service", "unknown"), d.get("window_start", 0))
        s.n = int(d.get("n") or 0)
        s.n_business = int(d.get("nb") or 0)
        s.n_client = int(d.get("nc") or 0)
        s.by_event = dict(d.get("by_event") or {})
        s.users = SpaceSaving.from_dict(d.get("users") or {}, settings.user_capacity)
        s.distinct_users = DistinctCounter.from_dict(d.get("du") or {}, settings.distinct_capacity)
        s.distinct_ua = DistinctCounter.from_dict(d.get("dua") or {}, settings.distinct_capacity)
        s.distinct_ip = DistinctCounter.from_dict(d.get("dip") or {}, settings.distinct_capacity)
        s.intervals = IntervalStats.from_dict(d.get("iv") or {}, settings.interval_capacity)
        cache = d.get("cache") or [0, 0]
        s.cache_hit, s.cache_miss = int(cache[0]), int(cache[1])
        cache_pod = d.get("cache_pod") or [{}, {}]
        s.cache_hit_by_pod = dict(cache_pod[0] or {})
        s.cache_miss_by_pod = dict(cache_pod[1] or {})
        s.results = dict(d.get("results") or {})
        s.failures = dict(d.get("failures") or {})
        s.clicks = dict(d.get("clicks") or {})
        s.versions = {k: [int(v[0]), int(v[1])] for k, v in (d.get("versions") or {}).items()}
        s.pg_ratio = Histogram.from_dict(d.get("pg") or {})
        s.ua_events = int(d.get("ua_events") or 0)
        s.latency = LogHistogram.from_dict(d.get("lat") or {})
        s.latency_by_pod = {
            pod: LogHistogram.from_dict(h or {}) for pod, h in (d.get("lat_pod") or {}).items()
        }
        retry = d.get("retry") or [0, 0, 0]
        s.retry_events, s.retry_sum, s.retry_base = (int(x) for x in retry)
        s.fallback_used = int(d.get("fallback") or 0)
        s.cancel_reasons = dict(d.get("cancel_reasons") or {})
        s.cancel_by = dict(d.get("cancel_by") or {})
        s.segments = SegmentStats.from_dict(d.get("seg") or {}, settings.segment_capacity)
        s.first_ts = d.get("first_ts")
        s.last_ts = d.get("last_ts")
        s.seq = dict(d.get("seq") or {})
        return s

    def copy(self) -> "WindowSketch":
        return WindowSketch.from_dict(self.to_dict())

    @property
    def truncated(self) -> bool:
        return (
            self.users.truncated
            or self.intervals.dropped > 0
            or self.distinct_users.approximate
        )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<WindowSketch {self.service}@{self.window_start} n={self.n}>"


def build(service: str, window_start: int, envelopes: list[dict]) -> WindowSketch:
    s = WindowSketch(service, window_start)
    for env in envelopes:
        s.add(env)
    return s
