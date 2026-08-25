"""o2-hot-proxy — Dify 가 SigV4 를 못 해서 대신 서명해 주는 중계기.

## 왜 있나

`o2-hot-api`(06-datastream)의 Function URL 은 `authorization_type = AWS_IAM`
이다. 공개(`NONE`)로 열 수 없기 때문이다 — 이 계정은 Organizations 멤버
계정이라 공개 Function URL 이 조직 정책에 403 으로 막힌다(D-031, D-042).

그런데 Dify 의 Custom Tool 은 AWS 서명을 못 한다. **이 버전(1.16.1)의
소스에 그런 선택지 자체가 없다.**

    core/tools/entities/tool_entities.py
    class ApiProviderAuthType(StrEnum):
        NONE, API_KEY_HEADER, API_KEY_QUERY      # 이게 전부다

그래서 Dify 는 이 프록시를 평범한 HTTP 로 부르고, 서명은 여기서 한다.
자격증명은 EC2 인스턴스 역할(`o2-dev-dify-role`)을 IMDS 에서 받는다 —
프록시가 키를 보관하지 않는다.

    Dify api ──▶ ssrf_proxy(squid) ──▶ 이 프록시 ──SigV4──▶ o2-hot-api

## 왜 boto3 로 서명하나

**자격증명이 만료되기 때문이다.** IMDS 가 주는 것은 임시 자격증명이라
주기적으로 갱신해야 한다. `Session.get_credentials()` 가 돌려주는 객체는
갱신을 알아서 하므로, 요청마다 `get_frozen_credentials()` 로 그때의 값을
꺼내 쓰면 된다. 손으로 서명하면 이 갱신을 직접 구현해야 하고, 만료는
**한참 뒤에 403 으로만** 드러나서 원인을 찾기 어렵다.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin, urlparse

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

UPSTREAM = os.environ["O2_HOT_API_URL"].rstrip("/")
REGION = os.getenv("AWS_REGION", "ap-northeast-2")
PORT = int(os.getenv("PORT", "8788"))

# Dify 쪽 인증. 비우면 인증 없이 받는다 — 이 프록시는 docker 네트워크
# 안에만 떠 있고 포트를 호스트로 내보내지 않으므로 그것만으로도 닫혀
# 있지만, 넣어 두면 같은 네트워크의 다른 컨테이너까지 막힌다.
# Dify 에서는 Custom Tool 의 API_KEY_HEADER 로 넣는다.
PROXY_KEY = os.getenv("O2_HOT_PROXY_KEY", "")
PROXY_KEY_HEADER = os.getenv("O2_HOT_PROXY_KEY_HEADER", "x-o2-proxy-key").lower()

# Dify가 쓰는 논리 계약만 통과시킨다. raw Datadog query endpoint는 운영자가
# Lambda를 직접 진단할 때만 쓰며 이 서명 프록시에는 노출하지 않는다.
ALLOWED_PATHS = {"/v1/hot/health", "/v1/hot/datadog/metric"}

_session = boto3.Session()
_credentials = _session.get_credentials()  # 갱신을 스스로 하는 객체다

if _credentials is None:
    sys.stderr.write(
        "[hot-proxy] AWS 자격증명을 찾지 못했습니다. "
        "인스턴스 역할과 IMDS 홉 제한(2)을 확인하세요.\n"
    )
    raise SystemExit(1)


def _sign(method: str, url: str, body: bytes, content_type: str | None) -> dict:
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type

    req = AWSRequest(method=method, url=url, data=body or None, headers=headers)
    SigV4Auth(_credentials.get_frozen_credentials(), "lambda", REGION).add_auth(req)
    return dict(req.prepare().headers)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "o2-hot-proxy"

    def log_message(self, fmt, *args):  # 기본 구현은 stderr 로 간다
        sys.stdout.write("[hot-proxy] %s\n" % (fmt % args))

    def _send(self, status: int, payload: dict | bytes, content_type: str | None = None):
        body = payload if isinstance(payload, bytes) else json.dumps(
            payload, ensure_ascii=False
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type or "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        if not PROXY_KEY:
            return True
        given = self.headers.get(PROXY_KEY_HEADER) or ""
        # 길이가 다르면 compare_digest 가 예외를 내지 않도록 문자열로 맞춘다
        import hmac

        return hmac.compare_digest(given, PROXY_KEY)

    def _proxy(self, method: str):
        path = urlparse(self.path).path

        # 프록시 자신의 상태 확인. AWS 를 부르지 않는다 — 서명이나 자격증명
        # 문제와 "프록시가 떠 있는가" 를 섞지 않기 위해서다.
        if path == "/healthz":
            return self._send(200, {"ok": True, "upstream": UPSTREAM})

        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})

        if path not in ALLOWED_PATHS:
            return self._send(
                403, {"error": "forbidden_path", "allowed": sorted(ALLOWED_PATHS)}
            )

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        content_type = self.headers.get("Content-Type")

        url = urljoin(UPSTREAM + "/", path.lstrip("/"))
        if urlparse(self.path).query:
            url += "?" + urlparse(self.path).query

        try:
            headers = _sign(method, url, body, content_type)
        except Exception as e:  # 자격증명 만료·IMDS 장애가 여기로 온다
            sys.stderr.write(f"[hot-proxy] 서명 실패: {e}\n")
            return self._send(500, {"error": "signing_failed", "detail": str(e)})

        req = urllib.request.Request(url, data=body or None, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return self._send(
                    resp.status, resp.read(), resp.headers.get("Content-Type")
                )
        except urllib.error.HTTPError as e:
            # 상류의 상태코드와 본문을 그대로 넘긴다. 여기서 200 으로
            # 바꾸면 Dify 가 실패를 성공으로 읽는다(T-011 과 같은 함정).
            return self._send(e.code, e.read(), e.headers.get("Content-Type"))
        except Exception as e:
            sys.stderr.write(f"[hot-proxy] 상류 호출 실패: {e}\n")
            return self._send(502, {"error": "upstream_failed", "detail": str(e)})

    def do_GET(self):
        self._proxy("GET")

    def do_POST(self):
        self._proxy("POST")


if __name__ == "__main__":
    sys.stdout.write(f"[hot-proxy] listening on :{PORT} → {UPSTREAM}\n")
    sys.stdout.flush()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
