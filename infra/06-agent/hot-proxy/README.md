# o2-hot-proxy — Dify 를 위한 SigV4 중계기

Dify 가 `o2-hot-api`(06-datastream)를 부를 수 있게 **서명만 대신** 해 준다.

```
Dify api ──▶ ssrf_proxy(squid) ──▶ hot-proxy ──SigV4──▶ o2-hot-api ──▶ Datadog
```

> **Terraform 이 만들지 않는다.** `dify/` 와 같은 성격의 폴더다 — 호스트에서
> 사람이 올린다. Terraform 이 만드는 것은 Lambda 쪽(06-datastream/hot-path.tf)과
> 인스턴스 역할 권한(../iam.tf)까지다.

## 왜 필요한가

`o2-hot-api` 의 Function URL 은 `AWS_IAM` 이다. 공개(`NONE`)로 못 연다 —
이 계정은 Organizations 멤버 계정이라 공개 Function URL 이 조직 정책에
403 으로 막힌다(D-031, D-042).

그런데 **Dify 는 AWS 서명을 못 한다.** 이 버전(1.16.1) 소스에 선택지 자체가 없다.

```python
# core/tools/entities/tool_entities.py
class ApiProviderAuthType(StrEnum):
    NONE, API_KEY_HEADER, API_KEY_QUERY      # 이게 전부다
```

그래서 Dify 는 평범한 HTTP 로 이 프록시를 부르고, 서명은 프록시가 한다.
자격증명은 인스턴스 역할(`o2-dev-dify-role`)을 IMDS 에서 받으므로
**프록시가 키를 보관하지 않는다.**

## 파일

| 파일 | 무엇 |
|---|---|
| `app.py` | 프록시 본체. 표준 라이브러리 + boto3(서명·자격증명 갱신) |
| `Dockerfile` | `python:3.12-slim` + boto3 |
| `docker-compose.hot-proxy.yaml` | Dify compose 에 얹는 조각 |
| `openapi.yaml` | **Dify Custom Tool 에 붙여넣을 스키마** |

## 배포

호스트에서 사람이 한다. `/opt/o2-hot-proxy/` 에 이 폴더를 올린다.

```bash
# 1) 이미지 빌드 (compose 의 -f 중첩에서 build context 가 헷갈리지 않게 분리한다)
sudo docker build -t o2-hot-proxy:latest /opt/o2-hot-proxy

# 2) Dify .env 에 두 줄
#    O2_HOT_API_URL                    ← 06-datastream 의 terraform output -raw hot_api_url
#    SSRF_PROXY_ALLOW_PRIVATE_DOMAINS  ← squid 가 이 컨테이너에 닿게 허용
sudo vi /opt/dify/docker/.env
#   O2_HOT_API_URL=https://<...>.lambda-url.ap-northeast-2.on.aws
#   SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=hot-proxy

# 3) 올리고, squid 를 다시 만든다(allowlist 는 부팅 때 생성된다)
cd /opt/dify/docker
C="sudo docker compose -f docker-compose.yaml -f /opt/o2-hot-proxy/docker-compose.hot-proxy.yaml"
$C up -d hot-proxy
$C up -d --force-recreate ssrf_proxy
```

`SSRF_PROXY_ALLOW_PRIVATE_DOMAINS` 를 빼먹으면 squid 의
`http_access deny to_private_networks` 에 걸려 Dify 에서만 실패한다.
프록시를 직접 부르면 되는데 Dify 에서만 안 되는 모양이라 원인이 잘 안 보인다.

### 확인

```bash
# squid 가 allowlist 를 만들었나
sudo docker exec docker-ssrf_proxy-1 cat /etc/squid/dify_allow_private.conf
#   acl dify_allowed_private_domains dstdomain hot-proxy
#   http_access allow client_localnet dify_allowed_private_domains

# Dify 가 실제로 가는 경로(squid 경유)로 때려 본다 — 이게 진짜 확인이다
sudo docker exec docker-api-1 sh -c 'curl -s --proxy http://ssrf_proxy:3128 \
  -X POST http://hot-proxy:8788/v1/hot/datadog/query \
  -H "Content-Type: application/json" -d "{\"query\":\"avg:system.cpu.user{*}\"}"'
```

## Dify 에 붙이기

스튜디오 → **도구** → **사용자 지정 도구 만들기** → `openapi.yaml` 내용을 붙여넣는다.

| 항목 | 값 |
|---|---|
| 스키마 | `openapi.yaml` |
| 인증 | `O2_HOT_PROXY_KEY` 를 썼으면 `API Key · Header`, 헤더 이름 `X-O2-Proxy-Key`. 안 썼으면 `None` |

워크플로에 넣은 뒤에는 **게시(Publish)** 해야 API 로 도는 버전에 반영된다
(`../dify/README.md` 3절과 같은 이유).

## 알아둘 것

### 두 망에 모두 붙어야 한다

`ssrf_proxy_network` 는 `internal: true` 라 바깥으로 못 나간다. 거기만
붙이면 IMDS 에 못 닿아 **자격증명을 못 받고 재시작을 반복한다.**
`default` 도 함께 붙인다 — Dify 의 api·worker 가 이미 그 모양이다.

### 툴 호출 타임아웃이 5초다

```
SSRF_DEFAULT_TIME_OUT=5   SSRF_DEFAULT_READ_TIME_OUT=5
```

실측은 **0.6초**(squid 경유, Datadog 왕복 포함)라 지금은 여유가 있다.
Lambda 콜드 스타트가 겹치면 2~3초까지 올라간다. 더 무거운 쿼리를 붙일
생각이면 `.env` 에서 이 값을 올린다.

### 경로를 좁혀 두었다

`/v1/hot/` 아래만 통과시킨다(`O2_HOT_ALLOWED_PREFIX`). 서명을 대신 해 주는
물건이라 경로를 그대로 믿으면 같은 자격증명으로 다른 것을 부르는 통로가 된다.

### 호스트로 포트를 내보내지 않는다

docker 네트워크 안에서만 보인다. 내보내면 "서명을 대신 해 주는 창구" 가
인스턴스 밖으로 열린다.
