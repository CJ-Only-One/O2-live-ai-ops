"""cue-warmer 전용 경로 — 큐시트 사전 확장의 캐시 워밍(D-041, D-065).

`admin.py` 와 인증 방식은 같다(HMAC 비교, kubectl 로 직접 넣는 키, Secrets
Manager 를 안 거침). 별도 파일로 둔 이유는 호출 주체가 사람이 아니라
cue-warmer 파드이고, 새는 키의 파급 범위를 admin.py 의 S3 조치 노브와
분리하기 위해서다(app/core/config.py 의 CUE_WARMER_ADMIN_KEY 주석 참조).
"""

from fastapi import APIRouter, Header, HTTPException

from app.core.admin_auth import require_admin_key
from app.core.config import settings
from app.schemas.common import BroadcastId
from app.services.broadcast import warm_meta

router = APIRouter()


@router.post("/internal/warm/{broadcast_id}")
def warm(broadcast_id: BroadcastId, x_admin_key: str | None = Header(default=None)):
    require_admin_key(settings.CUE_WARMER_ADMIN_KEY, x_admin_key)

    warmed = warm_meta(broadcast_id)
    if not warmed:
        # 없는 방송을 워밍하려 한 것 — 큐시트가 가리키는 broadcast_id 가
        # 틀렸거나 아직 편성 전이다. 조용히 200 을 주면 사람이 못 알아챈다.
        raise HTTPException(status_code=404, detail="broadcast not found")

    return {"broadcast_id": broadcast_id, "warmed": True}
