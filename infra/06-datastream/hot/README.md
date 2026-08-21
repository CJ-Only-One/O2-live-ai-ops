# Hot Path

Agent(Dify)가 `@webhook-dify` 알림을 받은 뒤 Datadog 에 보관된 인프라/APM
시계열 지표를 직접 역쿼리하기 위한 게이트웨이입니다.
`docs/DatadogMcpQueryInstruction.md` 구현안 A(HTTP REST API Gateway)를
구현합니다.

```
hot/
├── src/o2hot/
│   ├── settings.py   환경변수 → 설정 (값이 아니라 출처 이름만)
│   ├── secrets.py    Secrets Manager/SSM 실행 시점 조회 + 캐시
│   └── datadog.py    Datadog v1 /query 역쿼리
├── handlers/
│   └── serve.py      Lambda o2-hot-api
└── README.md          (이 파일)
```

Terraform 은 한 단계 위의 `hot-path.tf`.

## Warm/Cold 와의 관계

| 구분 | 데이터 출처 | 지연 | 담당 |
| --- | --- | --- | --- |
| **Hot** (이 디렉터리) | Datadog SaaS (인프라/APM 시계열) | 5~10초 | `o2-hot-api` |
| Warm | DynamoDB (`o2-agent-context`, 10초 사전집계) | 1~2ms | `o2-warm-api` (`../warm/`) |
| Cold | S3 Data Lake (원시 이벤트, Athena SQL) | 60초~ | `o2-warm-api` 의 `/v1/warm/athena` (별도 `o2-cold-api` 는 미구현) |

## 왜 v2 series 가 아니라 v1 query 인가

`o2warm/datadog.py` 가 쓰는 v2 `/series` 는 **전송 전용**입니다. 조회에는
v1 `/query` 를 씁니다 — 인증 헤더는 같지만(`DD-API-KEY` + `DD-APPLICATION-KEY`),
집계 Lambda 는 app-key 를 쓸 일이 없어 이 property 를 읽지 않았습니다.
그래서 `o2hot/settings.py` 가 `dd_secret_app_property`(기본 `app-key`)를
따로 갖습니다.

## 인증 — `o2-warm-api` 와 다르다

`o2-warm-api` 는 Function URL `authorization_type = NONE` + 공유 시크릿
헤더(`X-O2-Key`)입니다. 이 API는 **`AWS_IAM`(SigV4)** 입니다. 이유:

`docs/decisions.md` **D-031** 이 `o2-warm-api` 의 Function URL 이
**인터넷에서 모든 요청을 403 으로 거부한다**는 것을 이미 확인해
두었습니다 — 계정 밖 SCP/RCP 로 추정됩니다. 실제로 다시 확인한 결과,
이 계정(`066107819912`)은 AWS Organizations **멤버 계정**이라
`organizations:DescribeOrganization`/`ListPolicies` 가 `AdministratorAccess`
로도 막힙니다. 멤버 계정에서는 조직 정책을 조회·완화할 방법이 아예
없습니다.

그래서 D-031 이 "가장 깨끗하다"고 짚어 둔 대안을 택했습니다 — 익명
(`Principal: "*"`) 리소스가 아니므로 그 SCP/RCP 가 막는 패턴에 걸리지
않을 가능성이 높고, 무엇보다 **회전할 공유 키가 사라집니다.** 대신
`hot_api_invoker_role_arn` 변수(기본값: Dify EC2 인스턴스 역할)에 지정된
IAM 주체만 호출할 수 있습니다 — `hot-path.tf` 의
`aws_lambda_permission.hot_api_invoker`.

`handlers/serve.py` 에 `_authorized()` 가 없는 이유도 이것입니다.
SigV4 검증은 AWS 가 Lambda 를 부르기 전에 이미 끝냅니다.

### ⚠️ 미확인 — Dify 가 SigV4 를 할 수 있는가

Dify 의 Custom Tool(OpenAPI 3.0)이 AWS SigV4 서명을 기본으로 지원하는지
아직 확인하지 않았습니다. 못 하면 이 경로로는 Dify가 직접 못 붙습니다 —
Dify EC2 인스턴스(같은 IAM 역할)에서 로컬로 서명해 중계하는 작은 프록시가
필요합니다. 아직 만들지 않았습니다.

## 로컬에서 핸들러만 실행

AWS 자격증명 없이도 라우팅 로직은 확인할 수 있습니다(시크릿이 필요한
실제 Datadog 호출은 예외로 잡혀 500 이 됩니다).

```bash
cd handlers
python -c "
import serve
print(serve.handler({'requestContext': {'http': {'method': 'GET', 'path': '/v1/hot/health'}}}, None))
"
```

## 배포

새로 만들 시크릿이 없습니다 — Datadog 키(`o2/dev/datadog-new`)는
`o2-agg`/`o2-warm-api` 가 이미 쓰는 것을 그대로 읽고, 조회 API 인증은
SigV4 라 SSM 파라미터도 만들 게 없습니다.

```powershell
cd infra/06-datastream
terraform fmt
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
```

## 적용 후 확인 — SigV4 로 서명해서 호출한다

`curl` 만으로는 안 됩니다. AWS 자격증명으로 서명해야 합니다. 아래는
`o2-data` 프로파일 자격증명(위 Dify 역할과 같은 권한을 가진 호출자여야
합니다 — 예: 임시로 이 역할을 assume 하거나, 같은 principal 을
`hot_api_invoker_role_arn` 에 추가)로 [`awscurl`](https://github.com/okigan/awscurl)
을 쓰는 예시입니다.

```bash
pip install awscurl

HOT_URL=$(terraform output -raw hot_api_url)

awscurl --service lambda --region ap-northeast-2 \
  "$HOT_URL/v1/hot/health"

awscurl --service lambda --region ap-northeast-2 \
  -X POST -H "Content-Type: application/json" \
  -d '{"query": "avg:system.cpu.user{*}"}' \
  "$HOT_URL/v1/hot/datadog/query"
```

호출자가 `hot_api_invoker_role_arn` 이 아니면 Lambda 코드 실행 전에
403(`AccessDeniedException`)이 옵니다 — `o2-hot-api` 의 CloudWatch 로그에
아무것도 안 남습니다. D-031 이 `o2-warm-api` 에서 본 것과 같은 신호이니
헷갈리지 않도록 principal 을 먼저 확인합니다.
