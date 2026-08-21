"""비밀값을 실행 시점에 읽는다.

o2warm/secrets.py 와 같은 규칙이다 — 두 패키지가 Function URL(인증 없이
인터넷에 노출)이라는 같은 위험을 안고 있어서, 실패 처리를 각자 다르게
하면 한쪽만 조용히 열린 채로 배포되기 쉽다.

## 실패를 값으로 구분한다

`""` 과 `None` 을 다르게 쓴다.

| 반환 | 뜻 | 호출자가 할 일 |
|---|---|---|
| `""`   | 출처가 아예 지정되지 않았다 (미설정) | 각자 판단 |
| `None` | 출처는 있는데 읽지 못했다 (오류)     | **막는다** |
| 값     | 성공                                  | 쓴다 |

`hot_api_key()`(조회 API 인증)는 이 표를 그대로 따른다 — 미설정은 로컬
운영으로 보고 열어 주지만, 조회 실패는 반드시 막는다.

`datadog_api_key()`/`datadog_app_key()`(Datadog 역쿼리)는 다르게 쓴다.
Hot API 의 존재 이유가 Datadog 조회이므로 미설정과 조회 실패 둘 다
호출자(datadog.py)가 즉시 에러로 바꾼다 — Warm 의 "미설정=열어준다"와
달리 여기서 "미설정=일단 진행"은 뜻이 없다.

조회 API 자체의 인증용 키는 여기 없다 — Function URL 이 AWS_IAM(SigV4)
이라 이 코드에 닿기 전에 AWS 가 이미 검증한다(`o2-warm-api` 의
X-O2-Key 와 다른 점. `../../../hot-path.tf` 머리말의 D-031 참고).

## 캐시

성공은 프로세스 수명 동안 유지한다. 실패는 짧게만 기억한다 — 영구
캐시하면 콜드 스타트 때의 일시적 오류가 그 컨테이너를 계속 망가진
상태로 둔다.
"""

from __future__ import annotations

import sys
import time

NEGATIVE_TTL = 60.0

# key -> (만료 시각, 값)  값이 None 이면 실패를 기억하는 중이다.
_cache: dict[str, tuple[float, str | None]] = {}


def resolve(
    *,
    value: str = "",
    ssm_param: str = "",
    secret_id: str = "",
    secret_property: str = "",
    region: str | None = None,
) -> str | None:
    """지정된 출처에서 비밀값을 찾는다.

    출처 우선순위는 **직접 주입 → Secrets Manager → SSM** 이다.
    반환값의 의미는 모듈 docstring 의 표를 따른다.
    """
    if value:
        return value

    if secret_id:
        return _cached(
            f"sm:{secret_id}:{secret_property}",
            lambda: _from_secrets_manager(secret_id, secret_property, region),
        )

    if ssm_param:
        return _cached(f"ssm:{ssm_param}", lambda: _from_ssm(ssm_param, region))

    return ""  # 출처 없음 — 오류가 아니다


def datadog_api_key() -> str | None:
    from .settings import settings

    return resolve(
        secret_id=settings.dd_secret,
        secret_property=settings.dd_secret_api_property,
        ssm_param=settings.dd_api_param,
    )


def datadog_app_key() -> str | None:
    from .settings import settings

    return resolve(
        secret_id=settings.dd_secret,
        secret_property=settings.dd_secret_app_property,
    )


def clear_cache() -> None:
    """테스트용. 런타임에서 부를 일은 없다."""
    _cache.clear()


def _cached(key: str, fetch) -> str | None:
    hit = _cache.get(key)
    if hit is not None:
        expires, cached = hit
        if cached is not None or expires > time.time():
            return cached

    got = fetch()
    # 성공은 만료 없이(0 은 위 조건에서 검사되지 않는다), 실패는 짧게.
    _cache[key] = (0.0 if got is not None else time.time() + NEGATIVE_TTL, got)
    return got


def _client(service: str, region: str | None):
    import boto3

    from .settings import settings

    return boto3.client(service, region_name=region or settings.region)


def _from_secrets_manager(secret_id: str, prop: str, region: str | None) -> str | None:
    try:
        raw = _client("secretsmanager", region).get_secret_value(SecretId=secret_id)["SecretString"]
    except Exception as e:
        _warn(f"Secrets Manager {secret_id} 조회 실패: {e}")
        return None

    if not prop:
        return raw

    import json

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        _warn(f"Secrets Manager {secret_id} 가 JSON 이 아닙니다 (property={prop})")
        return None

    got = parsed.get(prop)
    if not got:
        _warn(f"Secrets Manager {secret_id} 에 property '{prop}' 가 없습니다")
        return None
    return got


def _from_ssm(name: str, region: str | None) -> str | None:
    try:
        return _client("ssm", region).get_parameter(Name=name, WithDecryption=True)[
            "Parameter"
        ]["Value"]
    except Exception as e:
        _warn(f"SSM {name} 조회 실패: {e}")
        return None


def _warn(msg: str) -> None:
    sys.stderr.write(f"[o2hot] {msg}\n")
