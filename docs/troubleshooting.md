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
| T-021 | timeout은 없어졌는데 15초 안의 네 채팅으로 Candidate가 안 생긴다 | tumbling window 경계, epoch 정렬, 3+1 분리, rolling window 오해 |
| T-022 | 저장소의 Dify 입력 계약과 실제 게시 앱이 다르다 | DSL 미내보내기, `/v1/info`, `/v1/parameters`, `custom_alert_json`, API key 앱 매핑 |
| T-023 | SDK 가 봉투 필드를 늘렸는데 드리프트 시험이 안 깬다 | `ENVELOPE_FIELDS`, `pod_name`, 상수 없는 계약, 늘어난 쪽 감지 |
| T-024 | 없는 메트릭을 조회했는데 404 가 아니라 빈 태그 목록이 온다 | `/api/v2/metrics/.../all-tags`, 200+`tags:[]`, `/api/v1/search`, `trace.fastapi.request` |
| T-025 | 새 custom metric 값은 보이는데 tag-filter monitor가 계속 No Data다 | metric ingestion, tag index propagation, `all-tags`, prewarm, `{*}` 금지 |
| T-026 | Chat과 Datadog이 같은 장애인데 Incident가 두 개 생긴다 | `dev`, `o2-dev`, environment exact match, canonicalization |
| T-027 | 시험 파일을 저장소에 넣었는데 CI 가 한 번도 안 돌린다 | 명시 파일 목록, 두 가지 시험 양식, `NO TESTS RAN` 종료 코드 5 |
| T-028 | 로컬에서는 통과한 `test_history.py`가 CI에서 `NoRegionError`로 죽는다 | boto3 import-time client, AWS_DEFAULT_REGION, EC2 metadata, hermetic test |
| T-029 | Chat Source Adapter는 성공했는데 DLQ가 늘어난다 | disabled DynamoDB Stream, maximum record age, on-failure destination, cutover는 handler 안쪽 |
| T-030 | 앱은 정상인데 `o2.app.*`가 전부 No Data다 | DogStatsD, `useHostPort`, `DD_AGENT_HOST`, UDP 8125 |
| T-031 | distribution 값은 보이는데 p95 위젯만 No Data다 | `include_percentiles`, metric tag configuration, custom metric 비용, `avg` |
| T-032 | APM span에는 pod_name이 있는데 trace metric에서 by pod_name이 안 된다 | APM primary tag 후보, span-based metric, `@duration`, 나노초 |
| T-033 | 로컬 state 파일이 JSON인데 Terraform이 파싱하지 못한다 | Windows PowerShell, UTF-8 BOM, `Set-Content` |
| T-034 | Correlator가 Shadow 메시지를 받자마자 모두 실패한다 | 환경변수 JSON 매핑 로딩, dict와 set의 차집합 |
| T-035 | AWS CLI로 보낸 JSON이 Lambda에서 `SQS_BODY` 거부된다 | Windows PowerShell 네이티브 인자 quoting, `file://` |
| T-036 | validate는 통과하지만 IAM policy plan이 duplicate Sid로 실패한다 | `aws_iam_policy_document`, merge 중복, provider 렌더링 |
| T-037 | topologySpreadConstraints 를 걸었는데 파드가 안 갈린다 | merge key 중복, `matchLabelKeys`, 롤링 중 구 ReplicaSet 계산 |
| T-038 | 조치 실행기가 증설했는데 10초 뒤 원래 replicas로 돌아간다 | cue-warmer, 조치 소유권 충돌, 실험 잠금, RoleBinding 원복 |
| T-040 | 지표는 있는데 조회 값이 `0` 이나 `1.0` 으로 튄다 | `_latest()`, 미완성 버킷, 창 전체 합산 |
| T-041 | 부하 테스트 p95 가 서버 지표보다 6배 크다 | k6 이벤트 루프, 클라이언트측 계측, 부하 생성기 포화 |
| T-042 | `latency_p95_by_pod`가 실부하를 걸어도 계속 비어 있다 | `read_path_degraded` 노브가 켜져 있어 `inventory.check` 발행 자체가 꺼짐 |
| T-043 | Agent 가 늘린 파드가 몇 초 만에 원래대로 돌아간다 | cue-warmer 가 남의 조치를 자기 잔여물로 보고 되돌림 |
| T-044 | S2 Dify 워크플로가 매번 `status code 400` 으로 죽는다 | 방송 축 없는 알림에서 `broadcast_id` 가 `LIVE-001` 로 fallback |
| T-045 | Dify 컨테이너를 다시 만든 뒤 모든 요청이 502 | nginx 가 옛 컨테이너 IP 를 물고 있다 |
| T-046 | Bedrock 호출이 `Read timed out` 으로 끊긴다 | 플러그인이 botocore 기본 read timeout 60초를 그대로 쓴다 |


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
| `global.anthropic.claude-haiku-4-5-20251001-v1:0` | **2026-08-19 ResourceNotFoundException → 2026-08-27 재조회에서 `ACTIVE`.** 그 사이 열렸다 |

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

수정 적용 후 cold invocation은 5,369ms와 5,866ms에 정상 종료돼 timeout이 재발하지
않았다. 이어 같은 고정 15초 window에 네 메시지를 넣은 `bc_1044`에서 Candidate 1건,
Queue visible/in-flight 0, 원문 속성 0을 확인했다. 해당 성공 구간의 CloudWatch 값은
`Errors=0`, `Throttles=0`, `ConcurrentExecutions max=2`였다(M-011).

**왜 늦게 찾았나**

로컬 AC 테스트는 결정론적 분류·DynamoDB 조건부 쓰기·중복 처리를 검증했지만 Lambda
cold start와 SQS poller가 batch를 선점하는 동작은 포함하지 않았다. Terraform validate와
unit test가 모두 통과해 처리 용량도 검증된 것처럼 보였다. visible backlog만 봤다면 0이라
정상으로 오판했을 것이고, not-visible과 CloudWatch `REPORT`를 함께 봐야 원인이 보였다.

---

## T-021. timeout은 없어졌는데 15초 안의 네 채팅으로 Candidate가 안 생긴다

**증상**

T-020 수정 후 외부 WebSocket으로 서로 다른 네 사용자의 약한 신호를 보냈다. 네 연결과
16건의 팬아웃은 모두 성공했고 Worker도 5,369ms와 5,866ms에 정상 종료됐지만 Candidate는
0건이었다. 처리 결과는 `BELOW_THRESHOLD` 1건과 `LATE_EVENT_DROPPED` 3건이었다.

**원인**

문서의 "15초 안"을 첫 메시지부터 세는 rolling window로 읽었지만, 구현은 Unix epoch에
정렬된 15초 tumbling window를 사용한다. 네 메시지가 실제로 서로 15초 이내여도 고정
경계를 걸치면 이전 window 3건과 다음 window 1건으로 분리된다. cold processing이 끝났을
때 이전 window는 5초 late allowance도 지나 세 건이 late로 폐기됐다.

**현재 처리와 미결정 사항**

기존 구현 검증을 위해 window 시작 후 offset 2초에 새 `bc_1044` 시나리오를 보냈다.
네 메시지가 같은 window에 들어가자 `LOW/UNKNOWN` Candidate 1건이 생성됐고, matched
messages 4와 unique users 4가 확인됐다. 이것은 AC-004 구현 검증이지 운영 미탐의 해결이
아니다.

후속 Shadow matrix에서는 cold start 영향을 제거하고 경계를 직접 제어했다. offset
13.200초에 약한 신호 3건, 다음 window offset 0.399초에 1건을 보냈다. Worker는 네 건을
모두 정상 처리했지만 DynamoDB window는 3표와 1표로 갈렸고 Candidate는 없었다. 같은
관찰 구간의 Lambda는 `Errors=0`, `Throttles=0`, duration 67-288ms였다. 따라서 이 현상은
T-020의 timeout 재발이 아니라 window 의미 자체의 독립된 한계다(M-011).

운영 정책은 `VERIFY-CHAT-WINDOW-001`로 남긴다. Shadow replay에서 경계 미탐률과 비용을
측정한 뒤 다음 중 하나를 결정한다.

1. 현재 tumbling window를 유지하고 경계 미탐을 허용한다.
2. 중첩 window를 추가하고 Candidate 멱등성과 쓰기 비용을 함께 제한한다.
3. sliding window로 상태와 Candidate 계약을 다시 설계한다.

**왜 늦게 찾았나**

AC 단위 테스트 timestamp가 모두 같은 고정 window 안에 있었고, "within 15s"라는 표현도
rolling 의미로 읽힐 수 있었다. Lambda runtime 문제를 먼저 고친 뒤 timeout 없이 다시
외부 E2E를 수행했기 때문에 두 번째 독립 원인이 드러났다.

---

## T-022. 저장소의 Dify 입력 계약과 실제 게시 앱이 다르다

**증상**

저장소 `infra/06-agent/dify/README.md`와 DSL에는 `alert_title` 등 Datadog용 변수 8개와
유일한 workflow만 적혀 있다. 실제 Lambda API key로 `/v1/info`와 `/v1/parameters`를
조회하면 다른 게시 앱이 선택되고 `behavior`, `custom_alert_json`을 포함한 입력 10개가
나온다. 앱 목록에도 여러 workflow와 agent가 존재한다.

**원인**

Dify Studio에서 게시 workflow를 변경한 뒤 DSL을 저장소로 다시 export하지 않았다.
Terraform은 Dify 앱과 workflow를 관리하지 않으므로 EC2 Postgres의 배포 상태와 Git의
DSL이 자동으로 맞춰지지 않는다. Lambda API key가 어떤 앱을 가리키는지도 저장소의 앱
이름만으로는 알 수 없다.

**해결**

런타임 확인은 Lambda가 쓰는 API key로 다음 세 가지를 함께 본다.

1. `/v1/info`에서 실제 앱 이름과 mode를 확인한다.
2. `/v1/parameters`에서 게시 앱의 입력 변수 이름·타입·필수 여부를 확인한다.
3. Dify Postgres에서 해당 앱의 `workflow_id`가 가리키는 게시 graph가 필요한 변수를
   실제로 참조하는지 확인한다.

그 뒤 게시 앱에서 DSL을 다시 export하고 저장소 README의 입력 계약을 함께 갱신한다.
API key나 workflow graph 원문은 로그와 문서에 남기지 않는다. DSL 동기화 전에는 저장소
파일을 현재 배포 상태라고 보고 새 호출 경로를 활성화하지 않는다.

**왜 늦게 찾았나**

Dify는 모르는 입력 키를 조용히 무시하고, workflow 내부 실패도 HTTP 200으로 응답할 수
있다(T-011, T-012). 저장소 DSL만 읽으면 계약이 맞아 보이고, API key로 실제 앱을 조회해
게시 graph까지 대조해야 drift가 드러난다.

## T-023. SDK 가 봉투 필드를 늘렸는데 드리프트 시험이 안 깬다

**증상** — `o2-sdk-for-event` 0.3.0 이 모든 이벤트 봉투에 `pod_name` 을 추가했다.
집계 쪽(`o2warm/contract.py`)에 `E_POD_NAME = "pod_name"` 상수까지 만들어 뒀는데
`ENVELOPE_FIELDS` 집합에 넣는 것을 빠뜨렸다. **시험은 전부 통과했다.**

눈에 보이는 증상은 없다. 그게 문제다. 이 상태로 굳었으면 파드별 지표
(`cache_hit_rate_by_pod`, 앞으로 붙일 `latency_by_pod`)가 **조용히 빈 dict** 가
되고, Datadog 위젯은 "쿼리는 맞는데 비어 있는" 모양이 된다. 그때는 SDK·집계·
Terraform 셋 중 어디가 원인인지 알 수 없다.

**원인** — `tests/test_contract.py` 가 이벤트 이름·enum·`emit.*` 인자명은
검증하는데 **봉투 필드만 검증하지 않았다.** SDK 쪽에 봉투 키 목록을 내보내는
상수가 없어서(v0.3.1 `schemas.py` 기준) 대조할 대상이 없었기 때문이다.

그래서 "SDK 에 상수가 생겨야 검증할 수 있다" 고 판단하고 외부 저장소에
요청할 항목으로 미뤄 뒀다. **그 판단이 틀렸다.**

**해결** — 상수끼리 비교할 필요가 없다. `emit._envelope()` 을 직접 불러
실제 키 집합을 보면 된다. 같은 파일의 다른 시험이 이미 그 방식이다 —
`inspect.signature(emit.*)` 로 인자를 보고, `sinks._stream_for()` 를 직접
호출해 라우팅을 대조한다. 봉투만 예외로 둘 이유가 없었다.

```python
actual = set(o2emit._envelope(C.EVENT_ORDER_CREATE, {"order_id": "O-1"}))

missing = C.ENVELOPE_FIELDS - actual              # 집계가 쓰는데 봉투에 없다
unknown = actual - C.ENVELOPE_FIELDS - C.ENVELOPE_FIELDS_UNUSED  # 봉투에 생겼는데 모른다
```

**두 번째 단언이 핵심이다.** 드리프트 시험을 "빠진 것" 만 보게 짜면 이번
경우를 못 잡는다 — 우리를 문 것은 **늘어난 쪽** 이었다. 그래서 안 쓰기로 한
필드를 `ENVELOPE_FIELDS_UNUSED` 로 명시하게 했다. 안 쓰는 것과 빠뜨린 것을
구분하지 않으면 예외 목록이 곧 쓰레기통이 된다. SDK 에 필드가 새로 생기면
시험이 깨지고, **쓸지 말지 한 번은 정하게 된다.**

`_envelope()` 은 비공개 함수라 SDK 가 공개 상수를 내주면 그때 갈아탄다.
차단 요소가 아니므로 다음 SDK 변경 요청에 묶어 보낸다.

### 왜 늦게 찾았나

**상수를 만든 것으로 일을 끝냈다고 착각했다.** `E_POD_NAME` 을 정의하는
순간 "반영했다" 는 느낌이 들었는데, 그 상수는 아무도 참조하지 않는 죽은
값이었다. 정의와 등록이 두 걸음인 파일 구조에서 반복해서 날 실수다.

**"검증할 수단이 없다" 를 너무 빨리 받아들였다.** 상대 쪽에 상수가 없으니
대조할 수 없다고 결론 내렸는데, **같은 파일 바로 위에 런타임 객체를 직접
들여다보는 시험이 두 개나 있었다.** 이미 있는 패턴을 안 보고 없는 기능을
외부에 요청하려 했다.

**로컬 클론이 낡아서 판단이 한 번 더 틀어졌다.** SDK 를 확인할 때
`git fetch` 를 하지 않아 `origin/main`(`5b4d86e`)이 "존재하지 않는 객체" 로
보였고, 그래서 "SDK 쪽 작업이 아직 안 끝났다" 는 정반대 결론을 냈다.
실제로는 그 커밋이 이미 배포에 고정돼(`SDK_REF`) 돌고 있었다.
**남의 저장소 상태를 말하기 전에 fetch 부터 한다.**

---

## T-024. 없는 메트릭을 조회했는데 404 가 아니라 빈 태그 목록이 온다

**증상** — APM trace 지표에 `pod_name` 태그가 있는지 확인하려고 태그 목록을
조회했다.

```
GET /api/v2/metrics/trace.fastapi.request.duration/all-tags
→ 200 OK
→ {"data": {"attributes": {"tags": []}}}
```

빈 배열을 **답**으로 읽었다 — "이 지표에는 태그가 없구나". 그래서 "APM 에
파드 축이 없다" 는 결론까지는 맞게 갔지만, **근거가 틀린 채로** 갔다.

**원인** — `trace.fastapi.request.duration` **이라는 메트릭이 애초에 없다.**
실제 이름은 `trace.fastapi.request` 다. Datadog 의 `all-tags` 엔드포인트는
없는 메트릭 이름에 404 를 주지 않고 **200 과 빈 목록**을 준다.

그래서 이 응답만 보면 두 상황이 구분되지 않는다.

| 실제 상황 | 응답 |
|---|---|
| 메트릭은 있는데 태그가 하나도 없다 | `200` · `tags: []` |
| **메트릭 자체가 없다** | `200` · `tags: []` |

**해결** — 이름을 먼저 확인한다. 태그를 묻기 전에 그 메트릭이 존재하는지부터
묻는다.

```
GET /api/v1/search?q=metrics:trace.fastapi
→ trace.fastapi.request, trace.fastapi.request.hits, trace.fastapi.request.errors ...
```

또는 `/api/v1/query` 로 직접 조회해 `series` 가 비는지 본다. **빈 series 도
같은 함정이 있지만**(없는 메트릭도 빈 series 를 준다), `by {tag}` 를 붙여
scope 를 보면 `pod_name:N/A` 처럼 "지표는 있는데 그 태그가 없다" 가 드러난다.

**왜 늦게 찾았나** — `.duration` 이 관례상 그럴듯한 이름이라 **존재 자체를
의심하지 않았다.** 그리고 빈 배열이 오류가 아니라 정상 응답이라, 무언가
잘못됐다는 신호가 어디에도 없었다. 확인한 줄 알고 다음 단계로 넘어갔다.

**이 저장소에서 같은 모양을 이미 두 번 겪었다.**

| 어디 | 같은 모양 |
|---|---|
| `05-datadog/variables.tf` (`metric_prefix` 주석) | *"존재하지 않는 메트릭을 조회해도 Datadog 은 오류가 아니라 빈 series 를 준다"* |
| 이 문서 T-023 | 봉투 필드가 빠져도 시험이 안 깨진다 — 없는 것이 오류가 아니라 **빈 값**으로 나온다 |

**규칙** — Datadog 에서 빈 응답을 받으면 "없다" 로 읽기 전에 **이름이 맞는지를
먼저 확인한다.** 빈 응답은 답이 아니라 질문이다.

실측 결과 자체는 M-016 에 있다.

---

## T-025. 새 custom metric 값은 보이는데 tag-filter monitor가 계속 No Data다

**증상** — 합성 metric을 v1·v2 API에 제출하면 둘 다 `202 Accepted`였고 metric 목록과
`{*}` query에는 값이 보였다. 하지만 같은 시각의 `run:<id>` filter query는 series 0,
그 filter를 쓰는 monitor는 계속 `No Data`였다.

**원인** — 신규 custom metric의 값 ingestion과 tag 검색 index 반영은 동시에 보이지
않았다. 처음에는 tag가 유실됐다고 판단했지만, 후속 조회에서 `all-tags`에 `env`·`run`·
`service`가 모두 나타났고 같은 filtered query도 series 1을 반환했다. 즉 payload의 tag가
사라진 것이 아니라 **metric 값보다 tag-filter 사용 가능 시점이 늦었다.**

**해결** — 합성 monitor를 만들기 전에 다음 세 단계를 순서대로 확인한다.

1. metric 제출 API가 202를 반환한다.
2. `{*}` query에서 non-null point가 보인다.
3. 실제 monitor가 쓸 tag-filter query에서도 series가 보인다.

3번 전에는 monitor를 활성화하지 않는다. 반복 실험이면 metric과 tag를 미리 한 번 보내
prewarm한다. 이번에는 다른 producer가 없는 일회용 metric name임을 확인한 뒤에만 `{*}`로
측정했지만, 운영 metric은 다른 series까지 잡을 수 있으므로 **`{*}` 우회를 금지한다.**

**왜 늦게 찾았나** — 202와 metric 목록 등록을 같은 완료 신호로 읽었다. 반대로 filtered
series 0은 tag 누락으로 너무 빨리 해석했다. 어느 응답에도 “tag index가 아직 준비되지
않았다”는 오류가 없었고, 값 경로와 tag 검색 경로를 따로 확인하기 전까지 두 상황이 같은
빈 series로 보였다.

---

## T-026. Chat과 Datadog이 같은 장애인데 Incident가 두 개 생긴다

**증상** — 실제 Chat과 Datadog 신호가 모두 `LATENCY/api/READ_PATH`이고 발생 시각도 58초
이내였지만, Correlator는 두 source를 합치지 않고 각각 provisional Incident revision 1을
만들었다. 오류 로그는 없었고 두 결과 모두 개별적으로는 정상처럼 보였다.

**원인** — Chat 배포 환경은 `environment=dev`, Datadog 합성 monitor tag는 `env:o2-dev`였다.
Correlator는 environment·symptom·service·surface를 exact match하며, 환경이 다르면 같은
시간창이어도 병합하지 않는다. 비슷해 보이는 환경명을 임의로 합치지 않는 fail-safe 동작이다.

**해결** — 검증에서는 Datadog tag를 `env:dev`로 맞춰 재실행했고 동일 Incident revision 2로
병합되는 것을 확인했다. 운영 적용 전에는 다음 중 하나를 명시적으로 결정해야 한다.

1. 모든 producer가 하나의 표준 environment 값을 보내게 한다.
2. 공통 진입점 앞에 버전이 있는 명시적 environment mapping을 둔다.

접두사 제거 같은 fuzzy normalization은 서로 다른 환경을 잘못 병합할 수 있어 사용하지 않는다.
정책이 결정되기 전에는 exact match와
`CROSS_SOURCE_ENVIRONMENT_CANONICALIZATION_NOT_DECIDED` blocker를 유지한다.

**왜 늦게 찾았나** — 사람에게 `dev`와 `o2-dev`는 같은 환경처럼 보였고 source별 정상화
결과를 나란히 비교하지 않았다. exact match는 오류 대신 독립 Incident라는 그럴듯한 결과를
내므로, Dify를 열기 전에 Incident State를 확인할 때까지 불일치가 드러나지 않았다.

---

## T-027. 시험 파일을 저장소에 넣었는데 CI 가 한 번도 안 돌린다

**증상** — `lambda/test_runbook_lookup.py` 와 `lambda/test_action_state.py` 를
저장소에 넣고 CI 가 초록인 것을 확인했다. 그런데 **그 시험들은 한 번도 실행되지
않았다.** `test_history.py` 는 저장소에 들어온 뒤로 지금까지 그랬다.

**원인 둘이 겹쳐 있다.**

첫째, `tf.yml` 의 시험 단계가 **파일을 명시 목록으로 나열**한다. 디스커버리가
아니라서 새 파일을 넣어도 저절로 안 걸린다. 목록에 없는 시험은 존재하지 않는
것과 같다.

둘째, 목록에 넣어도 안 된다. `06-agent` 의 시험이 두 양식으로 쓰여 있다.

| 양식 | 예 | `python3 -m unittest <파일>` |
|---|---|---|
| `unittest.TestCase` | `test_incident_correlator.py` | 돈다 |
| 단독 스크립트 (`if __name__ == "__main__"`) | `test_history.py` · `test_runbook_lookup.py` · `test_action_state.py` | `NO TESTS RAN` |

단독 스크립트 양식은 `TestCase` 하위 클래스가 없어 수집이 0건이다.

**종료 코드는 파이썬 판마다 다르다.** 3.14 에서 확인한 값은 5 이고 그러면 CI 가
빨갛게 죽는다. 예전 판은 0 을 냈다 — 그 경우 초록으로 지나간다. 어느 쪽이든
**시험은 안 돈다**는 것이 같고, 앞의 경우는 "왜 깨지지" 로, 뒤의 경우는 조용히
넘어간다.

**조치** — 단독 스크립트를 직접 실행하는 단계를 `tf.yml` 에 더했다. 세 파일을
`TestCase` 로 고쳐 기존 목록에 합치는 방법도 있지만, 실행 줄 셋을 더하는 쪽이
작고 `test_history.py` 까지 같이 걸린다. `python3 lambda/test_x.py` 는 단언이
깨지면 예외로 죽어 0 이 아닌 코드를 낸다 — 실제로 판정 한 줄을 뒤집어 1 이
나오는 것을 확인했다.

**켠 첫 판에 하나가 깨졌다** — `test_history.py` 가 CI 에서만 `NoRegionError`
로 죽었다. 원인과 조치는 T-028 에 있다.

**이게 이 항목의 요점이다.** 시험이 CI 에서 안 돌면 "통과한다" 가 아니라
"결과를 모른다" 이다. 켜자마자 환경 차이 하나가 바로 나왔다.

**왜 늦게 찾았나** — CI 로그의 `Ran 52 tests` 를 보고 "시험이 돈다" 로 읽었다.
그 52건이 **어느 파일에서 나온 것인지** 는 안 셌다. 시험을 추가했으면 건수가
늘었는지를 봐야 하는데 초록만 봤다. 파일 목록을 손으로 관리하는 CI 에서는
**추가한 시험이 로그에 나타나는지**를 매번 확인해야 한다.

---

## T-028. 로컬에서는 통과한 `test_history.py`가 CI에서 `NoRegionError`로 죽는다

**증상** — T-027 후속으로 단독 스크립트 시험을 CI에 연결하자
`python3 lambda/test_history.py`만 `botocore.exceptions.NoRegionError: You must specify a
region`으로 실패했다. 같은 파일은 개발자 Mac에서 통과했다.

**원인** — `test_history.py`가 import하는 `ingress.py`는 module import 시점에
`boto3.client("lambda")`와 `boto3.client("s3")`를 만든다. Mac에는 AWS 기본 region이 있지만
GitHub Runner에는 없다. 테스트가 AWS API를 호출해서 실패한 것이 아니라 client 객체를 만드는
단계에서 환경 차이가 드러난 것이다. 자격증명이 없으면 boto3가 EC2 metadata를 찾으려 할 수도
있어 네트워크 비결정성도 남아 있었다.

**조치** — `test_history.py`가 application module을 import하기 전에 테스트 전용
`AWS_DEFAULT_REGION`, dummy credential, `AWS_EC2_METADATA_DISABLED=true`를 넣는다. 실제 AWS
호출은 계속 하지 않고, Lambda 코드나 배포 환경변수도 바꾸지 않는다. 빈 환경을 재현하는 이력
기능 변수들은 기존대로 비워 둔다.

**왜 늦게 찾았나** — CI에 시험을 연결하기 전에는 개발자 Mac의 AWS 설정을 테스트 전제로
착각했다. 로컬에서 boto3가 설치돼 있는 경로와 없는 경로는 검사했지만, **boto3는 있고 AWS
설정은 없는 Runner 경로**를 검사하지 않았다.

---

## T-029. Chat Source Adapter는 성공했는데 DLQ가 늘어난다

**증상** — 합성 Chat Candidate는 Adapter 로그에서 `status=ENQUEUED`, Lambda `Errors=0`이고
Signal Queue까지 정상 전달됐다. 그런데 E2E 종료 시 Adapter DLQ visible count가 1 증가해
“현재 Candidate 처리 실패”처럼 보였다.

**원인** — DynamoDB Stream event source mapping을 오래 비활성화했다가 다시 켜면 마지막
checkpoint 이후 Candidate record를 다시 본다. 이 mapping은 `maximum_record_age_in_seconds=300`
과 on-failure SQS destination을 사용한다. 이미 5분을 넘긴 record는 Lambda handler까지 오지
않고 destination으로 이동한다. 따라서 handler 안의 `CHAT_SOURCE_ADAPTER_NOT_BEFORE_EPOCH`
cutover로는 이 record를 `IGNORED_BEFORE_ACTIVATION` 처리할 수 없다.

**조치** — E2E 실행기는 작업 Queue는 반드시 빈 상태에서 시작하지만 기존 DLQ는 삭제하지
않는다. Signal·Invocation DLQ는 시작 baseline 증가 여부를 검사한다. Stream Adapter DLQ는
테스트 종료 시 메시지를 잠깐 읽고 visibility를 즉시 0으로 복구하면서, 이번 합성
`broadcast_id`가 포함됐는지 본문을 출력하지 않고 검사한다. 현재 Candidate가 없고 Adapter
로그가 `ENQUEUED`라면 오래된 record의 DLQ 이동과 이번 실행 실패를 분리할 수 있다.

**왜 늦게 찾았나** — DLQ 증가는 보통 handler 오류로 해석하지만, record-age 폐기는 handler
호출 전에 일어나 Lambda `Errors`와 애플리케이션 로그가 모두 정상이다. DLQ 전송 시각,
mapping의 최대 record age, 성공한 Candidate sequence를 함께 보지 않으면 서로 모순된 상태처럼
보인다.

---

## T-030. 앱은 정상인데 `o2.app.*`가 전부 No Data다

**증상** — 신규 이미지와 `DD_AGENT_HOST=status.hostIP`가 배포됐고 API 요청도 200이지만
Datadog에서 `o2.app.*` series가 하나도 생기지 않았다. 애플리케이션의 UDP `sendto`는
예외 없이 성공했다.

**원인** — Datadog Helm chart의 `dogstatsd.portEnabled=true`는 컨테이너의 8125/UDP만
선언한다. 노드 IP로 보내는 경로에 필요한 hostPort는 `dogstatsd.useHostPort=true`가 별도다.
실제 DaemonSet에는 `containerPort=8125`만 있고 `hostPort`가 비어 있어 패킷이 Agent에
도달하지 않았다.

**조치** — `04-platform` Datadog values에 `useHostPort=true`를 추가하고 plan/apply 뒤
DaemonSet의 `8125/UDP hostPort=8125`를 확인한다. 앱 파드에는 `DD_ENTITY_ID=metadata.uid`도
주입해 UDP와 APM의 Kubernetes origin 연결 근거를 제공한다. 그 뒤 실제 앱 요청과 Datadog
recent point를 다시 확인한다.

**왜 늦게 찾았나** — `portEnabled`라는 이름과 UDP `sendto`의 성공 때문에 수신 포트가
노드에도 열렸다고 오해했다. UDP는 목적지 listener가 없어도 송신 성공으로 보이며,
Datadog Agent 자체에는 다른 소스의 DogStatsD 패킷이 계속 들어와 전체 상태도 정상처럼 보였다.

---

## T-031. distribution 값은 보이는데 p95 위젯만 No Data다

**증상** — `o2.app.operation.duration`을 DogStatsD distribution(`|d`)으로 보냈고
`avg:` 쿼리에는 파드별 값이 보이는데, 같은 범위의 `p95:` 쿼리는 series가 0이었다.
대시보드 위젯과 Terraform은 오류 없이 생성되어 구성 자체는 정상처럼 보였다.

**원인** — Datadog distribution metric의 percentile 집계는 기본으로 활성화되지 않는다.
`datadog_metric_tag_configuration`에서 `include_percentiles=true`를 관리하지 않는 metric은
평균을 조회할 수 있어도 p95 시계열이 만들어지지 않는다.

**조치** — percentile이 명시 요구사항이 아닌 운영 현황 위젯은 실제 존재하는 `avg:`로
연결했다. p95가 필요한 monitor나 SLO를 추가할 때만 queryable tag 목록과
`include_percentiles=true`를 Terraform으로 함께 관리하고, 늘어나는 custom metric 비용을
먼저 확인한다. 데이터 주입 검증에서는 대시보드와 같은 tag filter로 recent point를 조회한다.

**왜 늦게 찾았나** — distribution 타입이면 percentile도 자동 생성된다고 생각했고,
Terraform validate와 dashboard apply가 유효한 쿼리의 데이터 존재 여부까지 검사하지 않는다.
단일 진단값도 정상 수집되어 `avg`에는 보였기 때문에 p95 쿼리를 따로 실행하기 전까지
수집 실패와 집계 설정 누락을 구분할 수 없었다.

---

## T-032. APM span에는 `pod_name`이 있는데 trace metric에서 `by {pod_name}`이 안 된다

**증상** — Trace Explorer의 개별 `fastapi.request` span에는 `pod_name`이 보이지만
`p95:trace.fastapi.request{service:api} by {pod_name}`은 파드별 시계열을 만들지 못했다.
APM additional primary tag 설정 화면에도 `pod_name`이 후보로 나오지 않았다.

**원인** — 수집된 span의 태그와 미리 집계되는 표준 trace metric의 tag set은 별개다.
`pod_name`은 span에는 들어왔지만 이 조직의 APM additional primary tag 후보가 아니므로
표준 `trace.fastapi.request` metric의 group-by 축으로 승격할 수 없다.

**조치** — `@duration`을 distribution으로 계산하는 span-based metric을 만들고
`pod_name`을 `group_by`로 선언한다. 실제 span 검색에서 `custom.pod_name`과
`duration`(나노초)을 먼저 확인한다. 위젯은 생성된 metric을 `by {pod_name}`으로 조회하고
기존 ms 계약에는 `1,000,000`으로 나눠 연결한다. DB 지연도 같은 방식으로
`operation_name:pymysql.query` span에서 만든다.

**왜 늦게 찾았나** — Trace Explorer에서 보이는 모든 span tag가 표준 trace metric에도
자동으로 붙는다고 생각하기 쉽고, additional primary tag UI는 선택 불가능한 이유를
설명하지 않는다. 실제 span payload와 metric tag set을 따로 확인해야 경계가 드러난다.

---

## T-033. 로컬 state 파일이 JSON인데 Terraform이 파싱하지 못한다

**증상** — `terraform state pull` 출력을 Windows PowerShell의
`Set-Content -Encoding utf8`로 저장한 뒤 `terraform state mv -state=...`를 실행하면,
첫 바이트에서 JSON 구문 오류가 나고 `version` 속성도 없다고 보고한다.

**원인** — Windows PowerShell 5.1의 `utf8` 인코딩은 파일 앞에 UTF-8 BOM을 쓴다.
Terraform state 파서는 BOM이 붙은 로컬 state 파일을 JSON으로 읽지 못한다. 원격 backend나
state 내용이 손상된 것이 아니라 로컬 복사 과정에서 바이트가 추가된 것이다.

**조치** — 원격 state를 다시 pull하고 `System.Text.UTF8Encoding($false)`를 사용해 BOM 없이
저장한다. 교차-state 이동은 원격에 push하기 전에 로컬 복사본에서 먼저 수행하고, 대상 주소의
누락·원본 잔존·목적지 초과가 모두 0인지 확인한다. 검증된 목적지 state를 먼저 push한 뒤 원본
state를 push해, 두 번째 push 실패 시에도 리소스 소유권을 복구할 수 있는 상태를 유지한다.

**왜 늦게 찾았나** — 파일 확장자와 화면에 보이는 내용은 정상 JSON이고 BOM은 일반 텍스트
출력에서 보이지 않는다. 또한 오류가 state lock 획득 단계에 함께 표시되어 backend 잠금 문제로
오해하기 쉽다.

---

## T-034. Correlator가 Shadow 메시지를 받자마자 모두 실패한다

**증상** — 비활성 배포 검증 뒤 Correlator 이벤트 소스를 Shadow allowlist로 열자, 합성 Signal 세 건이 Incident 상태를 만들지 못하고 모두 재시도 상태에 들어갔다. Lambda 로그에는 `_mapping`에서 `TypeError: unsupported operand type(s) for -: 'dict' and 'set'`가 기록됐다.

**원인** — `SEVERITY_LEVELS`는 심각도 순위를 담은 dict인데 환경변수 JSON 매핑을 검증하는 경로에서 `SEVERITY_LEVELS - {"UNKNOWN"}`처럼 set 차집합 연산을 직접 수행했다. 테스트 대부분은 파싱을 마친 설정 객체를 직접 주입해서 전체 환경변수 로딩 경로를 거치지 않았다.

**조치** — 허용 심각도 검증을 `set(SEVERITY_LEVELS) - {"UNKNOWN"}`로 바꾸고, 실제 Terraform 환경변수와 같은 완전한 JSON을 넣어 `_mapping()` 전체를 호출하는 회귀 테스트를 추가했다. 재시도 전에는 이벤트 소스를 비활성화하고 실패한 합성 메시지를 정확한 idempotency key로 회수한다.

**왜 늦게 찾았나** — 타입 오류는 JSON 환경변수가 존재할 때만 실행되는 초기화 분기 안에 있었고, 기존 단위 테스트가 계산 규칙 중심으로 설정 객체를 직접 전달해 배포 형태의 설정 로딩 경계를 건너뛰었다.

---

## T-035. AWS CLI로 보낸 JSON이 Lambda에서 `SQS_BODY` 거부된다

**증상** — 계약 예제 객체를 PowerShell에서 `ConvertTo-Json -Compress`한 뒤 `aws sqs send-message --message-body $json`으로 보내면, Correlator가 `CONTRACT_REJECTED:SQS_BODY`로 거부한다. 같은 객체를 로컬 JSON 파서로 읽으면 정상이다.

**원인** — Windows PowerShell이 네이티브 실행 파일에 문자열 인자를 전달하는 과정에서 JSON의 큰따옴표를 보존하지 않았다. SQS에는 JSON 객체 문자열이 아니라 따옴표가 손실된 본문이 저장됐다.

**조치** — JSON을 BOM 없는 UTF-8 임시 파일로 직렬화하고 AWS CLI에는 `--message-body file://<path>`로 전달했다. 전송 직후 임시 파일을 삭제하고, 실패 메시지는 이벤트 소스를 닫은 뒤 MessageId로 한정해 회수했다.

**왜 늦게 찾았나** — 전송 명령은 성공 MessageId를 반환하고 SQS도 본문 형식을 검증하지 않는다. 손상은 CLI 프로세스 경계에서 생기므로 송신 측 객체와 Lambda의 JSON 파싱을 따로 보면 모두 정상처럼 보인다.

---

## T-036. validate는 통과하지만 IAM policy plan이 duplicate Sid로 실패한다

**증상** — `terraform validate`는 성공하지만 `terraform plan`에서
`writing IAM Policy Document: duplicate Sid`로 중단된다.

**원인** — 브랜치 병합 과정에서 `aws_iam_policy_document` 안의 history 권한 statement 세 개가
내용과 `sid`까지 동일하게 두 번 들어갔다. HCL 구문은 유효하므로 validate는 이를 잡지 않고,
AWS 정책 JSON을 렌더링하는 plan 단계에서 provider가 중복 Sid를 거부했다.

**조치** — 동일한 statement 한 벌만 제거하고 target plan으로 IAM JSON과 Lambda 코드 변경 범위를
다시 확인한다. 정책을 병합한 뒤에는 validate뿐 아니라 자격증명이 있는 plan도 실행한다.

**왜 늦게 찾았나** — 충돌 표식 없이 정상 병합됐고 두 블록의 action 순서만 달라 육안 diff에서
별개 권한처럼 보였다. Terraform core의 validate와 provider의 정책 렌더링 검증 시점도 다르다.

---

## T-037. topologySpreadConstraints 를 걸었는데 파드가 안 갈린다

**증상** — 매니페스트에 `DoNotSchedule` 로 AZ 분산을 걸었는데 복제본 두 개가
같은 AZ 에 올라간다. 이벤트도 경고도 없고 Argo 는 `Synced` 로 보고한다.

**원인 A — 같은 `topologyKey` 로 항목을 둘 적으면 하나로 합쳐진다.**
이 배열의 merge key 가 `topologyKey` 다. `kubernetes.io/hostname` 으로 두 항목을
적으면 서버가 병합하면서 뒤엣것의 `whenUnsatisfiable` 을 버리고 `labelSelector` 는
합친다. 매니페스트에는 제약이 둘로 보이지만 클러스터에는 `ScheduleAnyway` 하나만
남는다. 게다가 `last-applied-configuration` 애노테이션에 그 중복 리스트가 남아
있으면 고친 매니페스트를 넣어도 3-way 병합 결과가 `maxSkew: 0` ·
`whenUnsatisfiable: ""` 이 되어 검증에서 apply 자체가 거부된다 — 애노테이션이
갱신되지 않으므로 다음 시도도 같은 자리에서 실패한다.

**원인 B — 롤링 중에는 구 ReplicaSet 파드까지 센다.**
제약은 파드가 스케줄되는 **순간에만** 판정한다. 구 파드가 양쪽 AZ 에 하나씩 남은
상태에서는 새 파드를 어느 쪽에 놓아도 skew 가 1 이라 둘 다 통과한다. 그렇게 새
파드 둘이 같은 AZ 로 간 뒤 구 파드가 빠지면 결과만 쏠린다. **각 단계는 제약을
지켰으므로 아무 신호도 남지 않는다.**

**조치**

- A: 두 번째 항목의 `topologyKey` 를 다르게 한다. AZ 분산이라면
  `topology.kubernetes.io/zone` 이 원래 의도에도 맞다. 이미 오염된 애노테이션
  때문에 apply 가 막히면 해당 리소스에
  `argocd.argoproj.io/sync-options: ServerSideApply=true` 를 붙인다 — SSA 는
  필드 소유권으로 병합해 이 이력을 타지 않고, 리소스 단위라 Argo 설정을 건드리지
  않는다.
- B: `matchLabelKeys: ["pod-template-hash"]` 를 넣는다. 같은 ReplicaSet 파드끼리만
  비교하므로 새 파드 둘이 서로를 보고 갈라진다. EKS 애드온(coredns·metrics-server)도
  스키마의 `topologySpreadConstraints` 가 `type: array` 로 열려 있어 그대로 전달된다.
- 고친 뒤 **롤링을 두 번 연속 돌려 확인한다.** 한 번만 보면 우연히 갈린 것과
  구분되지 않는다.
- 애노테이션을 추가할 때 `metadata` 아래에 `annotations:` 블록이 이미 있는지 본다.
  두 벌이 되면 YAML 중복 키라 뒤엣것만 남아 새로 넣은 값이 통째로 사라진다.

**왜 늦게 찾았나** — 세 겹으로 가려져 있다. 첫째, 병합된 결과가 patch 적용 후
상태와 일치하므로 Argo 가 드리프트로 잡지 않는다. 둘째, 원인 B 는 매 단계가
제약을 만족해 이벤트가 남지 않는다. 셋째, `rollout restart` 직후에는 우연히
갈리는 경우가 많아 그때만 확인하면 통과한다 — 실제로는 다음 배포에서 깨졌다.
서버 dry-run 결과가 맞게 나오는 것도 함정이다. 그 입력이 이미 애노테이션이
빠진 상태였는데 제약 두 개는 맞게 렌더링되어 통과로 보였다.

---

## T-038. 조치 실행기가 증설했는데 10초 뒤 원래 replicas로 돌아간다

**증상** — `o2-dev-dify-scale-executor`가 API를 2 → 3으로 바꿨고 새 파드도
Ready가 됐지만 약 10초 뒤 다시 2로 줄었다. Lambda 응답은 성공이고 Argo CD도
`Synced/Healthy`라 실패 주체가 보이지 않는다.

**원인** — Argo CD가 아니라 cue-warmer가 방송 큐시트의 기준값 2를 10초마다
재적용했다. API Deployment의 `/spec/replicas`는 Argo ignoreDifferences와
`RespectIgnoreDifferences=true`가 이미 적용돼 있었다. 반면 cue-warmer에는
Agent 실험 중 조치 소유권을 넘겨받는 잠금이 없어서, 정상적인 사전 확장 원복과
Agent의 임시 증설이 서로를 덮었다.

**조치**

- 실험 전 cue-warmer 로그와 `SCALE_ENABLED`를 확인한다. 두 번 이상의 reconcile
  주기 동안 목표 replicas가 유지돼야 증설 성공으로 판정한다.
- 2026-08-25 리허설에서는 별도 runtime gate가 없어 RoleBinding의 subject를
  임시로 비워 scale GET/PATCH를 403으로 막았다. 종료 직후 원래
  `ServiceAccount/o2-dev/cue-warmer`를 복원하고 로그가 다시 200으로 바뀌는 것까지
  확인했다. 이것은 긴급한 실험 격리 수단이지 최종 Runbook은 아니다.
- 반복 시연 전에는 `action_state`의 incident/action lock을 cue-warmer도 읽게 하거나,
  별도 experiment lock을 두어 한 시점의 replicas 소유자를 하나로 만든다. TTL과
  종료 시 기준값 복원도 같은 잠금 계약에 포함한다.

**왜 늦게 찾았나** — 실행 Lambda와 rollout은 모두 성공했고, replicas를 되돌리는
대표 주체인 Argo CD부터 확인하게 된다. 실제 원복 주체는 10초 주기의 다른
컨트롤러였고, Kubernetes 이벤트에는 "누가 scale을 바꿨는지"가 직접 남지 않아
cue-warmer 애플리케이션 로그를 보기 전까지 구분되지 않았다.

## T-040. 지표는 있는데 조회 값이 `0` 이나 `1.0` 으로 튄다

**증상** — 채널 총량 제한이 실제로 동작하는 중인데 Hot 논리 지표 조회가
`items_per_sec = 0.0`, `block_rate = 1.0` 을 준다. 같은 응답의 `sample_count` 은
1,193,650 이고 `status` 는 `OK`, `freshness_seconds` 는 23 초다. 즉 데이터도 있고
신선하다. 조금 전 같은 조회는 `block_rate = 0.0` 이었다.

**원인** — `o2hot/metric_catalog.py:227` 의 `_latest()` 가 창 안에서 타임스탬프가
가장 큰 점 **하나**를 값으로 쓴다. Datadog 의 마지막 버킷은 아직 집계 중이라
`null` 이 아니라 0 으로 채워져 오는 경우가 있고, 그 0 이 그대로 지표 값이 된다.
비율 지표는 분자 · 분모의 마지막 버킷이 서로 어긋나면 0 이나 1.0 같은 극단값이 된다.

**확인** — WebSocket 프로브로 실제 전달을 세면 팬아웃이 살아 있다.

```bash
kubectl exec -n o2-dev deploy/chat-gateway -- node -e '
const WebSocket=require("ws");
const ws=new WebSocket("ws://127.0.0.1:8080/ws?broadcast_id=<방송>");
let got=0; ws.on("message",d=>{try{got+=(JSON.parse(d).items||[]).length}catch(e){}});
setTimeout(()=>{console.log("수신",got);process.exit(0)},15000);'
```

**영향** — 복구 판정이 이 값을 읽는다. `items_per_sec <= 20000` 은 0 이 오면 무조건
통과하고 `block_rate <= 0.05` 는 1.0 이 오면 무조건 실패한다. 같은 `_latest()` 를
`latency_p95` · `failure_rate` · `cache_hit_rate` 도 쓴다. warm 도 방금 열린 창을
`latest` 로 주므로 같은 순간 `channel_limited_rate = 0` 이 나온다.

**고침 (2026-08-26)** — 값을 점 하나로 정하던 것을 **창 전체 집계**로 바꿨다.
`_latest()` 는 남아 있지만 이제 값 결정에 쓰지 않는다.

| `value_type` | 어떻게 | 왜 |
|---|---|---|
| `ratio` (6) | 분자 · 분모를 각각 창 전체 합산 후 나눔 | 비율의 평균은 비율이 아니다. 분모가 버킷마다 다르면 틀린다 |
| `rate` (2) | 창 평균 | "지금 처리량" |
| `count` (1) | 창 합 | 자명 |
| `gauge` (5) | 창 **최댓값** | 백분위는 평균낼 수 없다. 복구 판정에서 최댓값이 보수적이다 — 운 좋은 버킷 하나로 "복구" 를 선언하지 않는다 |

그리고 어느 경우든 **안 닫힌 마지막 버킷을 뺀다.** 판정 기준은 Datadog 응답이
series 마다 주는 `interval` 이다 — `버킷 시작 + interval > to_ts` 면 진행 중으로
본다. 매직넘버를 쓰지 않으려고 이 값을 쓴다.

비율은 카탈로그의 `primary` 를 ` / ` 로 쪼개 두 번 조회한다. 여섯 ratio 지표가
모두 정확히 `분자 / 분모` 두 조각이라 **카탈로그 스키마는 안 바꿨다.**

warm 쪽도 같이 고쳤다 — `o2warm/client.py` 의 `latest()` 와 `snapshot()` 이
`window_end <= now` 인 **닫힌 창**만 고른다. 닫힌 창이 없으면 `None` 이다. 부분값을
주느니 없다고 말하는 편이 낫다. `windows` 는 추세를 봐야 하므로 열린 창까지 그대로 준다.

회귀 시험은 `hot/tests/test_metric_catalog.py` 4개와
`warm/tests/test_client_latest_window.py` 3개다. 일곱 개 모두 고치기 전 상태에서
실패하는 것을 확인했다.

**왜 늦게 찾았나** — `status: OK` 에 `sample_count` 이 백만 단위라 응답만 보면
정상이다. 값이 0 이면 "부하가 안 걸렸나" 로 읽히고, 1.0 이면 "조치가 과했나" 로
읽힌다. 둘 다 그럴듯해서 지표를 의심하지 않는다. Valkey 카운터와 WebSocket 프로브로
같은 순간을 따로 재고 나서야 갈렸다.

## T-041. 부하 테스트 p95 가 서버 지표보다 6배 크다

**증상** — `loadtest/broadcast.js` 가 40,000 아이템/s 에서 전파 p95 1,252ms 를
보고하는데, 같은 시각 서버측 `o2.chat.propagation` p95 는 186ms 다.

**원인** — 두 값이 다른 구간을 잰다. 서버측은 발행 시각부터 WebSocket send 직전까지고,
k6 값은 거기에 네트워크와 **k6 자신의 이벤트 루프 지연**을 더한 것이다. VU 하나가
소켓 여러 개를 들고 단일 이벤트 루프로 프레임을 처리하므로, 노트북 한 대가 2,000 소켓에
초당 7,500 프레임을 받으면 그 밀림이 서버 지연으로 기록된다.

**확인** — 서버측 지표를 같이 본다. 서버가 평평한데 k6 만 오르면 생성기 쪽이다.
`k6 CPU%` 가 100% 에 안 닿아도 발생한다 — 코어 포화가 아니라 루프 지연이다.

**영향** — M-010 의 계단 값이 전부 k6 클라이언트측이다. 거기서 읽은 "2 파드 안전선
20,000 아이템/s" 는 서버 용량이 아니라 이 측정 방식의 한계선일 수 있다.
서버 용량을 정하려면 생성기를 여러 대로 나누거나 서버측 지표로만 판정한다.

**왜 늦게 찾았나** — k6 표는 연결 실패 0 · 깨진 프레임 0 으로 깨끗했고 p95 만 올랐다.
"서버가 느려졌다" 로 읽기 딱 좋다. `docs/measurements.md` M-010 주석에 이 현상이
경고로 적혀 있었지만, 그 크기를 재본 적이 없어서 얼마나 큰 편향인지 몰랐다.

## T-042. `latency_p95_by_pod`가 실부하를 걸어도 계속 비어 있다

**증상** — S2(파드 편중) real test에서 canary 파드에 실제 CPU 스로틀(p95 2.7s)까지
만들었는데, Dify 진단이 받은 `latency_p95_by_pod`는 계속 빈 값이고 `latency_samples_by_pod`도
표본이 1~3건뿐이었다. `GET /api/broadcasts/{id}`를 300~400건씩 반복 호출해도 안 바뀌었다.

**원인(확정, 2026-08-26 정정)** — `bc_1042`의 `read_path_degraded` 노브가 켜져 있었다.
`apps/api/app/services/broadcast.py`의 `get_snapshot()`은 `if not
_read_path_degraded(broadcast_id): _emit_inventory_check(...)`로 이 플래그가 켜지면
`inventory.check` 발행 자체를 건너뛴다(D-062, S3 조치 노브 — 응답 내용은 안 바뀌고
부가 발행만 끈다). `GET /api/admin/read-path-degraded?broadcast_id=bc_1042`로 확인하니
`read_path_degraded_active: true`였다 — S3 관련 이전 작업에서 켠 채로 안 지운 것으로
보인다. `POST .../read-path-degraded {"action":"clear"}`로 끄고 다시 15건 요청하니
`event_count: 15`(정확히 1:1), `latency_p95_by_pod`에 **지금 떠 있는 실제 파드 이름**으로
값이 즉시 채워졌다. 파이프라인 지연·유실이 아니라 발행 자체가 꺼져 있던 것이었다.

처음 의심했던 두 경로는 둘 다 틀렸다 — Datadog APM 미태깅설도, Kinesis 배치 경합으로
인한 조용한 데이터 유실설(`infra/06-datastream/lambda.tf`의 `already_applied` 가드 주석
근거로 세운 가설)도 아니었다. 후자는 해당 시간대 `o2-agg` Lambda의 `IteratorAge`를
CloudWatch로 직접 확인해(최대 3.8초, 문제 사례인 102초와 비교 불가) 기각했다.

**왜 늦게 찾았나** — 필드 이름과 근처 주석("APM span-based metric이 대체한다")이
그럴듯한 다른 원인을 가리켜서 거기부터 팠고, 그다음엔 Kinesis 파이프라인의 알려진
결함(같은 파일의 실측 경고 주석)이 있어 거기로 더 팠다. 둘 다 코드에 진짜 있는
문제이지만 **이번 증상의 원인은 아니었다** — 정작 원인은 같은 서비스의 다른 파일
(`broadcast.py`)에 있는 조건문 하나였고, `GET /api/admin/read-path-degraded`로
라이브 상태를 직접 찍어보고 나서야 드러났다. 문서·주석에서 그럴듯한 설명을 찾는 것과
라이브 상태를 직접 조회하는 것 중 후자를 먼저 했어야 더 빨리 찾았을 것이다.
---

## T-043. Agent 가 늘린 파드가 몇 초 만에 원래대로 돌아간다

**증상** — S2 E2E 에서 Agent 가 1차 조치로 `api` 를 2 → 3 으로 늘렸다. patch 는
성공했고 `ScalingReplicaSet` 이벤트도 남았는데, 3~5초 뒤 3 → 2 로 되돌아갔다.
두 번의 조치 시도에서 모두 같았다. 조치 실행기는 patch 뒤 `STABILIZATION_SECONDS`
만큼 자고 200 을 돌려주므로, **실행기가 성공을 보고하는 시점에는 이미 조치가
사라져 있다.** 검증 노드는 증설 전 상태를 보고 "효과 없음"으로 판정한다.

```
21:07:1x  Scaled up   api 2 -> 3     (Agent)
21:07:22  Scaled down api 3 -> 2     (5초 뒤)
21:10:4x  Scaled up   api 2 -> 3     (Agent, 재시도)
21:10:53  Scaled down api 3 -> 2     (3초 뒤)
```

**원인** — `cue-warmer` 다. 큐시트 기반 사전 확장기가 10초마다 `api` 의 scale 을
폴링해서, **현재값이 기준값과 다르면 기준값으로 되돌린다.**

```
2026-08-26 12:07:22 INFO cue-warmer 원복: api 3 -> 2
2026-08-26 12:10:53 INFO cue-warmer 원복: api 3 -> 2
```

워머는 `api=3` 을 보고 자기가 사전 확장으로 올려둔 잔여물이라고 판단한다.
**누가 올렸는지 구분하지 않는다.** Agent 와 워머가 같은 `spec.replicas` 를
소유하고 있고, 폴링 주기가 짧은 워머가 항상 이긴다.

**해결** — 실험 중에는 워머를 세운다. 조치 수단이 파드 수일 때 되돌리는 주체를
줄인다는 원칙은 `scenario-experiment.md` 3절에 이미 있다(거기서는 HPA·KEDA 를
대상으로 적었는데, 워머가 같은 역할을 한다).

```bash
kubectl scale deploy/cue-warmer -n o2-dev --replicas=0
# 실험이 끝나면
kubectl scale deploy/cue-warmer -n o2-dev --replicas=1
```

**이것은 임시 조치다.** 운영에서는 워머가 켜져 있으므로, 지금 구조로는 Agent 의
증설 조치가 운영에서 성립하지 않는다. 워머가 **자기가 설정한 값일 때만** 되돌리게
바꿔야 공존한다. 측정 결과를 남길 때는 "워머 정지 상태에서 측정"을 함께 적는다.

**왜 늦게 찾았나** — Argo CD 를 먼저 의심했다. `argocd.tf` 에 api `/spec/replicas`
ignore 와 `RespectIgnoreDifferences=true` 가 있다는 것을 알고 있었고, 그 설정이
안 먹는 사례를 아는 탓에 거기부터 팠다. 라이브 Application 을 찍어보니 설정은
정상이었고 **마지막 sync 가 전날 16:08** 이라 무죄였다. 되돌리는 주체 후보를
`replicas` 를 쓰는 워크로드로 넓히고 나서야 워머가 나왔다. 이벤트에 "누가"
되돌렸는지가 안 남는다는 것이 핵심 어려움이다 — `kubectl get events` 는
`deployment-controller` 만 보여준다. **그 값을 쓰는 컨트롤러를 먼저 세어봤어야
했다.**

---

## T-044. S2 Dify 워크플로가 매번 `status code 400` 으로 죽는다

**증상** — S2 E2E 에서 진입·진단·런북 조회·조치 실행까지 정상으로 간 뒤,
워크플로가 끝까지 못 가고 죽는다. Worker 로그에는 실패한 노드가 안 나온다.

```
[ERROR] RuntimeError: dify workflow failed: Request failed with status code 400
```

**원인** — 워크플로 안의 `read-path-degraded` 상태 조회 노드가 **존재할 수 없는
`broadcast_id`** 로 호출한다.

```
GET /api/admin/read-path-degraded?broadcast_id=LIVE-001  ->  400 Bad Request
```

`LIVE-001` 은 Dify normalize 의 fallback 값이다. S2 진입 monitor 는 서비스 단위
쿼리(`p99:trace.fastapi.request{service:api,env:dev}`)라 알림 태그에 방송 축이
없고, 그러면 normalize 가 `LIVE-001` 을 채운다. api 쪽 `BroadcastId` 는
`apps/api/app/schemas/common.py` 에서 `^bc_[0-9]+$` 로 제약돼 있어 `LIVE-001` 은
검증에서 떨어진다. 노드 하나의 400 이 워크플로 전체를 죽인다.

**S1 이 같은 뿌리의 문제를 먼저 밟았다.** 거기서는 팬아웃 총량(서비스 합계)으로
진입할 때 방송 축이 없어 **없는 방송에 채널 제한을 거는** 형태로 나타났고,
진입을 `by {broadcast_id}` multi-alert 로 옮겨 해결했다. S2 는 서비스 전체 꼬리
지연이 주제라 같은 해법을 쓸 수 없다.

**해결** — 아직 안 고쳤다. 방향은 둘을 같이 가는 것이다.

1. 방송 축이 없으면 `read-path-degraded` 노드를 **건너뛴다.** 이 조회는 S3 용이고
   S2 에는 필요 없다.
2. `LIVE-001` fallback 을 없앤다. 없는 값을 지어내면 그 값이 조회에 그치지 않고
   **조치 대상으로도 쓰인다**(S1 사례).

**왜 늦게 찾았나** — Worker 로그의 오류 문구가 Dify 가 만든 일반 문구라 어느 노드가
400 인지 안 나온다. Dify 는 VPC 내부 사설 IP 라 콘솔 실행 로그를 밖에서 못 본다.
**부르는 쪽이 아니라 불리는 쪽 로그로 좁혀서** 찾았다 — 워크플로가 부르는 대상을
DSL 환경변수에서 열거하고(`WARM_API_URL`, `HOT_PROXY_URL`, `API_ADMIN_URL` …)
각각의 로그를 훑으니 api 파드 접근 로그에 400 이 그대로 찍혀 있었다.
---

## T-045. Dify 컨테이너를 다시 만든 뒤 모든 요청이 502

**증상** — Dify 설정을 고치려고 `docker compose up -d api worker` 를 돌린 뒤부터
Agent 호출이 전부 `HTTP Error 502: Bad Gateway` 로 실패한다. **컨테이너는 전부
정상으로 보인다** — `docker compose ps` 에서 `docker-api-1` 은 `Up (healthy)` 고
`curl http://127.0.0.1:5001/health` 도 응답한다. 그래서 Dify 가 아니라 부르는
쪽(Lambda·네트워크)을 먼저 의심하게 된다.

**원인** — nginx 가 **옛 컨테이너 IP** 를 물고 있다.

```
[error] connect() failed (111: Connection refused) while connecting to upstream,
        upstream: "http://172.21.0.12:5001/v1/workflows/run"
```

`up -d` 는 컨테이너를 **재생성**하므로 api 가 새 IP 를 받는다. nginx 는 시작
시점에 upstream 이름을 한 번만 해석해 캐싱하기 때문에, 자기가 재시작되지 않는 한
없어진 IP 로 계속 연결을 시도한다. `docker compose ps` 는 nginx 를 `Up 33 hours`
로 보여주는데 그것이 정상이 아니라 **원인**이다.

**해결**

```bash
cd /opt/dify/docker && sudo docker compose restart nginx
```

확인은 `curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1/v1/workflows/run`
로 한다. **401 이 나오면 정상이다** — 인증 없이 빈 요청을 보냈으니 nginx 가 api 까지
도달했다는 뜻이고, 502 면 아직 옛 IP 를 보고 있다.

**애초에 안 밟는 법** — 설정만 바꿀 때는 `up -d`(재생성) 대신 `restart` 를 쓴다.
재생성이 필요하면 **nginx 도 같이 재시작한다.**

**왜 늦게 찾았나** — 모든 컨테이너가 healthy 라 Dify 를 용의선상에서 뺐다. 호출하는
Lambda 쪽과 보안그룹을 먼저 봤다. **nginx 의 에러 로그에 죽은 IP 가 그대로 찍혀
있었는데** 컨테이너 상태만 보고 로그를 안 봤다. 상태가 아니라 로그를 먼저 봤어야 했다.

---

## T-046. Bedrock 호출이 `Read timed out` 으로 끊긴다

**증상** — Dify 워크플로가 중간에 죽고 Worker 에 이렇게 남는다.

```
dify workflow failed: InvokeError:
AWSHTTPSConnectionPool(host='bedrock-runtime.ap-northeast-2.amazonaws.com', port=443):
Read timed out.
```

**Bedrock 쪽에는 오류가 없다.** 같은 시간대 CloudWatch `AWS/Bedrock` 에서
`InvocationClientErrors`·`InvocationServerErrors`·`InvocationThrottles` 가 전부 0 이고
`Invocations` 는 정상 집계된다. **모델은 응답했고 클라이언트가 기다리다 끊은 것이다.**

**원인** — Dify 의 Bedrock 플러그인이 botocore 클라이언트를 이렇게 만든다.

```python
# storage/cwd/langgenius/bedrock-*/provider/get_bedrock_client.py
client_config = Config(region_name=region_name)
```

`read_timeout` 을 안 주므로 **botocore 기본값 60초**가 적용된다. 2026-08-27 실측에서
호출당 서버측 지연이 **9.7~51.3초**였고 절반 이상이 30초를 넘었다. 서버측 51초짜리는
스트리밍 수신까지 더하면 클라이언트에서 60초를 넘는다.

느린 이유는 모델이 아니라 **보내는 양**이다 — 호출당 입력 16,000~21,700 토큰,
출력 최대 4,092 토큰. 같은 창에서 입력이 7,843 토큰이던 호출은 12.4초였다.

**`.env` 의 `TEXT_GENERATION_TIMEOUT_MS` 는 이 값이 아니다.** 그걸 60000 → 120000 으로
올려도 증상이 그대로였다. 그 값은 Dify 애플리케이션 레벨이고, 여기서 끊는 것은
플러그인 안의 botocore 다. **손잡이를 잘못 잡으면 "고쳤는데 안 낫는" 상태로 시간을 쓴다.**

**해결** — 셋 중 하나이고 아래로 갈수록 근본이다.

1. 플러그인의 `Config(...)` 에 `read_timeout` 을 준다. 빠르지만 **플러그인을
   재설치·업그레이드하면 날아가고 저장소에 안 남는다.**
2. 더 빠른 모델로 바꾼다. 같은 입력으로 직접 재보니
   `global.anthropic.claude-sonnet-5` **30.0초**, `global.anthropic.claude-haiku-4-5-20251001-v1:0`
   **11.8초**로 약 2.5배 차이였다(2026-08-27, 입력 24k~29k 토큰).
3. **보내는 양을 줄인다.** Warm 스냅샷 요청의 `windows=6` 을 줄이거나 진단에 안 쓰는
   필드(`rundown`·`policy`·`gaps`·`topology`)를 문맥에서 뺀다. 지연이 선형으로 준다.

**왜 늦게 찾았나** — 오류 문구에 `bedrock-runtime` 호스트가 찍혀서 **Bedrock 장애나
스로틀을 먼저 의심했다.** CloudWatch 를 봐야 그게 아니라는 게 갈리는데, 지표를 보기
전에 `.env` 에서 `timeout` 을 grep 해 제일 그럴듯한 이름(`TEXT_GENERATION_TIMEOUT_MS`)을
먼저 올렸다. **어느 계층이 끊었는지부터 확정했어야 했다** — 예외 타입이 botocore 것
(`AWSHTTPSConnectionPool`)이라는 게 처음부터 답을 가리키고 있었다.
