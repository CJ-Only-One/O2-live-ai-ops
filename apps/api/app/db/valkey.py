from redis import Redis

from app.core.config import settings

# 스킴은 config 가 정한다 — 클러스터의 Valkey 는 transit 암호화가 켜져 있어
# 평문(redis://)으로 붙으면 연결이 그 자리에서 끊긴다 (rediss:// 여야 한다).
#
# 타임아웃은 session.py 와 같은 이유로 짧게 끊는다. 없으면 Valkey 가 응답하지
# 않을 때 동기 핸들러가 스레드풀을 물고 매달린다.
valkey = Redis.from_url(
    settings.valkey_url,
    socket_connect_timeout=2,
    socket_timeout=2,
    decode_responses=True,
)
