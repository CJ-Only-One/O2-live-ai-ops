from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "o2-api"

    # 프론트 도메인이 바뀌어도 코드를 안 고치도록 env로 뺀다. 콤마로 구분한다.
    # 운영 값(실제 프론트 도메인)은 배포 환경변수로 주입해야 한다.
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    # ── 아래 이름은 계약이다 ──────────────────────────────────
    # 클러스터에서는 ConfigMap o2-data 와 Secret o2-db 가 envFrom 으로 통째로
    # 들어온다. 그 키 이름과 여기 필드 이름이 1:1 로 같아야 한다.
    #
    #   ConfigMap/Secret 키 == 이 클래스의 필드 == .env.example 항목
    #
    # 다른 이름(REDIS_URL 같은)을 새로 만들면 주입된 값이 조용히 무시되고
    # 아래 기본값(localhost)이 쓰인다. 기동은 성공하므로 알아채기 늦다.
    # ConfigMap 은 infra/04-platform/app_data_access.tf 가 만든다.

    # RDS(MySQL). 쓰기와 "주문 직후 조회" 는 writer 로 간다.
    DB_HOST: str = "localhost"

    # 읽기 전용 조회 대상. 리드 리플리카가 없는 동안에는 writer 와 같은 값이 온다.
    # 애플리케이션은 지금부터 둘을 나눠 쓴다 — 나중에 리플리카를 켜는 것만으로
    # 읽기가 분산되고 코드는 손대지 않는다 (docs/decisions.md D-017).
    DB_READER_HOST: str = ""
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "o2"

    # ElastiCache(Valkey). 세션·재고 카운터·룸 매핑·Pub/Sub.
    VALKEY_HOST: str = "localhost"
    VALKEY_READER_HOST: str = ""
    VALKEY_PORT: int = 6379

    # 클러스터의 Valkey 는 transit 암호화가 켜져 있어 평문 접속이 끊긴다.
    # 로컬 docker-compose 의 Valkey 는 TLS 가 없으므로 기본값이 false 다.
    VALKEY_TLS: bool = False

    # 주문 확정 큐. 재고 판정(DECR) 이 끝난 뒤 여기에 넣고 워커가 MySQL 에 기록한다.
    # 로컬에서는 비어 있을 수 있다 — 그때는 발행을 건너뛰도록 코드에서 분기한다.
    SQS_ORDER_QUEUE_URL: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    def _mysql_url(self, host: str) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{host}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def database_url(self) -> str:
        """writer. 쓰기와 쓰기 직후 조회."""
        return self._mysql_url(self.DB_HOST)

    @property
    def reader_database_url(self) -> str:
        """reader. 비어 있으면 writer 로 떨어진다."""
        return self._mysql_url(self.DB_READER_HOST or self.DB_HOST)

    @property
    def valkey_url(self) -> str:
        """TLS 여부에 따라 스킴이 갈린다 (rediss:// 가 TLS)."""
        scheme = "rediss" if self.VALKEY_TLS else "redis"
        return f"{scheme}://{self.VALKEY_HOST}:{self.VALKEY_PORT}"

    @property
    def valkey_reader_url(self) -> str:
        scheme = "rediss" if self.VALKEY_TLS else "redis"
        host = self.VALKEY_READER_HOST or self.VALKEY_HOST
        return f"{scheme}://{host}:{self.VALKEY_PORT}"


settings = Settings()
