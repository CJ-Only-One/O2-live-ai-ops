"""큐시트 사전 확장 — 캐시 워밍만(D-041 3번, D-065).

방송 시작·게스트 등장처럼 **신규 진입**이 몰리는 세그먼트(`expected.
entry_window_s` 가 있는 세그먼트) 앞에서, 그리고 그 진입이 이어지는
동안(`at` 부터 `entry_window_s` 만큼) `bcast:{id}:meta` 를 계속 데운다.
`entry_window_s` 가 끝나면 멈춘다 — 그때부터는 신규 진입이 끝났다는
뜻이므로 더 때릴 필요가 없다.

`entry_window_s` 가 없는 세그먼트(EVENT_ANNOUNCE·SALE_CLOSING처럼 이미 들어와
있는 시청자만 움직이는 경우)는 신규 진입이 없으므로 대상이 아니다. 파드
증설·노드 확보는 다음 단계다 — 이 파일은 캐시만 본다.

`GET /api/broadcasts/{id}` 를 직접 부르지 않는다. 그건 재고 조회와
`inventory.check` 발행까지 같이 하고, 후자는 "트래픽 폭증과 캐시 미스
폭주를 가르는 유일한 근거"(contracts.md 5.1)라 워머의 폴링이 매 tick 마다
가짜 히트로 그 지표를 오염시킨다. 대신 캐시만 채우는 내부 전용 경로
(`POST /api/internal/warm/{broadcast_id}`)를 쓴다.
"""

import logging
import signal
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import and_, create_engine, or_, select
from sqlalchemy.orm import Session, sessionmaker

from warmer import capacity, k8s
from warmer.config import settings
from warmer.models import CueSheet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("cue-warmer")

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=2,
    connect_args={"connect_timeout": 5},
)
SessionLocal = sessionmaker(bind=engine)

_running = True


def _stop(signum, _frame):
    global _running
    logger.info("종료 신호 수신(%s). 이번 tick 을 끝내고 종료한다.", signum)
    _running = False


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


def _to_naive_utc(value: str) -> datetime:
    """오프셋을 요구하고 UTC 로 바꾼다.

    save_cue_sheet()(apps/api/app/services/cue_sheet.py)가 강제하는 오프셋
    검증은 body 최상위의 scheduled_at·ends_at 에만 걸린다 — segments[].at
    은 body 를 통째로 JSON 컬럼에 저장할 때 그 검증을 안 거친다(D-065). 그래서
    이 재검증은 군더더기가 아니라 여기서만 걸리는 유일한 방어선이다. 안 하면
    오프셋 없는 세그먼트 시각이 이 프로세스가 도는 서버의 로컬 시간대로
    조용히 해석돼 몇 시간이 어긋난다."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"offset is required: {value!r}")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def candidate_broadcasts(db: Session, now: datetime) -> list[dict]:
    """지금부터 CACHE_LEAD_S 안에 시작하거나 이미 진행 중인 방송의 큐시트
    body 를 가져온다. SQL 단계에서는 방송 단위로만 거른다 — 세그먼트 단위
    판정(entry_window_s 유무·at 시각)은 필요한 컬럼이 JSON 안에만 있어
    파이썬에서 한다.

    ends_at 은 선택 필드다(cue-sheet-v1 스키마). ends_at 이 없는 행에
    scheduled_at 하한을 안 두면, 끝난 지 오래된 데모·취소된 방송이 매 tick
    영원히 후보로 다시 뽑혀 DB 조회와 JSON 파싱 비용이 서비스 수명 내내
    계속 늘어난다.

    **이미 끝난 방송도 STALE_LOOKBACK_S 동안은 후보로 남긴다.** 파드 원복이
    ends_at + REVERT_COOLDOWN_S 뒤에 일어나므로, 끝나자마자 후보에서 빼면
    되돌릴 기회 자체가 사라져 늘린 파드가 영원히 떠 있는다. 원복은 멱등이라
    (이미 baseline 이면 patch 를 건너뛴다) 남아 있는 동안 여러 번 돌아도
    문제가 없다."""
    horizon = now + timedelta(seconds=settings.CACHE_LEAD_S)
    lookback = now - timedelta(seconds=settings.STALE_LOOKBACK_S)
    rows = db.execute(
        select(CueSheet).where(
            CueSheet.scheduled_at <= horizon,
            or_(
                and_(CueSheet.ends_at.is_not(None), CueSheet.ends_at >= lookback),
                and_(CueSheet.ends_at.is_(None), CueSheet.scheduled_at >= lookback),
            ),
        )
    ).scalars().all()
    return [row.body for row in rows]


def needs_warming(body: dict, now: datetime) -> bool:
    """entry_window_s 가 있는 세그먼트 중 하나라도
    [at - CACHE_LEAD_S, at + entry_window_s) 구간에 지금이 들어와 있으면
    워밍 대상이다.

    at 은 진입이 "끝나는" 시각이 아니라 "시작되는" 시각이다(스키마의
    entry_window_s 설명 — "이 인원이 몇 초에 걸쳐 진입하는가"). 그래서
    at 에서 끊지 않고 entry_window_s 만큼 더 데운다. at 이후를 진입
    트래픽 자신이 유지한다는 가정은 진입 밀도가 높을 때만(예: 12,000명이
    60초에 걸쳐) 성립한다 — concurrent 가 작고 entry_window_s 가 길면
    (예: 50명이 1시간에 걸쳐, 평균 72초 간격) 30초 TTL 안에 자연 히트가
    안 나 at 직후 캐시가 다시 식는다. 그 가정에 기대지 않고 entry_window_s
    값 자체를 구간에 넣어 밀도와 무관하게 맞춘다.

    segments 자체는 검증되지 않은 채 들어올 수 있다(D-065 — save_cue_sheet
    는 세그먼트 형태를 검사하지 않는다). segment 나 expected 가 dict 가
    아닌 경우까지 방어한다 — 여기서 예외가 나면 이 함수를 부른 쪽에서
    tick 전체가 아니라 이 방송 하나만 걸러져야 하는데, 그 경계를 여기서
    지켜야 다른 방송의 워밍이 이 방송 때문에 밀리지 않는다."""
    segments = body.get("segments")
    if not isinstance(segments, list):
        segments = []

    for segment in segments:
        if not isinstance(segment, dict):
            continue

        expected = segment.get("expected")
        if not isinstance(expected, dict):
            continue

        entry_window_s = expected.get("entry_window_s")
        if not isinstance(entry_window_s, (int, float)) or entry_window_s < 0:
            continue

        try:
            at = _to_naive_utc(segment["at"])
        except (KeyError, TypeError, ValueError):
            logger.warning("세그먼트 at 파싱 실패, 건너뜀: %r", segment.get("at"))
            continue

        window_start = at - timedelta(seconds=settings.CACHE_LEAD_S)
        window_end = at + timedelta(seconds=entry_window_s)
        if window_start <= now < window_end:
            return True

    return False


def warm(client: httpx.Client, broadcast_id: str) -> bool:
    """실제로 워밍됐을 때만 True. 호출부(tick)가 이 값으로 warmed 건수를
    세므로, 여기서 실패를 삼키고 항상 성공한 것처럼 두면 CUE_WARMER_ADMIN_KEY
    불일치 같은 사고가 "이번 tick 워밍: N건" INFO 로그 뒤에 영원히 숨는다
    — 워밍이 계속 안 되고 있는데 로그만 정상으로 보인다."""
    try:
        res = client.post(
            f"{settings.API_BASE_URL}/api/internal/warm/{broadcast_id}",
            headers={"x-admin-key": settings.CUE_WARMER_ADMIN_KEY},
            timeout=5.0,
        )
    except httpx.HTTPError:
        logger.exception("워밍 요청 실패: %s", broadcast_id)
        return False

    if res.status_code == 200:
        logger.info("워밍: %s", broadcast_id)
        return True

    # 404 는 큐시트의 broadcast_id 오타나 편성 누락일 수 있다.
    # 403 은 CUE_WARMER_ADMIN_KEY 가 api 쪽과 안 맞는다는 뜻이다.
    logger.warning("워밍 실패(%s): %s", res.status_code, broadcast_id)
    return False


def desired_replicas(body: dict, now: datetime) -> dict[str, int]:
    """지금 걸쳐 있는 세그먼트들이 요구하는 서비스별 목표 파드 수.

    확장 창은 [at - SCALE_LEAD_S, at + duration) 이다. 캐시 워밍보다 앞서
    시작하는 이유는 파드가 Ready 되는 데 시간이 걸리기 때문이고(M-019),
    duration 은 그 부하가 이어지는 예상 시간이다(없으면 entry_window_s).

    **창이 끝나도 파드를 줄이지 않는다.** 이 창은 "언제 늘릴까" 만 정하고,
    줄이는 것은 방송 종료 후 revert 가 한다 — 게스트가 만든 WebSocket 연결은
    세그먼트가 끝나도 방송 끝까지 유지되므로 duration 으로 줄이면 그 연결이
    끊긴다.
    """
    segments = body.get("segments")
    if not isinstance(segments, list):
        return {}

    merged: dict[str, int] = {}
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        expected = segment.get("expected")
        if not isinstance(expected, dict):
            continue

        try:
            at = _to_naive_utc(segment["at"])
        except (KeyError, TypeError, ValueError):
            continue

        duration = segment.get("duration_s")
        if not isinstance(duration, (int, float)) or duration < 0:
            duration = expected.get("entry_window_s")
        if not isinstance(duration, (int, float)) or duration < 0:
            duration = 0

        window_start = at - timedelta(seconds=settings.SCALE_LEAD_S)
        window_end = at + timedelta(seconds=duration)
        if window_start <= now < window_end:
            merged = capacity.merge(merged, capacity.targets(expected))

    return merged


def _ended_long_enough(body: dict, now: datetime) -> bool:
    """방송이 끝나고 cooldown 까지 지났는가. ends_at 이 없으면 판단하지 않는다
    — 언제 끝났는지 모르는 방송을 임의로 줄이면 안 된다."""
    raw = body.get("ends_at")
    if not raw:
        return False
    try:
        ends_at = _to_naive_utc(raw)
    except (TypeError, ValueError):
        return False
    return now >= ends_at + timedelta(seconds=settings.REVERT_COOLDOWN_S)


def reconcile_scale(bodies: list[dict], now: datetime) -> int:
    """파드 수를 맞춘다. 바꾼 서비스 수를 돌려준다.

    **방송 하나가 아니라 전체를 한 번에 본다.** 파드 수는 방송별이 아니라
    클러스터가 공유하는 값이라, 방송마다 따로 조정하면 끝난 방송이 원복하고
    진행 중인 방송이 다시 늘리기를 매 tick 반복한다.

    방송 중에는 **늘리기만** 한다. 줄이는 것은 모든 방송이 끝나고 cooldown 이
    지난 뒤 baseline 으로 되돌리는 것 하나뿐이다(D-041 — 확장은 비용 위험,
    축소는 가용성 위험이라 조건을 확인하는 단계로만 한다).
    """
    if not settings.SCALE_ENABLED:
        return 0

    desired: dict[str, int] = {}
    for body in bodies:
        desired = capacity.merge(desired, desired_replicas(body, now))

    if desired:
        # 요구가 있으면 그쪽으로 올린다(비용 상한 안에서).
        targets = {
            service: min(pods, settings.MAX_REPLICAS)
            for service, pods in desired.items()
        }
        reverting = False
    elif all(_ended_long_enough(body, now) for body in bodies):
        # 지금 요구가 없고 남은 방송이 전부 끝났을 때만 되돌린다.
        # 후보가 아예 없을 때도(큐시트 없음) 여기로 온다 — 아무 방송도
        # 예정돼 있지 않은 상태의 정답은 baseline 이다.
        # MAX_REPLICAS 를 안 씌운다. 그건 확장 폭을 막는 비용 상한이지
        # 되돌릴 기준값을 깎는 값이 아니다.
        targets = settings.baseline_replicas
        reverting = True
    else:
        # 진행 중이거나 아직 cooldown 안 지난 방송이 있다 — 그대로 둔다.
        return 0

    ns = settings.APP_NAMESPACE
    changed = 0
    for service, target in targets.items():
        # order-worker 만 만지는 리소스가 다르다. KEDA 가 Deployment 의
        # replicas 를 소유하므로 그걸 patch 하면 다음 조절 주기에 되돌려진다
        # — ScaledObject 의 minReplicaCount(바닥)를 올려 KEDA 가 그 위에서
        # 계속 조절하게 둔다.
        keda = service in settings.KEDA_MANAGED
        read = k8s.get_min_replicas if keda else k8s.get_replicas
        write = k8s.set_min_replicas if keda else k8s.set_replicas

        current = read(ns, service)
        if current is None:
            continue

        # 방송 중이면 늘리기만. 원복 구간에서만 줄이는 방향을 허용한다.
        if current == target or (not reverting and current >= target):
            continue

        if write(ns, service, target):
            logger.info(
                "%s: %s %d -> %d",
                "원복" if reverting else "사전 확장",
                service,
                current,
                target,
            )
            changed += 1

    return changed


def tick(db: Session, client: httpx.Client) -> tuple[int, int]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    bodies = candidate_broadcasts(db, now)

    # 캐시 워밍은 방송마다 따로다 — 캐시 키가 방송별이라 서로 안 겹친다.
    warmed = 0
    for body in bodies:
        try:
            if needs_warming(body, now) and warm(client, body["broadcast_id"]):
                warmed += 1
        except Exception:
            # 방송 하나의 큐시트가 깨져 있어도 나머지 방송은 이번 tick 에
            # 그대로 처리돼야 한다 — 한 건의 문제로 전체가 밀리면 안 된다.
            logger.exception("세그먼트 판정 실패, 건너뜀: %r", body.get("broadcast_id") if isinstance(body, dict) else body)

    # 파드 수는 클러스터가 공유하는 값이라 전체를 한 번에 본다.
    try:
        scaled = reconcile_scale(bodies, now)
    except Exception:
        logger.exception("스케일 조정 실패")
        scaled = 0

    return warmed, scaled


def main() -> None:
    if not settings.CUE_WARMER_ADMIN_KEY:
        logger.error("CUE_WARMER_ADMIN_KEY 가 비어 있다. api 가 요청을 전부 거부한다.")

    logger.info(
        "워머 시작: tick=%ss cache_lead=%ss scale=%s",
        settings.TICK_S,
        settings.CACHE_LEAD_S,
        "on" if settings.SCALE_ENABLED else "off",
    )

    with httpx.Client() as client:
        while _running:
            try:
                with SessionLocal() as db:
                    warmed, scaled = tick(db, client)
                    if warmed or scaled:
                        logger.info("이번 tick: 워밍 %d건 · 스케일 %d건", warmed, scaled)
            except Exception:
                logger.exception("tick 실패")

            time.sleep(settings.TICK_S)

    logger.info("워머 종료")


if __name__ == "__main__":
    main()
