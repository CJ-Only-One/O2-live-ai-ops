# 결정 기록

구조를 정할 때 갈렸던 지점과 그 근거를 남긴다.
"왜 이렇게 했지"를 반년 뒤에 다시 묻지 않기 위한 문서다.

---

## D-001. 워크플로를 세 개로 나눈다

`app.yml` / `tf.yml` / `scan.yml`.

가르는 기준은 **"실패했을 때 누가 무엇을 해야 하는가"** 이다.

| 워크플로 | 실패하면 | 되돌리는 비용 |
|---|---|---|
| `app.yml` | 애플리케이션 배포가 멈춘다 | 낮다. 다시 배포하면 된다 |
| `tf.yml` | 인프라가 어긋난 상태로 남을 수 있다 | 높다. state 복구가 필요할 수 있다 |
| `scan.yml` | 시크릿이 히스토리에 남는다 | 되돌릴 수 없다. 키를 교체해야 한다 |

되돌리는 비용이 다르면 승인 절차도 달라야 한다.
그래서 `tf.yml`만 승인 게이트(`environment: infra`)를 갖는다.

---

## D-002. 인프라를 세 스택으로 나눈다

`01-network` → `02-eks` → `03-data`.

한 스택에 다 넣으면 **보안 그룹 규칙 하나 고치는 데 EKS 전체가 plan에 올라온다.**
plan이 길어지면 사람이 읽지 않게 되고, 읽지 않는 plan은 승인 게이트의 의미를 없앤다.

번호는 장식이 아니라 **의존 순서**다. `02`와 `03`은 `01`의 출력(VPC ID, 서브넷)을
remote state로 참조한다. apply는 반드시 이 순서로 돌아야 하고,
`tf.yml`의 apply 잡이 순서를 강제한다.

수명도 다르다. 네트워크는 거의 안 바뀌고, 데이터 계층은 그다음이며,
EKS는 버전 업그레이드로 가장 자주 손댄다. 수명이 다른 것을 한 state에 묶으면
자주 바뀌는 것 때문에 안 바뀌어야 할 것이 위험에 노출된다.

---

## D-003. 시크릿 스캔은 공식 액션 대신 바이너리를 쓴다

`gitleaks/gitleaks-action`은 조직 계정에서 라이선스 키를 요구한다.
바이너리를 직접 받으면 그 제약이 없고, 버전을 우리가 고정할 수 있다.

`--redact`는 필수다. 이 저장소는 public이라 **워크플로 로그도 공개**된다.
스캐너가 찾아낸 시크릿을 로그에 그대로 찍으면 스캔이 오히려 유출 경로가 된다.

---

## D-004. 배포는 GitOps로 한다 (Argo CD)

`app.yml`은 "빌드 + 배포"를 한 파일에서 다루지만, **EKS를 직접 건드리지 않는다.**
`deploy/` 의 이미지 태그를 갱신하는 커밋을 만드는 데서 끝나고,
그 커밋을 Argo CD가 읽어 클러스터에 반영한다.

push 방식(Actions가 `kubectl apply`)과 비교했을 때 결정적인 차이는 마지막 줄이다.

| | push | GitOps |
|---|---|---|
| 구성 요소 | 적다 | Argo 파드 추가 |
| 드리프트 감지 | 없다 | 있다 (`selfHeal`) |
| 감사 추적 | Actions 로그 | Git 커밋 |
| **클러스터 접근** | **CI에 EKS 수정 권한 필요** | **불필요 — Argo가 안에서 당겨온다** |

push 방식은 CI 토큰이 새면 클러스터로 가는 경로가 함께 열린다.
GitOps에는 그 경로가 아예 없다.

부작용도 받아들인다. `selfHeal: true` 때문에 `kubectl` 로 직접 고친 것은 되돌려진다.
특히 HPA를 도입하면 매니페스트의 `replicas` 와 충돌하므로,
그때는 `replicas` 필드를 매니페스트에서 제거해야 한다.

### 왜 Application 매니페스트만 `deploy/` 밖에 있나

`bootstrap/argocd-application.yaml` 에 따로 뒀다.
`deploy/` 안에 두면 Argo가 **자기 자신을 관리 대상으로 삼는다.**
이 파일은 클러스터를 세울 때 한 번만 손으로 적용하는 부트스트랩이고,
그 뒤로는 Argo가 `deploy/` 만 따라간다. 성격이 다르므로 자리도 나눈다.

### 평면 배치에서 태그를 갱신하는 법

kustomize가 없으므로 `kustomize edit set image` 를 쓸 수 없다.
`sed` 로 문자열을 바꾸면 주석이나 비슷한 문자열까지 건드릴 위험이 있어,
경로를 지정해 값만 고치는 `yq` 를 쓴다.

```
.spec.template.spec.containers[0].image
```

이 규약 때문에 매니페스트 파일명은 `deploy/<service>-deployment.yaml` 로 고정된다.
서비스를 추가할 때 이 이름을 지키지 않으면 태그 갱신이 조용히 건너뛰어진다
(워크플로가 경고를 남긴다).

---

## D-006. 매니페스트를 별도 저장소로 분리한다

매니페스트는 [`O2-live-deploy`](https://github.com/CJ-Only-One/O2-live-deploy)에 있다.
이 저장소에는 `deploy/` 가 없다.

### 왜 나눴나

`main` 에 브랜치 보호(PR 필수)를 걸자 **CI가 태그 갱신 커밋을 밀지 못하게 됐다.**
규칙은 행위자를 가리지 않고 "직접 푸시"를 막으므로 `github-actions[bot]` 도 예외가 아니었다.
그 결과 이미지는 ECR에 올라갔는데 매니페스트가 그대로여서,
Argo가 볼 Git 내용이 안 바뀌고 클러스터는 옛 버전을 계속 돌리는 상태가 됐다.

선택지는 둘이었다.

| | 결과 |
|---|---|
| 봇에게 우회 권한 부여 | 한 줄로 해결되지만, 배포마다 봇 커밋이 사람 커밋 사이에 쌓인다.<br>`git log` 절반이 노이즈가 되고, 배포될 때마다 팀원 전원의 로컬이 뒤처진다 |
| **저장소 분리** | 앱 저장소의 보호를 온전히 유지하고, 봇 커밋은 저쪽에만 쌓인다 |

후자를 골랐다. **코드의 생명주기와 배포 기록의 생명주기가 다르기 때문이다.**
코드는 리뷰 대상이지만 배포 기록은 기계가 남기는 로그에 가깝다.
둘을 같은 브랜치에 두면 "리뷰를 강제한다"와 "기계가 계속 쓴다"가 정면으로 충돌한다.

### 자격증명

`GITHUB_TOKEN` 은 자기 저장소에만 유효하므로 별도 자격증명이 필요하다.

처음에는 deploy key를 쓰려 했으나 **org 설정에서 비활성화**되어 있었다
(`deploy_keys_enabled_for_repositories: false`). org 전체에 영향을 주는 설정이라
건드리지 않고, fine-grained PAT으로 갔다.

- 시크릿 이름: `DEPLOY_REPO_TOKEN`
- 범위: `O2-live-deploy` **한 저장소**, `Contents: Read and write` 만
- **만료가 있다.** 만료되면 배포가 인증 오류로 조용히 멈춘다.
  갱신은 새 토큰을 만들어 같은 이름으로 `gh secret set` 하면 되고, 워크플로는 손대지 않는다.

`deploy` 잡의 `permissions` 를 `contents: read` 로 낮췄다.
이제 이 저장소에 쓰는 워크플로는 없다.

### 대가

- **저장소가 둘이다.** 매니페스트를 고치려면 다른 저장소를 열어야 한다.
- **커밋 추적이 한 번 끊긴다.** 완화를 위해 배포 커밋 메시지에
  원본 저장소·커밋 SHA·워크플로 실행 URL을 남긴다.

---

## 겪은 함정

구축 중 실제로 부딪힌 것들. 같은 자리에서 두 번 넘어지지 않기 위해 남긴다.

### IAM Role의 `description`에 한글을 쓸 수 없다

AWS가 `[	
 -~¡-ÿ]` 만 허용한다.
한글은 물론 em-dash(`—`)도 범위 밖이라 `ValidationError` 로 apply가 실패한다.
Terraform 변수나 출력의 `description` 은 AWS로 전달되지 않으므로 한글이어도 무방하다.

### `force_delete` 는 config가 아니라 state의 값으로 동작한다

이미지가 든 ECR 저장소는 그냥 destroy되지 않는다. `force_delete = true` 를
**나중에 추가하고 destroy하면 반영되지 않는다** — destroy는 state에 저장된 값을 쓰기 때문이다.
반영하려면 `apply` 를 한 번 거쳐 state를 갱신해야 하는데,
이미 다른 리소스가 지워진 뒤라면 그 apply가 지워진 것들을 되살린다.

만들 때 정해두거나, 삭제 대신 `terraform state rm` + `import` 로
소유권을 옮기는 편이 안전하다. 실제로 `o2/api` 는 후자로 처리했다.

### OIDC 프로바이더는 계정에 하나뿐이라 소유자를 정해야 한다

`token.actions.githubusercontent.com` 프로바이더는 계정 단위 리소스다.
여러 스택이 각자 `resource` 로 선언하면 두 번째 apply가 충돌하고,
한쪽이 destroy하면 다른 쪽이 조용히 깨진다.
**이 저장소의 `00-cicd` 가 소유자다.** 다른 스택은 `data` 로 참조할 것.

### GitHub OIDC의 `sub` 에 숫자 ID가 붙는다

이 조직은 `repo:CJ-Only-One@315606307/O2-live-ai-ops@1331684285:...` 형태다.
문서에 흔히 나오는 `repo:org/repo:*` 패턴만 신뢰 정책에 넣으면
`Not authorized to perform sts:AssumeRoleWithWebIdentity` 로 거절된다.
확인 방법:

```bash
gh api /repos/CJ-Only-One/O2-live-ai-ops/actions/oidc/customization/sub
```

### 컨테이너 `USER` 는 숫자여야 한다

매니페스트에 `runAsNonRoot: true` 를 걸면 kubelet이 root 여부를 검증하는데,
이미지가 `USER app` 처럼 **이름**으로 지정하면 검증이 불가능해
`CreateContainerConfigError` 로 컨테이너 생성 자체가 거부된다.
Dockerfile과 매니페스트가 같은 숫자 UID(여기서는 `10001`)를 가리켜야 한다.

---

## D-005. 인프라는 로컬에서 검증한 뒤 올린다

`infra/` 의 세 스택은 아직 비어 있다. 로컬에서 `plan` 으로 확인이 끝난 뒤
저장소에 올린다.

`tf.yml` 은 이를 견디도록 만들어져 있다 — `.tf` 파일이 없는 스택은
감지 단계에서 건너뛰므로, 인프라 코드가 없는 상태에서도 워크플로가 실패하지 않는다.

올릴 때 유의할 점:

- **NAT 게이트웨이와 RDS는 켜두는 것만으로 과금된다.** plan에서 개수를 확인할 것.
- state는 반드시 S3 백엔드로 둔다. RDS 비밀번호 같은 값이 state에 평문으로 들어가므로
  로컬에 두면 유출과 분실 위험을 동시에 진다.
- 첫 apply는 반드시 `01` → `02` → `03` 순서다. `02`·`03`이 `01`의 출력을 참조한다.

---

## D-007. 인프라 코드를 저장소로 흡수한다

`01-network` 와 `02-eks` 는 팀원이 작성해 로컬에서 돌리던 코드다.
`~/Downloads` 에 있어 **버전 관리도, 리뷰도, 이력도 없었다.**
실제 인프라가 그 코드로 바뀌는데 변경 근거가 어디에도 남지 않는 상태였다.

옮기면서 두 가지를 지켰다.

- **state 파일은 가져오지 않았다.** state는 S3(`o2-tfstate-066107819912`)에 있고,
  로컬에 남아 있던 `terraform.tfstate` 는 이전 과정의 잔재였다.
- **`terraform.tfvars` 는 커밋했다.** `.gitignore` 의 `*.tfvars` 규칙에 걸렸으나,
  이 파일들은 비밀이 아니라 환경 정의 그 자체다. 없으면 재현이 불가능하다.
  비밀이 필요해지면 tfvars가 아니라 Secrets Manager를 쓴다.

이제 `tf.yml` 이 PR에서 `plan` 을 돌려 무엇이 바뀌는지 보여준다.

### 남은 정리

- `00-cicd` 의 state만 다른 버킷(`o2-live-tfstate`)에 있다. 팀 버킷으로 합쳐야 한다.
- `02-eks/github_oidc.tf` 도 GitHub OIDC 프로바이더를 만든다(현재 `enable_github_oidc = false`).
  `00-cicd` 가 이미 소유하고 있으므로, 누가 저 값을 켜면 apply가 충돌한다.
  소유권을 한쪽으로 정해야 한다.

---

## D-008. 클러스터 안의 구성도 코드로 남긴다 (`04-platform`)

클러스터를 지웠다 만들면 **그 안의 것은 전부 사라진다.** Argo CD, 네임스페이스,
파드, access entry까지. 실제로 하루 만에 두 번 겪었다.

바깥(VPC·ECR·IAM)은 Terraform이 지키고 있었지만 안쪽은 손으로 복구하고 있었다.
`04-platform` 이 그 안쪽을 맡는다.

| | 이전 | 지금 |
|---|---|---|
| 클러스터 접근 권한 | `aws eks create-access-entry` 수동 | `cluster_admin_arns` 변수 |
| Argo CD 설치 | README 절차 수동 | `helm_release` (차트 10.2.2 = v3.4.6) |
| Argo Application | `kubectl apply` 수동 | 차트의 `extraObjects` |
| Load Balancer Controller | `terraform output` 복사 실행 | `helm_release` |

### 왜 `02-eks` 와 나눴나

`helm` 프로바이더는 설정 시점에 클러스터 주소와 토큰이 필요하다.
클러스터를 만드는 apply와 같은 스택이면 첫 실행에서 "아직 모르는 값"이라 깨진다.
스택을 나누고 remote state로 넘겨받아야 한다.

### 첫 apply가 두 단계인 이유

`helm` 프로바이더가 인증하려면 access entry가 있어야 하는데, 그것을 같은 스택이
만든다. 그래서 처음에는 `-target` 으로 권한을 먼저 만들고 나머지를 적용한다.
access entry를 `02-eks` 로 옮기면 이 어색함은 사라진다.

### 차트 버전을 고정한 이유

버전을 비워두면 클러스터를 다시 만들 때마다 다른 Argo CD가 깔린다.
`10.2.2` 는 실제 저장소를 조회해 `v3.4.6` 에 대응하는 것을 확인한 값이다.

### 기본값에서 바꾼 것

Argo CD 차트 기본값에는 **resource requests가 없다.** 그러면 파드가 BestEffort QoS가 되어
노드 메모리가 압박받을 때 가장 먼저 축출된다. 배포 시스템이 부하 상황에서 먼저 죽으면
복구 수단을 잃으므로, 주요 컴포넌트에 requests를 지정했다.

---

## D-009. CI/CD 자격증명의 소유자는 `00-cicd` 하나다

`02-eks/github_oidc.tf` 를 제거했다. 팀원과 합의된 변경이다.

### 겹쳤던 것

GitHub OIDC 프로바이더는 **AWS 계정당 하나만 존재할 수 있는데**,
`00-cicd` 와 `02-eks` 가 둘 다 이것을 `resource` 로 선언하고 있었다.
`02-eks` 쪽은 `enable_github_oidc = false` 라 만들어지지 않아 조용했지만,
누가 그 값을 켜는 순간 `EntityAlreadyExists` 로 apply가 깨진다.

더 위험한 것은 그걸 해결하겠다고 `import` 하는 경우다.
두 state가 하나의 리소스를 소유하게 되어, 한쪽 destroy가 다른 쪽을 조용히 부순다.

### 왜 `02-eks` 쪽을 지웠나

중복이어서가 아니라 **더 이상 쓰지 않는 아키텍처의 잔재이기 때문이다.**

그 파일은 CI에게 EKS access entry를 주고 있었다
(`AmazonEKSEditPolicy` + `app` 네임스페이스). 이는 **GitHub Actions가 직접
`kubectl` 로 배포하는 push 방식**을 전제한 설계다.

우리는 GitOps로 갔다(D-004). Actions는 ECR까지만 하고 배포는 Argo CD가
클러스터 안에서 당겨온다. **CI는 클러스터 접근 권한이 아예 필요 없다.**

### 남긴 것

`cluster.tf` 의 `aws_iam_openid_connect_provider.eks` 는 그대로 두었다.
이름이 비슷하지만 **클러스터 자신의 IRSA용**이고, `lbc_irsa.tf` 가 참조한다.
GitHub용과 전혀 다른 것이다.

### 배울 점 하나

팀원 코드는 CI 권한을 `AmazonEKSEditPolicy` + 네임스페이스 스코프로 좁혀 두었다.
반면 `00-cicd` 의 `o2-live-github-tf` 는 `AdministratorAccess` 다.
Terraform이 관리할 대상이 확정되면 그 감각대로 좁혀야 한다(코드에 TODO로 남김).

---

## D-010. Terraform state는 버킷 하나에 모은다

`s3://o2-tfstate-066107819912` 로 통일했다.

`00-cicd` 만 별도 버킷(`o2-live-tfstate`)에 있었다. 그 스택을 만들 당시
팀 버킷의 존재를 몰랐기 때문이다. 한 프로젝트의 state가 두 곳에 흩어지면
백업·권한·수명주기 정책을 두 벌 관리해야 하고, 새로 온 사람이 한쪽만 보고
전부인 줄 알기 쉽다.

```
o2-tfstate-066107819912/
  cicd/terraform.tfstate       ← 옮겨옴
  network/terraform.tfstate
  eks/terraform.tfstate
  data/terraform.tfstate
  platform/terraform.tfstate   ← 04-platform (아직 미적용)
```

이전 후 `terraform plan` 이 `No changes` 로 나오는 것을 확인했고,
빈 버킷은 삭제했다.

**참고:** 팀 버킷에 `data/terraform.tfstate` 가 이미 있다.
`03-data` 에 해당하는 코드가 어딘가 존재한다는 뜻이므로, 그것도 저장소로
흡수해야 한다.

### D-008 보충: 헬름 릴리스를 둘로 나눈 이유

`argo-cd` 차트의 `extraObjects` 에 Application을 함께 넣으려 했으나 실패했다.
헬름은 렌더링한 객체를 적용 전에 클러스터 API와 대조하는데,
그 시점에는 아직 CRD가 설치되지 않았기 때문이다.

```
no matches for kind "Application" in version "argoproj.io/v1alpha1"
```

같은 릴리스에서 CRD를 설치하면서 그 CRD의 인스턴스를 만들 수는 없다.
`argocd-apps` 차트를 두 번째 릴리스로 두고 `depends_on` 으로 순서를 강제한다.

### D-008 보충: 클러스터 생성자는 access entry 대상이 아니다

`cluster_admin_arns` 에 클러스터 생성자를 넣었더니 apply가 실패했다.

```
ResourceInUseException: The specified access entry resource is already in use
```

EKS가 클러스터 생성 시점에 생성자에게 관리자 access entry를 자동 부여한다.
EKS가 관리하는 것을 Terraform이 또 만들려 하면 충돌한다. 목록에서 제외한다.
