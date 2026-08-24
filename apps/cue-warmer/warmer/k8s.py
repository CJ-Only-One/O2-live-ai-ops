"""클러스터 안에서 Deployment 의 replicas 를 읽고 바꾼다.

kubernetes 클라이언트 라이브러리를 안 쓴다 — 이 파일이 부르는 API 는
scale 서브리소스 GET·PATCH 둘뿐이라, 의존성 하나를 더 들이는 것보다
httpx 로 직접 부르는 편이 짧다.

인증은 파드에 자동으로 마운트되는 ServiceAccount 토큰이다. RBAC 은
infra/04-platform/cue_warmer_access.tf 가 준다 — o2-dev 의
deployments/scale, get·patch 뿐이라 이미지나 env 는 못 만진다.
"""

import logging
from pathlib import Path

import httpx

logger = logging.getLogger("cue-warmer")

_SA_DIR = Path("/var/run/secrets/kubernetes.io/serviceaccount")
_TOKEN_PATH = _SA_DIR / "token"
_CA_PATH = _SA_DIR / "ca.crt"
_NAMESPACE_PATH = _SA_DIR / "namespace"

# 클러스터 안에서 API 서버를 가리키는 표준 주소. kubelet 이 모든 파드에
# 넣어주는 환경변수 대신 이 이름을 쓰는 이유는, 이 이름이 파드가 어느
# 노드에 있든 같기 때문이다.
_API = "https://kubernetes.default.svc"


class K8sUnavailable(RuntimeError):
    """클러스터 안이 아니거나 ServiceAccount 가 안 마운트된 상태."""


def namespace() -> str:
    return _NAMESPACE_PATH.read_text().strip()


def _client() -> httpx.Client:
    if not _TOKEN_PATH.exists():
        raise K8sUnavailable(f"ServiceAccount 토큰이 없다: {_TOKEN_PATH}")
    # 토큰은 주기적으로 회전된다. 파일을 매번 다시 읽어야 만료된 토큰을
    # 계속 쓰지 않는다 — 오래 도는 프로세스라 한 번 읽어 캐시하면 안 된다.
    token = _TOKEN_PATH.read_text().strip()
    return httpx.Client(
        base_url=_API,
        headers={"Authorization": f"Bearer {token}"},
        verify=str(_CA_PATH),
        timeout=5.0,
    )


def _scale_path(ns: str, deployment: str) -> str:
    return f"/apis/apps/v1/namespaces/{ns}/deployments/{deployment}/scale"


def get_replicas(ns: str, deployment: str) -> int | None:
    """현재 replicas. 못 읽으면 None — 호출자가 그 서비스만 건너뛴다."""
    try:
        with _client() as client:
            res = client.get(_scale_path(ns, deployment))
            res.raise_for_status()
            return res.json()["spec"]["replicas"]
    except (httpx.HTTPError, K8sUnavailable, KeyError):
        logger.exception("replicas 조회 실패: %s", deployment)
        return None


def set_replicas(ns: str, deployment: str, replicas: int) -> bool:
    """replicas 를 patch 한다. 성공했을 때만 True.

    실패를 삼키고 True 를 돌려주면 호출자의 "N건 확장" 로그가 거짓이 된다 —
    RBAC 이 안 붙은 상태(403)가 그 로그 뒤에 영원히 숨는다.
    """
    try:
        with _client() as client:
            res = client.patch(
                _scale_path(ns, deployment),
                json={"spec": {"replicas": replicas}},
                headers={"Content-Type": "application/merge-patch+json"},
            )
            res.raise_for_status()
            return True
    except (httpx.HTTPError, K8sUnavailable):
        logger.exception("replicas patch 실패: %s -> %s", deployment, replicas)
        return False


# ── KEDA ScaledObject ────────────────────────────────────────
#
# order-worker 는 Deployment 의 replicas 를 만지면 안 된다. KEDA 가 그 필드를
# 소유하고 SQS 큐 길이로 계속 조절하므로, 직접 patch 하면 다음 조절 주기에
# 되돌려진다(매니페스트에 replicas 필드 자체가 없는 이유이기도 하다).
#
# 대신 ScaledObject 의 minReplicaCount(바닥)만 올린다. KEDA 는 그 위에서
# 계속 자기 일을 한다 — 워머가 미리 올려둔 것으로 부족하면 KEDA 가 더 올린다.


def _scaledobject_path(ns: str, name: str) -> str:
    return f"/apis/keda.sh/v1alpha1/namespaces/{ns}/scaledobjects/{name}"


def get_min_replicas(ns: str, name: str) -> int | None:
    """ScaledObject 의 현재 minReplicaCount.

    이 필드는 생략 가능하다(KEDA 기본값 0). 없으면 0 으로 읽는다 — None 은
    "조회 실패" 라는 뜻으로만 쓴다.
    """
    try:
        with _client() as client:
            res = client.get(_scaledobject_path(ns, name))
            res.raise_for_status()
            return res.json().get("spec", {}).get("minReplicaCount", 0)
    except (httpx.HTTPError, K8sUnavailable):
        logger.exception("minReplicaCount 조회 실패: %s", name)
        return None


def set_min_replicas(ns: str, name: str, replicas: int) -> bool:
    try:
        with _client() as client:
            res = client.patch(
                _scaledobject_path(ns, name),
                json={"spec": {"minReplicaCount": replicas}},
                headers={"Content-Type": "application/merge-patch+json"},
            )
            res.raise_for_status()
            return True
    except (httpx.HTTPError, K8sUnavailable):
        logger.exception("minReplicaCount patch 실패: %s -> %s", name, replicas)
        return False
