from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "o2-api"

    # 프론트 도메인이 바뀌어도 코드를 안 고치도록 env로 뺀다. 콤마로 구분한다.
    # 운영 값(실제 프론트 도메인)은 배포 환경변수로 주입해야 한다.
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    # AWS RDS(MySQL) 접속 정보. 실제 값은 .env 또는 배포 환경변수로 주입한다.
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "o2"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()
