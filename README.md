# O2 live ai ops

라이브 스트리밍 서비스의 인프라와 배포를 담는 저장소.
애플리케이션 코드, 인프라 코드, 배포 매니페스트를 한 곳에서 관리한다.

## 구조

```
.github/workflows/
  app.yml        빌드 + 배포
  tf.yml         fmt · validate (PR 전용) — plan도 apply도 하지 않는다
  scan.yml       gitleaks
  docs.yml       결정 기록 인덱스 검사
infra/
  00-cicd/       GitHub OIDC, IAM 역할, ECR
  01-network/    VPC, 서브넷, 라우팅, NAT
  02-eks/        클러스터, 노드그룹, EKS 애드온
  03-data/       RDS, Valkey, 주문·Chat Signal SQS, Candidate DynamoDB
                 (backend key는 `datastore/` · D-015, D-017, D-047)
  04-platform/   Argo CD, Load Balancer Controller, ESO, Datadog 에이전트,
                 클러스터 접근 권한과 앱 배선
  05-datadog/    Datadog 대시보드
  06-agent/      Dify 호스트 — EKS 밖의 EC2 (D-028)
  06-datastream/ Kinesis, Firehose, S3 레이크, Glue, DynamoDB, Lambda
                 에이전트가 쓰는 내부 데이터 시스템 (backend key는 `data/` · D-029)
  07-media/      MediaMTX, NLB, CloudFront — 영상 (미작성 · D-033)
  08-chat-signal/ Chat Signal Lambda·실행 IAM — 트리거 비활성 골격 (D-048)
apps/<service>/  Dockerfile + src
loadtest/        부하 테스트 시나리오
AGENTS.md        작업 시작 전에 읽을 것 — 규약과 함정, 문서 지도 (D-022)
docs/
  architecture.md  전체 설계 (부하 가정, 캐싱, 스케일링, 리스크)
  decisions.md   결정 기록
  contracts.md   인터페이스 계약 (REST, WebSocket, 캐시 키, 이벤트)
  chat-incident-candidate.md  채팅 기반 Incident Candidate canonical spec
  schema.md      MySQL 테이블·Valkey 키·마이그레이션
```

**쿠버네티스 매니페스트는 이 저장소에 없다.**
[`CJ-Only-One/O2-live-deploy`](https://github.com/CJ-Only-One/O2-live-deploy)에 있고
Argo CD가 그쪽을 감시한다. `main` 의 브랜치 보호와 CI의 태그 갱신 커밋이
충돌해서 나눴다 — 근거는 D-006.

`infra/`의 번호는 **의존 순서**다. `02`와 `03`은 `01`의 출력을 remote state로
참조하고, `06`은 `02`가 만든 클러스터의 OIDC 프로바이더를 조회하므로 apply는
반드시 이 순서를 지켜야 한다. apply는 로컬에서 하므로
순서를 지키는 것은 사람의 몫이다 — `tf.yml` 은 문법과 포맷만 검사한다 (D-023).

`03-data`와 `06-datastream`은 이름이 비슷하지만 다른 것이다. 앞은 서비스가
읽고 쓰는 저장소, 뒤는 그 서비스를 관찰한 결과다. **state 키를 서로 바꿔 쓰면
상대 리소스를 지운다** (D-015, D-029).

`08-chat-signal`은 `03-data`의 Chat Signal SQS와 Candidate DynamoDB를 참조한다.
따라서 `03-data` 이후에 적용하며, Phase 1B에서는 event source mapping을 코드에
하드코딩해 비활성 상태로 둔다(D-048).

배경과 근거는 [`docs/decisions.md`](docs/decisions.md)에 있다.

## 워크플로

| | 트리거 | 하는 일 |
|---|---|---|
| `app.yml` | `apps/**` 변경 | PR은 `verify`(lint·test·build)까지. main 푸시에서 이미지 빌드 → Trivy 스캔 → ECR → 매니페스트 저장소에 태그 갱신 |
| `tf.yml` | `infra/**` PR | `fmt`·`init -backend=false`·`validate` 만. **plan도 apply도 하지 않는다** — AWS 접근이 필요 없다 (D-023) |
| `scan.yml` | 모든 PR·푸시, 주 1회 | 시크릿 유출 검사 |
| `docs.yml` | `docs/**`·`AGENTS.md` 변경 | 결정 기록 인덱스가 낡았는지 검사 |

넷으로 나눈 기준은 **실패했을 때 되돌리는 비용**이다.
앱 배포는 다시 하면 되지만 인프라는 그렇지 않고, 유출된 시크릿은 되돌릴 수 없다.
그래서 인프라만 CI가 적용하지 않는다 — 사람이 로컬에서 plan을 읽고 apply한다.

## 최초 셋업

### 1. Terraform 상태 저장소

state에는 RDS 비밀번호 같은 값이 평문으로 들어가므로 로컬에 두지 않는다.
S3 버킷과 잠금 테이블을 먼저 만든다. (이 두 개만은 손으로 만든다 —
state를 보관할 곳을 만드는 데 state가 필요한 순환을 피하기 위해서다)

**이미 만들어져 있다** — `s3://o2-tfstate-066107819912`. 아래는 재현이 필요할 때의
기록이다. 버킷 하나만 손으로 만들고, 각 스택은 `backend "s3"` 로 그 안의 키를 쓴다.

```bash
B=o2-tfstate-066107819912
aws s3api create-bucket --bucket $B --region ap-northeast-2 \
  --create-bucket-configuration LocationConstraint=ap-northeast-2
aws s3api put-public-access-block --bucket $B --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-versioning --bucket $B \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket $B --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}'
```

버전 관리를 켜는 이유는 잘못된 apply로 state가 깨졌을 때 되돌리기 위해서다.
오래된 버전은 90일 뒤 만료되게 lifecycle 규칙을 걸어두었다.

잠금에 DynamoDB는 필요 없다. Terraform 1.10부터 S3 자체 잠금(`use_lockfile`)을 쓴다.

### 2. GitHub 시크릿

| 이름 | 값 |
|---|---|
| `AWS_TF_ROLE_ARN` | Terraform용 IAM Role — `ReadOnlyAccess`. **지금 CI는 쓰지 않는다** — plan을 뺀 뒤(D-023) `tf.yml` 에 AWS 접근이 없다 |
| `AWS_APP_ROLE_ARN` | 애플리케이션 배포용 IAM Role — ECR push 등 좁은 권한 |
| `DEPLOY_REPO_TOKEN` | 매니페스트 저장소에 태그 갱신을 커밋할 fine-grained PAT.<br>`O2-live-deploy` 한 곳, `Contents: Read and write` 만. **만료 주의** |

**두 역할을 반드시 분리한다.** 그리고 둘 다 쓰기 범위를 좁게 유지한다 —
CI 자격증명에 쓰기 권한을 주면 PR 하나가 곧 인프라 변경 수단이 되기 때문이다 (D-011).
plan을 뺀 지금은 `tf.yml` 이 AWS에 아예 붙지 않아, public 저장소에서 PR로 CI 코드를
실행하는 경로가 하나 더 줄었다 (D-023).

### 3. Argo CD 등록

`infra/04-platform` 이 Argo CD 설치와 `o2-dev` Application 등록을 함께 한다.
손으로 `kubectl apply` 할 것은 없다 — 예전 `bootstrap/argocd-application.yaml`
은 같은 리소스를 두 곳에서 만들게 되어 제거했다. (D-011)

이후로는 배포 저장소에 태그 갱신 커밋이 올라올 때마다 Argo가 알아서 반영한다.
기본 폴링 주기는 180초다.

## 배포 흐름

```
푸시 → app.yml
        ├ verify   바뀐 서비스만. 언어를 판별하지 못하면 건너뛴다 (D-013)
        ├ image    이미지 빌드 → Trivy 스캔 → ECR (태그: 커밋 SHA)
        └ deploy   O2-live-deploy 의 <service>-deployment.yaml 태그 갱신 후 커밋
                     → Argo CD가 감지 → 클러스터에 반영
```

스캔은 **푸시 전에** 돈다. 올라간 뒤에 보면 통보일 뿐 게이트가 아니기 때문이다.
**CRITICAL이 하나라도 있으면 ECR 푸시가 막힌다.** HIGH는 막지 않고 기록만 한다 —
대개 베이스 이미지의 것이라 우리가 고칠 수 없고, 손쓸 수 없는 이유로 배포가 서면
결국 스캔을 끄게 되기 때문이다. 결과는 저장소 **Security 탭**에 쌓인다. 근거는 D-014.

`app.yml` 은 **EKS를 직접 건드리지 않는다.** 배포 요청을 커밋으로 남기는 데서 끝난다.
CI에 클러스터 수정 권한을 주지 않기 위해서다. 근거는 D-004에 있다.

매니페스트 파일명은 배포 저장소의 `<service>-deployment.yaml` 규약을 따른다.
평면 배치라 `yq` 가 이 경로로 이미지 태그를 찾아 고치기 때문이며,
이름이 어긋나면 태그 갱신이 건너뛰어진다(워크플로가 경고를 남긴다).

## 애플리케이션이 데이터 계층에 붙는 법

**접속 정보를 코드나 매니페스트에 적지 않는다.** 클러스터에서는 두 가지가
`envFrom` 으로 통째로 들어온다.

| 이름 | 종류 | 내용 |
|---|---|---|
| `o2-data` | ConfigMap | RDS·Valkey 엔드포인트, SQS 큐 URL |
| `o2-db` | Secret | `DB_PASSWORD` 하나 |
| `o2-events` | Secret | `O2_EVENTS_SALT` 하나 (D-027) |

둘 다 `infra/04-platform` 이 `03-data` 의 remote state 를 읽어 만든다.
데이터 스택을 다시 만들어도 그 스택을 apply 하면 따라간다.

이벤트와 DB의 `user_key`를 같은 값으로 만들려면 세 서비스가 동일한
`O2_EVENTS_SALT`를 봐야 한다. `o2-events` Secret 이 그 값을 나른다 — 원본은
Secrets Manager 에 있고 ESO 가 동기화한다 (D-027).

### 이름이 계약이다

```
ConfigMap/Secret 키  ==  apps/api 의 Settings 필드  ==  .env.example 항목
```

셋이 같아야 한다. `REDIS_URL` 같은 새 이름을 만들면 **주입된 값이 조용히 무시되고
기본값(localhost)이 쓰인다.** 파드는 정상적으로 뜨고 DB 호출에서만 실패하므로
알아채기 늦다. 현재 키 목록은 `apps/api/.env.example` 에 있다.

### 로컬과 클러스터의 차이는 둘뿐

`docker-compose` 가 같은 이름의 환경변수를 쓰므로 로컬에서 돌아가는 코드는
클러스터에서도 그대로 돈다. 다른 것은 두 가지다.

- **Valkey TLS.** 클러스터는 transit 암호화가 켜져 있어 평문 접속이 끊긴다.
  `VALKEY_TLS=true` 가 주입되고, `settings.valkey_url` 이 `rediss://` 를 낸다.
  로컬 컨테이너에는 TLS 가 없어 `false` 다.
- **SQS.** 로컬에는 큐가 없다. `SQS_ORDER_QUEUE_URL` 이 비면 발행을 건너뛰도록
  코드에서 분기한다.

### AWS 자격증명

**액세스 키를 만들지 않는다.** 파드는 EKS Pod Identity 로 임시 자격증명을 받는다.
매니페스트에 `serviceAccountName` 을 적고, 같은 이름이
`infra/04-platform` 의 `app_service_accounts` 목록에 있어야 한다.

이름이 어긋나면 파드는 뜨고 **AWS 호출에서만** 실패한다. 두 곳을 함께 고친다.

### 서비스를 새로 붙일 때

1. 매니페스트에 `serviceAccountName: <service>` 와 `envFrom` 두 줄
2. `infra/04-platform` 의 `app_service_accounts` 에 이름 추가 후 apply
3. 새 환경변수가 필요하면 `04-platform/app_data_access.tf` 의 ConfigMap 에
   추가하고, 같은 이름을 앱 설정과 `.env.example` 에도 넣는다

## 서비스 추가하기

1. `apps/<service>/` — Dockerfile과 소스
2. **배포 저장소**에 `<service>-deployment.yaml`, `<service>-service.yaml`
3. ECR 저장소 `o2/<service>` 생성 (`infra/00-cicd` 의 `services` 변수에 추가)

워크플로는 고치지 않아도 된다. `apps/` 아래를 훑어 바뀐 서비스만 빌드한다.

## 상태

- [x] 저장소 골격
- [x] `scan.yml` — gitleaks
- [x] `tf.yml` — PR `fmt`·`validate` 전용 (plan 없음 · D-023, apply는 로컬)
- [x] `app.yml` — 빌드 → ECR → 태그 갱신 커밋 (Argo가 배포)
- [x] `apps/api` — FastAPI (Python). 초기에는 Spring Boot(Kotlin)였다
- [x] 매니페스트를 `O2-live-deploy` 로 분리 (D-006)
- [x] Argo CD Application — `infra/04-platform` 이 소유 (`bootstrap/` 제거 · D-011)
- [x] `loadtest/spike.js` — 스파이크 시나리오 (k6)
- [x] `AWS_APP_ROLE_ARN` / `AWS_TF_ROLE_ARN` 시크릿 등록
- [x] `infra/00-cicd` — OIDC 프로바이더, IAM Role 2개, ECR (로컬 적용 완료)
- [x] 파이프라인 전 구간 검증 — 커밋 → ECR → 태그 갱신 → Argo → 파드 응답
- [x] Terraform state를 S3로 이전 (버전 관리·암호화·잠금)
- [x] `infra/01-network`, `02-eks` — 팀 코드 반영 (D-007)
- [x] `infra/04-platform` — 클러스터 안의 구성을 코드로 (D-008)
- [x] state를 팀 버킷(`o2-tfstate-066107819912`) 하나로 통일 (D-010)
- [x] `infra/03-data` — RDS, Valkey, SQS (D-017). 적용 완료
- [x] `infra/01-network` — `enable_data_tier = true` (private-data 서브넷)
- [x] `infra/04-platform` — 접속 정보를 클러스터로 넣는 배선 (D-018). 적용·검증 완료
- [x] `apps/api` — 환경변수 계약 반영, `docker-compose` 에 Valkey 추가
- [x] `apps/frontend` — 계약(`contracts.md`)에 맞춰 전면 수정 (D-019)
- [x] DB 스키마와 마이그레이션 방식 — `docs/schema.md` + Alembic
- [x] OIDC 프로바이더 소유권을 `00-cicd` 로 정리 (D-009)
- [x] 배포 저장소 ruleset이 태그 갱신 커밋을 막던 문제 해결 (D-012)
- [x] ~~`apps/testpage`~~ — 역할이 끝나 제거 (D-013 → D-020). ECR 저장소만 남겨둠
- [x] ~~`data/terraform.tfstate` 는 백데이터 파트 소관 (D-015)~~ — `06-datastream` 으로 흡수 (D-029)
- [x] `app.yml` — Trivy 이미지 스캔, 결과를 Code Scanning으로 (D-014)
- [x] Trivy를 CRITICAL 차단으로 승격 (D-014)
- [x] `docs/contracts.md` — REST·WebSocket·캐시 키·이벤트 계약 (D-016)
- [ ] `contracts.md` 5.5 — 모르는 `event_name` 을 수집단이 어떻게 처리하는지 확인 필요. `chat.send` 발행이 여기 막혀 있다
- [ ] `tf.yml` — `trivy config` 로 Terraform 미스컨피그 검사 (게이트 없이 리포트만)
- [ ] `scan.yml` — gitleaks 결과도 Code Scanning으로 이전
- [ ] 주 1회 ECR 최신 이미지 재스캔 — CI 스캔은 빌드 시점만 본다
