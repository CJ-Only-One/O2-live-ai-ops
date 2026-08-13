# O2 live ai ops

라이브 스트리밍 서비스의 인프라와 배포를 담는 저장소.
애플리케이션 코드, 인프라 코드, 배포 매니페스트를 한 곳에서 관리한다.

## 구조

```
.github/workflows/
  app.yml        빌드 + 배포
  tf.yml         plan(PR 전용) — apply는 로컬
  scan.yml       gitleaks
infra/
  00-cicd/       GitHub OIDC, IAM 역할, ECR
  01-network/    VPC, 서브넷, 라우팅, NAT
  02-eks/        클러스터, 노드그룹, EKS 애드온
  03-data/       Redis, RDS (미작성)
  04-platform/   Argo CD, Load Balancer Controller, 클러스터 접근 권한
apps/<service>/  Dockerfile + src
loadtest/        부하 테스트 시나리오
docs/            결정 기록
```

**쿠버네티스 매니페스트는 이 저장소에 없다.**
[`CJ-Only-One/O2-live-deploy`](https://github.com/CJ-Only-One/O2-live-deploy)에 있고
Argo CD가 그쪽을 감시한다. `main` 의 브랜치 보호와 CI의 태그 갱신 커밋이
충돌해서 나눴다 — 근거는 D-006.

`infra/`의 번호는 **의존 순서**다. `02`와 `03`은 `01`의 출력을 remote state로
참조하므로 apply는 반드시 이 순서를 지켜야 한다. apply는 로컬에서 하므로
순서를 지키는 것은 사람의 몫이다 — `tf.yml` 은 plan만 돌린다.

배경과 근거는 [`docs/decisions.md`](docs/decisions.md)에 있다.

## 워크플로

| | 트리거 | 하는 일 |
|---|---|---|
| `app.yml` | `apps/**` 변경 | 이미지 빌드 → ECR → 매니페스트 저장소에 태그 갱신 |
| `tf.yml` | `infra/**` PR | plan만 — 무엇이 바뀔지 보여준다. apply는 로컬 |
| `scan.yml` | 모든 PR·푸시, 주 1회 | 시크릿 유출 검사 |

세 개로 나눈 기준은 **실패했을 때 되돌리는 비용**이다.
앱 배포는 다시 하면 되지만 인프라는 그렇지 않고, 유출된 시크릿은 되돌릴 수 없다.
그래서 인프라만 CI가 적용하지 않는다 — plan을 사람이 읽고 로컬에서 apply한다.

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
| `AWS_TF_ROLE_ARN` | `tf.yml` plan용 IAM Role — `ReadOnlyAccess` |
| `AWS_APP_ROLE_ARN` | 애플리케이션 배포용 IAM Role — ECR push 등 좁은 권한 |
| `DEPLOY_REPO_TOKEN` | 매니페스트 저장소에 태그 갱신을 커밋할 fine-grained PAT.<br>`O2-live-deploy` 한 곳, `Contents: Read and write` 만. **만료 주의** |

**두 역할을 반드시 분리한다.** 그리고 둘 다 쓰기 범위를 좁게 유지한다 —
`plan` 은 임의 코드를 실행할 수 있으므로 CI 자격증명에 쓰기 권한을 주면
PR 하나가 곧 인프라 변경 수단이 된다. (D-011)

### 3. Argo CD 등록

`infra/04-platform` 이 Argo CD 설치와 `o2-dev` Application 등록을 함께 한다.
손으로 `kubectl apply` 할 것은 없다 — 예전 `bootstrap/argocd-application.yaml`
은 같은 리소스를 두 곳에서 만들게 되어 제거했다. (D-011)

이후로는 배포 저장소에 태그 갱신 커밋이 올라올 때마다 Argo가 알아서 반영한다.
기본 폴링 주기는 180초다.

## 배포 흐름

```
푸시 → app.yml
        ├ verify   바뀐 서비스만 gradle build + test
        ├ image    이미지 빌드 → ECR (태그: 커밋 SHA)
        └ deploy   O2-live-deploy 의 <service>-deployment.yaml 태그 갱신 후 커밋
                     → Argo CD가 감지 → 클러스터에 반영
```

`app.yml` 은 **EKS를 직접 건드리지 않는다.** 배포 요청을 커밋으로 남기는 데서 끝난다.
CI에 클러스터 수정 권한을 주지 않기 위해서다. 근거는 D-004에 있다.

매니페스트 파일명은 배포 저장소의 `<service>-deployment.yaml` 규약을 따른다.
평면 배치라 `yq` 가 이 경로로 이미지 태그를 찾아 고치기 때문이며,
이름이 어긋나면 태그 갱신이 건너뛰어진다(워크플로가 경고를 남긴다).

## 서비스 추가하기

1. `apps/<service>/` — Dockerfile과 소스
2. **배포 저장소**에 `<service>-deployment.yaml`, `<service>-service.yaml`
3. ECR 저장소 `o2/<service>` 생성 (`infra/00-cicd` 의 `services` 변수에 추가)

워크플로는 고치지 않아도 된다. `apps/` 아래를 훑어 바뀐 서비스만 빌드한다.

## 상태

- [x] 저장소 골격
- [x] `scan.yml` — gitleaks
- [x] `tf.yml` — PR plan 전용 (apply는 로컬, 역할은 읽기 전용 · D-011)
- [x] `app.yml` — 빌드 → ECR → 태그 갱신 커밋 (Argo가 배포)
- [x] `apps/api` — Spring Boot (Kotlin)
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
- [ ] `infra/03-data` — Redis, RDS
- [x] OIDC 프로바이더 소유권을 `00-cicd` 로 정리 (D-009)
- [ ] `infra/03-data` — 팀 버킷에 `data/terraform.tfstate` 가 이미 있다. 코드를 찾아 흡수할 것
