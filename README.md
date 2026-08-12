# O2 live ai ops

라이브 스트리밍 서비스의 인프라와 배포를 담는 저장소.
애플리케이션 코드, 인프라 코드, 배포 매니페스트를 한 곳에서 관리한다.

## 구조

```
.github/workflows/
  app.yml        빌드 + 배포
  tf.yml         plan(PR) / apply(main, 승인)
  scan.yml       gitleaks
infra/
  01-network/    VPC, 서브넷, 라우팅
  02-eks/        클러스터, 노드그룹, 애드온
  03-data/       Redis, RDS
apps/<service>/  Dockerfile + src
deploy/          쿠버네티스 매니페스트 (평면 배치)
loadtest/        부하 테스트 시나리오
docs/            결정 기록
```

`infra/`의 번호는 **의존 순서**다. `02`와 `03`은 `01`의 출력을 remote state로
참조하므로 apply는 반드시 이 순서를 지켜야 한다. `tf.yml`이 이를 강제한다.

배경과 근거는 [`docs/decisions.md`](docs/decisions.md)에 있다.

## 워크플로

| | 트리거 | 하는 일 |
|---|---|---|
| `app.yml` | `apps/**`, `deploy/**` 변경 | 이미지 빌드 → ECR → 배포 |
| `tf.yml` | `infra/**` 변경 | PR에서 plan, main에서 승인 후 apply |
| `scan.yml` | 모든 PR·푸시, 주 1회 | 시크릿 유출 검사 |

세 개로 나눈 기준은 **실패했을 때 되돌리는 비용**이다.
앱 배포는 다시 하면 되지만 인프라는 그렇지 않고, 유출된 시크릿은 되돌릴 수 없다.
그래서 `tf.yml`만 승인 게이트를 갖는다.

## 최초 셋업

### 1. Terraform 상태 저장소

state에는 RDS 비밀번호 같은 값이 평문으로 들어가므로 로컬에 두지 않는다.
S3 버킷과 잠금 테이블을 먼저 만든다. (이 두 개만은 손으로 만든다 —
state를 보관할 곳을 만드는 데 state가 필요한 순환을 피하기 위해서다)

```bash
aws s3api create-bucket --bucket o2-live-tfstate --region ap-northeast-2 \
  --create-bucket-configuration LocationConstraint=ap-northeast-2
aws s3api put-bucket-versioning --bucket o2-live-tfstate \
  --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket o2-live-tfstate \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

버전 관리를 켜는 이유는 잘못된 apply로 state가 깨졌을 때 되돌리기 위해서다.

### 2. GitHub 시크릿

| 이름 | 값 |
|---|---|
| `AWS_TF_ROLE_ARN` | Terraform용 IAM Role — 인프라를 만들 수 있는 넓은 권한 |
| `AWS_APP_ROLE_ARN` | 애플리케이션 배포용 IAM Role — ECR push 등 좁은 권한 |

**두 역할을 반드시 분리한다.** Terraform 역할은 사실상 관리자이므로,
앱 배포처럼 자주 도는 워크플로가 그 권한을 쓰게 두면 노출 표면이 커진다.

### 3. 승인 게이트

저장소 Settings → Environments → `infra` 생성 후 **required reviewers** 지정.
이 설정을 빼먹으면 `tf.yml`의 apply가 승인 없이 그냥 실행된다.

## 상태

- [x] 저장소 골격
- [x] `scan.yml` — gitleaks
- [x] `tf.yml` — plan / 승인 후 apply
- [ ] `app.yml` — 배포 방식 결정 대기 (`docs/decisions.md` D-004)
- [ ] `infra/01-network`, `02-eks`, `03-data` — 범위 결정 대기 (D-005)
- [ ] `apps/`, `deploy/`, `loadtest/`
