"""워머 설정.

DB_* 는 api·order-worker 와 같은 ConfigMap o2-data·Secret o2-db 를 그대로
쓴다 — 이름이 그쪽과 안 맞으면 주입값이 조용히 무시되고 기본값(localhost)이
쓰인다(AGENTS.md 의 "조용히 깨지는 것").

CUE_WARMER_ADMIN_KEY 는 api 의 같은 이름 Settings 필드와 값이 같아야 한다 —
여기서는 보내는 쪽, api 에서는 검증하는 쪽이다. 둘이 다른 Secret 키에서
나오면 워머가 영원히 403 을 받는다.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "o2-cue-warmer"

    # 읽기 전용이라 reader 를 따로 안 둔다. 조회 빈도가 낮고(10초 1회)
    # writer 부담이 무시할 만하다.
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "o2"

    # 클러스터에서는 api Service 의 클러스터 내부 DNS. 같은 네임스페이스면
    # 짧은 이름으로 닿는다 — o2-dev/api-service.yaml 의 Service 이름이 api.
    API_BASE_URL: str = "http://localhost:8000"
    CUE_WARMER_ADMIN_KEY: str = ""

    # Valkey TTL(30초, api/app/services/broadcast.py 의 VALKEY_TTL)보다
    # 짧아야 한다. 안 그러면 이번 tick 이 채운 캐시가 다음 tick 전에 만료된다.
    TICK_S: int = 10

    # 진입 세그먼트의 at 시각으로부터 몇 초 전부터 워밍을 시작할지.
    # TTL(30초) + 여유 한 tick. 값 자체는 실측(콜드 캐시 스탬피드) 전 상수다
    # — 재면 M-0NN 으로 남기고 이 기본값을 그 값으로 바꾼다.
    CACHE_LEAD_S: int = 40

    # ends_at 없는 큐시트가 매 tick 영원히 후보로 다시 뽑히는 것을 막는
    # 하한. scheduled_at 이 이보다 오래됐으면 ends_at 이 없어도 후보에서
    # 뺀다. 방송이 이보다 길게 이어지면 ends_at 을 채우는 게 정답이지
    # 이 값을 늘리는 게 정답이 아니다.
    STALE_LOOKBACK_S: int = 24 * 60 * 60

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()
