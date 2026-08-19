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
| D-027 | 이벤트를 Kinesis 로 보낸다 | `O2_EVENTS_SINK`, salt, `PutRecords`, chat-gateway 보류 |
| D-028 | Dify 는 EKS 밖에 둔다 (`06-agent`) | 블래스트 반경, SSM 터널, 포트 17080, IMDS 홉, Bedrock 프로필 |
| D-029 | 백데이터 파이프라인을 흡수한다 (`06-datastream`) | D-015 뒤집기, 코드만 이동, `No changes` |
| D-030 | 비밀값은 원본 하나, 읽기는 실행 시점에 | 사본 회전 사고, `` vs `None`, `DD_SITE` |
| D-031 | Function URL 을 에이전트 인그레스로 쓰지 않는다 | 403 `AccessDeniedException`, SCP/RCP 가설 |
| D-032 | `PENDING` 상품은 팔지 않는다 | `NOT_STARTED`, 정가 경로 없음, 화면 세 곳 일치 |
| D-033 | 영상 스택은 `07-media` 다 | 05 는 관측이 가져감, 충돌 표식 사고, 중복 번호 검사 |
| D-034 | `env` 태그는 한 값이어야 한다 | `DD_ENV` 하드코딩, APM↔지표 연결, 대시보드 기본 필터 |

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

---

## D-027. 이벤트를 Kinesis 로 보낸다

SDK 배선은 D-016 때 끝나 있었다. `apps/api` 와 `apps/order-worker` 는
`coupon.issue`·`order.create`·`inventory.check`·`order.cancel` 을 이미 발행한다.
빠져 있던 것은 목적지 하나다.

`O2_EVENTS_SINK` 의 기본값이 `stdout` 이라, 배선이 없는 동안 이벤트는 파드
로그로 나갔다. Datadog 로그 수집은 꺼져 있으므로(D-026) **어디에도 남지
않았다.** 로테이션과 함께 사라진 것이 전부다. 에이전트가 장애를 조사할 때 읽을
재료를 쌓는 것이 이 이벤트의 존재 이유인데, 쌓이는 곳이 없었다.

### 스트림은 만들지 않는다

`stream-business` / `stream-client` 는 백데이터 파트 소유이고 이미 ACTIVE 다.
우리는 생산자로서 쓰기 권한만 받는다. 이름이 SDK 기본값과 같아서
`O2_STREAM_*` 을 주입할 필요도 없다 — 주입하면 두 곳에 같은 사실이 생긴다.

### 권한은 두 스트림 모두에 준다

지금 우리가 내는 네 이벤트는 전부 `stream-business` 로 간다. 그런데도
`stream-client` 까지 주는 이유는 SDK 의 `sinks.py` 때문이다.

```python
def send(self, records):     # KinesisSink
    ...                      # 예외를 밖으로 던지지 않는다
```

`_stream_for()` 가 `client.*` / `live.*` 를 client 스트림으로 보내는데, sink 는
전송 예외를 삼킨다. 권한이 없으면 **이벤트가 사라진 줄도 모른 채 사라진다.**
나중에 `client.*` 를 하나 추가하는 순간 조용히 새는 구멍이 된다. 두 스트림
모두 우리는 생산자일 뿐이라 넓혀서 잃는 것도 없다.

### salt 는 Secrets Manager 에 둔다

SDK 는 `user_key` 를 그대로 싣지 않고 HMAC 으로 바꿔 담는다. 그 salt 를 세
서비스가 같은 값으로 봐야 같은 사용자로 조인된다. chat-gateway 는 Node 라
SDK 를 안 쓰지만 `events.ts` 의 `hashUserKey()` 가 같은 규칙을 구현하고 있어
**발행 스위치와 무관하게** 접속 시점에 이미 해싱한다. 그래서 세 파드 모두에
넣는다.

값이 바뀌면 같은 사용자가 다른 키로 보이고 과거 이벤트와의 조인이 끊긴다.
한 번 정하면 바꾸지 않는다.

ConfigMap 이 아니라 Secret 인 이유는, salt 가 새면 가명화된 `user_key` 를
역추적할 수 있기 때문이다. 경로는 Datadog 키와 같다 — 원본은 Secrets Manager,
ESO 가 동기화, Terraform 은 ARN 만 안다. **ESO 역할 정책에 그 ARN 을 같이
넣어야 한다.** 빠뜨리면 `SecretSyncedError` 로 Secret 이 안 생기고, 파드는
그것을 `envFrom` 하므로 `CreateContainerConfigError` 로 기동조차 못 한다.

### chat-gateway 의 Kinesis 경로는 안 만든다

`events.ts` 는 아직 stdout 하드코딩이다. 고치지 않는 이유는 `emitChatEvents`
스위치가 꺼져 있고, 켜는 조건이 우리 손에 없기 때문이다 — 모르는 `event_name`
이 들어갔을 때 수집단이 어떻게 처리하는지가 `contracts.md` 5.5 의 미확인
항목으로 남아 있다. 답이 오기 전에 경로를 만들면 쓰이지 않는 코드와 새 의존성
(`@aws-sdk/client-kinesis`)만 남는다. 답이 오면 그때 `emitChatSend()` 안쪽만
바꾼다.

### 적용 순서

Secret 이 없는 상태로 매니페스트가 먼저 동기화되면 파드가 기동하지 못한다.

```
1. Secrets Manager 에 o2/dev/events-salt 생성   (사람이 한 번)
2. infra/04-platform apply                      (ExternalSecret → Secret o2-events)
3. O2-live-deploy 푸시                          (Argo CD 가 envFrom 을 붙인다)
```

---

## D-028. Dify 는 EKS 밖에 둔다 (`06-agent`)

AI 에이전트 워크플로 오케스트레이션(Dify)을 클러스터 안이 아니라 같은 VPC
프라이빗 앱 서브넷의 EC2 한 대에 올린다.

### 왜 EKS 안이 아닌가

**첫째, 블래스트 반경.** 이 프로젝트의 본질은 EKS 에 의도적으로 장애를 주입하고
에이전트가 그것을 해결하는 것이다(`AGENTS.md` 첫 문단). 고치는 쪽이 부서지는 쪽
위에 살면 노드 장애 시나리오에서 에이전트도 같이 죽는다. 시연이 성립하지 않는다.
나머지 셋이 다 뒤집혀도 이 하나로 결정은 같다.

**둘째, 클러스터 사양.** 노드그룹은 `t3.small` × 2 (max 3) 다. Dify 셀프호스트는
컨테이너가 열다섯 개 뜨고 실사용 메모리가 8 GiB 다. EKS 에 넣으려면 어차피 전용
노드그룹을 새로 만들어야 하고, 그럴 바에는 EC2 한 대가 싸다.

**셋째, 운영 비용.** 배포 경로가 Argo CD GitOps(D-004, D-006)라 매니페스트 열다섯
개와 PVC, StatefulSet 을 직접 쓰고 유지해야 한다. Dify 공식 지원은 docker compose
이고 Helm 차트는 커뮤니티 관리다. `docker compose up -d` 한 줄과 바꿀 만한 것이 없다.

**넷째, DB 재사용 불가.** Dify 는 PostgreSQL 을 쓰는데 `03-data` 의 RDS 는 MySQL
8.4 다(D-025). compose 번들 postgres 를 그대로 쓴다.

**EKS 로 옮겨야 하는 시점** — Dify 가 시청자 트래픽 경로에 들어가 스케일링이
필요해질 때. 지금은 에이전트 운영 평면이라 해당 없다.

### 번호는 05 가 아니라 06 이다

`05` 는 `architecture.md` 10.3 에서 영상 스택으로 예약되어 있었다(D-01 교체로
생긴 것, 미작성). 같은 번호를 두 스택이 쓰면 apply 순서 문서가 깨진다.

> **D-033 정정.** 그 뒤 `05` 는 Datadog 대시보드 스택이 가져갔고 영상 스택은
> `07-media` 가 되었다. 이 절의 판단(빈 번호를 피한다)은 그대로 유효하다.

`tf.yml` 의 대상 스택 목록은 하드코딩이라 `06-agent` 를 거기 추가하지 않으면
**CI 가 새 스택을 조용히 건너뛴다.** 검사가 도는 줄 알고 깨진 코드를 올리게 된다.

### backend key 는 `dify/` 다

`agent/` 로 하지 않았다. AI 에이전트 백데이터 파트가 쓸 수 있는 이름이고, 키가
겹치면 서로의 리소스를 자기 것으로 인식해 지운다. D-015 에서 이미 한 번 겪었다.
이 스택이 소유하는 것은 Dify 호스트 하나뿐이므로 그대로 이름 짓는다.

### 접속은 SSM 포트 포워딩만 쓴다

퍼블릭 IP 도 ALB 도 붙이지 않는다. Dify 콘솔은 LLM API 키를 보관하고 sandbox
컨테이너로 임의 코드를 실행한다. 로그인 폼 하나를 믿고 인터넷에 내놓을 물건이
아니다. "개발할 때만 잠깐" 도 같다.

세션 설정(`SSM-SessionManagerRunShell`)은 이 스택이 관리한다. 유휴 60분,
최대 6시간이다. **유휴 상한 60분은 AWS 제한이라 더 못 올린다.** 6시간 연속 작업은
`tunnel.sh` 가 5분마다 트래픽을 흘려 유휴 상태를 만들지 않는 것으로 만든다.

이 문서는 **계정 전역**이다. EKS 노드 접속을 포함한 모든 세션에 적용되고,
이 스택을 destroy 하면 계정 기본값으로 돌아간다. 소유할 더 나은 스택이 생기면
`manage_session_preferences = false` 로 끄고 옮긴다.

### 겪은 함정

**로컬 포트는 17080 으로 고정한다.** Dify 는 브라우저에 socket.io 주소를
`NEXT_PUBLIC_SOCKET_URL` 그대로 내려준다. 기본값이 `ws://localhost` (포트 80)라,
8080 으로 터널을 열면 브라우저가 자기 기계의 80번으로 붙으러 가서 영원히 기다린다.
채팅플로우 편집 화면이 "데이터를 동기화할 수 있습니다"에서 멈추는 증상이다.

nginx 접근 로그에 `/socket.io/` 요청이 **한 건도 없는 것**이 이 증상의 판별법이다.
브라우저가 시도조차 하지 않은 것이라 서버를 아무리 봐도 정상으로 보인다.

값이 브라우저 번들에 박히므로 접속하는 사람 전원이 같은 로컬 포트를 써야 한다.
8080 은 다른 프로젝트와 겹치기 쉬워 17080 을 골랐다. `tunnel.sh` 와
`outputs.tf` 의 포트 포워딩 명령이 이 값을 쓴다.

**IMDS 홉 한계는 2 여야 한다.** Dify 는 docker 브리지 네트워크 안에서 돌고,
컨테이너에서 `169.254.169.254` 로 가는 패킷은 홉을 하나 더 쓴다. 1 이면 컨테이너가
인스턴스 역할을 못 받는다. **호스트에서 `aws` CLI 는 되는데 Dify 안에서만 Bedrock
이 실패하는** 형태라 원인이 잘 안 보인다.

**`http_put_response_hop_limit` 를 Terraform 이 관리하지 않으면 언젠가 1 로
돌아간다.** 현재 값이 우연히 2 라 `apply` 는 no-op 이지만 그래서 더 못 박아 둔다.

**포트 포워딩 파라미터는 JSON 대신 축약형을 쓴다.**
`--parameters portNumber=80,localPortNumber=17080` 이다. JSON 으로 쓰면 PowerShell
이 따옴표를 먹어 `Invalid parameters` 가 난다. 축약형은 macOS 와 PowerShell 에서
동일하게 동작해서 OS 분기 자체가 없어진다.

**`SECRET_KEY` 를 `set -x` 켜진 채로 만들지 않는다.** user_data 가 cloud-init 로그에
평문으로 남긴다. SSM 접근 권한이 있어야 읽히지만 로그에 남을 이유가 없는 값이다.

**`ssm-user` 는 부팅 시점에 없다.** 첫 SSM 세션에서 만들어지므로 user_data 의
`usermod -aG docker ssm-user` 는 조용히 실패한다. 세션에서는 `sudo docker compose`
로 쓴다.

### Bedrock 은 인스턴스 역할로 붙인다

액세스 키를 만들지 않는다. Dify 의 Bedrock 플러그인에 키 두 칸을 비우고 리전만
넣으면 boto3 가 IMDS 를 탄다.

서울 리전은 **inference profile 로만 호출된다.** 맨 모델 ID 는
`on-demand throughput isn't supported` 로 거절되고, 없는 프로필은
`The provided model identifier is invalid` 로 거절된다. 에러 문구가 다르므로
둘을 구분해서 읽는다.

Dify 는 리전에서 `apac.` 접두어를 유추해 붙인다. 그런데 Claude 4.5·5 계열은 이
계정에 `global.` 프로필만 있어서 존재하지 않는 ID 가 만들어진다. 검증한 조합은
`apac.amazon.nova-micro-v1:0` 와 `apac.anthropic.claude-3-5-sonnet-20241022-v2:0` 다.
테스트는 Nova Micro 로 한다 — 출력 100만 토큰에 $0.164 다.

### 아직 안 한 것

- **백업.** 데이터가 루트 볼륨에만 있다. 인스턴스를 교체하면 워크플로가 전멸한다.
  `lifecycle.ignore_changes = [ami, user_data]` 로 의도치 않은 교체는 막았지만
  백업은 아니다. 워크플로가 자산이 되면 별도 EBS 로 분리하고 DLM 을 건다
- **Datadog 계측.** EKS 밖이라 클러스터 에이전트가 안 잡는다
- **접속 IAM 정책.** 팀원용 정책이 문서에만 있고 코드에 없다. 사람 수가 정해지면
  `aws_iam_policy` 로 넣는다. 그 전까지는 콘솔에서 붙인 것과 코드가 어긋난다
- **HA.** 단일 인스턴스다. 에이전트 운영 평면이므로 서비스 SLA 대상이 아니다

---

## D-029. 백데이터 파이프라인을 흡수한다 (`06-datastream`)

D-015에서 "이 저장소의 관심사가 아니다. 흡수 대상도 아니다"라고 적었다.
**그 판단을 뒤집는다.** 코드를 `infra/06-datastream/` 으로 옮겼다.

### 왜 뒤집었나

D-015은 "다른 파트가 맡고 있으니 건드리지 않는다"는 **소유권** 판단이었다.
그 전제는 여전히 맞다 — 담당은 그대로다. 바뀐 것은 코드가 놓인 자리다.

이 저장소의 본질은 "장애를 만들고 그 위에서 AI 에이전트가 해결하는 것"이고,
에이전트가 판단에 쓰는 재료는 전부 이 파이프라인에서 나온다
(`o2-agent-context`, `o2-warm-api`). 즉 **진단 대상이 아니라 진단 도구**다.
도구가 저장소 밖에 있으면 세 가지가 깨진다.

- 계약이 갈라진다. 앱이 내보내는 이벤트와 집계기가 읽는 필드가 서로 다른
  저장소에서 각자 바뀐다. D-016이 막으려던 것이 정확히 이것이다
- 검사가 안 돈다. `tf.yml` 은 `infra/**` 만 본다. 밖에 있으면 fmt·validate가
  아무도 돌리지 않는 로컬 명령으로 남는다
- 재현이 안 된다. 인프라를 처음부터 세우는 사람이 `infra/` 를 다 apply해도
  에이전트가 눈을 뜨지 못한다

D-015의 진짜 결론은 "**state 키를 침범하지 않는다**" 하나였다. 그것은 그대로
지킨다. 코드 위치와 state 소유권은 별개다.

### 옮긴 것은 코드뿐이다

state도 리소스도 그대로 두었다. backend key는 여전히 `data/terraform.tfstate`
이고, `03-data` 는 `datastore/` 다. **이관 직후 첫 `plan` 은 `No changes` 여야
한다.** 이것이 이관이 성공했다는 유일한 증거다.

바꾼 것은 셋뿐이고 전부 Terraform 주소 밖이다.

| 바꾼 것 | state 영향 |
|---|---|
| 파일 이름 `01-s3.tf` → `s3.tf` (저장소 컨벤션) | 없음. 리소스 주소는 파일과 무관 |
| `backend.tf`+`providers.tf` → `versions.tf` | 없음. 같은 블록을 한 파일로 |
| 상대 경로 `../warm` → `./warm`, `../src/glue` → `./glue` | 없음. ZIP 내용이 같으면 해시도 같다 |

`warm/` 과 `glue/` 는 스택 폴더 **안에** 두었다. 스택이 자기 힘으로
plan/apply 되어야 한다는 원칙(D-002)이 여기서도 적용된다.

### 이름을 `03-data` 와 갈랐다

`data`라는 단어가 두 스택에 다 맞는 것이 D-015 사고의 출발점이었다.
같은 실수를 이름 단계에서 막는다.

| | `03-data` | `06-datastream` |
|---|---|---|
| 무엇 | 서비스가 읽고 쓰는 저장소 | 서비스를 **관찰한** 결과 |
| 죽으면 | 방송이 멈춘다 | 에이전트가 눈을 잃는다 |
| key | `datastore/` | `data/` |

`06` 인 것은 `05` 가 media로 예약되어 있어서다. 번호는 의존 순서이고
이 스택은 `02-eks` 뒤다 — `irsa.tf` 가 클러스터의 OIDC 프로바이더를 조회한다.

### 다른 스택과 일부러 다르게 둔 것

이관하면서 "통일"하고 싶은 자리가 셋 있었고, 셋 다 두었다.
**이미 apply된 리소스 30개를 흔들지 않는 것이 통일보다 우선이다.**

- aws provider `~> 5.0` (다른 스택은 `~> 6.0`)
- state 락은 `dynamodb_table` (다른 스택은 `use_lockfile`)
- `default_tags` 를 변수화하지 않음 — 바꾸면 30개 전부에 태그 diff

provider 상향은 6.0 upgrade guide를 보고 plan이 비는 것을 확인한 뒤
별도 PR로 한다. 이관과 섞으면 `No changes` 라는 검증 수단이 사라진다.

### 배운 것

**"우리 것이 아니다"와 "우리 저장소에 없다"는 다른 문장이다.** D-015는 앞을
근거로 뒤를 결론냈다. 소유권은 사람에게 있고 위치는 도구가 정한다.
어떤 코드가 이 저장소의 CI·계약·재현 경로 안에 있어야 하는가로 물었어야 했다.

---

## D-030. 비밀값은 원본 하나, 읽기는 실행 시점에

집계 Lambda 가 Datadog 키를 SSM 사본에서 읽게 하려다 멈췄다. **키는 이미
있었다** — `04-platform` 이 ESO 로 Agent 에 넣는 Secrets Manager
`o2/dev/datadog` 이 그것이다. 사본을 만들지 않고 같은 시크릿을 Lambda 가
직접 읽는다.

### 사본을 두면 회전이 사고가 된다

같은 키를 두 곳에 두는 것의 비용은 저장 공간이 아니라 **회전 절차**다.
Secrets Manager 만 바꾸고 SSM 사본을 잊으면 이렇게 된다.

| | 회전 후 |
|---|---|
| Datadog Agent (ESO 경유) | 정상 |
| 집계 Lambda | 403 |
| 겉으로 보이는 증상 | **비즈니스 지표만 조용히 멈춘다** |

`datadog.py` 가 전송 실패를 삼켜 집계를 막지 않기 때문에(의도된 설계, 부가
작업이 본류를 멈추면 안 된다) 알림도 예외도 없다. 인프라 지표는 멀쩡하니
대시보드를 봐도 절반은 살아 있다. **AGENTS.md 의 "어기면 조용히 깨지는 것"에
한 줄을 더할 뻔했고, 원본을 하나로 두는 쪽이 그 줄을 아예 없앤다.**

부수 효과가 하나 더 있다 — 이 경로에서는 **사람이 키를 만지지 않는다.**
복사·붙여넣기가 없으니 셸 히스토리·클립보드·채팅에 남을 자리가 없다.

### 값이 아니라 위치를 넘긴다

키를 Terraform 변수로 받으면 Lambda 환경변수가 되고, 그것은 **S3 remote
state 와 Lambda 콘솔에 평문으로 남는다.** state 버킷은 암호화·버저닝·퍼블릭
차단이 다 걸려 있지만, `s3:GetObject` 권한이 있는 주체는 그대로 읽는다.

그래서 Terraform 은 **이름만** 넘기고 값은 실행 시점에 읽는다.

| 비밀 | 원본 | 소비자 |
|---|---|---|
| Datadog `api-key` | Secrets Manager `o2/dev/datadog` | Agent(ESO) + `o2-agg` |
| 조회 API `X-O2-Key` | SSM SecureString `/o2/warm/api-key` | `o2-warm-api` |

`terraform.tfvars` 는 커밋되는 파일이고(루트 `.gitignore` 의
`!infra/*/terraform.tfvars`), 여기 들어가는 것이 이름뿐이라 그대로 커밋해도
된다. 값을 적는 경로(`warm_api_key`)는 남겨 두었지만 로컬 실험용이다.

### `""` 과 `None` 을 구분한다 — 이 결정의 핵심

`secrets.resolve()` 는 세 가지를 다른 값으로 돌려준다.

| 반환 | 뜻 |
|---|---|
| `""` | 출처가 지정되지 않았다 (미설정) |
| `None` | 출처는 있는데 읽지 못했다 (오류) |
| 값 | 성공 |

둘을 합치고 싶어지지만 **안전한 방향이 소비자마다 반대**라서 합칠 수 없다.

- Datadog 전송: 미설정이든 실패든 결과가 같다 — 안 보낸다
- 조회 API: 미설정이면 통과시키고(로컬·사설망 배려), **실패면 막아야 한다**

합쳐 두면 조회 실패가 "키 없음"으로 읽혀 **SSM 이 흔들리는 동안 인터넷에
열린 엔드포인트가 인증 없이 통과시킨다.** 즉 `o2-warm-api` 역할에서
`ssm:GetParameter` 를 빼면 엔드포인트가 열리는 것이 아니라 전부 401 이
된다. `tests/test_secrets.py::test_auth_closed_when_lookup_fails` 가 그
회귀를 막는다. **지우면 안 된다.**

### 같이 잡은 것 — `DD_SITE`

이 작업 중에 드러났다. 조직은 AP1 인데 `settings.py` 의 기본값은 US1
(`datadoghq.com`) 이고, `warm_env` 가 `DD_SITE` 를 주입하지 않았다.
키가 맞지 않는 사이트로 가면 403 이 나고 그것도 삼켜진다.

**틀려도 apply 는 성공하고 Lambda 도 정상으로 뜬다.** 증상은 "대시보드가
계속 빈다" 하나뿐이다. `04-platform` 의 `datadog_site` 와 같은 값이어야
한다는 제약을 `variables.tf` 설명에 적어 두었다.

### 검증

이벤트 60건을 `stream-business` 에 주입해 확인했다. 판정 근거는 `handler` 가
찍는 요약 JSON 의 `datadog_series` — 전송에 성공한 시계열 수다.

| 확인 | 값 |
|---|---|
| `datadog_series` | 24 (윈도우 2개) |
| DynamoDB `rps` | `coupon-api` 3 |
| Datadog `o2.warm.rps` (AP1) | 3.0 — **같은 값** |

같은 값이 양쪽에 있는 것이 설계 의도다. 계산은 Lambda 한 곳에서 하고
결과만 두 저장소로 보낸다.

### 배운 것

**"비밀값을 어디에 보관할까"를 묻기 전에 "이미 어디 있나"를 봐야 했다.**
새 저장소를 고르는 문제로 접근해서 사본을 만들려 했고, 실제 문제는
소비자를 원본에 연결하는 것이었다. 보관 위치를 늘리는 결정은 거의 항상
회전 절차를 늘리는 결정이다.

---

## D-031. Function URL 을 에이전트 인그레스로 쓰지 않는다

`o2-warm-api` 의 Function URL 이 **인터넷에서 모든 요청을 거부한다.**
Dify 가 이 경로로 붙는다는 전제(`README.md`, `handlers/serve.py`)가
성립하지 않는다. 대안을 정하기 전까지 Hot Path 연결을 진행하지 않는다.

### 사실

```
HTTP/1.1 403 Forbidden
x-amzn-ErrorType: AccessDeniedException
```

**CloudWatch 로그가 한 줄도 없다** — Lambda 가 호출되기 전에 막힌다.
함수 쪽 설정은 정상이다.

| 확인한 것 | 값 |
|---|---|
| `AuthType` | `NONE` |
| 리소스 정책 | `Principal: "*"`, `lambda:InvokeFunctionUrl`, 조건 일치 |
| Qualifier | 없음 |
| 외부 egress | 정상 (통제군 200) |

설정이 맞는데 거부되므로 거부는 이 계정의 Lambda 설정 밖에서 온다. 조직
차원의 SCP/RCP 가 Function URL 공개 접근을 막는 것으로 보이나,
`organizations:DescribeOrganization` 권한이 없어 확인하지 못했다.
**가설이며, 확인되면 이 절을 고친다.**

### 이 사실이 바꾸는 것

`X-O2-Key` 공유 시크릿 자체가 **Dify 가 SigV4 를 못 해서 쓰는 우회책**이다
(`handlers/serve.py` docstring). 그 우회책이 붙을 자리가 막혔으므로 선택지가
다시 열렸다.

| 대안 | 값 |
|---|---|
| 조직 정책을 푼다 | 가능하면 가장 싸다. 권한이 없어 확인 불가 |
| API Gateway | 인증·레이트리밋·로깅이 붙는다. 리소스가 늘고 과금된다 |
| ALB (기존 LBC 활용) | 이미 있는 인그레스를 쓴다. Lambda 타깃 그룹이 필요하다 |
| Function URL + IAM | Dify 가 SigV4 를 할 수 있으면 **보관할 키가 없어진다** |

마지막 것이 가장 깨끗하지만 Dify 쪽 제약을 확인해야 한다.

### 앞서 잘못 판단한 것

이 조사 전에 "환경변수가 비어 있으니 엔드포인트가 인증 없이 열려 있다"고
적었다. 코드상으로는 맞았지만 **실제 노출은 없었다** — AWS 가 앞에서
막고 있었다. 설정을 읽고 결론을 냈고 호출해 보지 않았다.

D-030 의 인증 수정은 그래도 유효하다. URL 이 열리는 순간 필요해지고,
그때 "열려 있었는지"를 다시 조사하고 싶지 않다.

### 배운 것

**"설정이 이렇다"와 "이렇게 동작한다"는 다른 문장이다.** 리소스 정책이
공개를 허용한다는 것은 공개되어 있다는 뜻이 아니다. 계정 밖의 정책 계층은
`describe` 로 안 보이고, 실제로 요청을 보내야만 드러난다.
**노출 여부는 설정이 아니라 요청으로 확인한다.**

---

## D-032. `PENDING` 상품은 팔지 않는다

화면은 "특가 오픈 예정" 이라고 말하는데 서버는 특가로 팔고 있었다.

`88216` 딥클렌징 오일은 `bc_1042`(LIVE) 편성이고 상태가 `PENDING` 이다.
어제 실제 주문에서 이렇게 팔렸다.

```
coupon.issue  {"coupon_id": "88216", "result": "SUCCESS", "remaining_qty": 43}
order.create  {"order_id": "od_01M09AYJ...", "total_amount": 13900}
```

정가는 26,000원이고 특가가 13,900원이다. **열리지도 않은 특가로 팔렸고 재고도
줄었다.** `contracts.md` 1.3 에 `NOT_STARTED / 409 / 특가 오픈 전` 이 정의돼
있었지만 서버에 그 검사가 없었다.

### 왜 정가 판매가 아니라 거부인가

실제 라이브커머스는 특가 전에도 정가로 파는 구성이 많다. 그쪽이 자연스럽다는
지적이 나왔고 타당하다. 그래도 거부를 택한다.

**이 시스템에는 정가 판매 경로가 없다.** 주문은 `sku_id` 와 `qty` 만 받고 금액은
서버가 `sale_price` 로 정한다. 정가로 팔려면 적용가를 주문에 남기고, 이벤트
payload 에도 넣고, 워커의 금액 계산도 바꿔야 한다. 가격 정책이라는 커머스
도메인 복잡도가 늘어나는데 **그것이 장애를 만들고 진단하는 데 기여하는 것이
없다** (`AGENTS.md` 의 판단 기준).

필요해지면 계약을 먼저 고치고 그때 넣는다. 지금은 계약에 이미 적혀 있던 것을
지키는 쪽이 논쟁 여지가 없다.

### 검사는 재고 차감보다 먼저

멱등키 등록이 재고 차감과 같은 Lua 스크립트 안에 있다. 상태 검사를 뒤에 두면
키가 먼저 등록되어, **특가가 열린 뒤 같은 키로 다시 시도해도 "이미 처리된 주문"
으로 막힌다.** 클라이언트는 상품별로 멱등키를 하나씩 들고 재시도한다
(`contracts.md` 1.2).

### 이벤트 `failure_code`

SDK 의 `COUPON_FAILURE` 열거에 `NOT_STARTED` 가 없다. 계약 밖 값을 넣으면
`SchemaError` 로 요청이 죽으므로 가장 가까운 `NOT_ELIGIBLE` 을 쓴다. 대응표는
`contracts.md` 5.2 에 적었다.

### 화면 세 곳을 함께 고쳤다

표시가 서로 달랐다. 홈 격자는 `PENDING` 을 `ON_SALE` 과 똑같이 그렸고, 상품
시트는 "특가 오픈 예정" 이라 쓰면서도 눌러 살 수 있었다.

| 위치 | 이전 | 이후 |
|---|---|---|
| 홈 격자 | 구분 없음 | "특가 오픈 예정" 배지 |
| 상품 시트 목록 | 문구만, 선택 가능 | 흐리게 + 선택 불가 |
| 구매 버튼 | "구매하기" | "특가 오픈 예정", 비활성 |

가격은 계속 보여준다. 숨기면 그 상품이 왜 목록에 있는지 알 수 없고, 곧 그
가격이 된다는 예고이기도 하다.

`SOLD_OUT` 도 같은 원칙으로 막는다. 다만 **수량(`stock_display`)으로는 막지
않는다.** 그 값은 최대 30초 지난 것이라 "3개 남음" 을 믿고 막으면 살 수 있는
것을 못 사게 된다. 판정은 여전히 `DECR` 결과가 한다.

---

## D-033. 영상 스택은 `05-media` 가 아니라 `07-media` 다

`architecture.md` 10.3 이 영상 스택을 `05-media` 로 예약했다. 그러나 코드가
쓰이기 전에 다른 스택들이 번호를 가져갔다.

```
05-datadog      Datadog 대시보드
06-agent        Dify 호스트        (D-028)
06-datastream   백데이터 파이프라인 (D-029)
07-media        영상               ← 남은 번호
```

**폴더도 state 도 없으므로 번호만 바꾸면 끝난다.** 마이그레이션이 없다.
`05-datadog`·`06-agent`·`06-datastream` 은 이미 apply 된 상태라 건드리지 않는다.
`06` 이 둘인 것도 그대로 둔다 — 이름이 다르고 backend key 도 달라 실제 충돌이
없으며, 번호를 다시 매기면 apply 된 스택의 문서·CI 목록·backend key 를 전부
따라 고쳐야 한다.

고친 곳은 `architecture.md`(Phase 표·구조도·스택 요약), `decisions.md` D-028,
`README.md`, `AGENTS.md` 의 apply 순서, `tf.yml` 의 대상 목록, `seed.py` 와
`LiveRoom.tsx` 의 주석이다.

### 함께 잡은 것 — 병합 충돌이 커밋돼 있었다

`decisions.md` 에 `=======` 와 `>>>>>>> main` 이 남은 채로 머지돼 있었다.
그 사이 130줄이 D-025(MySQL)와 D-026(APM)의 **중복본**이었고, 각각 D-029·D-030
번호를 달고 있었다. 그 결과 `D-030` 이 세 절에 붙어 있었다.

`check-docs-index.sh` 가 이것을 못 잡은 이유는 번호를 `sort -u` 로 비교하기
때문이다. **중복이 비교 전에 지워진다.** 인덱스와 본문의 집합은 여전히 같아서
검사가 통과했다.

그래서 검사를 셋 늘렸다.

```
같은 번호를 쓰는 절이 둘 이상인가     uniq -d
인덱스에 같은 번호가 두 번 있는가     uniq -d
병합 충돌 표식이 남아 있는가          ^<<<<<<< / ^=======$ / ^>>>>>>>
```

부분 읽기 전략은 **번호가 절을 유일하게 가리킨다는 전제** 위에 있다(D-021).
번호가 겹치면 `grep` 으로 고른 절과 실제로 읽는 절이 달라진다.

### 곁다리로 고친 인용 오류

`README.md` 가 `06-datastream` 의 근거를 D-025 로 적고 있었다. D-025 는 MySQL
8.4 다. `tf.yml` 의 주석도 media 예약을 D-025 로 인용하고 있었다.

---

## D-034. `env` 태그를 두 이름으로 쓰지 않는다

같은 요청이 Datadog 안에서 두 이름으로 갈려 있었다.

```
APM 트레이스   env:dev,  service:api     ← 파드가 DD_ENV=dev 로 뜬다
o2.warm.*      env:prod, service:api     ← 집계 Lambda 가 붙인 값
```

대시보드에서 실패율 스파이크를 보고 그 순간의 트레이스로 넘어가려면 Datadog 이
`env` 로 이어붙이는데, 이름이 달라 연결이 끊긴다. **apply 는 성공하고 화면만
조용히 안 이어진다.** 실제로 시간을 손으로 맞춰 트레이스를 찾았다.

원인은 `warm-path.tf` 의 하드코딩이었다.

```hcl
DD_ENV = "prod"   # → var.environment
```

`settings.py` 의 기본값도 `prod` 였다. 주입을 빠뜨리면 개발 데이터가 운영
이름으로 나가므로 `dev` 로 바꾼다. **기본값은 사고가 나도 덜 위험한 쪽이어야
한다.**

### 태그를 바꾸면 그래프가 갈린다

Datadog 은 태그가 다르면 다른 계열로 본다. `env:prod` 로 쌓인 그래프는 그
시점에서 끝나고 `env:dev` 로 새로 시작한다. 데이터가 지워지지는 않는다.

지금 `env:prod` 에 쌓인 것은 샘플 몇 점뿐이라 잃을 것이 없다. **진짜 운영 데이터가
쌓인 뒤에는 이 변경 비용이 훨씬 커진다** — 그래서 지금 고친다.

저장 계층은 영향이 없다. DynamoDB 키는 `service` 만 쓰고(`metric_pk`), `env` 는
Datadog 전송 시점에만 붙는 라벨이다. 베이스라인도 그대로다.

### 대시보드 기본 필터도 함께 고쳤다

`05-datadog` 의 기본값이 `service:coupon-api`, `env:prod` 였다. 그쪽 파트가 자기
샘플로 만든 값인데, 우리 서비스 이름은 `api`·`chat-gateway`·`order-worker` 다
(`contracts.md` 5.4). 열 때마다 손으로 바꿔야 했고, 안 바꾸면 빈 화면을 보고
파이프라인이 죽은 줄 안다.

### 다음에 같은 일이 나지 않게

`environment` 를 변수로 뺐다. 문자열이 박혀 있으면 진짜 prod 가 생길 때 또
고쳐야 하고, 그때는 어디에 박혀 있는지부터 찾아야 한다. 값은
**`04-platform` 의 `environment` 와 같아야 한다** — 변수 설명에 그 이유를 적었다.
