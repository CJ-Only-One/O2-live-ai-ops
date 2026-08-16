"""워커 설정.

이름은 계약이다. 클러스터에서는 api 와 같은 ConfigMap o2-data 와 Secret
o2-db 가 envFrom 으로 들어오므로, 그 키 이름과 여기 필드 이름이 1:1 로
같아야 한다. 다른 이름을 만들면 주입값이 조용히 무시되고 기본값이 쓰인다.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "o2-order-worker"

    # 쓰기 전용이라 reader 는 쓰지 않는다.
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "o2"

    SQS_ORDER_QUEUE_URL: str = ""
    AWS_REGION: str = "ap-northeast-2"

    # 한 번에 최대 10건까지 받는다. SQS 상한이다.
    SQS_BATCH_SIZE: int = 10

    # 롱 폴링. 0 이면 빈 응답이 계속 돌아와 요청 수만 늘어난다.
    SQS_WAIT_SECONDS: int = 20

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()
