# 결정 기록

구조를 정할 때 갈렸던 지점과 그 근거를 남긴다.
"왜 이렇게 했지"를 반년 뒤에 다시 묻지 않기 위한 문서다.

> **이 파일은 통째로 읽지 않는다.** 900줄, 약 15,000토큰이고 계속 자란다.
> 아래 인덱스에서 고른 뒤 그 절만 읽는다.
>
> ```bash
> grep -n '^## D-015' docs/decisions.md   # 시작 줄을 찾고
> sed -n '553,607p' docs/decisions.md     # 그 절만 읽는다
> ```

## 인덱스

| # | 결정 | 키워드 |
|---|---|---|
| D-001 | 워크플로를 세 개로 나눈다 | `app.yml` `tf.yml` `scan.yml` |
| D-002 | 인프라를 스택으로 나눈다 | 스택 분리, plan 길이, 수명 |
| D-003 | 시크릿 스캔은 바이너리로 | gitleaks, `--redact` |
| D-004 | 배포는 GitOps (Argo CD) | `selfHeal`, `replicas` 충돌, `yq` 태그 갱신 |
| D-005 | 인프라는 로컬에서 apply | plan만 CI, NAT·RDS 과금 |
| D-006 | 매니페스트를 별도 저장소로 | 브랜치 보호 충돌, `DEPLOY_REPO_TOKEN` |
| D-007 | 인프라 코드를 저장소로 흡수 | `~/Downloads`, tfvars 커밋 |
| D-008 | 클러스터 안도 코드로 (`04-platform`) | helm 프로바이더, CRD 순서 |
| D-009 | CI 자격증명 소유자는 `00-cicd` | OIDC 계정당 하나 |
| D-010 | state는 버킷 하나 | `o2-tfstate-066107819912` |
| D-011 | 파이프라인 점검 정리 | plan 권한, 소유자 중복 |
| D-012 | 배포 저장소 ruleset이 배포를 막음 | `bypass_actors` |
| D-013 | 파이프라인 검증용 페이지 | `apps/testpage` (D-020에서 제거) |
| D-014 | 취약점은 푸시 전에 (Trivy) | CRITICAL 차단, SARIF |
| D-015 | `data/` state는 데이터 계층이 아니다 | 백데이터 파트, `datastore/` 키 |
| D-016 | 계약을 코드보다 먼저 고정 | WebSocket 프레임, D-14·D-15 확정 |
| D-017 | `03-data` — 지금 정할 것만 | 암호화, 콜레이션, `volatile-lru`, 비밀번호 |
| D-018 | 접속 정보는 `04-platform`이 넣는다 | ConfigMap, ExternalSecret, Pod Identity |
| D-019 | 프론트엔드는 계약을 따른다 | SSE vs WebSocket, 재고 분리 |
| D-020 | 문서를 저장소로, 죽은 코드 정리 | `architecture.md`, `AGENTS.md`, 부하 스크립트 |
| D-021 | 문서는 매 세션 비용이다 | 토큰, 인덱스, 부분 읽기 |
| D-022 | 규약은 `AGENTS.md` 하나, 인덱스는 CI가 지킨다 | Codex·Copilot 호환, `check-docs-index.sh` |
| D-023 | PR에서 terraform plan을 돌리지 않는다 | CI 자격증명 제거, public 저장소 |
| D-024 | ESO 게이트를 Datadog에서 분리 | `enable_external_secrets`, `moved` |
| D-025 | MySQL 8.0 → 8.4 | 확장 지원 요금, `name_prefix`, 파라미터 그룹 교체 |
| D-026 | APM을 켠다 (D-024 뒤집기) | `portEnabled`, `ddtrace-run`, `status.hostIP` |

**"겪은 함정"** 절이 두 곳에 있다 (D-006 뒤, D-019 뒤).
증상으로 검색하는 편이 빠르다.

---

## D-001. 워크플로를 세 개로 나눈다

`app.yml` / `tf.yml` / `scan.yml`.

가르는 기준은 **"실패했을 때 누가 무엇을 해야 하는가"** 이다.

| 워크플로 | 실패하면 | 되돌리는 비용 |
|---|---|---|
| `app.yml` | 애플리케이션 배포가 멈춘다 | 낮다. 다시 배포하면 된다 |
| `tf.yml` | 인프라가 어긋난 상태로 남을 수 있다 | 높다. state 복구가 필요할 수 있다 |
| `scan.yml` | 시크릿이 히스토리에 남는다 | 되돌릴 수 없다. 키를 교체해야 한다 |

되돌리는 비용이 다르면 적용 방식도 달라야 한다.
그래서 `tf.yml` 만 CI가 적용하지 않는다 — plan을 사람이 읽고 로컬에서 apply한다.
(처음에는 `environment: infra` 승인 게이트를 붙인 apply 잡이었다. D-005, D-011)

---

## D-002. 인프라를 세 스택으로 나눈다

`01-network` → `02-eks` → `03-data`.

한 스택에 다 넣으면 **보안 그룹 규칙 하나 고치는 데 EKS 전체가 plan에 올라온다.**
plan이 길어지면 사람이 읽지 않게 되고, 읽지 않는 plan은 승인 게이트의 의미를 없앤다.

번호는 장식이 아니라 **의존 순서**다. `02`와 `03`은 `01`의 출력(VPC ID, 서브넷)을
remote state로 참조한다. apply는 반드시 이 순서로 돌아야 한다.
apply는 로컬에서 하므로 순서를 지키는 것은 사람의 몫이다.

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

### 왜 Application 매니페스트만 매니페스트 저장소 밖에 있나

매니페스트 저장소 안에 두면 Argo가 **자기 자신을 관리 대상으로 삼는다.**
처음에는 `bootstrap/argocd-application.yaml` 을 두고 한 번만 손으로 적용했으나,
지금은 `infra/04-platform` 의 `argocd-apps` 헬름 릴리스가 소유한다 (D-008, D-011).

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

`infra/` 의 스택은 로컬에서 `plan` 과 `apply` 로 확인이 끝난 뒤 저장소에 올린다.
CI는 적용하지 않는다 — PR에서 `plan` 만 돌려 무엇이 바뀔지 보여준다.
(`03-data` 는 D-017에서 작성했다)

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

- ~~`00-cicd` 의 state만 다른 버킷에 있다~~ → D-010에서 팀 버킷으로 합쳤다.
- ~~`02-eks/github_oidc.tf` 도 GitHub OIDC 프로바이더를 만든다~~ → D-009에서 제거했다.

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
| Argo Application | `kubectl apply` 수동 | `argocd-apps` 헬름 릴리스 |
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

---

## D-011. 파이프라인 점검에서 나온 정리

apply 잡을 없앤 뒤(2484b48) 남아 있던 전제와, 소유자가 둘인 리소스를 정리했다.

### PR의 plan은 읽기 전용 역할로 돈다

`o2-live-github-tf` 가 `AdministratorAccess` 였다. apply 잡이 있던 시절의 권한인데,
apply를 로컬로 옮긴 뒤에도 그대로 남아 **PR에서 도는 plan이 계정 관리자 자격을
쥐고 있었다.**

`terraform plan` 은 읽기 전용 동작이 아니다. `external` data source나 커스텀
provider가 plan 단계에서 실행되므로, 저장소에 PR을 열 수 있는 사람이면 그
자격증명으로 원하는 것을 할 수 있었다.

- 정책을 `ReadOnlyAccess` 로 교체
- 신뢰 정책의 `environment:infra` 제거 — 그 environment를 쓰는 잡이 없다
- `tf.yml` 의 plan에 `-lock=false` 추가. 읽기 전용 역할은 S3에 잠금 파일을 쓸 수
  없다. 상태를 바꾸지 않는 plan이라 잠금 없이 돌아도 안전하다

### `04-platform` 은 CI에서 plan하지 않는다

AWS 권한만 낮추면 구멍이 절반만 닫힌다. 이 스택은 헬름 릴리스를 관리해
plan에도 클러스터 접근이 필요했고, 그래서 `cluster_admin_arns` 에
`role/o2-live-github-tf` 를 넣어 **EKS 클러스터 관리자** 권한을 주고 있었다.
plan이 임의 코드를 실행할 수 있는 이상, AWS는 읽기 전용인데 클러스터는
관리자인 상태가 남는다.

권한을 좁히는 방향도 봤지만 헬름은 릴리스 상태를 Secret에 저장하므로
View 정책으로는 plan이 돌지 않는다. Secret을 읽을 수 있으면 argocd 관리자
비밀번호까지 읽히므로 좁히는 실익도 적다.

apply는 어차피 로컬이다. plan도 로컬로 옮기고 access entry를 회수한다.
대가는 이 스택만 PR에서 diff를 못 본다는 것이다.

### Argo CD Application의 소유자는 `04-platform` 하나다

`bootstrap/argocd-application.yaml` 과 `04-platform` 의 `argocd-apps` 릴리스가
같은 `Application/o2-dev` 를 만들고 있었다. 부트스트랩을 적용한 클러스터에
`04-platform` 을 apply하면 헬름이 자기가 만들지 않은 리소스를 발견하고 멈춘다.

D-008에서 이미 헬름으로 옮겼으므로 부트스트랩 파일이 잔재였다. 파일을 지우고,
그것만 검사하던 `app.yml` 의 `bootstrap` 잡도 함께 지웠다.

### ECR 저장소의 소유자는 `00-cicd` 하나다

`02-eks/ecr.tf` 가 `o2/testpage` 를 따로 만들고 있었다. 파이프라인이 쓰지 않는
검증용 저장소인데, `02-eks` 의 `ecr_repository_url` 출력이 그것을 가리켜
앱 이미지 주소로 오해하기 쉬웠다. 둘 다 제거했다. (OIDC 프로바이더를 정리한
D-009와 같은 이유 — 소유자가 둘인 리소스는 한쪽 destroy가 다른 쪽을 부순다)

### 배포 저장소도 검증을 갖는다

`O2-live-deploy` 에는 워크플로가 없었다. 매니페스트가 곧 클러스터 상태인데
문법·스키마 오류를 걸러줄 곳이 없어, 잘못된 값은 Argo의 sync 실패로만 드러났다.

`kubeconform -strict` 를 도는 워크플로를 추가했다. `-strict` 는 스키마에 없는
필드를 오류로 본다 — 오타 난 필드는 조용히 무시되어 "적용은 됐는데 설정이 안
먹는" 상태를 만들기 때문이다. push에서도 도는 이유는 태그 갱신 커밋이 PR 없이
main으로 직접 들어오기 때문이다.

### 그 밖에

- `:latest` 태그를 더 이상 밀지 않는다. 참조하는 곳이 없는데, 저장소를
  `IMMUTABLE` 로 바꾸면 두 번째 푸시부터 실패한다.
- 태그 갱신 커밋의 `git push` 에 rebase 재시도를 붙였다. 사람이 그 사이
  매니페스트를 고치면 non-fast-forward로 배포가 실패했다.

## D-012. 배포 저장소의 브랜치 규칙이 배포를 막았다

`O2-live-deploy` 의 `main` 에 ruleset(`pull_request` 필수)이 걸리면서
`app.yml` 의 `deploy` 잡이 죽었다.

```
remote: error: GH013: Repository rule violations found for refs/heads/main.
remote: - Changes must be made through a pull request.
 ! [remote rejected] main -> main (push declined due to repository rule violations)
```

D-006에서 앱 저장소의 브랜치 보호를 피하려고 매니페스트를 옮겼는데,
같은 규칙이 옮겨간 저장소에도 걸린 것이다. 증상이 고약한 이유는
**앞 구간이 전부 성공한 뒤에 끊긴다**는 데 있다. 이미지는 ECR에 올라가고
클러스터는 예전 이미지로 계속 잘 돌아, 대시보드를 보지 않으면 배포가
멈춘 줄 모른다.

ruleset의 `bypass_actors` 에 저장소 admin 역할을 넣어 푼다. 사람에게는
PR 규칙이 그대로 남고, 태그 갱신 커밋만 통과한다.

워크플로가 PR을 열고 auto-merge하게 바꾸는 방법도 있었으나, 배포마다
PR이 하나씩 쌓이는 대가에 비해 얻는 것이 없다. 이 저장소에 들어오는
사람 커밋은 매니페스트 변경뿐이고 그것은 여전히 PR을 거친다.

### 남은 위험

`bypass_actors` 는 **역할** 단위다. 개인을 지정할 수 없어 저장소 admin 전체가
직접 push할 수 있게 된다. `DEPLOY_REPO_TOKEN` 의 소유자가 admin이 아니게 되면
그날로 배포가 다시 멈추므로, PAT 만료와 함께 확인 대상이다.

## D-013. 파이프라인 검증용 페이지를 서비스로 둔다

`apps/testpage/` — nginx 정적 페이지 하나. 커밋에서 브라우저까지가
실제로 이어지는지 보는 것이 목적이다.

`api` 는 이 확인에 쓰기 나쁘다. JVM이라 빌드가 느리고, 무엇이 깨졌을 때
앱 문제인지 파이프라인 문제인지 구분이 안 된다. 빌드할 것이 없는 페이지는
실패하면 원인이 파이프라인뿐이다.

D-011에서 `02-eks/ecr.tf` 를 지우며 코드 밖으로 떨어져 나온 `o2/testpage`
저장소를 `terraform import` 로 `00-cicd` 에 흡수했다. 용도가 원래 같았고,
남겨두면 수명주기 정책도 스캔 설정도 붙지 않는다.

`verify` 잡은 `build.gradle.kts` 가 없으면 건너뛴다. 모든 서비스가 JVM이라는
전제가 워크플로에 박혀 있었고, 정적 페이지 하나에 gradle 프로젝트를 흉내내게
하는 것보다 전제를 걷어내는 쪽이 맞다. 빌드 검증은 이미지 빌드가 대신한다.

외부 노출은 ALB Ingress로 한다. 서비스는 `ClusterIP` 그대로 두고 Ingress만
붙인다 — 서비스마다 `LoadBalancer` 타입을 쓰면 서비스 수만큼 NLB가 생긴다.

---

## D-014. 이미지 취약점은 푸시 전에 본다 (Trivy)

ECR에 `scan_on_push` 가 켜져 있어 스캔이 이미 있다고 볼 수도 있지만, 이 계정의
레지스트리 스캔은 `BASIC` 이다. BASIC은 **OS 패키지만** 본다 — 우리 런타임
이미지에서는 Alpine의 `apk` 목록이 전부다.

정작 위험이 모이는 곳은 `app.jar` 안이다. Spring Boot fat JAR에 들어간 Java
라이브러리는 BASIC 스캔의 시야 밖이라, Log4Shell 같은 것이 터져도 ECR은
조용하다. Trivy는 JAR을 풀어 그 안의 의존성까지 본다. 결제·쿠폰이 붙기 전에
이 구멍을 닫아둔다.

Inspector로 올리면(`ENHANCED`) 레지스트리 스캔도 의존성을 보지만 유료다.
CI에서 무료로 같은 것을 보고, ECR BASIC은 그대로 둔다 — 저장된 이미지를
계속 지켜보는 역할은 남는다.

### 빌드와 푸시를 나눈다

`push: true` 로 한 번에 끝내면 스캔 결과를 **이미지가 이미 ECR에 올라간 뒤에**
보게 된다. 그러면 스캔은 통보이지 게이트가 아니다.

`load: true` 로 러너의 도커 데몬에 올리고, 스캔한 다음, `docker push` 한다.
레이어 캐시(`type=gha`)는 그대로 쓰므로 빌드 시간은 거의 늘지 않는다.

### 막는 기준과 보는 기준을 다르게 둔다

`exit-code: 0` 으로 시작해 리포트만 받았다. 첫 실행에서 CRITICAL 0건이
확인된 뒤 차단으로 올렸다. 첫날부터 막았으면 그때 있던 CRITICAL 5건 때문에
배포가 섰을 것이고, 그러면 사람들이 스캔을 끄는 쪽으로 갔을 것이다.

차단은 **CRITICAL만** 본다. HIGH는 기록만 한다. 지금 남은 HIGH는 전부
베이스 이미지(alpine)의 것이고 우리가 고칠 수 없다 — `eclipse-temurin` 이
갱신해야 사라진다. 손쓸 수 없는 이유로 배포가 서면 결국 스캔을 끄게 된다.
반면 CRITICAL은 대개 의존성 한 줄로 고쳐진다.

그래서 단계를 둘로 나눴다. 하나로 합치면 `limit-severities-for-sarif` 때문에
**Security 탭에서 HIGH가 통째로 사라진다.** 보이는 것과 막는 것을 같은 값으로
묶을 수 없다.

- 보고 단계 — `severity: CRITICAL,HIGH`, `exit-code: 0`, SARIF 출력
- 차단 단계 — `severity: CRITICAL`, `exit-code: 1`, `skip-setup-trivy: true`

차단 단계가 실패하면 그 뒤의 `docker push` 가 실행되지 않아 이미지가 ECR에
올라가지 않는다. SARIF 업로드는 차단보다 앞이라, 막힌 경우에도 무엇 때문에
막혔는지 Security 탭에서 볼 수 있다.

`ignore-unfixed: true` 는 처음부터 켠다. 아직 패치가 없는 취약점으로 배포가
막히면 손쓸 방법이 없어, 결국 예외 목록만 길어진다.

### 결과는 Code Scanning으로 보낸다

`scan.yml` 의 gitleaks는 SARIF를 만들어 워크플로 아티팩트로 던지고 끝냈다.
보려면 Actions 탭에서 zip을 받아 열어야 하니 아무도 보지 않았다.

이 저장소는 public이라 Code Scanning이 무료로 열려 있다. 올리면 Security 탭에
쌓이고, PR에 해당 줄로 붙고, 고쳐지면 알아서 닫힌다. gitleaks도 이쪽으로
옮길 것.

주의: 매트릭스 잡에서는 `category` 를 서비스마다 달리해야 한다. 같은 값으로
올리면 뒤에 끝난 잡이 앞의 결과를 덮어써 하나만 남는다.

또 하나, `limit-severities-for-sarif` 는 기본이 꺼짐이다. 켜지 않으면
`severity: CRITICAL,HIGH` 로 걸러도 SARIF에는 LOW/MEDIUM까지 전부 실려
Security 탭이 잠긴다.

### 시크릿 검사는 넣지 않는다

Trivy에도 시크릿 스캐너가 있지만 `scanners: vuln` 로 껐다. gitleaks가 이미
그 일을 하고 있고, 둘이 같은 것을 잡으면 중복 알림만 늘어난다.
---

## D-015. `data/terraform.tfstate` 는 데이터 계층이 아니다

D-010에서 "팀 버킷에 `data/terraform.tfstate` 가 이미 있으니 `03-data` 에
해당하는 코드를 찾아 흡수할 것"이라고 남겼다. 그 전제가 틀렸다.
열어보니 RDS·ElastiCache가 아니라 **AI 에이전트용 백데이터 파이프라인**이다.

```
Kinesis     stream-business, stream-client
Firehose    o2-business-to-s3, o2-client-to-s3
S3          o2-data-lake-066107819912
Lambda      o2-agg, o2-warm-api
DynamoDB    o2-agent-context
Glue        o2-ml-data-prep-job
IAM         o2-producer-irsa-role                 (SA: data-stream/o2-producer)
```

관리 리소스 30개. RDS와 ElastiCache는 계정에 **하나도 없다** —
데이터 계층은 아직 백지다.

### 왜 위험했나

`03-data` 를 쓰면서 backend key를 `data/terraform.tfstate` 로 두려던 참이었다.
그렇게 했으면 Terraform이 위 30개를 자기 것으로 인식하고, 다음 destroy에
전부 날아간다. **state 키는 이름이 비슷하다는 이유로 재사용하면 안 된다.**

`03-data` 의 backend key는 `datastore/terraform.tfstate` 로 간다.
이 스택의 키는 그대로 둔다.

### 다른 파트의 작업 영역이다

이 스택은 **AI 에이전트용 백데이터·데이터 스트림 파트**가 맡고 있다.
`stream-business` / `stream-client` → Firehose → S3 → Glue 라는 경로가
그 용도와 정확히 맞는다.

**이 저장소의 관심사가 아니다.** 흡수 대상도 아니고, 존치나 사양은 담당자가
정한다. state와 리소스 모두 **건드리지 않는다.**

D-007(`01-network`·`02-eks` 흡수)과 겉모습이 비슷해 흡수 대상으로 오해하기
쉬우나 다르다. 그쪽은 이 저장소가 책임지는 인프라였고, 이쪽은 아니다.

### 설계 문서의 D-09와 충돌하지 않는다

`live-commerce-architecture-decisions.md` 의 D-09는 "Kafka와 Kinesis 모두
도입하지 않는다"이다. 그 판단의 대상은 **커머스 이벤트 경로**(주문·재고·
캐시 무효화)이고, 거기에는 여전히 SQS와 Valkey Pub/Sub만 쓴다.
백데이터 파이프라인이 무엇을 쓰는지는 D-09의 범위 밖이다.

### 이 저장소가 지킬 것은 하나뿐이다

**state 키를 침범하지 않는다.** `data/` 는 그쪽이 쓰고 있으므로
`03-data` 의 backend key 는 `datastore/terraform.tfstate` 로 간다.
D-010의 각주("코드를 찾아 흡수할 것")는 이 결정으로 대체된다.

---

## D-016. 계약을 코드보다 먼저 고정한다 (`docs/contracts.md`)

애플리케이션을 만들기 전에 서비스 사이에 오가는 것의 모양을 먼저 적었다.
"스펙 전부 확정 → 전부 구현"이라는 워터폴이 아니라, **나중에 바꾸면 여러 서비스를
동시에 고쳐야 하는 것만** 골라 먼저 고정하는 것이다.

그 기준으로 고른 것은 넷이다.

| 항목 | 나중에 바꾸면 |
|---|---|
| WebSocket 프레임 포맷 | 서버·클라이언트·부하 테스트 전부 |
| 캐시 키 이름 | 무효화 경로 전부 |
| 이벤트 스키마 | 다른 파트와 재합의 |
| 오류 `code` 체계 | 클라이언트 분기 전부 |

인스턴스 클래스나 HPA 임계값처럼 나중에 값만 바꾸면 되는 것은 여기 넣지 않았다.
그런 것까지 미리 정하면 측정 전에 추측으로 채우게 된다.

### 함께 확정한 두 가지

**상품 정보는 WebSocket으로 푸시한다. 폴링 엔드포인트는 만들지 않는다.**
폴링은 대부분의 응답이 "바뀐 것 없음"인데도 Peak에서 초당 13,000건이 넘는다.
채팅 WebSocket이 어차피 열려 있으므로 같은 채널로 보내면 그 트래픽이 통째로
사라진다. 대가는 채팅 게이트웨이가 상품 정보 전달의 단일 경로가 된다는 것인데,
끊겼을 때는 재연결 후 스냅샷을 다시 받는 것으로 흡수한다.

**채팅 이벤트의 다중 소비는 필요 없다.** 소비자가 브로드캐스트 하나뿐이라
Valkey Pub/Sub으로 충분하다. 모더레이션이나 실시간 집계가 붙으면 그때
Valkey Streams를 먼저 본다 — 추가 인프라가 0이기 때문이다.

### 프레임을 처음부터 배열로 두는 이유

서버가 보내는 프레임은 단건이어도 배열을 싣는다. 200ms 창에 쌓인 것을 한 번에
보내기 위해서다.

트래픽이 없는 개발 초기에는 과해 보이지만, **이건 나중에 못 얹는다.**
단건 포맷으로 출발하면 배치를 도입할 때 서버·클라이언트·테스트를 전부 고쳐야
한다. 지금 배열로 두는 비용은 대괄호 한 쌍이다.

### 채팅도 이벤트로 남긴다 — 단 본문은 빼고

관측 데이터는 **비대칭**이다. 안 남긴 과거는 복구가 불가능하고, 빼는 것은
`emit` 한 줄을 지우면 된다. 볼륨을 근거로 반대했으나 계산해보니 약하다 —
Peak 20 msg/s × 3,600초 = 방송당 72,000건, 약 29 MB다.

없으면 에이전트가 짚는 것은 "CPU가 올랐다"까지이고, 있으면 "채팅 인입이
20 → 210 msg/s로 튀고 12초 뒤 포화됐다"까지 간다.

**대신 본문은 싣지 않는다.** 채팅은 이 시스템에서 **유일하게 외부인이 자유롭게
쓰는 입력**이고, 그것이 에이전트가 읽는 저장소로 흘러간다. 본문을 저장하면
시청자 아무나가 운영 에이전트에게 지시를 넣는 경로가 생긴다
(설계 문서 8.5). 주문·재고 이벤트는 전부 우리가 만든 값이라 이 문제가 없다.

길이·해시·중복 여부만 실어도 부하 분석 목적은 전부 달성된다. 본문이 필요한
용도는 모더레이션인데 지금 범위 밖이고, 필드 추가는 계약을 깨지 않으므로
나중에 붙일 수 있다.

**발행은 인입 지점에서만 한다.** 팬아웃 전달마다 발행하면 초당 80만 건이 되어
파드가 죽는다. 40,000배 차이이고, 브로드캐스트 루프에 `emit` 한 줄을 잘못 넣으면
그렇게 된다.

### 남은 것

`contracts.md` 5.4의 세 가지(`chat.send` 를 SDK에 추가 가능한지, 본문 제외 방침에
동의하는지, `service` 이름 규약)는 백데이터 파트에 확인이 필요하다.
애플리케이션 코드에 박히는 것이라 **개발 시작 전에 답이 있어야 한다.**

---

## D-017. `03-data` — 지금 정할 것만 정한다

RDS MySQL, ElastiCache Valkey, 주문 확정 SQS. 사이징은 전부 비워 두고
**나중에 못 바꾸는 것만** 정했다.

| 정한 것 | 왜 지금인가 |
|---|---|
| 스토리지 암호화 | 생성 시점에만 설정 가능. 나중엔 인스턴스 재생성 |
| 문자셋·콜레이션 | 나중에 바꿔도 기존 테이블은 안 바뀌어 JOIN 이 깨진다 |
| Valkey 축출 정책 | 아래 |
| 마스터 비밀번호 관리 방식 | 아래 |

인스턴스 클래스, 노드 수, Multi-AZ, 리드 리플리카는 전부 변수로 빼고 최소값으로
뒀다. 부하 테스트 전에 정하면 추측이고, 나중에 값만 바꾸면 되는 것들이다.

### 축출 정책을 기본값으로 두면 재고가 사라진다

Valkey 는 재고의 **캐시가 아니라 원본**이다. `stock:{sku}` 에는 TTL 을 걸지 않는다 —
만료되는 순간 재고가 소실되기 때문이다.

그런데 `maxmemory-policy` 가 `allkeys-lru` 면 메모리가 찰 때 **TTL 이 없는 키도
축출 대상이 된다.** 방송 중에 재고 키가 조용히 사라지고, 다음 주문에서 Lua
스크립트가 `-2`(미초기화)를 반환한다. 로그에는 "재고 없음"만 남는다.

`volatile-lru` 는 TTL 이 있는 키만 축출한다. 세션과 상품 상세는 지워져도 다시
채우면 되고 재고는 그렇지 않다 — 그 구분이 파라미터 하나로 표현된다.

TTL 을 걸지 않는다는 결정과 축출 정책은 **한 쌍이다.** 한쪽만 알고 있으면
나머지 하나가 조용히 배신한다.

### 비밀번호를 Terraform 이 만들지 않는다

`random_password` 로 만들어 넘기는 것이 흔한 패턴이지만 그 값은 state 에 평문으로
들어간다. `.gitignore` 의 경고와 D-005 가 말하는 것이 정확히 이것이다.

`manage_master_user_password = true` 를 쓰면 AWS 가 비밀번호를 만들어 Secrets
Manager 에 넣고 로테이션까지 맡는다. **state 에는 시크릿 ARN 만 남는다.**
파드 주입은 04-platform 의 ESO 경로를 그대로 쓴다 (Datadog 키와 같은 방식).

### 노드 SG 를 remote state 가 아니라 data source 로 읽는다

`02-eks` 는 자체 보안 그룹을 만들지 않고 EKS 가 자동 생성한 클러스터 SG 를 쓰는데,
그 ID 를 출력하지 않는다. 출력을 추가하려면 `02-eks` 를 다시 apply 해야 한다.

리소스 변경이 없는 출력만의 apply 라도, 돌아가는 클러스터 스택을 건드리는 것보다
`data "aws_eks_cluster"` 로 읽는 편이 싸다. D-002 가 스택을 나눈 이유가
"작은 것 하나 고치자고 EKS 전체를 plan 에 올리지 않기 위해서" 였다.

### `01-network` 의 `enable_data_tier` 를 켰다

private-data 서브넷과 DB/Cache 서브넷 그룹이 이 스택의 전제다.
CIDR 인덱스가 12,13 으로 고정되어 있어 기존 서브넷에 영향이 없고 서브넷 자체는
과금 대상이 아니다.

끄고 apply 하면 RDS 생성 단계에서 알아보기 어려운 오류가 나므로,
`data.tf` 에 precondition 을 두어 먼저 멈추고 무엇을 해야 하는지 알린다.

---

## D-018. 접속 정보를 매니페스트가 아니라 `04-platform` 이 넣는다

`03-data` 가 RDS·Valkey·SQS 를 만들었지만 그 주소는 `terraform output` 에만 있었다.
파드 입장에서는 없는 것과 같아서, 배포된 API 는 `config.py` 의 기본값
`localhost:3306` 을 보고 있었다. 매니페스트에 `env` 가 한 줄도 없었다.

### 왜 매니페스트에 적지 않나

엔드포인트를 `O2-live-deploy` 에 직접 쓰면 데이터 스택을 다시 만들 때마다
사람이 손으로 고쳐야 한다. 그리고 안 고쳐도 **파드는 정상적으로 뜬다** —
DB 연결에서만 실패하므로 배포 파이프라인은 초록불이다.

`04-platform` 이 `03-data` 의 remote state 를 읽어 ConfigMap 을 만들면,
데이터 스택을 재생성해도 이 스택을 apply 하는 것만으로 따라간다.

`03-data` 에 두지 않는 이유는 그 스택에 aws 프로바이더만 있어서다.
클러스터 안에 무언가 만들려면 kubectl 프로바이더가 필요하고,
그것은 이미 이 스택이 갖고 있다 (D-008).

| 무엇 | 어디에 | 왜 |
|---|---|---|
| DB/Valkey/SQS 주소 | ConfigMap `o2-data` | 비밀이 아니다 |
| DB 비밀번호 | ExternalSecret → Secret `o2-db` | 원본은 Secrets Manager |
| AWS 자격증명 | Pod Identity | 액세스 키를 만들지 않는다 |

### 조용히 깨지는 지점 두 개

**ServiceAccount 이름 불일치.** 매니페스트의 `serviceAccountName` 이
`app_service_accounts` 목록에 없으면 파드는 뜨고 SQS 호출에서만 실패한다.
기동이 성공하므로 알아채기 늦다. 서비스를 추가할 때 두 곳을 함께 늘려야 한다.

**ESO 게이트.** ESO 컨트롤러와 `ClusterSecretStore` 는 현재 `enable_datadog` 로
게이트되어 있다. 원래 둘 다 Datadog 전용이 아니므로 게이트를 분리하는 편이
맞지만, 돌아가는 스택을 지금 건드리지 않았다. `enable_datadog = false` 로 두면
DB 시크릿도 동기화되지 않는다.

### ServiceAccount 를 Terraform 이 만드는 이유

Pod Identity association 은 namespace + serviceAccount **이름 문자열**로 건다.
ServiceAccount 를 매니페스트 저장소에 두면 Argo 가 만들기 전까지 대상이 없어,
첫 배포에서 파드가 자격증명 없이 뜬다. 순서를 보장하려면 association 을 만드는
쪽이 SA 도 함께 만들어야 한다.

---

## D-019. 프론트엔드 계약은 `contracts.md` 를 따른다

프론트엔드가 mock 서비스 계층을 먼저 만들면서 계약이 갈렸다.

| 항목 | `contracts.md` | 프론트 mock |
|---|---|---|
| 실시간 채널 | WebSocket | SSE (`EventSource`) |
| 서비스 분할 | `api` 하나 | `live` / `product` / `coupon` / `checkout` 4개 |
| 상품 식별자 | `sku_id` | `id` |
| 수량 | `qty` | `quantity` |
| 재고 | 표시값과 판정값 분리 | `product.stock` 단일 값 |

현재 `apps/frontend` 는 CI/CD 동작 확인을 겸한 데모라 전면 수정이 예정되어 있다.
그래서 **계약 쪽을 유지하고 프론트를 맞추는 방향으로 정리한다.**

### SSE 가 아니라 WebSocket 인 이유

SSE 도 서버→클라이언트 푸시라는 목적은 같고, 채팅 전송을 별도 POST 로 빼면
동작한다(인입은 Peak 에서도 20 msg/s 라 가볍다). 배치 프레임·하트비트·팬아웃
구조도 둘 다 같다.

갈리는 것은 **재연결**이다. `EventSource` 의 내장 재연결에는 지터가 없다.
브라우저가 고정 간격으로 재시도하므로 스케일다운 순간 끊긴 클라이언트가 거의
동시에 몰린다. R-01(재연결 폭풍)이 정확히 그 상황이고, 이 프로젝트에서 채팅
게이트웨이는 스케일링 설계를 보여주는 유일한 컴포넌트다.

지터를 넣으려면 `EventSource` 를 버리고 직접 관리해야 하는데, 그러면 SSE 를
고를 이유였던 "내장 재연결"이 사라진다.

### 재고를 단일 값으로 두지 않는 이유

`product.stock` 하나로 주문 가부까지 판단하면 오버셀이 난다.
표시값은 몇 초 낡아도 되지만 판정은 항상 Valkey `DECR` 결과를 따라야 한다
(설계 문서 3.6). 이 분리는 UI 문구로 흡수한다 —
"주문 처리 중 품절되었습니다".

---

## 겪은 함정 (이어서)

### `db.t4g.micro` 는 Performance Insights 를 지원하지 않는다

```
InvalidParameterCombination: Performance Insights not supported
for this configuration.
```

micro·small 버스터블 클래스 전체가 제외 대상이다. `03-data` 의 첫 apply 가
여기서 멈췄고, Valkey 는 이미 만들어진 뒤였다.

끄는 것으로 잃는 것은 콘솔 UI 하나뿐이다. 설계 문서 4.1 의 버퍼 풀 적중률은
`performance_schema.global_status` 를 직접 조회하면 그대로 나온다.
인스턴스 등급을 올리는 Phase 6 에서 함께 켠다.

---

## D-020. 문서를 저장소 안으로 모으고 죽은 코드를 걷어낸다

### 설계 문서가 버전 관리 밖에 있었다

`live-commerce-architecture-decisions.md` 가 누군가의 `~/Downloads` 에 있었다.
**D-007과 똑같은 상황이다** — 그때는 인프라 코드였고 이번엔 설계 문서다.
프로젝트의 모든 수치와 근거가 담긴 문서인데 이력도 리뷰도 없었다.

`docs/architecture.md` 로 옮겼다. 앞으로 결정이 바뀌면 이 문서와
`decisions.md` 를 함께 고친다.

### `CLAUDE.md` 를 만든 이유

문서가 아홉 개로 늘었다. 새로 합류하는 사람이나 AI 에이전트가 어디부터
읽어야 하는지 알 수 없는 상태였다.

`CLAUDE.md` 는 **읽는 순서와 지도**다. 내용을 복제하지 않고 링크만 건다 —
같은 사실을 두 곳에 적으면 한쪽이 반드시 낡는다. 대신 **어기면 조용히
깨지는 것들**(state 키, 환경변수 이름, ServiceAccount 이름, apply 순서)은
요약해 두었다. 그것들은 링크를 따라가기 전에 눈에 들어와야 한다.

### 걷어낸 것

| 대상 | 왜 |
|---|---|
| `apps/testpage/` | 매니페스트가 이미 제거되어 배포되지 않는데, `app.yml` 이 `apps/*/` 를 훑어 워크플로가 바뀔 때마다 빌드·스캔·푸시가 돌고 있었다 |
| `apps/api` 의 `items` 라우터·`example` 모델 | 스켈레톤 예제. 테이블이 없어 500 을 반환하고 있었고, 계약(`contracts.md`)에 맞춘 도메인 테이블이 들어오면 어차피 사라질 것이었다 |
| `DebugPage` 의 `/items` 호출 | 위와 한 쌍. 헬스 확인만 남겼다 |

`o2/testpage` ECR 저장소는 **남겨두었다.** 목록에서 빼면 destroy 대상이 되는데
이미지가 11개 들어 있어 실패한다. 지우려면 `force_delete = true` 를 먼저 apply 해
state 를 갱신해야 한다 — destroy 는 config 가 아니라 state 의 값으로 동작하기
때문이다(같은 문서 "겪은 함정"). 스토리지 비용이 미미해 그 두 단계를 하지 않았다.

### 고친 것

**`loadtest/spike.js` 가 아무것도 측정하지 않고 있었다.** `${BASE_URL}/` 를
때리는데, ALB 하나를 프론트엔드와 공유하게 되면서 `/` 는 프론트 정적 페이지로
간다. api 는 부하를 전혀 안 받고 있었다. 게다가 응답 본문에 `service` 필드를
기대하는 검사가 있어 **thresholds 가 무조건 실패**한다.

`/api/health` 로 바꾸고 기본 포트도 8080 에서 8000 으로 맞췄다.

이런 종류의 고장이 위험한 이유는 부하 테스트가 잘못된 결과를 내서가 아니라,
**아무도 안 돌려봐서 아직 아무 일도 안 일어났다는 데 있다.**
경로 규약이 바뀌면 부하 시나리오도 함께 바뀌어야 한다.

---

## D-021. 문서는 매 세션 비용이다

팀원들이 AI 에이전트로 작업한다. 문서 구조가 곧 **매 대화의 토큰 비용**이다.

측정해보니 주요 문서가 약 46,000토큰이었다. "결정 기록 좀 읽어봐" 한 마디에
15,000토큰이 들어가고, 그중 실제로 필요한 것은 한 절이다.

### `CLAUDE.md` 는 특별하다

**매 세션 자동으로 읽힌다.** 여기 있는 모든 줄이 팀원 전원의 모든 대화에
곱해진다. 7,133바이트(약 2,400토큰)에서 3,825바이트(약 1,275토큰)로 줄였다.

기준은 **"틀리면 조용히 깨지는가"** 하나다. 파드가 정상적으로 뜨고 런타임에만
실패하는 것들(state 키, 환경변수 이름, ServiceAccount 이름, apply 순서)만
본문에 두고 나머지는 링크로 뺐다. 그런 것들은 링크를 따라가기 전에 눈에
들어와야 한다.

설명서가 아니라 **지도**다. 늘리기 전에 링크로 대신할 수 있는지 본다.

### 큰 문서에는 인덱스를 둔다

`decisions.md`(~15k)와 `architecture.md`(~20k)는 append-only 라 계속 자란다.
상단에 인덱스를 넣고 **읽는 방법을 명시**했다.

```bash
grep -n '^## D-015' docs/decisions.md
sed -n '553,607p' docs/decisions.md
```

인덱스만 읽으면 약 1,000토큰이다. 인덱스에서 고르고 한 절만 읽으면
전체 대비 **8분의 1 수준**으로 끝난다.

줄 번호를 인덱스에 박지 않은 이유는 문서가 자라면 전부 어긋나기 때문이다.
제목으로 찾게 두면 낡지 않는다.

### 같은 사실을 두 곳에 적지 않는다

토큰 문제이기 이전에 정합성 문제다. 두 곳에 적으면 한쪽이 반드시 낡고,
그때부터 어느 쪽이 맞는지 알 수 없다. `CLAUDE.md` 가 `README.md` 의 내용을
복제하고 있던 것을 걷어냈다.

### 배포 저장소에도 진입점을 두었다

`O2-live-deploy` 에서 작업하는 에이전트는 앱 저장소 문서를 못 본다.
매니페스트만 보고는 `serviceAccountName` 이 왜 그 이름이어야 하는지 알 수 없다.
그쪽에도 `CLAUDE.md` 를 두고 규약과 링크만 적었다.

---

## D-022. 규약 파일은 `AGENTS.md` 하나, 인덱스는 CI가 지킨다

D-021에서 문서 구조를 토큰 기준으로 정리했는데, 두 가지가 빠져 있었다.

### 팀원마다 쓰는 도구가 다르다

`CLAUDE.md` 는 Claude Code 만 읽는다. 같은 저장소에서 다른 도구를 쓰면
규약을 전혀 못 본 채로 작업하게 된다.

| 도구 | 읽는 파일 |
|---|---|
| Claude Code | `CLAUDE.md` |
| Codex, Cursor, Aider, Jules | `AGENTS.md` |
| GitHub Copilot | `.github/copilot-instructions.md` |

**`AGENTS.md` 를 원본으로 삼는다.** 도구 중립적인 이름이고 가장 널리 읽힌다.
`CLAUDE.md` 는 `@AGENTS.md` 한 줄로 그것을 가져오고, Copilot 쪽은 가리키기만
한다. 내용은 어디에도 복제하지 않는다.

**심볼릭 링크를 쓰지 않았다.** 팀에 Windows 환경이 있고, 그쪽에서 심볼릭 링크는
`core.symlinks` 설정과 개발자 모드에 걸린다. 체크아웃했을 때 링크가 아니라
경로 문자열이 담긴 텍스트 파일로 풀리면 규약이 통째로 사라진다.

import 가 동작하지 않는 경우를 대비해 `CLAUDE.md` 본문에 "이 문장이 보이면
`AGENTS.md` 를 직접 읽으라"고 적어두었다.

### 인덱스를 사람에게 맡기면 낡는다

D-021의 부분 읽기 전략은 **인덱스가 정확하다는 전제** 위에 있다.
그런데 결정을 추가하면서 인덱스를 빠뜨리면 그 전제가 조용히 깨진다.
다음 사람은 필요한 결정을 못 찾거나, 인덱스를 못 믿어서 전체를 다시 읽는다.

문서에 "인덱스도 같이 고치세요" 라고 적는 것으로는 지켜지지 않는다.
`scripts/check-docs-index.sh` 가 본문 제목과 인덱스 행을 대조하고,
`docs.yml` 이 PR 에서 그것을 돌린다.

**만들자마자 실제 누락을 잡았다.** D-021을 추가하면서 인덱스를 빠뜨린 것이
그대로 걸렸다. 규칙을 문서로 부탁하는 것과 CI 로 막는 것의 차이가 그것이다.

키워드 열은 검사하지 않는다. 사람이 판단할 영역이고, 그것까지 검사하려 들면
스크립트가 문서를 소유하게 된다.

---

## D-023. PR에서 `terraform plan` 을 돌리지 않는다

`tf.yml` 이 PR 마다 plan 을 돌려 결과를 코멘트로 붙이고 있었다. 그 목적은
"무엇이 바뀔지 보여준다" 였는데, D-005의 규칙과 앞뒤가 맞지 않았다.

**로컬에서 apply 까지 하고 올리므로, PR 시점의 plan 은 정상이라면 언제나
`No changes` 다.** "무엇이 바뀔지 미리 본다"는 목적은 apply 한 사람이 자기
plan 을 읽는 것으로 이미 달성된다. CI 가 사후에 같은 것을 다시 붙이면
아무도 읽지 않는 출력만 쌓인다. D-002 가 스스로 적어둔
"읽지 않는 plan 은 승인 게이트의 의미를 없앤다" 에 그대로 걸린다.

게다가 `-detailed-exitcode` 를 쓰지 않아 **변경이 있어도 초록불이었다.**
게이트도 아니었다.

### 게이트로 승격하지 않은 이유

`-detailed-exitcode` 로 "변경이 있으면 실패" 를 만들면 규칙이 강제된다.
그런데 그러면 **남이 만든 드리프트가 관계없는 PR 을 막는다.**

PR 은 코드가 바뀐 사건이고 드리프트는 시간이 흐른 사건이다. 둘을 묶으면
내가 고칠 수 없는 이유로 내 PR 이 서고, 그러면 사람들은 검사를 끄는 쪽으로
간다. D-014 에서 Trivy HIGH 를 차단하지 않기로 한 것과 같은 판단이다.
드리프트를 보고 싶으면 주기 실행으로 분리하는 것이 맞는 자리다.

### 부수 효과가 더 크다

plan 을 빼면 이 워크플로에 **AWS 접근이 아예 필요 없어진다.**

```
terraform fmt -check              자격증명 불필요
terraform init -backend=false     자격증명 불필요 (프로바이더만 받음)
terraform validate                자격증명 불필요
```

- `AWS_TF_ROLE_ARN` 시크릿과 그 IAM 역할이 필요 없어진다
- **이 저장소는 public 이다.** PR 을 열 수 있는 사람이 CI 에서 코드를 실행할
  수 있는 경로가 하나 줄어든다

D-011 은 "plan 은 임의 코드를 실행할 수 있다"는 이유로 권한을
`AdministratorAccess` 에서 `ReadOnlyAccess` 로 낮췄다. 이것은 그 방향의
끝이다 — 권한을 좁히는 대신 자격증명 자체를 없앤다.

### 덤으로 `04-platform` 이 검사 대상에 들어왔다

D-011 에서 이 스택을 CI 에서 뺀 이유는 plan 에 클러스터 접근이 필요해서였다.
plan 을 안 돌리니 그 이유가 사라졌다. 이제 여섯 스택 전부 `fmt` 와
`validate` 를 거친다.

---

## D-024. ESO 게이트를 Datadog 에서 분리한다

Datadog 을 나중에 뺄 계획이라 영향을 점검하다가 찾았다.
`enable_datadog = false` 로 두면 **API 파드가 기동조차 못 하는 상태**였다.

```
enable_datadog = false
  → helm_release.external_secrets 삭제        (ESO 컨트롤러 자체)
  → ExternalSecret CRD 삭제                   (Helm 소유임을 확인)
  → ExternalSecret CR 삭제
  → 그것이 소유한 Secret 삭제                 (ownerReferences, blockOwnerDeletion)
  → api 파드가 envFrom 대상을 못 찾음
  → CreateContainerConfigError
```

원인은 게이트 하나에 성격이 다른 둘이 묶여 있던 것이다. `enable_datadog` 이
지우는 12개 중 **Datadog 전용은 5개뿐**이고, 나머지는 시크릿을 쓰는 모든 것의
공용 기반이었다. `ClusterSecretStore` 의 리소스 이름이
`datadog_secret_store` 였던 것이 그 착시를 만들었다 — Datadog 이 첫 사용자였을
뿐 그 리소스는 클러스터 단위 공용이다.

`enable_external_secrets` 를 새로 만들어 ESO 계열을 옮겼다.
분리 후 `enable_datadog = false` 로 dry-run 하면 **4개만 삭제되고 전부
Datadog 전용**이다.

### 이름 변경을 `moved` 로 처리했다

`datadog_secret_store` → `aws_secret_store` 는 이름만 바뀐 것인데, 그냥
바꾸면 Terraform 이 삭제·재생성으로 본다. 그 사이 ExternalSecret 들이
참조를 잃는다.

```hcl
moved {
  from = kubectl_manifest.datadog_secret_store
  to   = kubectl_manifest.aws_secret_store
}
```

실제 plan 결과는 `0 to change, 0 to destroy` 였고, apply 후에도
ClusterSecretStore 의 나이가 그대로였다(재생성되지 않았다는 증거).

### 잘못 조합하면 plan 단계에서 막는다

`enable_app_data_wiring = true` + `enable_external_secrets = false` 는
apply 는 성공하고 **파드에서만 실패**한다. 그런 실패는 원인 추적이 오래 걸린다.
`terraform_data` 의 precondition 으로 plan 단계에서 멈추게 했다.

### 배운 것

**리소스 이름이 소유권을 암시한다.** `datadog_secret_store` 라는 이름 때문에
그것이 Datadog 의 일부처럼 보였고, 게이트가 그렇게 붙었다.
공용 리소스에 특정 사용자의 이름을 붙이면 나중에 그 사용자를 지울 때
공용 기반이 함께 끌려 나간다.

---

## D-025. MySQL 8.0 이 아니라 8.4 를 쓴다

D-017 에서 `03-data` 의 "지금 정할 것"을 고르며 엔진을 8.0 으로 잡았다.
근거는 설계 문서 4장이 InnoDB 버퍼 풀과 REPEATABLE READ 기준으로 쓰여
있다는 것이었다. 그 근거는 8.4 에서도 그대로 성립한다.

바꾸는 이유는 성능이 아니라 요금이다.

### 확인한 것

Cost Explorer 를 usage type 단위로 나눠 보니 RDS 하루 $6.15 의 내역이 이랬다.

```
5.473  APN2-ExtendedSupport:Yr1-Yr2:MySQL8.0
0.570  APN2-InstanceUsage:db.t4g.micro
0.080  APN2-RDS:GP3-Storage
```

MySQL 8.0 은 표준 지원이 끝나 vCPU 시간당 확장 지원 요금이 붙는다.
**인스턴스 요금 자체의 10배**이고, 계정 전체 지출(하루 약 $15)의 36% 였다.
`db.t4g.micro` 한 대에 월 $164 다.

이 요금은 **인스턴스를 정지해도 계속 붙는다.** 야간에 내리는 식으로는
줄지 않는다. 8.4 는 LTS 라 해당 요금이 없다.

### 파라미터 그룹 이름을 고정하지 않는다

`db_engine_version` 은 인스턴스의 `engine_version` 과 파라미터 그룹의
`family` 를 함께 움직인다. family 가 바뀌면 파라미터 그룹은 교체되는데,
`create_before_destroy = true` 는 옛 그룹이 살아 있는 동안 새 그룹을 만든다.
이름이 `o2-dev-mysql8` 로 고정이면 그 순간 이름이 충돌해 apply 가 깨진다.

`name` 대신 `name_prefix` 를 쓴다. 다음 메이저 버전에서 다시 걸리지 않는다.

### 되돌릴 수 없다

메이저 업그레이드에는 다운그레이드가 없다. `backup_retention_period = 1`
이라 자동 백업만으로는 얇아서, apply 전에 수동 스냅샷을 남긴다.

```bash
aws rds create-db-snapshot --region ap-northeast-2 \
  --db-instance-identifier o2-dev-mysql \
  --db-snapshot-identifier o2-dev-mysql-pre84
```

plan 결과는 `1 to add, 1 to change, 1 to destroy` 였다.
인스턴스는 in-place 업데이트고 재생성되지 않는다.

### 배운 것

**끄는 것보다 요금제를 보는 것이 먼저다.** 처음에는 "비싼 리소스를 야간에
내리자"로 접근했고, 그 방향의 절감은 하루 $1.5 였다. 실제 최대 항목은
리소스가 아니라 지원이 끝난 버전에 붙은 요금이었고, 한 줄로 하루 $5.5 였다.
서비스 단위 그래프만 보면 "RDS 가 비싸다"까지만 보인다. usage type 까지
쪼개야 원인이 나온다.

---

## D-026. APM 을 켠다. 소켓이 아니라 hostPort 로 받는다

Datadog 을 붙일 때 로그와 APM 을 명시적으로 껐다. 근거는 "이번 범위는 메트릭과
Kubernetes 이벤트" 였고, 데이터량과 과금 모델이 다르다는 것이었다. 그 판단은
관측 범위를 넓히는 일이 미뤄도 되는 일이라는 전제 위에 있었다.

그 전제가 틀렸다. 이 프로젝트의 목적은 서비스를 운영하는 것이 아니라 **장애를
만들고 AI 에이전트가 감별하게 하는 것**이다. 감별은 원인이 여럿인데 증상이
같을 때만 의미가 있고, 그것을 가르는 근거가 구간별 시간이다.

파드 지표로 볼 수 있는 것은 여기까지다.

    api 파드 CPU 80%

가를 수 없는 것.

    캐시가 비어 DB 로 몰렸나
    DB 커넥션이 고갈됐나
    Valkey 가 느려졌나

셋 다 "api 가 느리다" 로 보이고, 조치는 서로 다르다. 캐시 워밍 / 파드 축소 /
Valkey 확인. 에이전트에게 CPU 숫자만 주고 이 셋 중 하나를 고르라고 하면
그것은 감별이 아니라 추측이다.

무료 트라이얼 기간이라 지금 켜는 비용은 0 이다. 트라이얼이 끝나면 APM 은
호스트 단위 과금이라 노드 수에 비례한다 — 노드 3 대 규모에서는 로그(수집량
과금)보다 예측이 쉽다. 로그는 계속 끈다.

### 소켓이 아니라 hostPort

Helm 차트가 두 방식을 제공한다.

`socketEnabled` — 에이전트가 UDS 소켓을 노드에 만들고 애플리케이션 파드가
그것을 `hostPath` 로 마운트한다. 네트워크를 타지 않아 더 빠르다. 대신 매니페스트
셋 전부에 볼륨과 마운트를 넣어야 하고, 파드에 노드 파일시스템 접근 권한을 준다.

`portEnabled` — 에이전트가 hostPort 8126 을 연다. 애플리케이션은 `DD_AGENT_HOST`
하나만 알면 된다.

후자를 골랐다. 트레이스 전송량이 성능 문제가 되는 규모가 아니고, 매니페스트에
추가되는 것이 환경변수 한 개 대 볼륨 두 개다. 되돌리기도 쉽다.

`DD_AGENT_HOST` 는 `status.hostIP` 로 넣는다. **서비스 이름으로 부르면 안 된다.**
에이전트는 DaemonSet 이라 노드마다 하나씩 있는데, 서비스로 부르면 다른 노드의
에이전트에 갈 수 있다. 그러면 트레이스에 붙는 노드 태그가 실제로 실행된 노드와
달라져, "이 노드에서만 느리다" 같은 판단이 조용히 틀린다.

보안 그룹은 손댈 것이 없었다. EKS 클러스터 SG 에 자기 자신을 참조하는 전 포트
허용 규칙이 이미 있고, VPC CNI 파드가 노드 SG 를 쓰므로 파드 → 노드 8126 이
그 규칙에 들어간다. 확인 없이 넘기면 트레이스가 조용히 안 들어오는 쪽으로
실패한다 — 애플리케이션은 정상 기동하므로 알아채기 어렵다.

### 코드에 임포트하지 않는다

`ddtrace-run uvicorn ...` / `node --require dd-trace/init ...` 로 감싼다.
소스에 `import ddtrace` 를 넣지 않는 이유는, 넣으면 계측을 끄려 할 때 이미지를
다시 빌드해야 하기 때문이다. 지금 방식은 `DD_TRACE_ENABLED=false` 로 끝난다.

부하 테스트에서 계측 자체의 오버헤드를 재려면 이 스위치가 필요하다. 이미지가
같아야 비교가 성립한다.

### chat-gateway 에서 얻는 것은 제한적이다

WebSocket 은 HTTP 요청처럼 트레이스가 잡히지 않는다. 업그레이드 요청 한 번이
트레이스이고, 그 뒤 오가는 프레임은 트레이스 밖이다. 여기서 얻는 것은 Valkey
Pub/Sub 호출 시간과 런타임 지표다.

채팅 쪽 판단 근거는 결국 커스텀 지표여야 한다 — 연결 수, tick 당 드롭 수,
발화율. 그것은 무엇을 재야 하는지가 장애 시나리오로 확정된 뒤에 설계한다.
이름과 태그를 먼저 박으면 시나리오가 지표에 맞춰지는 역전이 일어난다.
