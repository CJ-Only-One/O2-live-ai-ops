# 트러블슈팅 기록

만들면서 실제로 막혔던 것과 그 원인을 남긴다.
`decisions.md` 가 "왜 이렇게 했나" 라면 여기는 **"왜 안 됐나"** 다.

회고할 때 참고하고, 같은 증상을 다시 만났을 때 원인부터 찾지 않기 위한 문서다.

> **이 파일은 통째로 읽지 않는다.** 아래 인덱스에서 증상으로 고른 뒤 그 절만 읽는다.
>
> ```bash
> grep -n '^## T-005' docs/troubleshooting.md
> sed -n '120,150p' docs/troubleshooting.md
> ```

## 인덱스

| # | 증상 | 키워드 |
|---|---|---|
| T-001 | Dify LLM 노드가 0.3초 만에 실패한다 | `model identifier is invalid` Bedrock `global.` |
| T-002 | 프롬프트에 변수 이름이 글자 그대로 나온다 | Dify 변수, `/` 삽입, 칩 |
| T-003 | 워크플로를 고쳤는데 API 응답이 안 바뀐다 | Dify 게시, 초안 |
| T-004 | Lambda VPC 설정 저장이 실패한다 | `CreateNetworkInterface`, `AWSLambdaVPCAccessExecutionRole` |
| T-005 | Lambda 가 Dify 호출에서 타임아웃 난다 | 사설 IP, 포트 80 vs 17080 |
| T-006 | 콘솔이 만든 IAM 역할이 안 지워진다 | 고객 관리형 정책, `service-role/` |
| T-007 | 수동 이벤트에는 필드가 비어서 온다 | `$ALERT_TRANSITION`, `$HOSTNAME`, 필수 변수 |
| T-008 | `terraform import` 가 시작 전에 실패한다 | `data.aws_secretsmanager_secret`, 사전 생성 |
| T-009 | `terraform plan` 출력에 비밀값이 평문으로 찍힌다 | import, state, 키 교체 |
| T-010 | 문서·자료의 메뉴 이름이 화면과 다르다 | Dify 출력 노드, Datadog Test 버튼, Monitor 섹션명 |
| T-011 | Dify 는 워크플로가 실패해도 HTTP 200 을 준다 | `data.status`, 비동기, `raise` |
| T-012 | Dify 가 넘긴 값을 안 쓰는데 에러도 안 난다 | 모르는 입력 키 무시, 계약 불일치 |
| T-013 | 아무 일도 안 하는데 클러스터가 느려진다 | `CPUCreditBalance`, t3 버스트, `kubectl top`, `/proc/*/task` |
| T-014 | Function URL 이 403 인데 정책은 분명히 허용이다 | `InvokeFunction` 도 필요, `FunctionUrlAuthType` 조건, 시뮬레이터 함정, 페더레이션 토큰 |
| T-015 | 부하 테스트에서 서버가 느린 게 아니라 k6 가 못 따라간 것이었다 | `dropped_iterations`, `preAllocatedVUs`, `maxVUs`, 생성기 병목 |
| T-016 | 노드를 바꿨더니 총 여유가 45% 인데 파드가 안 뜬다 | `Insufficient memory`, DaemonSet Pending, 파드 쏠림, `topologySpreadConstraints` |
| T-017 | 부하도 안 줬는데 AI 에이전트가 계속 깨어난다 | `notify_no_data`, `@webhook-dify`, Downtime, EWMA baseline 오염 |
| T-018 | 과거 사례가 늘 비는데 워크플로는 성공으로 끝난다 | `s3vectors:GetVectors`, `returnMetadata`, 의도한 조용한 실패, 웜 컨테이너가 옛 자격증명을 든다 |
| T-019 | Worker Lambda가 타임아웃 나는데 Dify 쪽은 매번 성공으로 남는다 | `urllib.request.urlopen timeout=55`, `workflow_runs`, Hot Path·Runbook Lookup, Slack 승인 |
| T-020 | 채팅은 전달되는데 Incident Candidate가 생성되지 않는다 | Chat Signal Worker 5초 timeout, 예약 동시성 1, SQS in-flight, `LATE_EVENT_DROPPED` |

---

## 기록 기준

**남긴다**

- 증상에서 원인이 바로 안 보인 것
- 30분 이상 쓴 것
- **조용히 실패한 것** — 에러도 안 나고 결과도 그럴듯한데 틀린 경우
- 문서·자료·UI 가 실제와 달랐던 것
- 두 번째 사람도 똑같이 밟을 것

**안 남긴다**

- 오타, 경로 실수
- 에러 메시지를 그대로 검색해서 한 번에 나온 것
- 이 저장소 밖 사정 (개인 환경, 일시적 네트워크)

한 항목이 길어지면 원인을 아직 모르는 것이다. 원인을 한 줄로 못 쓰면 더 파야 한다.

**항목 형식** — `## T-0NN. 증상` 뒤에 **증상 / 원인 / 해결 / 왜 늦게 찾았나** 순서.
마지막 항목이 제일 값어치 있다. 다음 사람이 아끼는 시간이 거기서 나온다.

번호는 이어서 붙이고 **상단 인덱스에 한 줄 넣는다.** 빠뜨리면 CI 가 막는다
(`scripts/check-docs-index.sh docs/troubleshooting.md T`).

---

## T-001. Dify LLM 노드가 0.3초 만에 실패한다

**증상**

```
PluginInvokeError: [models] Error: ValidationException:
The provided model identifier is invalid.
```

`FAIL / 0.332s / 0 Tokens`. 모델을 부르기도 전에 끝난다.

**원인**

서울 리전(`ap-northeast-2`)에서 Bedrock 은 맨 모델 ID 로 호출되지 않는다.
`apac.` 또는 `global.` 이 붙은 **inference profile** 로만 호출된다.
그리고 이 계정의 `apac.` 프로필에는 신형 Claude 가 없다 — `global.` 쪽에만 있다.

**해결**

드롭다운에서 고르지 말고 **Add Model** 로 ID 를 직접 넣는다.
계정에서 실제로 쓸 수 있는 목록은 이렇게 뽑는다.

```bash
aws bedrock list-inference-profiles --region ap-northeast-2 --query 'inferenceProfileSummaries[].inferenceProfileId' --output table
```

2026-08-19 실측:

| 모델 ID | 결과 |
|---|---|
| `apac.amazon.nova-lite-v1:0` | 정상 (팀 기본값) |
| `global.anthropic.claude-sonnet-5` | 정상 |
| `global.anthropic.claude-opus-5` | 정상 |
| `apac.anthropic.claude-3-5-sonnet-20241022-v2:0` | **ResourceNotFoundException** |
| `global.anthropic.claude-haiku-4-5-20251001-v1:0` | ResourceNotFoundException |

**왜 늦게 찾았나**

팀 공유 문서가 반대로 안내하고 있었다 — "Claude 5 를 피하고 3.5 Sonnet v2 를 쓰라".
`apac.` 에 신형 Claude 가 없다는 부분은 맞았지만 `global.` 을 훑지 않은 상태였고,
정작 권장하던 3.5 Sonnet v2 는 그사이 호출되지 않게 됐다.
**문서를 믿고 드롭다운만 뒤졌다.** 계정에서 직접 목록을 뽑았으면 5분이었다.

---

## T-002. 프롬프트에 변수 이름이 글자 그대로 나온다

**증상**

워크플로는 성공한다. 그런데 LLM 답변이 알림 내용과 무관하거나,
결과에 `{{alert_title}}` 같은 문자열이 그대로 보인다.

**원인**

Dify **워크플로** 앱의 LLM 노드에서는 변수를 타이핑으로 넣을 수 없다.
`{{alert_title}}` 이라고 치면 그냥 글자로 취급돼서, LLM 이 실제 값 대신
그 문자열을 읽는다. (챗플로우의 프롬프트 템플릿 문법과 다르다.)

**해결**

입력 칸에서 **`/` 를 눌러** 변수 목록에서 고른다. 제대로 들어가면 **파란 칩**으로 보인다.
검은 글씨면 잘못 들어간 것이다.

`/` 를 눌렀는데 목록이 안 뜨면 시작 노드에 변수를 안 만들었거나
노드가 선으로 연결되지 않은 것이다.

**왜 늦게 찾았나**

**에러가 안 난다.** 워크플로는 `succeeded` 로 끝나고 LLM 도 그럴듯한 답을 만든다.
"내용은 그럴듯한데 이 알림 얘기가 아닌" 상태라, 결과를 자세히 읽기 전까지 모른다.

---

## T-003. 워크플로를 고쳤는데 API 응답이 안 바뀐다

**증상**

Dify UI 실행은 새 결과가 나오는데, `/v1/workflows/run` 은 옛 결과를 준다.
또는 `workflow not published` 가 난다.

**원인**

편집 화면에서 도는 것은 **초안**이다. API 는 **게시된 버전**만 실행한다.

**해결**

우측 상단 **게시 → 게시 업데이트**. 워크플로를 고칠 때마다 매번 해야 한다.

**왜 늦게 찾았나**

UI 에서 잘 도니까 반영된 걸로 착각한다. 프롬프트 한 줄 고치고
게시를 빠뜨리는 일이 반복해서 생긴다. **증상이 "안 고쳐졌다" 하나뿐이라
코드나 캐시를 먼저 의심하게 된다.**

---

## T-004. Lambda VPC 설정 저장이 실패한다

**증상**

```
The provided execution role does not have permissions to
call CreateNetworkInterface on EC2
```

**원인**

VPC 안의 Lambda 는 서브넷에 ENI 를 만들어야 하고, 그 권한이 별도 정책에 있다.
콘솔에서 함수를 만들면 `AWSLambdaBasicExecutionRole` 만 붙는다.

**해결**

```bash
aws iam attach-role-policy --role-name <역할> --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole
```

IAM 반영에 몇 초 걸린다. 바로 다시 저장하면 같은 에러가 한 번 더 날 수 있다.
저장 자체도 ENI 생성 때문에 1~2분 걸린다.

Terraform 으로 만들면 [`../infra/06-agent/lambda.tf`](../infra/06-agent/lambda.tf) 의
`alert_relay_vpc` 어태치먼트가 이걸 처리한다.

---

## T-005. Lambda 가 Dify 호출에서 타임아웃 난다

**증상**

```
URLError: <urlopen error [Errno 110] Connection timed out>
```

`incoming:` 로그는 찍힌다. 즉 인증·파싱까지는 통과했고 네트워크 구간만 막혔다.

**원인 — 두 개가 겹쳐 있었다**

1. **환경변수 `DIFY_URL` 이 예제 IP 그대로였다.** 안내 문서에 설명용으로 쓴
   `10.0.2.15` 를 복사했고 실제는 `10.0.92.21` 이었다.
2. **보안그룹 포트가 17080 이었다.** 17080 은 SSM 포트포워딩이 만드는
   **각자 로컬 PC 의 포트**다. 서버에서는 nginx 가 **80** 하나로 콘솔·API·웹을 다 받는다.

**해결**

```bash
aws ec2 authorize-security-group-ingress --group-id <Dify SG> --protocol tcp --port 80 --source-group <Lambda SG> --region ap-northeast-2
```

`DIFY_URL` 은 콘솔에서 고친다. CLI 의 `update-function-configuration --environment` 는
변수를 통째로 덮어써서 나머지가 날아간다.

Terraform 에서는 `aws_instance.dify.private_ip` 로 만들어 하드코딩 자체를 없앴다.

**왜 늦게 찾았나**

증상이 "그냥 안 된다" 하나뿐이다. IP 가 틀렸는지 포트가 틀렸는지 SG 가 틀렸는지
타임아웃만 봐서는 구분이 안 된다. 그리고 **원인이 둘이라 하나를 고쳐도 증상이 그대로였다.**

`10.0.` 으로 시작하는 사설 IP 는 겉보기에 그럴듯해서 눈으로 안 걸러진다.

---

## T-006. 콘솔이 만든 IAM 역할이 안 지워진다

**증상**

`delete-role` 이 "정책이 붙어 있다"며 실패한다.
AWS 관리형 ARN 으로 `detach-role-policy` 를 해도 떨어지지 않는다.

**원인**

콘솔에서 Lambda 를 만들면 AWS 관리형 정책을 붙이는 게 아니라
**계정 전용 사본**을 만든다. 이름은 비슷한데 ARN 이 다르다.

```
arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole              ← AWS 관리형
arn:aws:iam::066107819912:policy/service-role/AWSLambdaBasicExecutionRole-4a9dc102-...  ← 콘솔이 만든 사본
```

**해결**

실제로 붙어 있는 ARN 을 먼저 확인하고, 그걸로 detach 한다.

```bash
aws iam list-attached-role-policies --role-name <역할> --query 'AttachedPolicies[].PolicyArn' --output text
```

사본 정책은 그 역할만 쓰므로, 다른 곳에서 쓰지 않는 걸 확인하고 같이 지운다.

```bash
aws iam list-entities-for-policy --policy-arn <사본 ARN>
```

**왜 늦게 찾았나**

이름이 `AWSLambdaBasicExecutionRole` 로 시작해서 AWS 관리형으로 보인다.
ARN 중간의 계정 번호를 봐야 구분된다.

---

## T-007. 수동 이벤트에는 필드가 비어서 온다

**증상**

`api/v1/events` 로 테스트 이벤트를 쏘면 payload 가 이렇게 온다.

```json
{ "alert_transition": "null", "host": "", "tags": "env:test", ... }
```

`alert_transition` 이 문자열 `"null"` 이고 `host` 는 빈 문자열이다.

**원인**

이 변수들은 **모니터 알림에서만** 채워진다. 수동 이벤트는 모니터가 아니다.
`$ALERT_QUERY`, `$ALERT_PRIORITY` 도 마찬가지다.

**해결**

- Dify 시작 노드에서 이 변수들을 **필수로 두지 않는다.** 필수인데 비면 API 가 400 을 낸다
- Lambda 의 폐기 조건을 `alert_transition == "Recovered"` 로 둔다.
  `!= "Triggered"` 로 하면 수동 이벤트가 전부 걸러져서 테스트가 막힌다
- 계약 검증은 **실제 모니터의 Test Notifications** 로 한다. 수동 이벤트로는 검증이 안 된다

**왜 늦게 찾았나**

수동 이벤트로 E2E 가 통과해서 "다 된다"고 판단했는데,
실제 모니터를 붙이고서야 채워지는 필드가 다르다는 걸 알았다.
**테스트 경로와 실전 경로의 payload 가 다르다는 것 자체가 안 보인다.**

---

## T-008. `terraform import` 가 시작 전에 실패한다

**증상**

```
Error: reading Secrets Manager Secret (o2/dev/dify-alert): couldn't find resource
```

import 명령을 쳤는데 import 는 시작도 못 하고 끝난다.

**원인**

Terraform 은 어떤 명령이든 **`data` 소스를 먼저 읽는다.**
`data.aws_secretsmanager_secret` 이 참조하는 시크릿이 없으면
import 든 plan 이든 그 지점에서 멈춘다.

**해결**

시크릿을 먼저 만든다. 값을 화면에 찍지 않고 옮기려면 이렇게 한다.

```bash
aws secretsmanager create-secret --name o2/dev/dify-alert --region ap-northeast-2 --secret-string "$(aws lambda get-function-configuration --function-name datadog-to-dify --region ap-northeast-2 --query 'Environment.Variables' --output json | python3 -c "import sys,json;v=json.load(sys.stdin);print(json.dumps({'dify-api-key':v['DIFY_KEY'],'webhook-secret':v['SECRET']}))")"
```

**왜 늦게 찾았나**

"import 는 리소스 하나만 건드리니 다른 건 상관없겠지" 라고 생각하기 쉽다.
`data` 소스는 그렇지 않다.

---

## T-009. `terraform plan` 출력에 비밀값이 평문으로 찍힌다

**증상**

콘솔에서 만든 Lambda 를 import 한 뒤 plan 을 돌리면
환경변수의 API 키와 공유 비밀값이 그대로 출력된다.

```
- "DIFY_KEY" = "app-..." -> null
- "SECRET"   = "57ced..." -> null
```

**원인**

import 가 실제 리소스 상태를 그대로 state 로 가져오기 때문이다.
콘솔에서 환경변수에 값을 직접 넣어뒀다면 그 값이 state 에 들어온다.
S3 버전 관리가 켜져 있으면 **이후 apply 로 지워도 옛 state 버전에는 남는다.**

**해결**

- 구조: 값이 아니라 **시크릿 이름만** 환경변수에 넣고 Lambda 가 실행 시점에 읽는다
  (`06-datastream` 과 같은 패턴, `docs/decisions.md` D-026)
- 이미 새어 나갔으면 **키를 교체한다.** state 에서 지우는 것으로는 부족하다

**왜 늦게 찾았나**

늦게 찾은 게 아니라 **피할 수 있었다.** 콘솔로 먼저 만들고 나중에 코드로 흡수하는
순서를 택하면 이 노출이 한 번은 일어난다. 처음부터 Terraform 으로 만들었으면 없었다.

---

## T-010. 문서·자료의 메뉴 이름이 화면과 다르다

**증상**

안내대로 따라가는데 그 메뉴가 화면에 없다.

**원인**

Dify 와 Datadog 둘 다 UI 를 자주 바꾼다. 2026-08 기준 확인된 것들이다.

| 자료에 있는 것 | 실제 화면 | 비고 |
|---|---|---|
| Dify **종료(End) 노드** | **출력** | 노드 추가 목록의 주황색 아이콘. "직접 답변"은 챗플로우용이라 다른 것 |
| Datadog Webhook **Test 버튼** | **없다** | `Delete` / `Edit` 만 있다. 테스트는 `api/v1/events` 에 `@webhook-<이름>` 을 넣어 쏜다 |
| Datadog Monitor **Notify your team** | **Configure notifications & automations** | 알림 본문 텍스트 박스가 그 안에 있다 |
| Datadog **Monitors** 위치 | `Monitoring → Monitors` | `Settings → Event Management` 가 아니다 |

**해결**

메뉴 이름으로 못 찾으면 **하는 일로** 찾는다.
예를 들어 "알림 본문이 들어있는 큰 텍스트 박스" 를 찾으면 섹션 이름이 뭐든 상관없다.

**왜 늦게 찾았나**

이름이 없으면 "내가 권한이 없나", "버전이 다른가" 를 먼저 의심하게 된다.
바뀐 이름을 확인한 뒤에는 몇 초다.

---

## T-011. Dify 는 워크플로가 실패해도 HTTP 200 을 준다

> **아직 겪지 않았다.** 비동기 구조를 설계하면서 발견해 미리 남긴다.
> 이 항목만 사후 기록이 아니다.

**증상 (예상)**

Worker 로그에 `dify ok: 200` 이 찍히는데 Slack 에도 결과가 없고 재시도도 없다.
알림이 조용히 사라진다.

**원인**

워크플로가 죽어도 HTTP 계층은 정상이다. 상태는 본문 안에 있다.

```json
{ "data": { "status": "failed",
            "error": "The provided model identifier is invalid.", "outputs": {} } }
```

T-001 의 모델 오류가 정확히 이 경로로 샌다. UI 에서 겪었기 때문에 보였을 뿐,
Lambda 를 거쳤으면 200 으로 통과했다.

여기에 두 번째 문제가 겹친다. **비동기 호출에서 Lambda 는 반환값을 읽지 않는다.**
`return {"statusCode": 502}` 는 성공으로 취급된다. 예외가 나거나 타임아웃이 나야 실패다.

**해결**

`data.status` 를 확인하고 **예외를 던진다.**

```python
status = result.get("data", {}).get("status")
if status != "succeeded":
    raise RuntimeError(f"dify workflow {status}: {result.get('data', {}).get('error')}")
```

**왜 미리 적어두나**

큐도 DLQ 도 알람도 전부 정상으로 보이는데 알림만 사라진다.
**감시 장치를 다 만들어두고도 못 잡는 종류**라, 겪고 나서 찾으면 오래 걸린다.

---

## T-012. Dify 가 넘긴 값을 안 쓰는데 에러도 안 난다

**증상**

Lambda 는 `alert_query` 를 넘기는데 LLM 답변에 그 내용이 전혀 반영되지 않는다.
워크플로는 `succeeded` 로 끝나고 로그에도 아무 이상이 없다.

**원인**

**Dify 는 모르는 입력 키를 조용히 무시한다.** 400 을 내지 않는다.

즉 Lambda 가 보내는 `inputs` 의 키 이름과 Dify 시작 노드의 변수 이름이
어긋나면 그 값은 그냥 사라진다. 실제로 Datadog webhook 을 15필드로 바꾸고
DSL 도 고쳤는데 **Lambda 만 옛 5필드로 남아** 있어서, 계약이 중간에서
끊긴 채로 한동안 돌았다.

**해결**

계약을 한 곳에 적고 네 지점을 같이 고친다 —
Datadog webhook Payload, Lambda 의 `inputs`, Dify 시작 노드 변수, 프롬프트.
목록은 [`../infra/06-agent/dify/README.md`](../infra/06-agent/dify/README.md) 1절.

확인은 **값이 실제로 답변에 반영되는지**로 한다. 마커를 하나 심어 보면 확실하다.

```bash
curl -s -X POST 'http://localhost:17080/v1/workflows/run' \
  -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"inputs":{"alert_query":"MARKER_5512 > 0.1", ...},"response_mode":"blocking","user":"c"}'
```

답변에 `MARKER_5512` 가 안 나오면 그 변수는 워크플로에 닿지 않은 것이다.

**왜 늦게 찾았나**

에러가 안 난다. `succeeded` 가 뜨고 LLM 이 그럴듯한 답까지 만든다.
T-002 와 같은 종류인데 더 나쁘다 — T-002 는 답변에 `{{변수}}` 라는 흔적이라도
남지만, 이건 **아무 흔적도 남지 않는다.** 답변 품질이 조금 나쁜 것과
구분이 안 된다.

계약을 바꿀 때 "어디를 같이 고쳐야 하는가" 를 문서에 적어두지 않으면
반드시 한 곳이 남는다.

---

## T-013. 아무 일도 안 하는데 클러스터가 느려진다

**증상** — 에러가 없다. 파드는 `Running` 이고 재시작도 0 이다. 그런데 전반적으로
느리다. 임계값을 넘는 지표도 없어서 알람이 울리지 않는다.

이 절은 **부하 테스트를 하기 전에 반드시 확인할 것**을 담는다. 크레딧이 없는
노드에서 부하를 걸면 앱 성능이 아니라 스로틀링을 재게 되고, 그 숫자는
그럴듯하게 나오지만 틀린 값이다.

### 1. 크레딧부터 본다

노드그룹이 `t3` 계열이면(`02-eks/terraform.tfvars` 의 `node_instance_types`)
CPU 를 항상 다 쓸 수 있는 것이 아니다. 시간당 정해진 만큼 크레딧을 받고,
그보다 많이 쓰면 빚을 진다.

```bash
ID=$(aws ec2 describe-instances --region ap-northeast-2 \
  --filters "Name=private-dns-name,Values=<노드이름>" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)

for M in CPUCreditBalance CPUSurplusCreditBalance CPUSurplusCreditsCharged; do
  echo "== $M"
  aws cloudwatch get-metric-statistics --region ap-northeast-2 \
    --namespace AWS/EC2 --metric-name $M \
    --dimensions Name=InstanceId,Value=$ID \
    --start-time $(date -u -v-6H +%Y-%m-%dT%H:%M:%SZ) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
    --period 3600 --statistics Average \
    --query 'sort_by(Datapoints,&Timestamp)[].[Timestamp,Average]' --output text
done
```

`CPUCreditBalance` 가 0 이면 baseline 으로 제한된 상태다. `t3.small` 의
baseline 은 **노드당 400m** 이다 — `kubectl top nodes` 가 그보다 높게 나오면
빚을 지고 있다는 뜻이다.

T3 기본값이 `unlimited` 이라 크레딧이 떨어져도 그냥 돌아간다. 대신 초과분이
과금된다. 모드는 이렇게 본다.

```bash
aws ec2 describe-instance-credit-specifications --instance-ids $ID --region ap-northeast-2
```

**빚은 인스턴스에 붙어 있다.** 노드를 교체하면 사라지지만 종료 시점에
미상환분이 청구된다. 실측값과 금액 계산은 M-008 에 있다.

### 2. 어느 파드가 먹는지 본다

```bash
kubectl top pods -A --sort-by=cpu
```

`metrics-server` 가 없으면 이 명령이 안 된다. `describe nodes` 는 **요청량**
(예약한 양)만 보여주므로 실사용량을 알 수 없다.

### 3. 파드 안에서 어느 스레드인지 좁힌다

컨테이너에 `ps` 도 `py-spy` 도 없는 경우가 많다. `/proc` 을 직접 읽는다.

```bash
# 스레드별 누적 CPU 시간 (14번 필드 = utime, 단위는 tick — 보통 1/100초)
kubectl exec -n <ns> <pod> -- sh -c \
  'for t in /proc/1/task/*; do echo "$(basename $t) $(awk "{print \$14}" $t/stat) $(cat $t/comm)"; done' \
  | sort -k2 -n -r | head -5
```

한 스레드만 값이 압도적이면 그 스레드가 범인이다. **현재 속도**는 두 번 재서
차이를 본다 — 10초에 약 1000 ticks 면 한 코어를 통째로 쓰는 중이다.

```bash
kubectl exec -n <ns> <pod> -- sh -c \
  'awk "{print \$14}" /proc/1/task/31/stat; sleep 10; awk "{print \$14}" /proc/1/task/31/stat'
```

I/O 대기인지 순수 스핀인지는 이걸로 가른다.

```bash
kubectl exec -n <ns> <pod> -- cat /proc/1/task/31/syscall
```

`running` 이면 유저 공간에서 도는 중 — 폴링이 아니라 바쁜 루프다.

### 실제 사례 (2026-08-20)

`api` 가 987m, `order-worker` 가 955m 을 **트래픽 0 인 상태에서** 상시 소모하고
있었다. 마지막 주문 처리가 같은 날 새벽 1시였고 측정은 오후 5시 40분이었다.

원인은 이벤트 SDK(`o2events`) 의 emitter 스레드였다. `_run()` 의 `deadline`
갱신이 `if batch:` 안에 있어, 큐가 비어 있으면 배치가 비어 그 블록에 못 들어가고
`deadline` 이 과거에 멈춘다. 그러면 `get(timeout=...)` 의 timeout 이 0.0 으로
고정되어 즉시 반환하고 루프가 쉬지 않고 돈다.

**이벤트가 없을수록 CPU 를 더 쓴다.** 이벤트가 흐르면 `batch` 가 차면서
`deadline` 이 정상 갱신되므로, 바쁜 서비스에서는 안 보이고 한가한 서비스에서
먼저 드러난다.

`chat-gateway` 만 멀쩡했던 것이 결정적인 단서였다. 그 서비스는 TypeScript 라
이 SDK 대신 같은 봉투를 내는 얇은 클라이언트를 쓴다
(`apps/chat-gateway/src/events.ts`). **Python SDK 를 쓰는 두 서비스만 정확히
영향을 받았다.**

수정은 o2-sdk-for-event#2 (`5b4d86e`, 0.3.1), 반영은 이 저장소 #91 이다.
배포 후 4m·1m 으로 떨어졌다.

### 왜 늦게 찾았나

**`metrics-server` 가 없어서 `kubectl top` 을 쓸 수 없었다.** CPU 를 태우고
있다는 사실 자체가 안 보였다. 노드 여유를 `describe nodes` 의 요청량으로만
보고 있었는데, `api` 의 CPU 요청량은 100m 이라 표에는 얌전하게 찍힌다.
실제로 987m 을 쓰고 있어도 그 차이를 볼 수단이 없었다.

같은 날 `metrics-server` 를 넣자마자 5분 만에 드러났다.

증상 쪽도 고약했다. 크레딧 고갈은 **에러를 내지 않는다.** 파드가 죽지도, 재시작
하지도 않는다. 알람을 걸 임계값도 마땅치 않다 — 방송 시작 직후에는 CPU 가 원래
높기 때문이다. 부하 테스트를 먼저 돌렸다면 "`chat-gateway` 가 4,000 을 못
버틴다" 는 결론을 냈을 것이고, 그 숫자로 40,000 을 외삽했을 것이다.

---

## T-014. Function URL 이 403 인데 정책은 분명히 허용이다

**증상** — Lambda Function URL(`authorization_type = AWS_IAM`)에 SigV4 로 서명해
호출하면 `403 Forbidden` 이다.

```
HTTP/1.1 403 Forbidden
x-amzn-ErrorType: AccessDeniedException
{"Message":"Forbidden. For troubleshooting Function URL authorization issues, see: ..."}
```

**함수 로그에는 아무것도 남지 않는다** — Lambda 가 호출되기 전에 막힌다.
D-031 이 본 것과 겉모습이 똑같아서 "또 조직 정책" 으로 오해하기 쉽다.

### 원인 — 액션이 하나 더 필요하다

Function URL 호출에는 **`lambda:InvokeFunctionUrl` 과 `lambda:InvokeFunction`
둘 다** 있어야 한다. 하나만 있으면 거부된다.

같은 엔드포인트에 세션 정책만 바꿔 가며 잰 값이다.

| 신원 기반 정책 | 결과 |
|---|---|
| `lambda:InvokeFunctionUrl` 만 (Resource 를 `*` 로 넓혀도) | **403** |
| `lambda:InvokeFunction` 만 | **403** |
| 둘 다 (Resource 는 함수 ARN 하나로 좁혀도) | **200** |
| `lambda:*` | 200 |

이름이 `InvokeFunctionUrl` 이라 그것 하나로 끝날 것 같지만 아니다.

### 조건 키를 신원 기반 정책에 걸지 않는다

`lambda:FunctionUrlAuthType` 은 **리소스 기반 정책에만** 채워진다.
신원 기반 정책에 걸면 조건이 매칭되지 않아 그대로 막힌다.

```bash
# 키를 직접 주입하면 통과한다 — 그래서 시뮬레이터만 믿으면 안 된다
aws iam simulate-principal-policy --policy-source-arn <role> \
  --action-names lambda:InvokeFunctionUrl --resource-arns <fn-arn> \
  --context-entries ContextKeyName=lambda:FunctionUrlAuthType,ContextKeyValues=AWS_IAM,ContextKeyType=string
# → allowed

# 키 없이 = 실제 요청과 같은 조건
aws iam simulate-principal-policy --policy-source-arn <role> \
  --action-names lambda:InvokeFunctionUrl --resource-arns <fn-arn>
# → implicitDeny, MissingContextValues=[lambda:FunctionUrlAuthType]
```

### 가려내는 법

403 의 출처가 IAM 인지 조직 정책인지부터 가른다. **세션 정책을 좁힌 임시
자격증명**으로 같은 엔드포인트를 때려 보면 한 번에 갈린다.

```bash
aws sts get-federation-token --name t --duration-seconds 900 \
  --policy '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
    "Action":["lambda:InvokeFunctionUrl","lambda:InvokeFunction"],"Resource":"<fn-arn>"}]}'
```

이 자격증명으로 200 이 나오면 조직 정책이 아니라 **호출자 정책 문제**다.
15분 만료에 그 함수 호출 외에는 아무것도 못 하므로 안전하다.

네트워크 경로 의심(VPC 안에서만 막히는가)은 **같은 자격증명을 VPC 안팎에서
각각** 써 보면 끝난다. 양쪽이 같으면 경로 문제가 아니다.

### 왜 늦게 찾았나

**증상이 D-031 과 완전히 같았다.** 같은 403, 같은 `AccessDeniedException`,
같은 "함수 로그 없음". 그래서 "조직 SCP/RCP" 라는 이미 있는 설명에 끼워
맞췄고, 정작 IAM 정책을 의심하는 데 오래 걸렸다.

**IAM 시뮬레이터가 `allowed` 라고 답한 것이 결정적으로 방해했다.** 조건 키를
내가 직접 주입해 놓고 그 결과를 "IAM 은 문제없다" 로 읽었다. 시뮬레이터는
내가 준 컨텍스트로만 답한다 — 실제 요청에 그 키가 오는지는 알려주지 않는다.

단서는 처음부터 있었다. `o2-warm-api` 의 리소스 정책에 statement 가 둘이었고
(`FunctionURLAllowPublicAccess` + `FunctionURLAllowInvokeAction`), 그중 하나가
바로 `lambda:InvokeFunction` 이었다. 콘솔이 만들어 준 것이라 "AWS 가 뭔가
붙였나 보다" 하고 넘겼다. **자동 생성된 정책에 왜 statement 가 둘인지 묻지
않은 것이 실수였다.**

---

## T-015. 부하 테스트에서 서버가 느린 게 아니라 k6 가 못 따라간 것이었다

**증상** — `read-path.js` 를 400 RPS 로 돌리니 p95 가 **3,514ms** 로 뛰었다.
직전 계단 200 RPS 에서는 127ms 였으니 28배다. 서버가 무너진 것으로 읽었다.

```
RATE  p95(ms)  RPS   드롭    api CPU
 200      127  200      0    433m
 400     3514  366   1628    951m     ← 목표 400 인데 366 만 나갔다
```

`드롭 1628` 은 k6 가 도착률을 못 지켜 아예 못 보낸 요청 수다. **이것을 서버가
느려서 생긴 결과로 해석했다.**

### 원인 — `preAllocatedVUs` 가 응답 시간 가정과 안 맞았다

고정 도착률(`constant-arrival-rate`)에서 필요한 VU 수는 `RATE × 응답시간` 이다.

```
400 RPS × 3.5초 = 1,400 VU 필요
maxVUs = RATE × 3 = 1,200        ← 여기서 막혔다
```

VU 상한에 걸려 요청을 못 만들면 k6 는 그 이터레이션을 버리고
(`dropped_iterations`), **남은 요청은 큐에서 더 오래 기다린 것들이라 p95 가
실제보다 부풀려진다.** 원인과 결과가 뒤집혀 보인다.

`preAllocatedVUs` 를 `RATE/4`(응답 250ms 가정)에서 `RATE`(1초 가정)로,
`maxVUs` 를 `RATE×3` 에서 `RATE×5` 로 올리고 다시 쟀다.

| 조건 | p95 | 실제 RPS | 드롭 |
|---|---|---|---|
| `maxVUs = RATE × 3` | 3,514ms | 366 | 1,628 |
| `maxVUs = RATE × 5` | **1,352ms** | 392 | 234 |

**서버는 그렇게까지 느리지 않았다.** 2.6배가 생성기 탓이었다.

### 가리는 법 — 두 지표를 같이 본다

`loadtest/run.sh` 가 k6 프로세스의 CPU·RSS 를 파드 지표와 같이 찍는 이유가 이것이다.

| `프레임/s`·`RPS` | `k6 CPU%` | 판정 |
|---|---|---|
| 예상대로 | 낮음 | 정상 |
| 낮음 | **높음** | **생성기가 병목** |
| 낮음 | 낮음 + 파드 CPU 높음 | 서버가 병목 (찾던 것) |

`dropped_iterations` 임계도 걸어 두었다. 다만 **0 이 아니라 10** 이다 —
첫 틱에 VU 를 깨우는 동안 두세 건이 밀리는데(200 RPS 에서 12,000건 중 2건,
VU 는 50 중 3개만 썼다) 그것까지 실패로 보면 정상 계단을 포화점으로 읽는다.

### 왜 늦게 찾았나

**숫자가 그럴듯했다.** p95 3.5초, 드롭 1,628, api CPU 951m — 셋 다 "서버가
한계에 닿았다" 는 이야기로 매끄럽게 읽혔다. 특히 CPU 951m 이 1 코어에 붙어
있어서 그쪽이 진짜 병목(uvicorn 워커 1개)이 맞았기 때문에, **맞는 결론과
틀린 숫자가 섞여 있었다.**

`드롭` 을 표에 찍어 두지 않았다면 아예 몰랐을 것이다. 실제로 처음에는
`k6 CPU 17%` 를 보고 "생성기는 여유" 로 넘겼는데, CPU 는 여유여도 **VU 상한**
이라는 다른 축에서 막힐 수 있다는 것을 생각하지 못했다.

**측정 도구의 한계를 측정값에 같이 기록하지 않으면 이 실수는 반복된다.**
그래서 `measurements.md` M-009 에 버린 값과 그 이유를 각주로 남겼다.

---

## T-016. 노드를 바꿨더니 총 여유가 45% 인데 파드가 안 뜬다

**증상** — 노드그룹을 교체한 뒤 Datadog DaemonSet 하나가 계속 `Pending` 이다.

```
0/2 nodes are available: 1 Insufficient memory,
                         1 node(s) didn't satisfy plugin(s) [NodeAffinity].
```

그런데 클러스터 전체로 보면 자리가 남는다.

```
총 requests 3,468Mi / 2대 합계 6,280Mi = 55%
```

### 원인 — 교체 직후 파드가 한 노드에 몰린다

노드그룹을 지우면 전 파드가 한꺼번에 `Pending` 이 됐다가 새 노드가 등록되는
순간 배치된다. 그때 **먼저 Ready 된 노드로 쏠리고, 쿠버네티스는 나중에 뜬
노드로 재분배하지 않는다.** 스케줄러는 배치 시점에만 판단한다.

2026-08-21 c6i.large 교체 직후 실측 — 노드 등록 시각 차이는 **1초**였다.

| 노드 | 파드 | 메모리 requests |
|---|---|---|
| ip-10-0-153-138 | **24개** | 2,956Mi (**94%**) |
| ip-10-0-66-38 | 4개 (DaemonSet 뿐) | 256Mi (8%) |

DaemonSet 은 **노드마다 하나씩** 떠야 한다. 다른 노드에 자리가 있어도 소용없다.

```
노드1 allocatable 3,140Mi − 사용 2,956Mi = 184Mi 여유
Datadog 요구                              256Mi   → 못 뜬다
```

**"1 Insufficient memory" 와 "1 NodeAffinity" 를 합쳐 읽어야 한다.** 앞은
자리가 없는 노드, 뒤는 이미 이 DaemonSet 이 떠 있는 노드다.

### 해소

```bash
kubectl rollout restart deploy -n o2-dev
```

노드1 이 꽉 차 있으므로 새 파드가 노드2 로 간다. 해소 후 노드1 69% · 노드2 41%.

**8 GiB 노드(m6i.large)에서는 같은 쏠림이 나도 다 들어갔다.** 4 GiB 는 이
워크로드의 패킹 습성에 여유가 부족하다 (M-008).

### 재발을 줄이는 것과 못 막는 것

매니페스트에 `topologySpreadConstraints` 를 넣었다
(`app.kubernetes.io/part-of: o2`, maxSkew 1, DoNotSchedule).
`name` 이 아니라 `part-of` 로 묶는 이유는, 서비스마다 따로 흩으면 `replicas: 1`
짜리 넷이 같은 노드에 몰려도 **각자 제약을 만족해 아무것도 막지 못하기**
때문이다. 같은 서비스의 파드끼리도 갈라야 하면 자기 이름 기준 제약을 하나 더
건다 — 두 제약은 AND 로 걸린다.

**그래도 교체 직후는 못 막는다.** 파드가 배치되는 순간 노드가 하나만 Ready 면
토폴로지 도메인이 하나뿐이라 skew 가 0 이고, 제약이 아무 일도 하지 않는다.
제약이 듣는 것은 **두 노드가 다 Ready 인 상태에서 배치될 때** — 평상시 롤아웃,
파드 재생성, HPA 증설이 여기 해당한다.

**노드를 추가하거나 교체한 뒤에는 배치를 확인하는 습관이 낫다.**

```bash
kubectl get pods -n o2-dev -o wide
```

### 왜 늦게 찾았나

**"메모리 부족" 이라는 메시지를 용량 문제로 읽었다.** 총합이 55% 라 앞뒤가 안
맞는데도, 노드를 4 GiB 로 줄인 직후라 "역시 작았나" 하는 쪽으로 먼저 기울었다.

배치를 본 뒤에야 24 대 4 라는 것을 알았다. `kubectl get pods -o wide` 한 번이면
보이는 것을 `describe node` 의 합계만 보고 있었다. **자원 문제인지 배치 문제인지
가르는 데는 합계가 아니라 분포를 봐야 한다.**

---

## T-017. 부하도 안 줬는데 AI 에이전트가 계속 깨어난다

**증상** — 부하 테스트를 시작하기도 전인데 Dify 릴레이 Lambda 가 계속 돌고 있다.

```
datadog-to-dify          최근 3일 호출 173  (8/19 145 · 8/20 19 · 8/21 9)
datadog-to-dify-worker   호출 121
o2-dify-worker           호출 23   오류 15   ← 65% 실패
o2-dev-dify-alert-dlq-o2 메시지 4건 적체
```

방송도 주문도 없는 개발 환경인데 알림이 나가고 있었다.

### 원인 — 데이터가 없는 것이 알람이 된다

`[O2][시나리오 2·5] 주문 응답 p95 지연` 모니터에 `notify_no_data = True`,
`no_data_timeframe = 10` 이 걸려 있다.

```
주문 트래픽이 없다
  → o2.warm.latency_p95 지표가 안 올라간다
  → 10분 뒤 No Data 판정
  → 알림 발송 → @webhook-dify → Dify 기동
```

**dev 환경은 평소 트래픽이 0 이라 이 조건이 상시 참이다.**

같은 태그의 모니터 10개 중 `@webhook-dify` 가 붙은 것이 **7개**다.
`monitor.tf` 를 grep 하면 6개로 세지는데 배포된 상태는 7개다 —
그래서 손으로 고르지 말고 **`stack:05-datadog` 태그로 걸어야 한다.**

### 비용은 지금 문제가 아니다. 나중이 문제다

8월 Bedrock 청구는 **$0.07** 이다. 현재 워크플로가 763토큰(M-001)이고
Nova Lite 단가가 1K 당 $0.0000355~0.000071 이라 알림 하나에 0.005센트다.

**모델을 Claude 로 바꾸거나 Datadog 조회(pull)를 붙이면 자릿수가 뛴다.**
M-006 의 "webhook 재시도 5회 = 토큰 6배" 가 그때 실제 비용이 된다.

### 진짜 손해는 돈이 아니다

- **늑대소년** — 상시로 울면 진짜 알람을 못 알아본다
- **측정 오염** — 부하 테스트 중 에이전트가 끼어들면 원인 구분이 안 된다
- **시연 신뢰도** — 지금까지 에이전트가 반응한 이력이 **전부 "데이터가 없음"**
  이고, 그마저 `o2-dify-worker` 는 65% 가 실패했다

### 부하 테스트 전에는 Downtime 으로 덮는다

```
Monitors → Manage Downtimes → monitor tag `stack:05-datadog`, Group scope `*`
```

**고정 종료 시각을 준다.** 무기한으로 걸면 푸는 것을 잊는다.
`notify_end_states` 를 비워 두면 창이 끝날 때 `No Data` 상태여도 알림이 안 나간다
— 그게 없으면 만료 시각에 밀린 것이 한꺼번에 터진다.

**Downtime 은 새 알림만 막는다.** 이미 ingress Lambda 가 받아 Worker 로 넘긴
비동기 호출과 재시도(`maximum_retry_attempts = 2`)는 그대로 실행된다.
걸고 1~2분 기다렸다가 부하를 시작한다.

**그리고 Downtime 으로는 못 막는 것이 하나 있다** — 집계 Lambda 의 EWMA 학습이다.
`baseline.py` 의 스파이크 가드는 `samples >= 30` 일 때만 걸리므로 처음 30개 창은
가드 없이 학습된다. 부하 구간이 "평시" 로 박히면 조기 경보가 영영 안 울린다.
테스트 후 `o2-agent-context` 의 `sk = BASELINE#RPS` 항목을 지운다.

### 왜 늦게 찾았나

**"에이전트가 왜 깨어나지" 에서 원인까지 네 단계였다.**
Dify 로그 → Worker Lambda → ingress Lambda → Datadog webhook → 모니터 설정.

그리고 **찾을 생각을 안 했다.** 부하 테스트를 준비하면서 "테스트하면 알람이
울릴 테니 미리 뮤트하자" 는 맥락으로 모니터를 열어봤고, 그때 `No Data` 5건이
눈에 띄어 우연히 발견했다. 알람이 나가는 것을 **아무도 받고 있지 않아서**
(SNS 토픽 `o2-dev-dify-alert-relay-alarm` 구독자 0명) 증상이 사람에게 안 보였다.

**받는 사람이 없는 알림은 조용히 실패한다.** 비용도 지금은 작아서 청구서로도
안 드러났다.

---

## T-018. 과거 사례가 늘 비는데 워크플로는 성공으로 끝난다

**증상** — 이력을 붙였는데 Dify 의 `past_cases` 가 언제나 빈 문자열이다.
겉으로는 아무 문제가 없다.

- Dify 워크플로 `succeeded`
- Lambda 성공, DLQ 비어 있음, 알람 안 울림
- `incidents/` 에 원본 JSON 도 정상으로 쌓인다
- **저장은 되는데 검색만 안 된다**

원인은 CloudWatch 로그 한 줄에만 있다.

```
history search failed: AccessDeniedException ... is not authorized to perform:
s3vectors:GetVectors on resource: .../index/incidents
```

### 원인 — QueryVectors 는 GetVectors 도 요구한다

`s3vectors:QueryVectors` 만 주면 거부된다. `returnMetadata = true` 로 부르면
AWS 가 메타데이터를 돌려주면서 **`s3vectors:GetVectors` 를 함께 검사한다.**

| 신원 기반 정책 | 결과 |
|---|---|
| `QueryVectors` 만 | **AccessDeniedException** |
| `QueryVectors` + `GetVectors` | 200 |
| `PutVectors` 만 (저장) | 200 — 그래서 저장은 되고 검색만 죽는다 |

**저장이 되니까 권한은 맞다고 착각하기 쉽다.** 쓰기와 읽기가 요구하는 액션
집합이 다르다.

T-014 와 같은 종류의 함정이다 — API 이름(`QueryVectors`)만 보고 권한을 맞추면
걸린다. 그쪽은 `InvokeFunctionUrl` 에 `InvokeFunction` 이 더 필요했다.

### 가려내는 법

증상이 조용하므로 **로그를 먼저 본다.** 알람을 기다리면 영원히 안 온다.

```bash
aws logs tail /aws/lambda/datadog-to-dify-worker --since 30m --region ap-northeast-2 \
  | grep -E "history"
```

정상이면 이 줄이 나온다. `matched 0 of 0` 은 권한이 아니라 **아직 이력이
비었다**는 뜻이므로 구분해야 한다.

```
history: matched 2 of 3
history: stored incidents/dt=2026-08-21/....json
```

권한만 따로 떼어 확인하려면 CLI 로 같은 호출을 해 본다.

```bash
aws s3vectors list-vectors --vector-bucket-name o2-dev-dify-history-vectors \
  --index-name incidents --region ap-northeast-2
```

### 고쳤는데 그대로다 — 실행 환경이 옛 자격증명을 들고 있다

권한을 고쳐 `apply` 한 뒤에도 **같은 에러가 계속 났다.** 정책은 분명히 맞았다.

```bash
# 인라인 정책에 GetVectors 가 들어 있고 Resource 도 에러 메시지와 글자까지 같다
aws iam get-role-policy --role-name o2-dev-dify-alert-worker-role \
  --policy-name o2-dev-dify-alert-worker

# 조건 키가 없으므로 시뮬레이터를 믿어도 된다 (T-014 의 함정은 조건 키 얘기다)
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<계정>:role/o2-dev-dify-alert-worker-role \
  --action-names s3vectors:QueryVectors s3vectors:GetVectors \
  --resource-arns arn:aws:s3vectors:ap-northeast-2:<계정>:bucket/<버킷>/index/incidents
# → 셋 다 allowed
```

**Lambda 실행 환경이 정책 변경 전에 받은 자격증명을 캐시하고 있었다.**
IAM 변경은 새 세션에 즉시 반영되지만 살아 있는 세션에는 늦게 붙는다.

가려내는 단서는 **로그 스트림 ID** 다. 실패한 호출이 전부 같은 스트림이면
같은 실행 환경이다.

```bash
aws logs tail /aws/lambda/datadog-to-dify-worker --since 30m --region ap-northeast-2 \
  | grep -E "INIT_START|history"
```

`INIT_START` 가 없으면 웜이다. 새 실행 환경에서 돈 회차는 스트림 ID 가 다르고
`INIT_START` 가 찍힌다 — 그때 `history: matched 3 of 3` 로 바뀌었다.

**함정: 확인하려고 알림을 자주 쏘면 그 컨테이너가 안 죽는다.** 2~3분 간격으로
테스트하면 고장난 환경을 직접 붙잡고 있는 셈이다. **약 15분 유휴로 두면**
회수된다. `update-function-configuration` 으로 억지로 흔들지 마라 — terraform
state 와 어긋나 다음 plan 에 엉뚱한 diff 가 뜬다.

급하면 페이로드를 만들어 직접 부르는 편이 빠르다. Ingress 를 거치지 않으므로
webhook 시크릿도 필요 없다.

```bash
aws lambda invoke --function-name datadog-to-dify-worker --region ap-northeast-2 \
  --cli-binary-format raw-in-base64-out --payload file://payload.json out.json
```

이때 `cycle_key` 를 알아볼 수 있는 값으로 두면 나중에 테스트 데이터만 골라낼
수 있다. 이력에 실제로 한 건이 쌓이기 때문이다.

### 왜 늦게 찾았나

**조용히 실패하도록 일부러 만들었기 때문이다.** 검색은 보조 기능이라 실패해도
예외를 올리지 않는다 — 과거 사례 하나 때문에 알림 분석 전체를 잃지 않으려는
설계이고, 그 판단 자체는 맞다(D-044).

문제는 **그 방어가 동시에 눈가리개라는 점이다.** 알람도 DLQ 도 안 울리므로
로그를 직접 열어 보기 전에는 기능이 죽은 것을 모른다. 저장은 정상이라
`incidents/` 만 확인하면 "잘 되는구나" 로 끝난다.

배포 직후 로그를 한 번 봤기 때문에 잡았다. **안 봤으면 발표 때 "과거 사례를
참고합니다" 라고 말하면서 실제로는 한 번도 참고하지 않는 상태였다.**

조용한 실패를 의도했다면 **그것을 확인하는 절차도 같이 만들어야 한다.**
지금은 배포 후 로그 확인이 그 절차다. 검색 실패가 반복되는 것이 문제가 되면
`history search failed` 를 메트릭 필터로 잡아 알람에 붙인다.

두 번째로 늦은 이유는 따로다. **고친 뒤에도 같은 에러가 나오니 "정책이 틀렸나"
로 돌아가 정책만 세 번 다시 봤다.** 정책은 처음부터 맞았고 봐야 할 것은
로그 스트림 ID 였다. 같은 에러 메시지라도 **고치기 전과 후는 다른 사건**이다 —
고친 뒤에도 같은 증상이면 원인이 같다고 가정하지 말고 "변경이 이 호출에
도달했는가" 를 먼저 묻는다.

---

## T-019. Worker Lambda가 타임아웃 나는데 Dify 쪽은 매번 성공으로 남는다

**증상**

```
Error: timed out
```

`worker.py` 304행 `urllib.request.urlopen(req, timeout=55)` 에서 예외가 난다.
그런데 Dify EC2 안에서 `workflow_runs` 테이블을 직접 조회하면 같은 실행이
`status=succeeded` 로 정상 종료돼 있다.

**원인**

Hot Path·Runbook Lookup API 가 붙으면서 워크플로 1회 처리 시간이 실측
39.8~58초대로 늘었다(M-001). Worker(`worker.py`)의 urlopen 타임아웃은 여전히
55초, Lambda 함수 자체 타임아웃도 60초로 남아 있어서 워크플로가 실제로는
끝났는데도 클라이언트가 먼저 포기하는 상황이 생겼다.

여기에 Slack 승인이 얹히면 Dify 승인 노드가 최대 600초까지 기다리므로 격차가
훨씬 커진다. 또한 Worker 의 재시도 정책(`maximum_retry_attempts=2`)과 겹치면,
이미 성공한 실행에 대해 클라이언트만 타임아웃 나서 불필요한 재실행(중복 LLM
비용, 중복 인시던트 적재)까지 유발할 수 있었다.

**해결**

`worker.py` 의 urlopen timeout 을 55→820초로, `lambda_o2.tf` 의 Lambda 함수
timeout 을 60→850초로 올렸다(Lambda 자체 상한 900초 대비 여유를 둠). 이 둘의
대소관계(Lambda timeout > urlopen timeout)는 반드시 유지해야 한다 — 반대가
되면 Lambda 런타임이 이 예외처리보다 먼저 함수를 강제 종료해서 DLQ 로그가
지금보다 훨씬 알아보기 어려운 형태로 남는다.

**왜 늦게 찾았나**

클라이언트 쪽 예외(`Error: timed out`)만 보면 Dify 워크플로 자체가 실패한
것처럼 보인다. 하지만 Dify 는 자기 `workflow_runs` 테이블에 `succeeded` 를
정확히 남기기 때문에, "워크플로가 느려서 실패한다"와 "워크플로는 끝났는데
클라이언트가 먼저 포기한다"는 겉으로 같은 에러 메시지를 낸다. Dify Postgres
를 EC2 안에서 직접 조회해 대조해보고 나서야 후자라는 게 확인됐다.

---

## T-020. 채팅은 전달되는데 Incident Candidate가 생성되지 않는다

**증상**

외부 ALB WebSocket으로 합성 사용자 4명이 15초 안에 약한 지연 신호를 보냈다.
네 연결은 모두 성공했고 각 채팅은 네 클라이언트에 전달됐지만 Candidate는 없었다.

Worker 로그에는 다음 순서가 남았다.

```text
REPORT Duration: 5000.00 ms Status: timeout
chat_signal_processed ... status=BELOW_THRESHOLD
chat_signal_processed ... status=BELOW_THRESHOLD
chat_signal_processed ... status=LATE_EVENT_DROPPED
chat_signal_processed ... status=LATE_EVENT_DROPPED
```

Queue는 visible 0, not-visible 4였다. 메시지가 사라진 것이 아니라 Lambda poller가
받아 둔 채 처리하지 못하고 있었다. DynamoDB에는 중간 상태 7건만 있고 Candidate는
0건이었다. 원문 속성은 0건이었다(M-011).

**원인**

두 제한을 실제 SQS-Lambda 경로 없이 정했다.

1. 함수 timeout 5초는 cold start, boto3 자격증명 초기화, 순차 DynamoDB 쓰기를 합친
   첫 invocation보다 짧았다. 첫 호출은 정확히 5초에서 강제 종료됐다.
2. 예약 동시성은 1인데 event source mapping의 최대 동시성을 제한하지 않았다. 같은
   1분 구간에서 CloudWatch `Throttles=2`, `ConcurrentExecutions max=1`이 확인됐다. SQS
   poller가 받은 다음 batch가 throttling과 visibility 30초 동안 기다렸고, 그 결과
   15초 window + 5초 late allowance를 넘겨 정상 메시지가 late로 폐기됐다.

**해결**

먼저 D-049 순서대로 생산자를 `off`로 바꾸고 Chat Gateway를 재시작한 뒤 event source
mapping을 Disabled로 바꿨다. 데이터 리소스는 삭제하지 않았다.

Worker timeout은 10초, 예약 동시성은 2로 바꾸고 event source mapping의
`maximum_concurrency=2`를 명시한다. poller 최대치와 함수 예약치를 같게 해 throttling으로
in-flight 메시지가 늦어지는 경로를 닫는다. Queue visibility 30초는 함수 timeout보다
길고, 원문 보존 60초 안에서 한 번 재시도할 여지를 남기므로 유지한다.

수정 배포 후에는 새 broadcast ID로 같은 외부 WebSocket 4사용자 시나리오를 다시 실행해
Candidate 1건, Queue visible/in-flight 0, Lambda timeout 0, 원문 속성 0을 모두 확인한다.

**왜 늦게 찾았나**

로컬 AC 테스트는 결정론적 분류·DynamoDB 조건부 쓰기·중복 처리를 검증했지만 Lambda
cold start와 SQS poller가 batch를 선점하는 동작은 포함하지 않았다. Terraform validate와
unit test가 모두 통과해 처리 용량도 검증된 것처럼 보였다. visible backlog만 봤다면 0이라
정상으로 오판했을 것이고, not-visible과 CloudWatch `REPORT`를 함께 봐야 원인이 보였다.
