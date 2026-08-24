"""내부 전용 경로(admin.py·internal.py)가 공유하는 인증 검사.

두 라우트가 각자 같은 HMAC 비교를 복제해서 갖고 있으면, 한쪽만 손보고
(타이밍·길이 검사·로깅 같은) 다른 쪽을 빠뜨리는 드리프트가 생긴다.
"""

import hmac

from fastapi import HTTPException


def require_admin_key(expected: str, provided: str | None) -> None:
    if not expected or not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="forbidden")
