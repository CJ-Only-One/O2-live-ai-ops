# 06-datastream

AI 에이전트가 쓰는 **내부 데이터 시스템**. 서비스가 내보내는 이벤트를 받아
데이터 레이크에 쌓고(cold), 10초 윈도우로 집계해 에이전트에게 먹인다(warm).

```
파드(o2-dev/api·order-worker, data-stream/o2-producer)
   └─ Kinesis  stream-business / stream-client
        ├─ Firehose ──▶ S3 o2-data-lake-*/raw/…      (cold)
        │                  └─ Glue o2-ml-data-prep-job ──▶ ml-ready/
        └─ Lambda o2-agg ──▶ DynamoDB o2-agent-context (warm)
                                  └─ Lambda o2-warm-api (Function URL) ──▶ 에이전트
```

`stream-client` 로 가는 `client.action` 은 브라우저가 아니라 **api 의 수집
엔드포인트**가 낸다 (`POST /api/broadcasts/{id}/events`, D-036). 클릭이 서버
이벤트와 같은 윈도우에서 만나야 `click_ratio` 가 나오므로, `warm-path.tf` 의
`O2_WARM_CLICK_ROUTE` 는 실제 서비스 이름(`api`)과 같아야 한다.

## `03-data` 와 무엇이 다른가

| | 03-data | 06-datastream (여기) |
|---|---|---|
| 무엇 | 서비스가 읽고 쓰는 저장소 | 서비스를 **관찰한** 결과 |
| 리소스 | RDS, ElastiCache Valkey, SQS | Kinesis, Firehose, S3, Glue, DynamoDB, Lambda |
| 죽으면 | 방송이 멈춘다 | 에이전트가 눈을 잃는다 (방송은 돈다) |
| backend key | `datastore/` | **`data/`** |

이름이 비슷해 헷갈리기 쉽다. **state 키를 서로 바꿔 쓰면 상대 리소스를
자기 것으로 인식하고 다음 destroy 에 지운다.** 근거는
[D-015](../../docs/decisions.md) · [D-029](../../docs/decisions.md).

## 이 저장소로 들어오기 전에 다른 곳에 있었다

원래 `dataInfra/infra-data/` 에서 관리했고 리소스 30개는 **이미 apply 되어
있다.** 옮긴 것은 코드뿐이고 state 와 리소스는 그대로다 (D-029).
그래서 첫 `plan` 은 **`No changes`** 가 나와야 한다. 뭔가 뜨면 옮기는 과정에서
어긋난 것이니 apply 하지 말고 원인을 찾는다.

이관하면서 바꾼 것은 셋뿐이다.

- 파일 이름을 저장소 컨벤션(서술형)으로: `01-s3.tf` → `s3.tf` 등.
  **Terraform 주소는 그대로**라 state 에 영향이 없다
- `backend.tf` + `providers.tf` → `versions.tf` 하나로
- 상대 경로: `../warm` → `./warm`, `../src/glue` → `./glue`

## 다른 스택과 다른 두 가지

의도한 것이므로 "통일"하려다 리소스를 흔들지 않는다.

| | 여기 | 다른 스택 | 왜 |
|---|---|---|---|
| aws provider | `~> 5.0` | `~> 6.0` | 5.x 로 apply 된 state. 올리려면 6.0 upgrade guide 보고 plan 이 비는지 확인 후 따로 |
| state 락 | `dynamodb_table` | `use_lockfile` | 이미 DynamoDB 로 잠긴 state. 바꾸면 락이 두 곳으로 갈린다 |

`default_tags` 도 다른 스택처럼 변수화하지 않았다. 바꾸는 순간 리소스 30개
전부에 태그 diff 가 뜬다.

## 의존

`02-eks` 다음이다. `irsa.tf` 가 `o2-eks` 클러스터의 OIDC 프로바이더를 조회해
프로듀서 파드의 신뢰 정책을 만든다. remote state 가 아니라 **클러스터 이름으로
직접 조회**하므로, 클러스터가 없으면 plan 단계에서 멈춘다.

apply 순서는 `01` → `02` → (`03` ∥ `05` ∥ `06`) → `04`.

## 변수 두 개

둘 다 기본값이 빈 문자열이고, 비워 두면 해당 기능만 꺼진 채 나머지는 돈다.

| 변수 | 비우면 | 넘기는 법 |
|---|---|---|
| `datadog_ssm_param` | Datadog 전송만 꺼진다. DynamoDB 집계는 그대로 | `terraform.tfvars` (파라미터 **이름**이지 키가 아니다) |
| `warm_api_key` | 조회 API 가 인증 없이 열린다 | `TF_VAR_warm_api_key` 환경변수 |

**`warm_api_key` 를 `terraform.tfvars` 에 적지 않는다.** 루트 `.gitignore` 의
`!infra/*/terraform.tfvars` 때문에 그 파일은 커밋된다.

Datadog 키 자체도 Terraform 밖에 둔다. 변수로 넘기면 remote state 에 평문으로
남기 때문이다.

```powershell
aws ssm put-parameter --name /o2/datadog/api-key `
  --type SecureString --value "<KEY>" --profile o2-data
```

## 함정

### `raw/` 는 30일 뒤에 지워진다

`s3.tf` 의 수명주기 규칙이다. 개인 계정 비용 때문에 둔 것이라 의도한
동작이지만, **Glue 가 30일보다 오래된 원본을 다시 읽는 일은 없다**는 전제가
깔린다. 재처리가 필요해지면 규칙부터 확인한다.

### Function URL 은 인터넷에서 403 이다

`authorization_type = "NONE"` 에 리소스 정책도 `Principal: "*"` 인데 모든
요청이 거부된다. 계정 밖의 조직 정책으로 보인다 — **Dify 가 이 경로로 붙을 수
없다**는 뜻이라 인그레스를 다시 정해야 한다. 조사 기록은 D-031,
재현 절차와 대안은 `warm/DEPLOY.md` 함정 절.

`warm_api_key` 는 그래도 채운다. URL 이 열리는 순간 필요해지고, 비어 있으면
**인증 없이 열린 채로** 뜬다.

### 배치 창 2초는 성능 설정이 아니다

`maximum_batching_window_in_seconds = 2` 는 클릭(client)과 서버 요청(business)이
**같은 10초 윈도우 안에서 만나게** 하는 값이다. 늘리면 늦게 온 쪽이 다음
윈도우로 밀려 `click_ratio` 가 조용히 틀어진다.

## 명령

```bash
terraform init
terraform plan -out=tfplan          # 첫 plan 은 No changes 여야 한다
terraform apply tfplan
```

Lambda 코드(`warm/`) 단위 테스트는 `warm/README.md`,
배포 절차는 `warm/DEPLOY.md`.
배포 후 확인용 스크립트는 `smoke/` — 실제 AWS 리소스를 건드리므로
`AWS_PROFILE` 을 확인하고 돌린다.
