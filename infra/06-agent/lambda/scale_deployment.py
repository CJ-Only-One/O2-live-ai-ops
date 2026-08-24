"""Deployment replicas 를 patch 하는 조치 실행기.

S2(docs/scenario-experiment.md 0.6) "느린 파드 격리" 조치와 그 조치의 원복
(rollback)이 둘 다 이 엔드포인트다 — "0으로 줄이기"와 "원래 값으로
되돌리기"는 replicas 파라미터만 다른 같은 동작이라 실행기를 하나로 뒀다.
개별 Pod 를 지우지 않는 이유: Deployment 가 즉시 같은 스펙으로 다시 만들기
때문에, 격리하려면 Deployment 자체의 replicas 를 조정해야 한다.

권한은 EKS Access Entry + o2-dev 네임스페이스 deployments/scale 서브리소스
get·patch 뿐이다(infra/04-platform 의 RBAC — 이 파일과 다른 스택). 그 밖은
K8s 쪽에서 403 이 난다 — 이 코드가 잘못된 인자를 받아도 클러스터에서 더
할 수 있는 게 없다.

요청: {"namespace": "o2-dev", "deployment": "chat-gateway-canary", "replicas": 0}
응답: {"deployment": ..., "previous_replicas": N, "replicas": 0, "already_at_target": bool}

★ Precheck 재확인 — 이미 목표 replicas 면 patch 를 안 보내고 그대로 성공
  응답한다(멱등). Dify 의 Precheck 노드가 이미 한 번 확인했더라도 그 뒤로
  시간이 지났으므로 여기서 다시 GET 해서 재확인한다.
"""

import base64
import hmac
import json
import os
import ssl
import urllib.error
import urllib.request

import boto3
import botocore.session
from botocore.signers import RequestSigner

CLUSTER_NAME = os.environ["CLUSTER_NAME"]
CLUSTER_ENDPOINT = os.environ["CLUSTER_ENDPOINT"]
CLUSTER_CA = os.environ["CLUSTER_CA"]  # base64. EKS 가 주는 그대로 넣는다.
REGION = os.environ["AWS_REGION"]
SECRET_NAME = os.environ["SCALE_EXECUTOR_SECRET_NAME"]
API_KEY_HEADER = "x-api-key"

# 이 실행기가 건드릴 수 있는 유일한 네임스페이스. RBAC 도 같은 범위지만
# 여기서도 한 번 더 막는다 — 잘못된 인자가 K8s 까지 안 가고 여기서 죽는다.
ALLOWED_NAMESPACE = "o2-dev"

_secrets = None
_ca_file = "/tmp/eks-ca.crt"


def _load_secrets():
    global _secrets
    if _secrets is None:
        raw = boto3.client("secretsmanager").get_secret_value(SecretId=SECRET_NAME)
        _secrets = json.loads(raw["SecretString"])
    return _secrets


def _eks_bearer_token() -> str:
    """aws-iam-authenticator 토큰 스펙. STS GetCallerIdentity 를 presign 하고
    x-k8s-aws-id 헤더에 클러스터 이름을 실어, K8s API 서버가 그 서명을
    검증해 이 Lambda 의 IAM Role 을 신원으로 받아들이게 한다. kubectl 이나
    aws-iam-authenticator 바이너리 없이 botocore 만으로 만든다."""
    session = botocore.session.get_session()
    client = session.create_client("sts", region_name=REGION)
    signer = RequestSigner(
        client.meta.service_model.service_id,
        REGION,
        "sts",
        "v4",
        session.get_credentials(),
        session.get_component("event_emitter"),
    )
    params = {
        "method": "GET",
        "url": f"https://sts.{REGION}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15",
        "body": {},
        "headers": {"x-k8s-aws-id": CLUSTER_NAME},
        "context": {},
    }
    signed_url = signer.generate_presigned_url(
        params, region_name=REGION, expires_in=60, operation_name=""
    )
    return "k8s-aws-v1." + base64.urlsafe_b64encode(signed_url.encode()).decode().rstrip("=")


def _ca_bundle_path() -> str:
    # urllib 는 파일 경로만 받는다. 콜드 스타트마다 한 번 /tmp 에 푼다.
    if not os.path.exists(_ca_file):
        with open(_ca_file, "wb") as f:
            f.write(base64.b64decode(CLUSTER_CA))
    return _ca_file


def _k8s_request(method: str, path: str, body: dict | None = None) -> dict:
    token = _eks_bearer_token()
    url = f"{CLUSTER_ENDPOINT}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        req.add_header("Content-Type", "application/merge-patch+json")

    ctx = ssl.create_default_context(cafile=_ca_bundle_path())
    with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
        return json.loads(resp.read())


def lambda_handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    secrets = _load_secrets()

    received = headers.get(API_KEY_HEADER) or ""
    expected = secrets["scale-executor-api-key"]
    if not hmac.compare_digest(received, expected):
        # ★ 실제 값은 로그에 안 남긴다 — runbook_lookup.py 와 같은 이유.
        print(
            "rejected: bad api key",
            "received_len=", len(received),
            "expected_len=", len(expected),
        )
        return {"statusCode": 403, "body": json.dumps({"error": "forbidden"})}

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError as e:
        return {"statusCode": 400, "body": json.dumps({"error": f"bad json: {e}"})}

    namespace = body.get("namespace")
    deployment = body.get("deployment")
    replicas = body.get("replicas")

    if namespace != ALLOWED_NAMESPACE:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"namespace must be '{ALLOWED_NAMESPACE}'"}),
        }
    if not deployment or not isinstance(deployment, str):
        return {"statusCode": 400, "body": json.dumps({"error": "deployment required"})}
    if not isinstance(replicas, int) or isinstance(replicas, bool) or replicas < 0:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "replicas must be a non-negative integer"}),
        }

    scale_path = f"/apis/apps/v1/namespaces/{namespace}/deployments/{deployment}/scale"

    try:
        current = _k8s_request("GET", scale_path)
    except urllib.error.HTTPError as e:
        return {
            "statusCode": e.code,
            "body": json.dumps({"error": f"get failed: {e.read().decode()[:500]}"}),
        }

    previous_replicas = current.get("spec", {}).get("replicas")

    # Precheck 재확인 — 이미 목표치면 patch 를 보내지 않는다(멱등).
    if previous_replicas == replicas:
        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "deployment": deployment,
                    "previous_replicas": previous_replicas,
                    "replicas": replicas,
                    "already_at_target": True,
                }
            ),
        }

    try:
        _k8s_request("PATCH", scale_path, {"spec": {"replicas": replicas}})
    except urllib.error.HTTPError as e:
        return {
            "statusCode": e.code,
            "body": json.dumps({"error": f"patch failed: {e.read().decode()[:500]}"}),
        }

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "deployment": deployment,
                "previous_replicas": previous_replicas,
                "replicas": replicas,
                "already_at_target": False,
            }
        ),
    }
