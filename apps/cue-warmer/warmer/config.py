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

    # ── 파드 사전 확장 ────────────────────────────────────────
    #
    # 끄면 캐시 워밍만 돈다. RBAC(04-platform 의 enable_cue_warmer_scaling)이
    # 안 붙은 상태로 켜면 스케일 호출이 403 으로 실패하고 로그에 남는다 —
    # ServiceAccount 자체는 그 변수와 무관하게 항상 만들어지므로 파드는 뜬다.
    SCALE_ENABLED: bool = False

    # 파드가 Ready 되는 데 걸리는 시간. M-019 실측이 4초 또는 13~14초로
    # 양분되고(readinessProbe periodSeconds=10 에 양자화된다) 8회 중 6회가
    # 후자라 최악값에 여유를 얹었다. 노드를 새로 띄워야 하면 분 단위가 되므로
    # 그 경우는 이 값으로 못 덮는다 — 증설 슬롯이 기존 노드 안에 있어야 한다.
    SCALE_LEAD_S: int = 60

    # 방송이 끝나고 baseline 으로 되돌리기까지 기다리는 시간.
    # 종료 즉시 줄이면 아직 안 빠진 WebSocket 연결이 끊긴다 — 축소는 가용성
    # 위험이라 여유를 준다(D-041 "축소는 큐시트 종료만으로 실행하지 않는다").
    # 지표(활성 연결·backlog)까지 보는 것은 아직 안 한다.
    REVERT_COOLDOWN_S: int = 600

    # 비용 상한. 개인 계정이라 큐시트가 잘못 적혀도 여기서 막힌다.
    # 노드 여유가 CPU 530~650m·메모리 20~30% 수준이라(2026-08-24 실측)
    # 이보다 크게 잡으면 Karpenter 가 노드를 새로 사고 그때부터 시간당 요금이다.
    MAX_REPLICAS: int = 6

    # 파드를 만질 네임스페이스. api·chat-gateway 와 같은 곳이다.
    APP_NAMESPACE: str = "o2-dev"

    # 방송이 끝나고 되돌릴 기준값. 사본을 두는 이유는 워머가 재시작해도
    # 되돌릴 값을 알아야 하기 때문이다 — "늘리기 전 값을 기억해두기" 는
    # 파드가 죽으면 같이 사라진다.
    #
    # ★ O2-live-deploy 의 api-deployment.yaml·chat-gateway-deployment.yaml
    #   replicas 와 같아야 한다. 그쪽이 원본이고 여기는 사본이다.
    #   **어긋나도 아무도 안 알려준다** — Argo 는 그 필드를 무시하도록
    #   설정돼 있어서(argocd.tf ignoreDifferences) 워머가 되돌린 값이
    #   Git 과 달라도 selfHeal 이 고쳐주지 않는다. 매니페스트에서 replicas 를
    #   바꾸면 여기도 같이 바꾼다.
    #
    # 사본을 하나로 유지한다. 매니페스트 env 로 또 덮어쓰면 같은 값이 세 곳에
    # 생겨 어긋날 자리가 늘어난다.
    #
    # order-worker 는 Deployment 가 아니라 ScaledObject 의 minReplicaCount 다
    # (order-worker-scaledobject.yaml 의 minReplicaCount).
    BASELINE_API_REPLICAS: int = 2
    BASELINE_CHAT_REPLICAS: int = 2
    BASELINE_ORDER_MIN_REPLICAS: int = 1

    # KEDA 가 Deployment 의 replicas 를 소유하는 서비스. 여기 있는 것은
    # ScaledObject 의 minReplicaCount(바닥)를 올리고, KEDA 가 그 위에서
    # 큐 길이를 보고 계속 조절한다. Deployment 를 직접 patch 하면 KEDA 의
    # 다음 조절 주기에 되돌려진다.
    KEDA_MANAGED: frozenset[str] = frozenset({"order-worker"})

    @property
    def baseline_replicas(self) -> dict[str, int]:
        return {
            "api": self.BASELINE_API_REPLICAS,
            "chat-gateway": self.BASELINE_CHAT_REPLICAS,
            "order-worker": self.BASELINE_ORDER_MIN_REPLICAS,
        }

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()
