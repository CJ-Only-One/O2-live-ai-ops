# Warm Path 배포

**적용 완료 상태다.** 마지막 apply는 2026-08-17 (`0 added, 5 changed, 0 destroyed`)
— 비밀값을 실행 시점에 읽도록 바꾸고 `DD_SITE`를 주입한 변경이다.

깨끗한 저장소에서 `terraform plan`을 돌리면 **`No changes`가 나와야 한다.**
그렇지 않으면 배포된 것과 코드가 갈라진 것이니 먼저 그 차이를 확인한다.

---

## 0. 프로파일을 먼저 지정한다

`versions.tf`의 provider에 `profile`이 없어서 기본 자격증명 체인을 탄다.
**이 환경의 `default` 프로파일은 죽어 있어** 그대로 돌리면 plan 단계에서
`SignatureDoesNotMatch`가 난다. 자격증명 문제이지 코드 문제가 아니다.

```powershell
$env:AWS_PROFILE = "o2-data"
aws sts get-caller-identity        # Account 가 066107819912 여야 한다
```

`terraform` 명령마다 `dynamodb_table is deprecated` 경고가 뜨는 것은 정상이다.
이 스택은 DynamoDB 락을 의도적으로 유지한다 (`versions.tf` 주석 참고).

## 1. 비밀값은 등록할 것이 없다

**Datadog API 키는 이미 있다.** `04-platform`이 ESO로 Agent에 넣는 것과
같은 시크릿을 집계 Lambda가 직접 읽는다.

```
Secrets Manager  o2/dev/datadog
  ├── api-key    ← o2-agg 가 실행 시점에 읽는다 (secretsmanager:GetSecretValue)
  └── app-key    ← Agent 전용 (컨트롤플레인 수집)
```

사본을 만들지 않는 이유는 회전 때문이다. 사본이 둘이면 한쪽만 바꿨을 때
**인프라 지표는 정상인데 비즈니스 지표만 조용히 멈춘다** — `datadog.py`가
전송 실패를 삼켜 집계를 막지 않기 때문이다(의도된 설계). 증상이 그것뿐이라
알아채기 늦다.

조회 API 키는 SSM SecureString에 있다.

```
SSM  /o2/warm/api-key  (SecureString)   ← o2-warm-api 가 실행 시점에 읽는다
```

둘 다 **이름만** `terraform.tfvars`에 있고 값은 state에 남지 않는다.
`TF_VAR_warm_api_key`를 쓰던 옛 방식은 값이 state에 남으므로 배포에 쓰지 않는다.

키를 새로 만들 일이 생기면 값이 화면을 거치지 않게 인라인으로 생성한다.

```powershell
$b = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
aws ssm put-parameter --name /o2/warm/api-key --type SecureString --overwrite `
  --value ([Convert]::ToBase64String($b)) --profile o2-data
```

## 2. plan · apply

변수는 전부 `terraform.tfvars`에 있어서 `-var`를 붙이지 않는다.

```powershell
cd infra/06-datastream
terraform fmt
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
```

`DD_SITE`가 걸린 변경이면 plan을 특히 눈여겨본다. **이 값이 틀려도 apply는
성공하고 Lambda도 정상으로 뜬다.** 조직이 AP1인데 US1으로 보내면 403이 나고
`datadog.py`가 그것을 삼키므로, 증상은 "대시보드가 계속 빈다" 하나뿐이다.
`04-platform`의 `datadog_site`와 같은 값이어야 한다.

## 3. 적용 후 확인

### 파이프라인

```powershell
# 두 스트림이 다 연결됐는지 — click_ratio 가 여기 달려 있다
aws lambda list-event-source-mappings --function-name o2-agg --profile o2-data `
  --query "EventSourceMappings[].{stream:EventSourceArn,state:State}"

# 이벤트를 흘려보낸 뒤 지표가 쌓이는지
aws dynamodb query --table-name o2-agent-context --profile o2-data `
  --key-condition-expression "pk = :p AND begins_with(sk, :s)" `
  --expression-attribute-values '{\":p\":{\"S\":\"METRIC#coupon-api\"},\":s\":{\"S\":\"TS#\"}}' `
  --no-scan-index-forward --limit 3
```

### Datadog 전송 — `datadog_series` 를 본다

`handler`가 호출마다 요약 JSON을 찍는다. 그 안의 **`datadog_series`가 전송에
성공한 시계열 수**이고, 이것이 0보다 크면 Datadog이 2xx로 받았다는 뜻이다.
전송 실패 사유는 같은 로그의 `[o2warm]` 줄에 남는다.

```powershell
aws logs tail /aws/lambda/o2-agg --since 10m --profile o2-data `
  --filter-pattern "datadog_series"
aws logs tail /aws/lambda/o2-agg --since 10m --profile o2-data `
  --filter-pattern "o2warm"      # 전송이 0 일 때 사유
```

Datadog 쪽에서도 확인한다 (`api.ap1...` — 사이트가 US1이 아니다).

```powershell
$now = [int][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
curl.exe -s -H "DD-API-KEY: <api-key>" -H "DD-APPLICATION-KEY: <app-key>" `
  "https://api.ap1.datadoghq.com/api/v1/query?from=$($now-900)&to=$now&query=avg:o2.warm.rps%7Bservice:coupon-api%7D"
```

**검증된 결과** (2026-08-17, 이벤트 60건 주입):

| 확인 | 값 |
|---|---|
| `datadog_series` | 24 (윈도우 2개) |
| DynamoDB `rps` | `coupon-api` 3, `payment-api` 3 |
| Datadog `o2.warm.rps` | 3.0 — **DynamoDB와 같은 값** |

같은 값이 양쪽에 있는 것이 설계 의도다 — 계산은 Lambda 한 곳에서 하고
결과만 두 저장소로 보낸다 (`src/o2warm/datadog.py` 참고).

### 조회 API

키는 SSM에서 꺼내 쓴다.

```powershell
$k = aws ssm get-parameter --name /o2/warm/api-key --with-decryption `
  --query Parameter.Value --output text --profile o2-data
curl.exe -s -H "X-O2-Key: $k" "<warm_api_url>v1/warm/snapshot?service=coupon-api&windows=6"
```

**단, 지금 Function URL은 인터넷에서 닿지 않는다.** 아래 "함정" 절을 본다.
함수 자체를 시험하려면 URL을 우회해 직접 호출한다.

```powershell
aws lambda invoke --function-name o2-warm-api --profile o2-data `
  --payload fileb://event.json out.json
```

---

## 코드를 고칠 때

```powershell
cd warm
python -m venv .venv                       # 없으면 만든다 (커밋 대상이 아니다)
.\.venv\Scripts\python.exe -m pip install pytest boto3
.\.venv\Scripts\python.exe -m pytest
```

기준: **`66 passed, 1 skipped`**. 스킵 1건은 `o2events` 미설치로 계약 검증을
건너뛴 것이다(`test_contract.py`). 개발 의존성을 다 깔면 그것도 돈다.

`terraform apply`가 소스 해시를 보고 재배포하므로 별도 빌드 단계는 없다.
`warm_sources`가 `o2warm/**/*.py`를 통째로 담으므로 새 모듈을 추가해도
Terraform 쪽은 고칠 것이 없다.

**`test_contract.py`가 깨지면 먼저 앱 팀과 이야기한다.** 이벤트 계약이
바뀌었다는 뜻이고, 그대로 배포하면 해당 지표가 조용히 `null`이 된다.

**`test_secrets.py`의 `test_auth_closed_when_lookup_fails`를 지우지 않는다.**
조회 실패를 "키 미설정"으로 뭉개면 SSM이 흔들리는 동안 Function URL이
인증 없이 열린다. 그 회귀를 막는 시험이다.

---

## 함정

### Function URL이 인터넷에서 403이다

`authorization_type = "NONE"`이고 리소스 정책도 `Principal: "*"`인데
모든 요청이 거부된다.

```
HTTP/1.1 403 Forbidden
x-amzn-ErrorType: AccessDeniedException
```

CloudWatch 로그가 한 줄도 없다 — **Lambda가 호출되기 전에 막힌다.** 함수 쪽
설정은 정상이므로 거부는 이 계정의 Lambda 설정 밖에서 온다. 조직 차원의
SCP/RCP가 Function URL 공개 접근을 막는 것으로 보이나,
`organizations:DescribeOrganization` 권한이 없어 확인하지 못했다. **가설이다.**

결과가 중요하다 — **Dify가 이 경로로 붙을 수 없다.** Hot Path를 연결하기
전에 정해야 한다: 조직 정책을 풀 것인가, API Gateway나 ALB로 인그레스를
바꿀 것인가. `X-O2-Key` 자체가 Dify의 SigV4 불가를 우회하려는 것이므로
(`handlers/serve.py` docstring), IAM 인증이 가능해지면 키가 아예 필요 없어진다.

### 인증 조회가 실패하면 열리지 않고 막힌다

`secrets.resolve()`는 **미설정(`""`)과 조회 실패(`None`)를 다른 값으로**
돌려준다. 조회 API는 실패를 401로 처리하고, Datadog 전송은 둘 다 "안 보낸다"로
같이 처리한다. 안전한 방향이 서로 반대여서 값으로 갈라 놓았다.

즉 `o2-warm-api` 역할에서 `ssm:GetParameter`를 빼면 엔드포인트가 열리는 것이
아니라 **전부 401이 된다.**

### `raw/`는 30일 뒤에 지워진다

Cold Path 보존은 30일이다. 그보다 오래된 분석은 애초에 불가능하다.

### 배치 창 2초는 성능 설정이 아니다

클릭과 서버 요청이 같은 10초 윈도우에서 만나야 `click_ratio`가 나온다.
창을 늘리면 두 스트림이 다른 윈도우로 갈라져 그 지표가 조용히 `null`이 된다.

---

## 운영 시 주의

**샤드 1개 기준 설계다.** 스트림당 샤드를 늘리면 같은 윈도우에 쓰는 동시
호출이 샤드 수만큼 늘어 낙관적 잠금 재시도가 잦아진다. 샤드가 4개를 넘어가면
`merge_sketch` 재시도 횟수를 올리거나, 파티션 키가 이미 `user_key`로 잡혀
있으므로 샤드별 부분 아이템으로 쪼개는 편이 낫다.

**비용은 이벤트량이 아니라 호출 횟수에 비례한다.** 배치 창 2초 기준으로
서비스 하나당 초당 약 0.5회 읽기 + 1회 쓰기다. 트래픽이 늘면 샤드를 늘리기
전에 배치 창을 늘리는 쪽을 먼저 검토한다.

**Datadog 커스텀 메트릭은 과금된다.** `DATADOG_SCALARS` 20개 × 서비스 수 +
`failure_rate`(이벤트 6종) + `confidence`가 시계열이 된다. 태그를 늘리고 싶어지는
순간이 비용이 새는 지점이다 — 맵과 고카디널리티 값은 DynamoDB에만 둔다.

**`METRIC#` TTL은 7일이다.** 그보다 오래된 분석은 Cold Path(S3 원본 →
Athena)의 몫이다. Warm을 길게 잡아 Cold를 대신하려 들면 DynamoDB 비용만
오르고 재집계는 여전히 불가능하다.
