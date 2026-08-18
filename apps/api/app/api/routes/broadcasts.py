from fastapi import APIRouter

from app.core.errors import ApiError, openapi_errors
from app.schemas.broadcast import BroadcastOut
from app.services import broadcast as broadcast_service

router = APIRouter()


@router.get(
    "/broadcasts/{broadcast_id}",
    response_model=BroadcastOut,
    responses=openapi_errors(("INVALID_REQUEST", 404)),
)
def get_broadcast(broadcast_id: str):
    """방송 진입 스냅샷 (contracts.md 2.1).

    이 엔드포인트가 캐시 스탬피드의 발생 지점이다. 푸시로 바꿔도 진입 시
    1회 조회는 남고, 방송 시작 30초에 그것이 몰린다 (architecture.md 3.8).
    """
    snapshot = broadcast_service.get_snapshot(broadcast_id)
    if snapshot is None:
        raise ApiError("INVALID_REQUEST", "방송을 찾을 수 없습니다", status_code=404)
    return snapshot
