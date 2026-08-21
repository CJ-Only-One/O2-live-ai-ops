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

### MTTR

Datadog 은 한 장애에 `Triggered` 와 `Recovered` 를 두 번 보내고 `cycle_key` 가
그 둘을 묶는다. 두 파일의 시각 차가 MTTR(장애 발생부터 복구까지)이다.

```
MTTR = resolutions/<cycle_key>.json  －  incidents/…/<cycle_key>.json
```

`Recovered` 는 Dify 로 보내지 않지만 **시각은 남긴다** (`lambda/ingress.py`).

### 이력 쪽에서 아직 안 한 것

- **검증 필터.** 지금은 사람이 검증하지 않은 판단도 검색된다.
  `human_verified` 메타데이터는 붙어 있지만 항상 `false` 다. 지금 필터를
  걸면 결과가 늘 0건이라 기능이 죽은 것을 눈치채기 어렵다.
  사례가 쌓이면 `_search` 에 메타데이터 필터를 걸고, 그 전까지는
  프롬프트의 "참고이지 정답이 아니다" 문장이 유일한 방어선이다
  (근거: `docs/architecture.md` 7.4)
- **`outcome` 채우기.** `resolved` · `mttr_sec` · `root_cause_label` 이 비어 있다.
  `incidents/` 와 `resolutions/` 를 `cycle_key` 로 짝짓는 재색인 스크립트가
  한 번에 채운다. 검증 필터와 같이 만든다
- **Athena.** 원본이 `dt=` 로 파티션되어 있어 Glue 테이블만 얹으면 되지만,
  건수가 적어 아직 `aws s3 cp` 로 충분하다

## 아직 안 한 것

- **EBS 스냅샷.** 개발 단계라 걸지 않았다. 워크플로 자체는 [`dify/`](dify/) 의 DSL 로 백업되고
  **인시던트 이력은 S3 로 빠져나갔다.** 남은 것은 Dify 지식베이스와 워크플로 postgres 다.
  그것들이 자산이 되는 시점에 DLM 으로 건다
- **Datadog 계측.** EKS 밖이라 클러스터 에이전트가 안 잡는다. 필요해지면 호스트 에이전트를 따로 넣는다
- **HA.** 단일 인스턴스다. 에이전트 운영 평면이므로 서비스 SLA 대상이 아니다
