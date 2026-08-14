# Warm Path 배포

Terraform 코드는 `infra/06-datastream/warm-path.tf` 에 반영돼 있고,
`lambda.tf` 수정도 적용된 상태입니다.
**아직 `apply` 하지 않았습니다** — plan 검토 후 승인하는 기존 절차를 따릅니다.

---

## 1. Datadog 키 등록 (선택)

키를 Terraform 변수로 넘기면 S3 remote state 에 평문으로 남습니다.
파라미터는 Terraform 밖에서 만들고 이름만 넘깁니다.

```powershell
aws ssm put-parameter --name /o2/datadog/api-key `
  --type SecureString --value "<DATADOG_API_KEY>" --profile o2-data
```

생략하면 Datadog 전송만 꺼지고 DynamoDB 집계는 그대로 동작합니다.

## 2. plan

```powershell
cd infra/06-datastream
terraform fmt
terraform validate
terraform plan `
  -var 'datadog_ssm_param=/o2/datadog/api-key' `
  -var 'warm_api_key=<32자 이상 랜덤 문자열>'
```

예상: **6 to add, 2 to change, 0 to destroy**

| | |
|---|---|
| 추가 | 로그 그룹, IAM 역할·정책 2개, Lambda `o2-warm-api`, Function URL, `stream-client` 매핑 |
| 변경 | `o2-agg` (코드·핸들러·메모리·타임아웃·환경변수), `stream-business` 매핑 (배치 창) |
| 삭제 | 없음 |

`o2-agg` 변경이 크게 잡히는 것이 정상입니다. 배관만 하던 함수가
집계기로 바뀝니다.

## 3. 적용 후 확인

```powershell
# 두 스트림이 다 연결됐는지 — click_ratio 가 여기 달려 있습니다
aws lambda list-event-source-mappings --function-name o2-agg --profile o2-data `
  --query "EventSourceMappings[].{stream:EventSourceArn,state:State}"

# 이벤트를 흘려보낸 뒤 지표가 쌓이는지
aws dynamodb query --table-name o2-agent-context --profile o2-data `
  --key-condition-expression "pk = :p AND begins_with(sk, :s)" `
  --expression-attribute-values '{\":p\":{\"S\":\"METRIC#coupon-api\"},\":s\":{\"S\":\"TS#\"}}' `
  --no-scan-index-forward --limit 3

# Agent 조회 계층
curl -H "X-O2-Key: <키>" "<warm_api_url>v1/warm/snapshot?service=coupon-api&windows=6"
```

---

## 코드를 고칠 때

```powershell
cd warm
.venv\Scripts\activate
pytest                     # 59건 — 여기가 통과해야 배포합니다
```

`terraform apply` 가 소스 해시를 보고 재배포하므로 별도 빌드 단계는 없습니다.

**`test_contract.py` 가 깨지면 먼저 앱 팀과 이야기하세요.** 이벤트 계약이
바뀌었다는 뜻이고, 그대로 배포하면 해당 지표가 조용히 `null` 이 됩니다.

---

## 운영 시 주의

**샤드 1개 기준 설계입니다.** 스트림당 샤드를 늘리면 같은 윈도우에 쓰는
동시 호출이 샤드 수만큼 늘어 낙관적 잠금 재시도가 잦아집니다. 샤드가
4개를 넘어가면 `merge_sketch` 재시도 횟수를 올리거나, 파티션 키가 이미
`user_key` 로 잡혀 있으므로 샤드별 부분 아이템으로 쪼개는 편이 낫습니다.

**비용은 이벤트량이 아니라 호출 횟수에 비례합니다.** 배치 창 2초 기준으로
서비스 하나당 초당 약 0.5회 읽기 + 1회 쓰기입니다. 트래픽이 늘면 샤드를
늘리기 전에 배치 창을 늘리는 쪽을 먼저 검토하세요.

**`METRIC#` TTL 은 7일입니다.** 그보다 오래된 분석은 Cold Path(S3 원본 →
Athena)의 몫입니다. Warm 을 길게 잡아 Cold 를 대신하려 들면 DynamoDB
비용만 오르고 재집계는 여전히 불가능합니다.
