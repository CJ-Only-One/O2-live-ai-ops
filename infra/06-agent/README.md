# 06-agent — Dify 호스트

AI 에이전트 워크플로 오케스트레이션(Dify)을 **EKS 밖 EC2 한 대**에 올린다.
같은 VPC 프라이빗 앱 서브넷이라 EKS 파드에서 사설 IP 로 닿는다.

## 왜 EKS 안이 아닌가

| 이유 | 내용 |
|---|---|
| **블래스트 반경** | 이 프로젝트는 EKS 에 의도적으로 장애를 주입하고 에이전트가 그것을 해결한다. 고치는 쪽이 부서지는 쪽 위에 살면 노드 장애 시나리오에서 에이전트도 같이 죽는다 |
| **클러스터 사양** | 현재 노드그룹은 `t3.small` × 2 (max 3). Dify 는 컨테이너 9개에 실사용 8 GiB 다. 어차피 전용 노드그룹을 새로 파야 하고, 그럴 바에는 EC2 가 싸다 |
| **운영 비용** | 배포 경로가 Argo CD GitOps(D-004, D-006)라 매니페스트 9개 + PVC + StatefulSet 을 직접 쓰고 유지해야 한다. Dify 공식 지원은 docker compose 이고 Helm 차트는 커뮤니티 관리다 |
| **DB 재사용 불가** | Dify 는 PostgreSQL 을 쓴다. `03-data` 의 RDS 는 MySQL 8.4 라 못 쓴다. compose 번들 postgres 를 그대로 쓴다 |

**EKS 로 옮겨야 하는 시점** — Dify 가 시청자 트래픽 경로에 들어가 스케일링이
필요해질 때. 지금은 에이전트 운영 평면이라 해당 없다.

## 사양

| 항목 | 값 | 근거 |
|---|---|---|
| 인스턴스 | `t3.large` (2 vCPU / 8 GiB) | 공식 최소는 2 vCPU / 4 GiB 지만 워커 인덱싱에서 OOM. 8 GiB 가 실사용 하한 |
| 스토리지 | gp3 60 GiB, 암호화 | 이미지 약 10 GiB + postgres·weaviate 데이터 |
| 배치 | `private_app_subnet_ids[0]` | 데이터 서브넷은 RDS/ElastiCache 전용. NAT 경유 아웃바운드가 필요하다 |
| 퍼블릭 IP | 없음 | 인터넷 노출하지 않는다 |
| 인그레스 | EKS 노드 SG 에서 TCP 80 만 | nginx 가 콘솔·API 를 전부 앞단에서 받는다 |
| 이그레스 | 전체 허용 | 이미지 pull, SSM, LLM API |
| 접속 | SSM Session Manager | SSH 키·bastion 없음. 노드그룹과 같은 방식 |
| 스택 | 컨테이너 9개 + postgres + redis + weaviate | 전부 compose 번들 |

### 비용 감각

`t3.large` 온디맨드(ap-northeast-2)는 시간당 약 $0.12, 상시 가동 시 월 $80 대다.
**개인 계정이므로 안 쓸 때는 인스턴스를 정지한다** — EBS 요금만 남는다.
정확한 값은 apply 전에 확인할 것:

```bash
aws pricing get-products --service-code AmazonEC2 --region us-east-1 \
  --filters 'Type=TERM_MATCH,Field=instanceType,Value=t3.large' \
            'Type=TERM_MATCH,Field=location,Value=Asia Pacific (Seoul)' \
            'Type=TERM_MATCH,Field=operatingSystem,Value=Linux' \
            'Type=TERM_MATCH,Field=tenancy,Value=Shared' \
            'Type=TERM_MATCH,Field=preInstalledSw,Value=NA' \
            'Type=TERM_MATCH,Field=capacitystatus,Value=Used'
```

## 진행 순서

apply 순서에서 이 스택은 `02-eks` 뒤, `04-platform` 앞이다 —
노드 SG 를 읽어야 하고, `04-platform` 이 접속 정보를 파드에 주입하기 때문이다.

```
01-network → 02-eks → (03-data ∥ 06-agent) → 04-platform
```

## Agent 공통 진입점 Phase 1B-3D

`agent_entry_transport.tf`은 Signal Queue와 별도의 Agent Invocation Queue 사이에서 사용할
Generic Worker와 실행 ledger를 만든다. Phase 3D부터 Worker 입력은 병합 전 source trigger가
아니라 Correlator가 만든 `agent.incident.v1` revision이다.

```text
agent.trigger.v1 Signal Queue -> Incident Correlator -> Incident State
                                                    -> Agent Invocation Queue
                                                    -> disabled Generic Worker
                                                    -> private contract-test Dify

Generic Worker -> revision ledger + per-Incident lock
```

Phase 1B에는 실행 게이트가 두 개 있다.

| 게이트 | 값 |
|---|---|
| SQS event source mapping | `enabled=false` |
| Worker 환경변수 | `AGENT_ENTRY_EXECUTION_ENABLED=false` |

따라서 Terraform apply만으로 Dify 호출이 생기지 않는다. Worker는 Agent Invocation Queue
body를 `agent.incident.v1`로 검증하고, 실행이 활성화된 Shadow Phase에서만 DynamoDB의
revision 멱등 항목과 Incident lock을 함께 획득한 뒤 전용 테스트 앱을 호출한다. 같은
`idempotency_key`의 `SUCCEEDED` 항목은 다시 호출하지
않는다. `IN_PROGRESS`·`FAILED`도 자동으로 Dify를 재호출하지 않고 SQS redelivery를
DLQ까지 진행시킨다. 외부 호출은 성공했는데 ledger 확정만 실패한 애매한 구간에서 LLM을
두 번 실행하지 않기 위한 fail-closed 정책이다. 운영자가 Dify 실행 여부를 확인한 뒤에만
ledger를 정리하고 재투입한다.

Worker는 Incident State의 최신 revision을 consistent read한다. Queue에 대기하는 동안 더
최신 revision이 만들어졌다면 오래된 메시지는 `SUPERSEDED`로 기록하고 Dify를 호출하지
않는다. 같은 Incident의 다른 revision이 실행 중이면 lock 획득이 실패해 SQS에서 재전달된다.

전용 API key는 `o2/dev/dify-agent-entry-contract-test` Secrets Manager secret에서 실행
시점에만 읽는다. 값은 Terraform state, 코드, 로그에 남기지 않는다.
최종 `custom_alert_json` 직렬화 결과가 게시 입력 상한 30,000자를 넘으면 secret 조회,
ledger 획득, Dify 호출 전에 거부한다.

현재 `06-agent` 전체 plan에는 Phase 1B와 무관하게 먼저 병합된 기존 Lambda 코드 변경이
함께 잡힌다. 이 변경을 검토하지 않은 상태에서 전체 stack을 apply하지 않는다.
2026-08-23에는 Phase 1B 대상 저장 plan이 `14 add, 0 change, 0 destroy`이고 두 실행
게이트가 모두 `false`임을 확인한 뒤 한 번만 target apply했다. apply 후 Phase 1B 대상
재-plan은 `No changes`, 전체 plan은 기존 변경만 `0 add, 4 change, 0 destroy`였다.
상세 근거는 `docs/agent-entrypoint.md` 6.2에 있다.

Phase 1B apply 후 다음을 확인한다.

```bash
terraform output -raw agent_entry_event_source_enabled
aws lambda get-event-source-mapping --uuid <mapping-uuid> \
  --query '{State:State,LastProcessingResult:LastProcessingResult}' \
  --region ap-northeast-2
aws sqs get-queue-attributes --queue-url "$(terraform output -raw agent_invocation_queue_url)" \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
  --region ap-northeast-2
```

성공 조건은 event source가 `Disabled`, Queue/DLQ가 비어 있고 새 Dify workflow run이
0건인 것이다. 2026-08-23 실환경에서 이 조건을 모두 확인했다. Phase 3 전에는 event
source나 실행 플래그를 켜지 않는다.

Phase 3D 합성 Shadow E2E는 D-053에 따라 event source와 실행 플래그를 함께 켜고, 매 실행의
합성 `incident_id` 정확히 1개만 허용한다. 기본값은 두 게이트 `false`와 빈 allowlist다.
미허용 Incident는 Incident State 조회·Secret 조회·ledger 획득·Dify 호출 전에 실패한다.
상세 상태와 적용 순서는 `docs/agent-entrypoint.md` 6.7을 따른다.

## Datadog Source Adapter Phase 4A

`datadog_source_adapter.tf`은 기존 `o2-dify-ingress`와 분리된 Shadow Function URL을 만든다.
기존 ingress·Worker·Dify 코드를 수정하지 않으며 신규 Lambda는 Signal Queue까지만 전송한다.

```text
Datadog synthetic monitor
  ├─ existing webhook -> existing ingress -> existing Worker/Dify
  └─ shadow webhook   -> disabled Datadog Source Adapter -> Signal Queue
                                                           -> consumer disabled
```

기본값은 실행 `false`, 합성 cycle allowlist empty, cutover 2100-01-01이다. 활성화할 때는
합성 cycle key 정확히 1개와 명시 cutover가 함께 있어야 Terraform precondition을 통과한다.
Correlator와 Generic Worker를 별도로 켜지 않으므로 Adapter apply만으로 Dify는 호출되지 않는다.

권한은 기존 O2 webhook secret read, Signal Queue `SendMessage`, 기본 Lambda 로그뿐이다.
Function URL은 Terraform state에는 존재하지만 sensitive output으로만 노출하고 공유 문서·로그에
기록하지 않는다. secret 값은 Terraform이 읽지 않아 state에 없으며 로그에도 남지 않는다.
계약·인증·Queue 실패 로그는 내용 없이 CloudWatch metric/alarm으로 변환한다.

2026-08-24 구현 검증에서 06-agent Python suite 48개가 통과했고 기존 Lambda-runtime
`boto3` transaction 1개만 로컬에서 skip됐다. Terraform `fmt`·`validate`가 통과했으며 대상
plan은 신규 리소스만 `8 add, 0 change, 0 destroy`였다. apply는 하지 않았다. 실제 양쪽
source 지연 측정과 비활성 apply 순서는 `docs/agent-entrypoint.md` 6.8이 원본이다. 전체 stack
plan의 별도 기존 IAM 1개·Lambda 3개 update는 대상 저장 plan에서 제외해야 한다.

## Incident Correlator Phase 3B

D-055에 따라 `agent.trigger.v1`은 Agent 호출이 아니라 상관관계 전 source 신호다.
Phase 3B는 기존 `agent-trigger` Queue의 물리 이름을 유지하면서 다음 비활성 경로를 추가한다.

```text
agent.trigger.v1 Signal Queue
  -> disabled Incident Correlator
  -> Incident State DynamoDB
  -> agent.incident.v1 Agent Invocation Queue
  -> consumer 없음
```

| 게이트 | 기본값 |
|---|---|
| Correlator event source | `false` |
| `INCIDENT_CORRELATOR_EXECUTION_ENABLED` | `false` |
| correlation window | `0` |
| 합성 source allowlist | empty |
| Datadog monitor mapping | empty |

window `0`은 미설정 상태다. Phase 3C에서 두 source 도착 지연을 측정하기 전에는 값을
지어내지 않는다. event source와 실행 플래그를 켜더라도 window가 0이거나 합성 allowlist가
1-3개가 아니면 Terraform precondition이 실패한다. 기존 Agent Worker event source와
Correlator도 동시에 활성화할 수 없다.

Chat은 현재 S3 범위인 `READ_PATH → LATENCY/api` mapping만 갖는다. Datadog은 alert 제목이나
본문을 해석하지 않고 명시한 monitor ID mapping만 사용한다. mapping이 없거나 같은 조건의
OPEN Incident가 둘 이상이면 `AMBIGUOUS`로 기록하고 강제 병합하지 않는다.

Phase 3B apply만으로는 Signal Queue를 소비하지 않고 Agent Invocation Queue에도 consumer가
없으므로 Dify 호출은 0건이어야 한다. 적용·검증 순서는 `docs/agent-entrypoint.md` 6.5가
원본이다.

2026-08-24 병합본에서 Phase 3B 대상 저장 plan `13 add, 0 change, 0 destroy`만 적용했다.
적용 후 Correlator와 기존 Generic Worker event source는 모두 `Disabled`, Correlator 실행
플래그는 `false`, window는 `0`, 합성 allowlist와 Datadog mapping은 비어 있었다. Signal
Queue/DLQ와 Invocation Queue/DLQ는 모두 0건이고, Invocation Queue consumer와 Correlator
Log Stream도 0개였다. Incident State는 `ACTIVE`, `PAY_PER_REQUEST`, SSE·TTL·PITR enabled,
GSI `ACTIVE`, item 0이었다. 전체 stack 재-plan의 기존 `5 change`는 별도 검토 대상으로
남겼으며 적용하지 않았다.

2026-08-24 Phase 3C-A에서 test-only window 300초와 실행별 합성 key 두 개만 허용해
Signal Queue 직접 E2E를 수행했다. Chat→Datadog과 Datadog→Chat 모두 revision 1
`PROVISIONAL`에서 같은 Incident의 revision 2 `CORRELATED`로 전환됐다. Invocation Queue
consumer는 0개라 Dify 실행은 없었다. 종료 후 실행 gate·window·allowlist·Datadog mapping을
기본 비활성값으로 복귀하고 합성 DynamoDB 항목과 Queue 메시지만 개별 삭제했다. 운영
correlation window는 실제 source Adapter 전달 지연을 재기 전까지 미확정이다.

### 1. 버전 고정

```bash
curl -s https://api.github.com/repos/langgenius/dify/releases/latest | jq -r .tag_name
```

나온 태그를 `terraform.tfvars` 의 `dify_ref` 에 넣는다. `main` 인 채로 두면
그날 깨진 커밋을 클론한다.

### 2. apply

D-005 대로 **로컬에서 사람이** 돌린다. CI 는 `plan` 도 돌리지 않는다(D-023).

```bash
cd /Users/jyc/Desktop/Workspace/projects/cj-cw-o2/O2-live-ai-ops/infra/06-agent
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

### 3. 부팅 확인

user_data 는 **띄울 수 있는 상태까지만** 만든다. docker compose up 은 사람이 한다.

```bash
aws ssm start-session --target $(terraform output -raw instance_id) --region ap-northeast-2
sudo tail -f /var/log/cloud-init-output.log   # "finished" 나올 때까지
```

### 4. 기동

```bash
cd /opt/dify/docker
docker compose up -d
docker compose ps          # 전부 running/healthy 인지
```

첫 기동은 이미지 pull 에 5-10분 걸린다.

### 5. 초기 설정

콘솔은 퍼블릭에 열지 않는다. SSM 포트 포워딩으로 당겨온다.

```bash
terraform output -raw ssm_port_forward_command   # 이대로 실행
```

브라우저에서 `http://localhost:17080/install` — 관리자 계정을 만든다.
그 다음 모델 공급자 등록:

- **Bedrock** — `enable_bedrock_access = true` 면 인스턴스 역할로 붙는다. 액세스 키를 넣지 않는다
- 외부 API — 키는 Dify UI 에만 넣는다. Terraform 이나 매니페스트에 쓰지 않는다

### 6. 앱 연결

`terraform output -raw dify_api_base` 값을 `04-platform` 의 ConfigMap 으로 넣는다.
**매니페스트에 IP 를 직접 적지 않는다** (D-018 과 같은 원칙).

ConfigMap 키 이름은 `Settings` 필드, `.env.example` 과 반드시 일치시킨다 —
어긋나면 파드는 정상적으로 뜨고 런타임에만 기본값(`localhost`)으로 실패한다.

## 스튜디오 접속

퍼블릭 IP 도 ALB 도 붙이지 않는다. SSM 포트 포워딩으로 로컬에 당겨온다.

```bash
./tunnel.sh          # http://localhost:17080
```

★ **로컬 포트를 바꾸지 말 것.** 서버의 `NEXT_PUBLIC_SOCKET_URL` 이
`ws://localhost:17080` 으로 고정돼 있다. 다른 포트로 열면 화면은 정상으로 뜨고
워크플로 동기화만 무한 로딩에 걸린다. 증상이 조용해서 원인 추적이 오래 걸린다.
바꿔야 하면 서버 `.env` 와 함께 바꾼다.

로컬에 플러그인이 필요하다: `brew install --cask session-manager-plugin`

워크플로 편집, 디버그 실행, SSE 스트리밍 전부 정상 동작한다.
사람마다 각자 터널을 열면 되고 서로 간섭하지 않는다.

### 세션 길이

| 설정 | 값 | 비고 |
|---|---|---|
| `idleSessionTimeout` | 60분 | **AWS 상한이 60분이다.** 더 못 올린다 |
| `maxSessionDuration` | 360분 (6시간) | 활동 여부와 무관한 절대 상한 |

두 값은 `session_preferences.tf` 가 계정 전역 문서
`SSM-SessionManagerRunShell` 로 관리한다.

유휴 60분 상한 때문에 설정만으로는 6시간이 안 된다. `tunnel.sh` 가
5분마다 로컬 포트로 요청을 흘려 **유휴 상태 자체를 만들지 않는다.**
그래서 실제로 걸리는 상한은 `maxSessionDuration` 인 6시간이다.

간격을 바꾸려면:

```bash
KEEPALIVE_INTERVAL=120 ./tunnel.sh
```

⚠️ `SSM-SessionManagerRunShell` 은 **계정 전역**이다. Dify 호스트뿐 아니라
EKS 노드 접속을 포함한 모든 세션에 적용되고, 이 스택을 `destroy` 하면
계정 기본값(유휴 20분)으로 돌아간다. 다른 스택도 세션 설정을 필요로 하게
되면 `manage_session_preferences = false` 로 두고 계정 베이스라인 쪽으로 옮긴다.

콘솔에서 Preferences 를 한 번이라도 저장한 계정이면 문서가 이미 있어서
apply 가 `DocumentAlreadyExists` 로 실패한다. 그때는 가져온다:

```bash
terraform import 'aws_ssm_document.session_preferences[0]' SSM-SessionManagerRunShell
```

### 퍼블릭 IP 를 붙이지 않는 이유

Dify 콘솔은 **LLM API 키를 보관하고 sandbox 컨테이너로 임의 코드를 실행한다.**
로그인 폼 하나를 믿고 인터넷에 내놓을 물건이 아니다. 개발 중에만 잠깐
열어두는 것도 같다 — 스캐너는 상시로 돈다.

나중에 팀 상시 접속이 필요해지면 순서는 이렇다:
내부 ALB + OIDC(Cognito) → 그래도 부족하면 VPN. 퍼블릭 IP 직결은 어느 단계에도 없다.


## 함정

| 증상 | 원인 |
|---|---|
| apply 가 인스턴스를 교체하려 함 | AMI SSM 파라미터가 갱신됐다. `lifecycle.ignore_changes = [ami]` 로 막아뒀다. 그래도 뜨면 무엇이 바뀐 건지 먼저 본다 |
| **인스턴스 교체 = 워크플로 전멸** | 데이터가 루트 볼륨에만 있다. 보존이 필요하면 별도 EBS 를 붙이고 `/opt/dify/docker/volumes` 를 그쪽으로 옮긴다 |
| `docker: permission denied` | 그룹 반영이 안 됐다. 세션을 다시 연다 |
| 파드에서 Dify 호출이 타임아웃 | 노드 SG 가 아닌 곳에서 부른 것이다. 인그레스는 노드 SG 로만 열려 있다 |
| plugin_daemon 이 계속 재시작 | 메모리 부족. `free -m` 확인 후 인스턴스 등급을 올린다 |
| 로그에 `history search failed: UnknownServiceError` | Lambda 런타임의 boto3 가 `s3vectors` 를 모른다. 같은 줄에 boto3 버전이 찍힌다. 런타임을 올리거나(`python3.13`) zip 에 최신 boto3 를 넣는다. **알림 분석 자체는 계속 돈다** — 이력만 안 쌓인다 |

## 워크플로 소스

Dify 안에서 만든 워크플로는 Terraform 이 만들지 않는다. DSL 로 내보내
[`dify/`](dify/) 에 커밋한다 — 입력 계약과 내보내기 절차는 [`dify/README.md`](dify/README.md).

알림을 여기까지 실어 나르는 Lambda 는 [`lambda.tf`](lambda.tf) 와
[`lambda/ingress.py`](lambda/ingress.py) 와 [`lambda/worker.py`](lambda/worker.py) 에 있다.

## 이력 저장소

에이전트가 내린 판단을 쌓아, 다음 알림이 왔을 때 **"이미 해결한 인시던트와
비슷한가"** 를 판정한다. 정의는 [`history.tf`](history.tf) 에 있다.

| 무엇 | 어디 | 쓰임 |
|---|---|---|
| 원본 JSON | `o2-dev-dify-history-*` (S3) | 진실은 여기 하나뿐. 재색인·분석·MTTR |
| 벡터 | `o2-dev-dify-history-vectors` / 인덱스 `incidents` (S3 Vectors) | 비슷한 인시던트 검색 |

```
s3://…-history/incidents/dt=2026-08-21/<cycle_key>.json   Triggered + Dify 판단
s3://…-history/resolutions/<cycle_key>.json               Recovered 시각
```

### 왜 Dify 번들 weaviate 가 아닌가

Dify 는 벡터 DB(weaviate)를 이미 컨테이너로 들고 있다. 그런데 그것은
**루트 볼륨에만 있고 `delete_on_termination = true`** 라, 아래 "함정" 표의
"인스턴스 교체 = 워크플로 전멸" 이 그대로 적용된다. 이력은 이 프로젝트의
산출물이므로 EC2 밖에 둔다.

S3 Vectors 는 2025년 12월 GA 이고 서울 리전에서 쓸 수 있다.
이 규모(월 5,000건)에서 OpenSearch 대비 비용이 두 자릿수 배 싸다.

### 흐름

검색과 저장이 **전부 `lambda/worker.py` 안에서** 끝난다.

```
알림 → 임베딩 1회(Bedrock Titan) → S3 Vectors 검색 → past_cases 로 Dify 실행 → 저장
```

**Dify 는 벡터를 모른다.** 시작 노드에 텍스트 변수(`past_cases`)가 하나 는 것이
전부다 — 지식 검색 노드도 외부 지식 API 도 없다.
입력 계약은 [`dify/README.md`](dify/README.md) 1.1.1.

검색용 벡터와 저장용 벡터가 같다. 그래서 Bedrock 호출이 알림당 한 번이다.
이유는 `lambda/worker.py` 의 `_alert_text` 주석에 있다.

### 켜져 있는 파이프라인은 하나뿐이다

`lambda_o2.tf` 의 두 번째 파이프라인은 **같은 zip 을 공유하지만 이력은 꺼져 있다.**
환경변수(`HISTORY_BUCKET` 등)가 없으면 그 기능만 꺼지고 중계는 정상으로 돈다.

**환경변수만 복사해 붙이지 마라.** 두 파이프라인이 같은 Datadog 모니터를
받으면 `cycle_key` 가 같아서 서로의 인시던트를 덮어쓴다. 켜려면 키에
파이프라인 구분을 먼저 넣는다.

### 무엇이 저장되나

세 자리가 하는 일이 다르다. 섞으면 검색이 망가진다.

| 자리 | 들어가는 것 | 왜 |
|---|---|---|
| **벡터** | 알림 텍스트만 | 검색 키. 들어오는 알림과 성격이 같아야 한다 |
| **벡터 메타데이터** | 결과 요약 + 필터 키 | **프롬프트에 그대로 들어간다.** 작아야 한다 |
| **S3 원본** | 전부 | 재색인·분석·검증 |

`outcome` 은 이렇게 채워진다.

| 필드 | 누가 | 언제 |
|---|---|---|
| `state` | 자동 | Triggered 에 `unresolved`, Recovered 에 `auto_recovered` |
| `mttr_sec` | 자동 | Recovered 때 계산 |
| `root_cause_label` | **사람** | `scripts/verify.py` |
| `verified` | **사람** | 〃 |
| `human_correction` | **사람** | 〃 |

### 검증 전에는 원인을 말하지 않는다

검색 결과로 프롬프트에 들어가는 문장이다.

```
[미검증] 주문 생성 큐 적체 · 12분 뒤 자동복구
[확인됨] 주문 생성 큐 적체 · db_lock_contention · 사람이 조치 · 23분
[오탐]   주문 생성 알림 · 오탐, 조치 없음
```

**미검증 사례는 사실만 말한다.** 에이전트 추측을 여기 넣으면 다음 알림에서
그것이 "과거 사례" 로 다시 읽혀 추측이 사실로 승격된다.

추측 전문은 S3 원본의 `agent.hypothesis` 에 그대로 남는다 — 지우는 것이 아니라
검색 코퍼스에서 빼는 것이고, 사람이 검증할 때 그걸 읽는다. 근거는 D-045 와
`docs/architecture.md` 7.4.

### `state` 다섯 가지 — "복구" 는 "해결" 이 아니다

Datadog `Recovered` 는 **"지표가 임계 아래로 돌아왔다"** 일 뿐이다. 진짜 고쳤는지,
저절로 돌아왔는지, 방송이 끝나 부하가 사라졌는지, 모니터를 껐는지 구분하지 못한다.

| 값 | 뜻 | 누가 |
|---|---|---|
| `unresolved` | 아직 복구 신호가 없다 (**시작값**) | 자동 |
| `auto_recovered` | 지표는 돌아왔다. **아무도 안 고쳤다** | 자동 |
| `human_fixed` | 사람이 조치해서 해결 | 사람 |
| `agent_fixed` | 에이전트가 런북을 실행해 해결 | (런북 실행기 생긴 뒤) |
| `false_alarm` | 오탐. 장애가 아니었다 | 사람 |

★ **자동 기록은 절대 `human_fixed` 로 가지 않는다.** 지금 에이전트는
`action_taken = "none"` 이다 — 분석만 하고 아무것도 고치지 않는다. 이걸
해결로 적으면 발표의 MTTR 숫자가 거짓이 된다.

### MTTR

`cycle_key` 가 Triggered 와 Recovered 를 묶는다. 두 시각의 차다.

```
mttr_sec = recovered_at － occurred_at
```

★ Datadog `$DATE_POSIX` 가 초인지 밀리초인지 문서로 확정되지 않아 **값의 크기로
가른다** (`worker.py` `_epoch_sec`). 단위를 틀리면 1000배 어긋나는데 그 숫자가
그럴듯해 보여서 아무도 눈치채지 못한다.

★ flapping — Recovered 가 여러 번 오면 **첫 번째만** 센다. 이미 닫힌 건은 건너뛴다.

### 원인 라벨

`labels.txt` 가 통제 어휘의 원본이다. 자유 텍스트를 안 쓰는 이유는 하나다 —
같은 원인이 세 표현으로 갈리면 **"이 원인이 N번 재발" 을 셀 수 없고**, 그러면
런북을 무엇부터 쓸지도 모른다. 라벨 하나가 런북 하나에 대응한다.

### 도구

```bash
./scripts/verify.py         # 미검증 건에 사람이 원인을 확정한다
./scripts/verify.py --list  # 목록만
./scripts/label-report.py   # 라벨별 횟수 + 런북 유무
```

★ **`pip install` 이 필요 없다.** 두 스크립트는 셔뱅이 `uv run --script` 이고
파일 안에 의존성이 선언돼 있다(PEP 723). `uv` 만 있으면 첫 실행에서 알아서
받아 격리된 환경으로 돌린다 — 이 저장소에 venv 를 만들지 않는다.

`botocore[crt]` 가 의존성에 들어 있는 이유는 **`aws login` 으로 받은 자격증명을
읽으려면 그게 있어야 하기 때문이다.** 없으면 `MissingDependencyException` 이 난다.

`uv` 가 없으면 `brew install uv`. 굳이 안 쓰겠다면 `python3 scripts/...` 로도
돌지만 그때는 boto3 를 직접 깔아야 한다.

버킷 이름은 `terraform output` 으로 읽는다. 스크립트에 적어 두지 않는다 —
**출력은 `apply` 뒤에 생기므로 apply 전에는 안 돈다.**

`label-report.py` 가 런북을 무엇부터 쓸지 알려준다. 같은 라벨이 3회 반복되면
표시된다 (심각도가 높으면 1회로도 쓴다).

★ 사람이 기억해서 돌리는 일로 두면 안 돌아간다. 회고 때 또는 주 1회 돌린다.

### 실패했을 때 예외를 올리나 — 경로마다 다르다

규칙이 아니라 결과로 정했다. **헷갈려서 통일하지 마라.**

| 어디 | 실패하면 | 왜 |
|---|---|---|
| 과거 사례 검색 | 안 올린다 | 보조 정보 하나 때문에 알림 분석 전체를 잃을 수 없다 |
| Triggered 저장 | **안 올린다** | Dify 가 이미 성공했다. 재시도하면 LLM 비용 두 배 + 중복 |
| Recovered 적재 | **올린다** | LLM 을 안 부르고 멱등하다. 재시도가 공짜라 막히면 알려야 한다 |
| 복구 시각 기록 (Ingress) | 안 올린다 | 200 을 못 주면 Datadog 이 알림을 재전송한다 |

### 이력 쪽에서 아직 안 한 것

- **검증 필터.** 지금은 사람이 검증하지 않은 판단도 검색된다.
  `human_verified` 메타데이터는 붙어 있지만 항상 `false` 다. 지금 필터를
  걸면 결과가 늘 0건이라 기능이 죽은 것을 눈치채기 어렵다.
  사례가 쌓이면 `_search` 에 메타데이터 필터를 걸고, 그 전까지는
  프롬프트의 "참고이지 정답이 아니다" 문장이 유일한 방어선이다
  (근거: `docs/architecture.md` 7.4)
- **런북.** 라벨은 정했는데 `runbooks/<label>.md` 가 아직 하나도 없다.
  `label-report.py` 가 후보를 알려주면 사람이 쓴다. 그다음 Worker 가 라벨로
  **정확 키 조회**해서 프롬프트에 넣는다 — 런북은 유사도 검색으로 찾으면 안 된다
- **Athena.** 원본이 `dt=` 로 파티션되어 있어 Glue 테이블만 얹으면 되지만,
  건수가 적어 아직 `aws s3 cp` 로 충분하다

## 아직 안 한 것

- **EBS 스냅샷.** 개발 단계라 걸지 않았다. 워크플로 자체는 [`dify/`](dify/) 의 DSL 로 백업되고
  **인시던트 이력은 S3 로 빠져나갔다.** 남은 것은 Dify 지식베이스와 워크플로 postgres 다.
  그것들이 자산이 되는 시점에 DLM 으로 건다
- **Datadog 계측.** EKS 밖이라 클러스터 에이전트가 안 잡는다. 필요해지면 호스트 에이전트를 따로 넣는다
- **HA.** 단일 인스턴스다. 에이전트 운영 평면이므로 서비스 SLA 대상이 아니다
