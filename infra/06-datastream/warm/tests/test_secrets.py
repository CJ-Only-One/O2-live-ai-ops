"""비밀값 조회와 그 실패 처리.

여기서 지키는 것은 한 문장입니다 — **조회 실패는 인증 미설정과 달라야 한다.**
둘이 같아지면 Function URL 이 SSM 장애 중에 열립니다. 그 회귀를 막는 것이
`test_auth_*` 들의 목적입니다.
"""

from __future__ import annotations

import json

import pytest

import serve
from o2warm import secrets
from o2warm.settings import settings


@pytest.fixture(autouse=True)
def _clean():
    secrets.clear_cache()
    yield
    secrets.clear_cache()


class FakeSM:
    """Secrets Manager 대역. 호출 횟수를 세어 캐시를 검증합니다."""

    def __init__(self, payload, *, fail=False):
        self.payload = payload
        self.fail = fail
        self.calls = 0

    def get_secret_value(self, SecretId):  # noqa: N803 — boto3 시그니처
        self.calls += 1
        if self.fail:
            raise RuntimeError("AccessDeniedException")
        return {"SecretString": self.payload}


class FakeSSM:
    def __init__(self, value, *, fail=False):
        self.value = value
        self.fail = fail
        self.calls = 0

    def get_parameter(self, Name, WithDecryption):  # noqa: N803
        self.calls += 1
        if self.fail:
            raise RuntimeError("ParameterNotFound")
        return {"Parameter": {"Value": self.value}}


@pytest.fixture
def patch_client(monkeypatch):
    """`secrets._client` 를 갈아끼웁니다. boto3 를 부르지 않습니다."""

    def install(**by_service):
        monkeypatch.setattr(secrets, "_client", lambda svc, region: by_service[svc])
        return by_service

    return install


# ── 출처별 조회 ───────────────────────────────────────────────


def test_direct_value_wins_without_any_lookup(patch_client):
    sm = FakeSM(json.dumps({"api-key": "from-sm"}))
    patch_client(secretsmanager=sm)

    got = secrets.resolve(value="injected", secret_id="o2/dev/datadog", secret_property="api-key")

    assert got == "injected"
    assert sm.calls == 0


def test_secrets_manager_json_property(patch_client):
    patch_client(secretsmanager=FakeSM(json.dumps({"api-key": "dd-key", "app-key": "other"})))

    assert secrets.resolve(secret_id="o2/dev/datadog", secret_property="api-key") == "dd-key"


def test_secrets_manager_plain_string_when_no_property(patch_client):
    patch_client(secretsmanager=FakeSM("bare-secret"))

    assert secrets.resolve(secret_id="o2/plain", secret_property="") == "bare-secret"


def test_secrets_manager_takes_precedence_over_ssm(patch_client):
    """원본이 Secrets Manager 라 그쪽이 먼저입니다."""
    ssm = FakeSSM("from-ssm")
    patch_client(secretsmanager=FakeSM(json.dumps({"api-key": "from-sm"})), ssm=ssm)

    got = secrets.resolve(
        secret_id="o2/dev/datadog", secret_property="api-key", ssm_param="/o2/datadog/api-key"
    )

    assert got == "from-sm"
    assert ssm.calls == 0


def test_ssm_used_when_no_secret_id(patch_client):
    patch_client(ssm=FakeSSM("param-value"))

    assert secrets.resolve(ssm_param="/o2/warm/api-key") == "param-value"


def test_no_source_is_empty_string_not_none():
    """미설정은 오류가 아닙니다. 이 구분이 인증 로직의 근거입니다."""
    assert secrets.resolve() == ""


# ── 실패 ─────────────────────────────────────────────────────


def test_lookup_failure_returns_none(patch_client):
    patch_client(secretsmanager=FakeSM(None, fail=True))

    assert secrets.resolve(secret_id="o2/dev/datadog", secret_property="api-key") is None


def test_missing_property_returns_none(patch_client):
    """시크릿은 읽혔지만 property 가 없으면 설정이 틀린 것입니다."""
    patch_client(secretsmanager=FakeSM(json.dumps({"app-key": "only-this"})))

    assert secrets.resolve(secret_id="o2/dev/datadog", secret_property="api-key") is None


def test_non_json_with_property_returns_none(patch_client):
    """엉뚱한 값을 키로 써서 조용히 전송하는 것보다 실패가 낫습니다."""
    patch_client(secretsmanager=FakeSM("not-json"))

    assert secrets.resolve(secret_id="o2/dev/datadog", secret_property="api-key") is None


# ── 캐시 ─────────────────────────────────────────────────────


def test_success_is_cached(patch_client):
    sm = FakeSM(json.dumps({"api-key": "dd-key"}))
    patch_client(secretsmanager=sm)

    for _ in range(3):
        assert secrets.resolve(secret_id="o2/dev/datadog", secret_property="api-key") == "dd-key"

    assert sm.calls == 1


def test_failure_is_not_cached_forever(patch_client, monkeypatch):
    """콜드 스타트 때의 일시적 오류가 컨테이너를 계속 망가뜨리면 안 됩니다."""
    sm = FakeSM(None, fail=True)
    patch_client(secretsmanager=sm)

    assert secrets.resolve(secret_id="o2/x", secret_property="k") is None
    assert secrets.resolve(secret_id="o2/x", secret_property="k") is None
    assert sm.calls == 1  # TTL 안에서는 재조회하지 않습니다

    # TTL 이 지나면 다시 시도하고, 그 사이 복구됐으면 성공합니다.
    # 고정 epoch 을 쓰면 안 됩니다 — 현재보다 과거면 만료가 지나가지 않습니다.
    future = secrets.time.time() + secrets.NEGATIVE_TTL + 1
    monkeypatch.setattr(secrets.time, "time", lambda: future)
    sm.fail = False
    sm.payload = json.dumps({"k": "recovered"})

    assert secrets.resolve(secret_id="o2/x", secret_property="k") == "recovered"
    assert sm.calls == 2


# ── 조회 API 인증 ────────────────────────────────────────────


def _request(key: str | None = None) -> dict:
    headers = {"X-O2-Key": key} if key is not None else {}
    return {"headers": headers, "requestContext": {"http": {"method": "GET", "path": "/v1/warm/health"}}}


def test_auth_open_when_no_source_configured(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "")
    monkeypatch.setattr(settings, "api_key_param", "")

    assert serve._authorized(_request()) is True


def test_auth_closed_when_lookup_fails(monkeypatch, patch_client):
    """**이 테스트가 이 파일의 이유입니다.**

    출처는 지정됐는데 읽지 못한 상황입니다. 예전 구현은 빈 문자열로
    뭉개 인증을 통과시켰습니다 — SSM 장애가 곧 엔드포인트 개방이었습니다.
    """
    monkeypatch.setattr(settings, "api_key", "")
    monkeypatch.setattr(settings, "api_key_param", "/o2/warm/api-key")
    patch_client(ssm=FakeSSM(None, fail=True))

    assert serve._authorized(_request()) is False
    assert serve._authorized(_request("아무값")) is False


def test_auth_matches_key_from_ssm(monkeypatch, patch_client):
    monkeypatch.setattr(settings, "api_key", "")
    monkeypatch.setattr(settings, "api_key_param", "/o2/warm/api-key")
    patch_client(ssm=FakeSSM("real-key"))

    assert serve._authorized(_request("real-key")) is True
    assert serve._authorized(_request("wrong-key")) is False
    assert serve._authorized(_request()) is False


def test_handler_returns_401_when_key_unreadable(monkeypatch, patch_client):
    """`_authorized` 만 맞고 핸들러가 통과시키면 의미가 없습니다."""
    monkeypatch.setattr(settings, "api_key", "")
    monkeypatch.setattr(settings, "api_key_param", "/o2/warm/api-key")
    patch_client(ssm=FakeSSM(None, fail=True))

    assert serve.handler(_request("아무값"), None)["statusCode"] == 401


# ── Datadog 쪽은 실패와 미설정을 구분하지 않습니다 ──────────


def test_datadog_key_collapses_failure_to_empty(monkeypatch, patch_client):
    """전송은 부가 작업이라 둘 다 결과가 같습니다 — 보내지 않는다."""
    monkeypatch.setattr(settings, "dd_api_key", "")
    monkeypatch.setattr(settings, "dd_secret", "o2/dev/datadog")
    monkeypatch.setattr(settings, "dd_secret_property", "api-key")
    monkeypatch.setattr(settings, "dd_param", "")
    patch_client(secretsmanager=FakeSM(None, fail=True))

    assert secrets.datadog_api_key() == ""


def test_datadog_submit_skips_without_key(monkeypatch):
    """키가 없으면 HTTP 를 시도조차 하지 않습니다."""
    from o2warm import datadog

    monkeypatch.setattr(datadog, "api_key", lambda: "")

    def explode(*a, **k):
        raise AssertionError("키가 없는데 전송을 시도했습니다")

    monkeypatch.setattr(datadog.urllib.request, "urlopen", explode)

    assert datadog.submit([{"metric": "o2.warm.rps", "points": []}]) is False


def test_datadog_configured_sees_secret_source(monkeypatch):
    monkeypatch.setattr(settings, "dd_api_key", "")
    monkeypatch.setattr(settings, "dd_param", "")
    monkeypatch.setattr(settings, "dd_secret", "o2/dev/datadog")

    assert settings.datadog_configured is True
