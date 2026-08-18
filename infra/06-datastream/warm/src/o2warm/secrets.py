"""비밀값을 실행 시점에 읽습니다.

## 왜 환경변수로 넘기지 않는가

Terraform 변수로 받아 Lambda 환경변수에 넣으면 **S3 remote state 와 Lambda
콘솔에 평문으로 남습니다.** 저장 위치 이름만 넘기고 실행 시점에 읽으면
그 문제가 사라집니다. 콜드 스타트 때 한 번이라 조회 비용은 무시할 수준입니다.

## 왜 Datadog 과 조회 API 가 이 모듈을 공유하는가

두 곳에서 같은 일을 따로 구현하면 캐시 정책과 실패 처리가 갈립니다.
특히 실패 처리는 **호출자마다 안전한 방향이 반대**여서 (아래) 한 곳에
모아 두고 호출자가 결정하게 하는 편이 안전합니다.

## 실패를 값으로 구분합니다

`""` 과 `None` 을 다르게 씁니다. 이 구분이 이 모듈의 핵심입니다.

| 반환 | 뜻 | 호출자가 할 일 |
|---|---|---|
| `""`   | 출처가 아예 지정되지 않았다 (미설정) | 각자 판단 |
| `None` | 출처는 있는데 읽지 못했다 (오류)     | **막는다** |
| 값     | 성공                                  | 쓴다 |

둘을 합치면 조회 실패가 "키 미설정"으로 보입니다. 조회 API 는 키가 없으면
인증을 통과시키므로(로컬 운영 배려), 합쳐 두면 **SSM 이 일시적으로 흔들릴
때 엔드포인트가 열립니다.** 실패는 반드시 미설정과 달라야 합니다.

## 캐시

성공은 프로세스 수명 동안 유지합니다. 실패는 짧게만 기억합니다 —
영구 캐시하면 콜드 스타트 때의 일시적 오류가 그 컨테이너를 계속
망가진 상태로 두고, 캐시를 아예 안 하면 집계 Lambda 가 2초마다 실패한
조회를 반복합니다.
"""

from __future__ import annotations

import sys
import time

NEGATIVE_TTL = 60.0

# key -> (만료 시각, 값)  값이 None 이면 실패를 기억하는 중입니다.
_cache: dict[str, tuple[float, str | None]] = {}


def resolve(
    *,
    value: str = "",
    ssm_param: str = "",
    secret_id: str = "",
    secret_property: str = "",
    region: str | None = None,
) -> str | None:
    """지정된 출처에서 비밀값을 찾습니다.

    출처 우선순위는 **직접 주입 → Secrets Manager → SSM** 입니다.
    Secrets Manager 가 SSM 보다 앞인 것은 이 저장소의 원본이 그쪽이기
    때문입니다(`o2/dev/datadog`). SSM 은 대안 경로로 남겨 둡니다.

    반환값의 의미는 모듈 docstring 의 표를 따릅니다.
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

    return ""  # 출처 없음 — 오류가 아닙니다


def datadog_api_key() -> str:
    """Datadog 전송용 키. 실패와 미설정을 구분하지 않습니다.

    전송은 부가 작업이고 둘 다 결과가 같습니다 — 보내지 않는다.
    (`datadog.py` 모듈 docstring 의 "실패해도 집계를 막지 않습니다" 참고)
    """
    from .settings import settings

    return (
        resolve(
            value=settings.dd_api_key,
            secret_id=settings.dd_secret,
            secret_property=settings.dd_secret_property,
            ssm_param=settings.dd_param,
        )
        or ""
    )


def warm_api_key() -> str | None:
    """조회 API 인증용 키. **실패와 미설정을 반드시 구분합니다.**

    `None` 이면 호출자는 요청을 거절해야 합니다. 여기서 `""` 로 뭉개면
    조회 실패가 "인증 없음"으로 읽혀 엔드포인트가 열립니다.
    """
    from .settings import settings

    return resolve(value=settings.api_key, ssm_param=settings.api_key_param)


def clear_cache() -> None:
    """테스트용. 런타임에서 부를 일은 없습니다."""
    _cache.clear()


def _cached(key: str, fetch) -> str | None:
    hit = _cache.get(key)
    if hit is not None:
        expires, cached = hit
        if cached is not None or expires > time.time():
            return cached

    got = fetch()
    # 성공은 만료 없이(0 은 위 조건에서 검사되지 않습니다), 실패는 짧게.
    _cache[key] = (0.0 if got is not None else time.time() + NEGATIVE_TTL, got)
    return got


def _client(service: str, region: str | None):
    import boto3

    from .settings import settings

    return boto3.client(service, region_name=region or settings.region)


def _from_secrets_manager(secret_id: str, prop: str, region: str | None) -> str | None:
    """SecretString 이 JSON 이면 property 를, 아니면 문자열 전체를 씁니다.

    `o2/dev/datadog` 은 `{"api-key": ..., "app-key": ...}` 형태라 property 가
    필요합니다. 단일 문자열 시크릿도 받아들이는 편이 호출자를 단순하게 합니다.
    """
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
        # property 를 지정했는데 JSON 이 아니면 설정이 틀린 것입니다.
        # 문자열 전체를 키로 쓰면 엉뚱한 값이 조용히 전송되므로 막습니다.
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
    sys.stderr.write(f"[o2warm] {msg}\n")
