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
