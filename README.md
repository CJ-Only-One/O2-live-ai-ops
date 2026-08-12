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

### 4. Argo CD 등록

클러스터에 Argo CD를 설치한 뒤, 이 저장소를 보게 한 번만 등록한다.

```bash
kubectl apply -f bootstrap/argocd-application.yaml
```

이후로는 `main` 에 태그 갱신 커밋이 올라올 때마다 Argo가 알아서 반영한다.
기본 폴링 주기는 180초다.

## 배포 흐름

```
푸시 → app.yml
        ├ verify   바뀐 서비스만 gradle build + test
        ├ image    이미지 빌드 → ECR (태그: 커밋 SHA)
        └ deploy   deploy/<service>-deployment.yaml 의 태그 갱신 후 커밋
                     → Argo CD가 감지 → 클러스터에 반영
```

`app.yml` 은 **EKS를 직접 건드리지 않는다.** 배포 요청을 커밋으로 남기는 데서 끝난다.
CI에 클러스터 수정 권한을 주지 않기 위해서다. 근거는 D-004에 있다.

매니페스트 파일명은 `deploy/<service>-deployment.yaml` 규약을 따른다.
평면 배치라 `yq` 가 이 경로로 이미지 태그를 찾아 고치기 때문이며,
이름이 어긋나면 태그 갱신이 건너뛰어진다(워크플로가 경고를 남긴다).

## 서비스 추가하기

1. `apps/<service>/` — Dockerfile과 소스
2. `deploy/<service>-deployment.yaml`, `deploy/<service>-service.yaml`
3. ECR 저장소 `o2/<service>` 생성

워크플로는 고치지 않아도 된다. `apps/` 아래를 훑어 바뀐 서비스만 빌드한다.

## 상태

- [x] 저장소 골격
- [x] `scan.yml` — gitleaks
- [x] `tf.yml` — plan / 승인 후 apply
- [x] `app.yml` — 빌드 → ECR → 태그 갱신 커밋 (Argo가 배포)
- [x] `apps/api` — Spring Boot (Kotlin)
- [x] `deploy/` — 평면 매니페스트
- [x] `bootstrap/` — Argo CD Application
- [x] `loadtest/spike.js` — 스파이크 시나리오 (k6)
- [x] `AWS_APP_ROLE_ARN` / `AWS_TF_ROLE_ARN` 시크릿 등록
- [x] `infra/00-cicd` — OIDC 프로바이더, IAM Role 2개, ECR (로컬 적용 완료)
- [x] `infra` 환경 승인 게이트 — 필수 리뷰어 SangMun, j0chan
- [x] 파이프라인 전 구간 검증 — 커밋 → ECR → 태그 갱신 → Argo → 파드 응답
- [ ] Terraform state를 S3로 이전 — **끝나기 전에는 `infra/` 를 커밋하지 말 것**
      (CI에는 state가 없어 이미 있는 리소스를 다시 만들려다 깨진다)
- [ ] `infra/01-network`, `02-eks`, `03-data` — 로컬 검증 후 반영 (D-005)
