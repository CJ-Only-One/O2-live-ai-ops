# 결정 기록

구조를 정할 때 갈렸던 지점과 그 근거를 남긴다.
"왜 이렇게 했지"를 반년 뒤에 다시 묻지 않기 위한 문서다.

> **이 파일은 통째로 읽지 않는다.** 1,900줄, 약 29,000토큰이고 계속 자란다.
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
| D-035 | 승인 대기 중에는 상태를 바꾸지 않는다 | `SNAPSHOT#DETECT`, 감시 3등급, 만료시각 |
| D-036 | 클라이언트 이벤트 수집을 api 가 맡는다 | `stream-client` 첫 발행자, `click_ratio` 가 0 이던 이유, 대역/계약 시험 |
| D-037 | 스케일링 부품은 필요해질 때 넣는다 | metrics-server 는 Phase 4, KEDA·Prometheus·EBS CSI 재검토 |
| D-038 | 영상은 ALB 로 먼저 내보낸다 | MediaMTX, `paths` 누락, `?session=` 이 CDN 캐싱을 깬다 |
| D-039 | CloudFront 는 `/hls` 만 통과시킨다 | `07-media` 신설, 캐시 정책 둘, `hlsCDNSecret` 공유 |
| D-040 | 재생 복구는 회로 차단기로 묶는다 | 초당 50건 폭주, 조용한 영구 정지, 숨김 탭 정책 |
| D-041 | 큐시트로 미리 늘리되 AI가 스케일러가 되지는 않는다 | 큐시트, CapacityPlan, 결정론적 실행, HPA·KEDA 보정, Karpenter 안전망, Dify 제외 |
| D-042 | `o2-hot-api` 는 `AWS_IAM`(SigV4)이다 | D-031 후속, 멤버 계정은 SCP/RCP 조회 불가, `aws_lambda_permission`, Dify SigV4 미확인 |
| D-043 | Dify 는 SigV4 를 못 한다 — 서명을 프록시로 분리한다 | `ApiProviderAuthType`, `hot-proxy`, squid allowlist, `internal: true`, IMDS |
| D-044 | 인시던트 이력은 S3 Vectors 에 둔다 | 번들 weaviate 유실, DynamoDB 는 유사검색 불가, 임베딩 1회, 공유 zip, MTTR |
| D-045 | 검증 전에는 원인을 말하지 않는다 | `outcome.state` 다섯 값, 복구≠해결, 추측 세탁, 통제 어휘, Recovered 를 Worker 로 |
| D-046 | Runbook 조회도 D-043 과 같은 이유로 Lambda 릴레이를 쓴다 | `aws_iam_role.dify` 죽은 권한, SigV4, Function URL, x-api-key |
| D-047 | 채팅 분석은 Chat Gateway에서 SQS로 직접 분기한다 | Valkey 팬아웃 전용, Lambda, DynamoDB, 60초 원문, Incident Candidate |
| D-048 | Chat Signal Worker는 독립 `08-chat-signal` 스택에 둔다 | EKS 비결합, state 분리, 비활성 trigger, fail-safe skeleton |
| D-049 | Phase 4 Shadow는 생산자와 소비자를 독립 스위치로 제어한다 | enable_event_source, chat_signal_mode, 순차 활성화, 즉시 롤백 |
| D-050 | Agent 앞에서 source별 JSON을 공통 envelope로 정규화한다 | agent.trigger.v1, discriminator, custom_alert_json, idempotency, read-only |
| D-051 | Karpenter·KEDA 는 안전망이지 주력이 아니다 | D-037 조건 충족, NodePool 을 좁힌 이유, IAM 태그 조건, ScaledObject 는 배포 저장소 |

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
`o2/dev/datadog-new` 가 그것이다. 사본을 만들지 않고 같은 시크릿을 Lambda 가
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
| Datadog `api-key` | Secrets Manager `o2/dev/datadog-new` | Agent(ESO) + `o2-agg` |
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

## D-036. 클라이언트 이벤트 수집을 api 가 맡는다

`stream-client` 는 만들어진 뒤로 **한 건도 받은 적이 없었다.** ESM·Firehose·IAM
까지 전부 서 있는데 발행자가 없었다. `contracts.md` 5.1 은 `client.action` 의
발행 위치를 "frontend → 수집 엔드포인트"라고만 적었고, 그 엔드포인트는 어느
저장소에도 없었다.

없는 동안 잃고 있던 것은 지표 둘이다. `ua_diversity` 는 클라이언트 이벤트가
분모라 항상 null 이었고, `click_ratio` 는 — 아래에 적는다 — null 보다 나빴다.

### 브라우저가 Kinesis 에 직접 쓰지 않는다

자격증명이 번들에 들어간다. Cognito 자격증명 풀을 세우는 방법이 있으나, 그것은
"클릭 하나 때문에 인증 인프라를 하나 더 세우는" 일이다. api 는 이미 두 스트림에
대한 쓰기 권한을 갖고 있고(04-platform `app_events.tf`), SDK 가 `client.` 접두사를
보고 `stream-client` 로 보낸다. 새로 만들 것이 없다.

경로는 `POST /api/broadcasts/{broadcast_id}/events` 다. 방송을 경로에 둔 이유는
봉투 때문이다 — SDK 미들웨어는 BaseHTTPMiddleware 라 **라우팅 전에** 돌고, 그
시점에 `request.path_params` 는 비어 있다. 그래서 경로 문자열에서 뽑는다.
본문에 넣었다면 미들웨어가 볼 수 없어 봉투의 `broadcast_id` 가 계속 null 이었을
것이다. 실제로 지금까지 모든 이벤트가 그 상태였고, 세그먼트 축 하나가 죽어
있었다.

### 자유 문자열을 받지 않는다

이 엔드포인트는 인증 없이 인터넷에 열려 있고, 들어온 값은 에이전트가 읽는
DynamoDB 까지 간다. `chat.send` 에서 본문을 뺀 이유와 같다(architecture.md 8.5).
`action` 은 enum, `target_id` 는 `^[A-Za-z0-9_-]{1,64}$`, 배치는 20건까지.
`device_type` 과 `ua_key` 는 **서버가 채운다** — 클라이언트가 보낸 값을 실으면
세그먼트 축이 조작 가능해지고, "모바일만 실패한다" 같은 판단이 흔들린다.

`client_ts` 도 받지 않는다. 집계는 `received_ts` 로만 윈도우를 나누므로
(`o2warm/windows.py`) 쓰이지 않을 값을 신뢰 경계 밖에서 들여올 이유가 없다.

### 구매 버튼 한 번이 클릭 둘이다

집계의 짝은 (`COUPON_BUTTON_CLICK`, `coupon.issue`) 와
(`CHECKOUT_CLICK`, `order.create`) 둘이다(`o2warm/settings.py` `CLICK_PAIRS`).
우리는 특가와 주문이 한 요청이라 누름 하나가 서버 이벤트 둘을 만든다. 클릭을
하나만 내면 짝이 한쪽만 성립해 정상 트래픽의 비율이 0.5 로 눌리고, 그 0.5 가
새로운 "정상" 이 된다. 화면의 쿠폰 버튼은 서버를 부르지 않는 장식이라 쓰지
않는다 — 그것을 쓰면 요청 없는 클릭이 섞인다.

### `click_ratio` 는 null 이 아니라 0 이었다

배선을 붙이면서 알게 된 것이다. `O2_WARM_CLICK_ROUTE` 의 기본값은 클릭을
`coupon-api` / `order-api` 로 보내는데, 우리 봉투의 `service` 는 `api` 하나다
(contracts.md 5.4). 클릭과 요청이 다른 파티션으로 갈린다.

문제는 갈렸을 때의 **모양**이다. `api` 윈도우에는 요청만 남아
`click_ratio = 0.0` 이 된다. 그런데 0.0 은 이 지표에서 "버튼을 누르지 않고 API 만
두드리는 트래픽", 즉 매크로의 신호다. 실제로 DynamoDB 의 과거 윈도우는 주문이
있는 것마다 전부 `click_ratio: 0` 이었다 — 파이프라인이 에이전트에게 계속
"전량 매크로" 라고 말하고 있었다.

**조용한 null 보다 나쁘다.** null 은 모른다는 뜻이라 사람이 확인하러 가지만,
0.0 은 안다는 뜻이라 그대로 판단에 들어간다. `warm-path.tf` 에서 두 action 을
모두 `api` 로 보내고, `O2_WARM_CLIENT_SERVICE` 도 `api` 로 둔다 — 그래야
`LIVE_ENTER` / `LIVE_LEAVE` 가 서버 이벤트 없는 파티션을 따로 만들지 않고
`ua_diversity` 가 같은 윈도우에서 계산된다.

이 값은 06-datastream 을 apply 해야 반영된다. 코드 배포만으로는 클릭이 여전히
다른 파티션으로 간다.

### 시험을 둘로 나눈다

`o2events` 는 비공개 저장소라 CI 의 테스트 스텝에는 토큰이 없다. SDK 를 그대로
import 하면 시험이 항상 깨지고, 항상 깨진 시험은 아무도 안 본다.

- `apps/api/tests/conftest.py` 가 SDK 가 없으면 최소 대역을 넣는다. 이때
  검증되는 것은 우리 코드다 (경로·입력 검증·발행 인자)
- `apps/api/tests/test_sdk_contract.py` 는 SDK 가 있을 때만 돈다. enum 이
  계약과 같은지, `client.action` 이 정말 `stream-client` 로 가는지를 본다

둘 다 있어야 의미가 있다. 대역만 있으면 계약이 바뀌어도 초록이 뜬다.
이미지 안에서 한 번 돌리는 것이 확인 방법이다 —
`kubectl exec ... python -m pytest`.
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

---

## D-035. 승인 대기 중에는 상태를 바꾸지 않는다

초안에서 "컨펌 대기 중 병렬 작업 여섯 가지"로 잡았던 것을 **둘로 줄인다** —
상황 악화 감시, 명령셋 준비·dry-run. 나머지 넷은 대기 중이 아니라 다른
시점에 속한다.

### 왜 여섯이 아니라 둘인가

| 초안 항목 | 제자리 | 이유 |
|---|---|---|
| 임시 조치 | 승인 요청 전, 또는 안 함 | 되돌릴 수 있으면 승인이 필요 없으니 이미 끝나 있어야 하고, 필요하면 대기 중에 할 수 없다. 증상을 가려 승인자가 거부하게 만들고, PRE 기준선도 오염시킨다 |
| 가설 검증 | 승인 요청 전 | 컨펌 화면의 `근거`·`배제` 를 채우는 작업이다. 대기 중에 하면 승인한 근거와 실행 시점 근거가 달라진다 |
| 스냅샷 | 감지 직후 / 실행 직전 | 아래 참조 |
| 차선책 계산 | 컨펌 화면 안 | `[10%만]` 이 이미 차선책이다. 거부 후에 새 안을 내밀면 사람이 두 번 판단해야 한다. 방송 중에는 그럴 시간이 없다 |

여섯을 병렬로 돌리면 사람은 "에이전트가 이미 뭔가 하고 있다"로 읽는다.
그러면 승인이 형식이 된다. 대기 중에 남는 둘은 **시스템 상태를 바꾸지
않는다**는 공통점이 있고, 그것이 이 결정의 선이다.

부수 효과로 Step Functions 병렬 상태의 필요가 더 줄었다. 옮기지 않는다.

### 스냅샷을 `DETECT` 와 `PRE` 로 나눈다

`o2warm` 의 스냅샷 phase 에 `DETECT` 를 더한다
(`infra/06-datastream/warm/src/o2warm/store.py`).

| phase | 용도 | 남기는 것 |
|---|---|---|
| `DETECT` | 그때 에이전트가 본 것 — 사후 재현·라벨링 | 번들 전체 |
| `PRE` | 조치 효과의 기준선 | 지표만 |
| `POST` | 조치 후 상태 | 지표만 |

하나로 쓸 수 없는 이유가 양쪽에 있다.

- **PRE 를 감지 시점에 찍으면** 진단과 승인 대기 동안의 자기악화분이 조치
  효과에 섞인다. 커넥션 쏠림처럼 스스로 악화되는 장애에서 오염이 크다
- **DETECT 를 PRE 로 대신할 수 없다.** 지표 시계열은 TTL 7일이라 사후 조회가
  되지만 `confidence`·`gaps`·`rundown`·`policy` 는 조회 시점 기준으로 다시
  계산된다. 오판을 되짚을 때 필요한 것이 정확히 그 값들이다

`compare_snapshots` 는 `PRE`/`POST` 만 본다. `DETECT` 를 비교에 끼우면 대기 중
악화분까지 조치 성과로 잡힌다. `DETECT` 만 있는 인시던트는 409 그대로다.

### 상황 악화 감시

승인 대기가 몇 분이면 그동안 장애가 진행한다. 화면의 숫자가 낡으면 사람은
없는 상황을 보고 결정한다.

- 대상은 **컨펌 화면에 적힌 숫자만**. 카드에 없는 지표가 움직여도 승인 판단이
  바뀌지 않는다
- 주기는 **15초**. Warm Path 가 10초 윈도우 + 병합 지연으로 10~15초이므로
  더 자주 조회하면 같은 윈도우를 다시 읽는다
- **연속 두 윈도우가 같은 방향일 때만** 갱신한다. 숫자가 15초마다 오르내리면
  사람이 읽지 못한다

| 등급 | 조건 | 행동 |
|---|---|---|
| 숫자 갱신 | 파라미터 그대로, 수치만 변함 | 화면만 갱신. 승인 유효 |
| 재승인 | 조치 파라미터가 바뀜 (30% → 40%) | 기존 승인 무효화, 새 컨펌 |
| 철회 | 진단 근거가 무너짐 | 요청을 거두고 재진단 |

재승인 등급이 없으면 **2,460명을 승인했는데 3,300명이 끊긴다.**
승인은 판단이 아니라 파라미터에 걸린다.

`confidence.freshness` 가 떨어지면 감시가 눈이 먼 상태다. 낡은 숫자를 조용히
계속 보여주는 것이 가장 위험하므로 갱신을 멈추고 `감시 불가` 를 띄운다.
"계산할 수 없는 값은 0이 아니라 null" 과 같은 원칙이다.

### 만료는 3분 고정이 아니다

```
만료시각 = 포화 ETA − 실행 소요 − 안정화 대기(60초)
```

초안의 "3분 무응답"은 사람 기준으로 잡은 값이다. 실제 기한은 조치가 아직
의미를 갖는 마지막 시각이고, 그것은 장애마다 다르며 감시가 ETA 를 다시
계산할 때마다 움직인다. 만료되면 조용히 끝내지 말고 결과를 알린다.

### 배운 것

**승인 대기를 "노는 시간"으로 보면 거기에 일을 채우게 된다.** 그런데 그
시간에 에이전트가 하는 일이 늘어날수록, 사람이 승인하는 대상은 흐려진다.
대기 중에 필요한 것은 일이 아니라 **사람이 보는 숫자를 살아 있게 유지하는
것**이다.

---

## D-037. 스케일링 부품은 필요해질 때 넣는다

`architecture.md` 9.2 가 4계층 대응을 설계로 박아 두었다. 그대로 다 넣으면
파드가 10칸 넘게 든다. 지금 클러스터는 33칸 중 29칸을 쓰고 있어 **Phase 5 를
시작조차 못 하는 것으로 계산됐고**, 노드를 t3.medium 으로 올리는(월 +$39)
근거가 그것이었다.

하나씩 따져보니 그 계산이 틀렸다.

| 부품 | 무엇을 사는가 | 판단 |
|---|---|---|
| metrics-server | `metrics.k8s.io` — `kubectl top` 과 HPA 의 전제 | **Phase 4 에 넣는다.** 1칸 |
| KEDA | 시각·큐 길이로 미리 늘리기 | 데모면 `kubectl scale` 로 충분 |
| Prometheus | KEDA 의 커스텀 지표 공급 | **넣지 않는다.** Datadog 과 중복 |
| EBS CSI | PVC | Prometheus 를 안 넣으면 쓸 곳이 없다 |

### Prometheus 를 빼면 EBS CSI 도 빠진다

지금 PVC 를 쓰는 파드가 하나도 없다. MySQL·Valkey 는 클러스터 밖(RDS·
ElastiCache)이고, MediaMTX 는 HLS 를 메모리에 들고 있어 디스크를 안 쓴다.
EBS CSI 가 필요했던 유일한 이유가 Prometheus 였다.

그리고 우리는 지표를 이미 Datadog 으로 보낸다. 같은 값을 Prometheus 로 또
모으는 것은 중복이고, KEDA 는 Datadog 스케일러도 지원하므로 반응형이 정말
필요해지면 그쪽이 맞다.

**둘을 빼면 10칸이 아니라 1칸이다.** 노드 증설의 근거가 사라졌다.

### metrics-server 는 왜 남기나

Datadog 이 같은 값을 수집하지만 **읽는 쪽이 다르다.** Datadog 은 사람이
웹에서 보고, `metrics.k8s.io` 는 쿠버네티스 자신이 읽는다. 쿠버네티스는
Datadog 을 읽지 못하므로 HPA 를 만들어도 `unknown` 만 뜬다.

당장 아쉬운 것은 `kubectl top` 이다. 지금 노드 여유를 `describe nodes` 의
**요청량**으로만 보고 있는데, 그것은 예약한 양이지 실제로 쓰는 양이 아니다.
어느 노드가 메모리 96% 로 보여도 실사용은 훨씬 낮을 수 있고, 그 차이를 볼
수단이 없다. Phase 4 에서 "파드 하나가 몇 RPS 를 견디나" 를 잴 때 CPU 포화를
봐야 하므로 그 전에는 들어와야 한다.

설치는 `02-eks/addons.tf` 의 애드온 목록에 한 줄이다. 그 파일에 이미
"Phase 2에서 추가" 로 예고돼 있다.

### 지금 넣지 않는 이유

영상 스택(D-033)과 겹치지 않고, 넣어도 Phase 4 전까지 쓸 일이 없다.
**넣는 시점을 늦추는 것이 아니라 필요해지는 시점에 맞추는 것이다** —
지금 넣으면 쓰지도 않는 파드가 마지막 남은 칸을 하나 먹는다.

### KEDA 를 안 쓰기로 확정한 것은 아니다

`architecture.md` 9.1 의 근거는 그대로 유효하다 — 방송 시작 스파이크는 30초
안에 끝나서 반응형만으로는 구조적으로 못 따라간다. 다만 **방송 시각을 아는
데모**에서는 사람이 미리 `kubectl scale` 하는 것과 cron scaler 가 하는 일이
같다. Phase 6 에서 실제 스케일링 동작을 시연 대상으로 삼기로 하면 그때 넣는다.

`order-worker-deployment.yaml` 에 "KEDA 를 붙일 때는 replicas 필드를 제거해야
한다" 는 주석이 남아 있다. 그 전제는 아직 살아 있다.

---

## D-038. 영상은 ALB 로 먼저 내보내고 CloudFront 는 나중에 붙인다

`07-media`(D-033)의 첫 구현이다. MediaMTX 파드 하나가 RTMP 를 받아 HLS 로
내보내고, 기존 ALB 가 `/hls` 경로로 그것을 배포한다.

```
OBS → RTMP:1935 → NLB → MediaMTX → 2초 세그먼트 → ALB /hls → 브라우저
```

**Terraform 스택을 만들지 않았다.** CloudFront 를 미루면 들어갈 리소스가 없다.
NLB 는 Service 매니페스트의 애노테이션으로 AWS Load Balancer Controller 가
만든다. `04-platform` 이 만드는 것은 송출 비밀번호 Secret 하나뿐이다.

**ALB 도 새로 만들지 않았다.** `frontend-ingress.yaml` 에 `/hls` 규칙 한 줄을
더했다. 프론트와 같은 출처라 CORS 가 걸리지 않는다.

### 경로 접두사가 스트림 이름의 일부다

ALB 는 경로를 벗겨 넘기지 않는다(rewrite 가 없다). `/hls/bc_1042/index.m3u8`
가 그대로 MediaMTX 에 도착하므로 스트림 이름도 `hls/bc_1042` 여야 한다.

`live` 를 쓰면 프론트의 `/live/:broadcastId` 라우트와 겹쳐 SPA 가 뜨지 않는다.

### 붙이면서 밟은 것 셋

**`paths` 절이 없으면 어떤 경로도 허용되지 않는다.** `authInternalUsers` 로
권한만 열면 되는 줄 알았는데 MediaMTX 는 권한과 경로를 따로 본다. 송출이
NLB 를 지나 파드까지 닿고 인증도 통과한 뒤 `path 'hls/bc_1042' is not
configured` 로 끊겼다. 어디서 막혔는지는 로그를 `debug` 로 올려야 보였다.

**OBS 는 서버 주소 뒤에 스트림 키를 그대로 이어붙인다.** 서버에 쿼리스트링을
넣으면 키가 그 뒤로 붙어 비밀번호가 오염된다.

```
서버 rtmp://.../hls?user=publisher&pass=XXXX  +  키 bc_1042
  → rtmp://.../hls?user=publisher&pass=XXXX/bc_1042    ← 인증 실패
```

서버 주소에 경로까지 넣고 키를 비우거나, 키 쪽에 쿼리를 붙여야 한다.

**ALB 헬스체크가 영영 실패한다.** MediaMTX 는 `/` 에 404 를 준다. 송출이 없으면
200 을 주는 경로가 아예 없으므로 `success-codes: 200-404` 로 "살아 있으면
무엇이든 답한다" 를 기준으로 삼았다. 이 애노테이션은 **Ingress 가 아니라
Service 에** 둔다 — Ingress 에 두면 ALB 의 모든 대상 그룹에 적용되어
api·frontend 의 404 까지 정상으로 친다.

### ★ CloudFront 를 붙일 때 먼저 고칠 것

**MediaMTX 가 플레이리스트와 세그먼트 주소에 세션 ID 를 붙인다.**

```
main_stream.m3u8?session=bf3a69a2-74f9-4a6e-8264-1867f0d3b5db
5c56efa752c6_main_seg0.ts?session=ccc2814d-bce3-49fc-ba6f-de33d5b52f43
```

시청자마다 값이 다르다. CloudFront 는 기본적으로 쿼리스트링이 다르면 다른
객체로 보므로 **캐시가 전혀 먹지 않는다.** 시청자 수만큼 오리진을 치게 되고,
"세그먼트는 파일이라 오리진은 세그먼트당 1회만 맞는다"(`architecture.md` 2.2)는
전제가 통째로 무너진다. 파드 하나로 40,000 명을 감당한다는 계산이 여기 걸려 있다.

**apply 는 성공하고 재생도 된다.** 조용히 비싸지고 조용히 느려질 뿐이라 늦게
드러난다.

**MediaMTX 에 이 상황을 위한 설정이 따로 있다.**

```
hlsCDNSecret: ""   # CDN 에서 온 요청을 식별하는 비밀값.
                   # CDN 이 Authorization: Bearer 헤더로 넣어 보낸다.
```

이 값이 붙은 요청은 시청자별 세션이 아니라 **CDN 세션 하나로 묶인다**
(`internal/servers/hls/muxer.go` 의 `cdnSession`). 세션 ID 가 주소에 안 붙으므로
캐시 키가 시청자마다 갈리지 않는다.

CloudFront 쪽에서는 오리진 요청에 그 헤더를 추가하도록 설정한다.

**실제로 확인했다.** 돌고 있는 스트림에 설정을 넣고 헤더 유무로 비교했다.

```
헤더 없이     main_stream.m3u8?session=17286727-96be-4e3c-bea1-2a01e2977248
Bearer 붙임   main_stream.m3u8

세그먼트도 같다
헤더 없이     1560d55d3ca3_main_seg0.ts?session=3809a8e2-...
Bearer 붙임   1560d55d3ca3_main_seg0.ts
```

파일명이 콘텐츠 해시라 **같은 세그먼트는 항상 같은 주소가 된다.**
`.ts` 를 TTL 1년 immutable 로 두는 캐시 설계가 그제서야 성립한다.

> **정정.** 이 절을 처음 쓸 때 `hlsAlwaysRemux: true` 를 해법으로 적었으나
> 틀렸다. 그것은 읽는 사람이 없어도 먹서를 유지하는 설정이고 세션 ID 와
> 무관하다. 소스를 확인하고 고쳤다.

캐시 키에서 `session` 을 제외하는 방법도 있지만 택하지 않는다. CDN 쪽에 숨은
규칙을 하나 더 만드는 일이고, 나중에 "왜 캐시가 이상하지" 를 조사할 때
보이지 않는다.

지금은 시청자가 우리뿐이라 문제가 드러나지 않는다. **CloudFront 를 붙이는
작업의 첫 항목으로 둔다.**

---

## D-039. CloudFront 는 `/hls` 만 통과시킨다

D-038 에서 미뤄둔 CDN 을 붙인다. `infra/07-media` 가 이때 처음 생긴다 —
CloudFront 는 매니페스트로 만들 수 없어 Terraform 이 필요하다.

영상 스택의 나머지는 그대로 매니페스트가 소유한다 (D-033).

| 구성요소 | 만드는 곳 |
|---|---|
| MediaMTX 파드 · NLB · ALB `/hls` | `O2-live-deploy` 매니페스트 |
| 송출 비밀번호 · CDN 비밀값 | `04-platform` |
| CloudFront · 캐시 정책 | **`07-media`** |

### 프론트와 API 는 통과시키지 않는다

전부 CloudFront 뒤로 넣는 선택지도 있었다. 도메인이 하나로 통일되고
WebSocket 도 지원된다.

**캐시하면 안 되는 경로를 하나씩 예외 처리해야 한다는 것이 문제다.** 목록이
틀리면 API 응답이 캐시되어 **남의 주문 상태가 다른 사람에게 보인다.** 지금
필요한 것은 영상 팬아웃 흡수뿐이고, 그 이득이 이 위험을 감수할 만큼 크지 않다.

`/api`·`/ws`·`/` 는 지금처럼 ALB 로 직접 간다.

### 캐시 정책을 둘로 나눈다

플레이리스트와 세그먼트는 수명이 정반대다.

| 대상 | TTL | 근거 |
|---|---|---|
| `.m3u8` | 1~2초 | 2초마다 내용이 바뀐다. 세그먼트 길이보다 짧아야 재생이 안 끊긴다 |
| `.ts` | 1년 | 파일명이 콘텐츠 해시라 내용이 바뀌면 이름이 바뀐다. 무효화가 불필요하다 |

플레이리스트도 캐시를 아예 끄지는 않는다. 방송 시작 30초에 진입이 몰리는데
(설계 문서 3.8) 그때 오리진이 그대로 맞는다.

### 쿼리스트링을 캐시 키에서 뺀다

`hlsCDNSecret` 이 세션 ID 를 없애주지만, 캐시 정책에서도 한 번 더 막는다.
설정이 빠졌을 때 **조용히 비싸지는 것**보다 두 겹으로 막는 편이 낫다 (D-038).

### 비밀값은 한 곳에만 둔다

`o2/dev/media-cdn-secret` 하나를 두 스택이 읽는다.

```
07-media      CloudFront 오리진 커스텀 헤더 Authorization: Bearer <값>
04-platform   Secret o2-media 에 넣어 MediaMTX 에 MTX_HLSCDNSECRET 으로 주입
```

값을 양쪽에 적으면 한쪽만 회전했을 때 **재생은 되는데 캐시만 안 먹는 상태**가
된다. 그 상태는 화면상 정상이라 알아채기 어렵다.

**다만 `07-media` 는 이 값을 state 에 남긴다.** CloudFront 의 오리진 커스텀
헤더가 평문 문자열이라 다른 방법이 없다. 그래서 이 시크릿은 CDN 전용으로 두고
다른 용도와 공유하지 않는다.

### 엣지 범위는 좁게

`PriceClass_200` 이다. 시청자가 한국에 있으므로 전 세계 엣지로 넓혀도
빨라지지 않고 GB당 요금만 오른다.

### 적용 순서

```
1. Secrets Manager 에 o2/dev/media-cdn-secret 생성
2. 07-media apply            배포 생성에 10~15분
3. 04-platform apply         o2-media 에 MTX_HLSCDNSECRET 추가
4. 매니페스트 머지            MediaMTX 가 그 값을 읽음
5. hls_base_url 을 출력값으로 바꾸고 04-platform apply
6. api 재시작 + 시드          broadcasts.hls_url 갱신
```

5번 전까지는 CloudFront 가 서 있어도 아무도 그것을 통해 보지 않는다.
그래서 중간에 멈춰도 서비스가 깨지지 않는다.

## D-040. 재생 복구는 회로 차단기로 묶는다

플레이어가 요청 폭주를 냈다. 초당 50건, 정상의 100배다.

원인은 회복 판정이었다. `playing` 이벤트 하나로 실패 카운터를 0 으로
되돌렸는데, 붙었다 끊기기를 반복하는 상태에서는 백오프가 매번 초기화되어
사실상 무한 즉시 재시도가 된다. 그리고 "포기" 를 화면에 표시만 하고
hls.js 인스턴스를 죽이지 않아서, 포기한 뒤에도 요청이 계속 나갔다.

### 복구 로직을 컴포넌트에서 떼어냈다

`services/streamRecovery.ts` 는 시계·탐색·부착·해제를 주입받는 순수 상태
기계다. DOM 을 모르므로 가짜 시계로 **호출 횟수를 세어 검증할 수 있다.**
`.tsx` 안에 두면 Node 에 DOM 이 없어 검증이 막히고, 그러면 "폭주하지
않는다" 를 또 말로만 주장하게 된다. 상한을 숫자로 고정하는 것이 이
분리의 목적이다.

상태는 넷이고 상태마다 나가는 요청량이 정해진다.

```
idle        붙지 않음
attached    재생에 필요한 만큼
recovering  5초당 재부착 1회, 최대 12회
open        30초 ± 5초 지터당 탐색 1건
```

`12회` 는 **재부착 횟수**지 HTTP 요청 수가 아니다. 재부착 하나가
매니페스트·플레이리스트·세그먼트 요청 여러 건을 낸다.

### 폭주를 막으면 반대편으로 넘어간다

첫 수정은 폭주만 막았다. 그랬더니 **조용히 영영 멈추는** 경로가 생겼다.

`onStalled` 가 상태만 `recovering` 으로 바꾸고 아무것도 예약하지 않았다.
재부착을 거는 곳이 `onFatal` 뿐이었으므로, **fatal 이 오지 않는 정지**에서는
재부착도 탐색도 0 회다. m3u8 이 200 을 반환하면서 내용만 갱신을 멈추면
(송출이 끊겨도 muxer 가 마지막 플레이리스트를 붙들고 있는 동안) hls.js 는
오류로 보지 않는다. 화면에는 "다시 연결하는 중" 만 남는다 — 실제로는
아무것도 하지 않으면서.

빠져나갈 길도 없었다. 회로는 재부착 12회를 채워야 열리는데 재부착이 0회라
영영 안 열리고, 수동 재시도 버튼은 회로가 열려야 보인다.

그래서 정지 감시를 붙였다. 8초 넘게 멈춰 있으면 재부착을 예약한다.
`waiting` 은 **버퍼가 이미 마른 뒤에** 뜨므로, 이 값은 "버퍼가 다시 찰
시간" 이 아니라 "일시적 딸꾹질이 스스로 회복할 시간" 이다.

**폭주는 지표에 튀지만 영구 정지는 조용하다.** 요청이 0건이라 아무 알람도
울리지 않고, 시청자가 말해주기 전까지 모른다. 둘 다 막아야 끝난다.

### 숨겨진 탭에서는 복구하지 않는다

정상 재생은 그대로 두고 (탭을 내려놓고 소리만 듣는 사용을 깨지 않는다)
복구는 탭이 돌아온 뒤에 한다. 절충이 아니라 제약이다 — 브라우저가
백그라운드 탭의 타이머를 분 단위로 클램프하므로 숨김 중에 8초든 30초든
약속할 수 없다. 게다가 숨김 중 방송이 끊기면 지킬 오디오도 이미 없다.

숨김 상태에서 0 이 되는 것은 **재부착·탐색 예약**이지 요청 전체가 아니다.
재생 중인 플레이어의 세그먼트 요청은 계속 나간다.

### 함께 고친 것 둘

`liveSyncDurationCount` 를 기본값 3 으로 되돌렸다. 2 로 낮추면 지연이 줄지만
버퍼가 세그먼트 2개뿐이라, 6초 영상의 키프레임 때문에 세그먼트가 2초와 약
3.7초로 들쭉날쭉할 때 금방 마른다. 그 끊김이 재시도를 불렀다.

hls.js 내부 재시도도 상한을 명시했다 (`manifestLoadingMaxRetry: 2`,
`levelLoadingMaxRetry: 2`, `fragLoadingMaxRetry: 3`). 재부착은 컨트롤러가
관리하므로 여기서는 빨리 넘겨 총 요청량을 묶는다.

### 기각한 가설

"6초 영상이 6초마다 송출을 재접속시켜 폭주했다" 는 틀렸다. 폭주 시각에도
RTMP 연결 하나가 유지됐다 (같은 날 8분·60분·34분 연결). 6초 영상은 화면
내용만 반복될 뿐 HLS 타임라인은 이어진다. 세그먼트 길이를 불균일하게 만드는
간접 영향만 남는다.

### 검증 방식

가짜 시계로 시간을 돌려 호출 횟수를 센다. 60초에 오류 600회를 쏟아도
재부착은 12회 이하다. 정지 감시가 없으면 3건이 깨진다 — 감시가 실제로
일하고 있다는 뜻이다.

```bash
cd apps/frontend && npm test
```

## D-041. 큐시트로 미리 늘리되 AI가 스케일러가 되지는 않는다

라이브커머스의 쿠폰 오픈·상품 공개·방송 시작 스파이크는 발생 시각을 큐시트로
미리 안다. 반면 HPA 는 메트릭을 본 뒤 움직이고, 빈 노드가 없으면 노드 준비까지
기다려야 한다. `architecture.md` 9.1 의 계산처럼 스파이크가 끝난 뒤 용량이
도착할 수 있으므로 **큐시트 기반 사전 확장을 주력 경로로 쓴다.**

그렇다고 AI Agent 를 autoscaler 로 만들지는 않는다. LLM 이 replica 수를 자유롭게
생성하고 Kubernetes 나 AWS API 를 직접 호출하면 같은 입력에도 결과가 달라지고,
비용 상한·축소 안전 조건·재실행 멱등성을 보장하기 어렵다. 역할은 다음처럼 나눈다.

| 역할 | 하는 일 | 하지 않는 일 |
|---|---|---|
| AI Agent | 큐시트·과거 실측·현재 여유를 읽고 용량 계획을 제안하고 설명한다 | 임의의 replica/node 수를 직접 적용하지 않는다 |
| Capacity Planner | 실측한 파드당 안전 처리량과 정책으로 `CapacityPlan` 을 계산한다 | 측정하지 않은 처리량을 추정값으로 확정하지 않는다 |
| Validator | 시간·최소/최대·비용 상한·큐시트 신선도·권한 범위를 검사한다 | 범위를 벗어난 계획을 묵시적으로 통과시키지 않는다 |
| Executor | 검증된 계획을 멱등하게 실행하고 Ready/Healthy 를 확인한다 | API 호출 성공만 보고 확장이 끝났다고 판단하지 않는다 |

계산의 입력은 `docs/measurements.md` 의 실측값이어야 한다. 기본 모양은 아래와
같지만 `safe_capacity_per_pod` 와 여유율은 Phase 4 부하 테스트 전에는 값이 없다.

```
desired_pods = ceil(expected_peak / safe_capacity_per_pod * safety_factor)
```

큐시트의 자연어를 AI가 해석할 수는 있어도 Executor가 받는 것은 구조화된
`CapacityPlan` 뿐이다. 최소 필드는 `broadcast_id`, `event_id`, `starts_at`,
`expires_at`, 서비스별 목표 replica, 목표 node capacity, 근거가 된 측정 버전,
계획 버전이다. `event_id + plan_version` 을 멱등 키로 삼아 같은 일정이 다시
들어와도 중복 확장하지 않는다. 큐시트가 수정되면 옛 예약을 취소하고 새 버전으로
교체한다. 없거나 오래된 큐시트는 정상으로 간주하지 않고 baseline 용량을 유지하며
알린다(`06-datastream` 의 `gaps` 원칙과 같다).

### 실행 순서는 노드가 먼저다

```
1. 관리형 노드그룹 desired capacity 또는 예약 여유 노드를 먼저 확보
2. Node Ready 와 allocatable 여유 확인
3. 서비스 replica 사전 확장
4. Deployment Available 과 ALB healthy target 확인
5. 모두 만족한 뒤에만 사전 확장 완료로 기록
```

사전 실행 시각은 고정된 "10분 전"이 아니다. 노드·파드 준비 시간의 실측 p99와
안전 여유를 방송 이벤트 시각에서 빼서 정한다. 현재 문서의 시간은 설계 추정치라
운영 타이머의 근거로 쓰지 않는다. 노드 자동 확장이 아직 필요하지 않으면 D-037
대로 관리형 노드그룹과 수동/예약 실행으로 시작한다.

### HPA·KEDA·Karpenter 는 사전 확장의 대체재가 아니라 안전망이다

사용자 트래픽 경로의 HPA/KEDA 를 없애고 Dify 에만 붙이는 안은 택하지 않는다.
사전 계획이 정확해도 큐시트 누락, 실제 참여자 편차, 장애성 재시도, 방송 지연은
남는다. 역할은 다음과 같다.

| 계층 | 역할 |
|---|---|
| 큐시트 기반 사전 확장 | 알려진 이벤트의 첫 스파이크를 받을 주력 용량 |
| HPA/KEDA | 예상보다 크거나 오래 지속되는 부하를 보정. 첫 스파이크 해결책은 아님 |
| 예약 여유 노드 | Pod 가 즉시 스케줄되도록 노드 대기를 제거 |
| Karpenter | 예상 밖 Pending Pod·노드 장애에 대응하는 최후 안전망. 실측 필요 전에는 생략 가능 |

같은 Deployment 의 replica 소유자는 하나여야 한다. HPA/KEDA 또는 별도 Executor가
`scale` 을 소유하면 배포 매니페스트의 `replicas` 를 제거한다. 그렇지 않으면 Argo CD
`selfHeal` 이 사전 확장을 원래 값으로 되돌린다(D-004, `O2-live-deploy/AGENTS.md`).

### 축소는 큐시트 종료만으로 실행하지 않는다

확장은 비용 위험이고 축소는 가용성 위험이다. 자동 확장은 정책 범위 안에서
허용할 수 있지만, 축소는 다음 조건을 모두 확인하는 결정론적 단계로만 수행한다.

- 큐시트 이벤트가 종료됐고 새 버전에서 연장되지 않았다
- cooldown 동안 RPS·오류율·지연이 정상 범위에 있다
- SQS backlog 와 진행 중 주문/워크플로가 없다
- WebSocket 활성 연결이 축소 후 용량 이하고 graceful drain 이 가능하다

순서는 `신규 연결 차단 → Pod graceful drain → Pod 점진 축소 → 재검증 → Node 축소`다.
chat-gateway 는 9.4와 `contracts.md` 3.6의 종료·지터 재연결 계약을 지킨다. AI는
축소를 제안할 수 있지만 이 조건을 우회할 수 없다.

### Dify 는 이 스케일링 경로의 예외다

Dify 는 D-028 대로 EKS 밖 EC2에 두므로 HPA 대상이 아니다. 현재는 Lambda 비동기
대기열과 Worker 예약 동시성으로 유입을 제한하고, 먼저 Dify 동시 처리량을 측정한다.
HPA를 붙이기 위해 Dify를 대상 EKS로 옮기면 장애 대응기가 장애 대상과 같은 실패
도메인에 들어가는 비용이 더 크다.

나중에 다른 장애 도메인의 Kubernetes 로 옮길 이유가 생기더라도 전부를 한 HPA로
늘리지 않는다. 무상태 API는 요청량 기반 HPA 후보이고, workflow/Celery worker는
CPU보다 queue backlog 기반 KEDA 후보이다. PostgreSQL·Redis·vector store는 먼저
외부화해야 하며 HPA 대상이 아니다.

---

## D-042. `o2-hot-api` 는 `AWS_IAM`(SigV4)이다 — 이 계정에서는 조직 정책을 완화할 수 없다

D-031 이 남긴 미해결 질문("Function URL 인그레스를 어떻게 열 것인가")에 대한
답이다. Hot Path(`o2-hot-api`, Datadog 역쿼리) 구현 중 같은 문제를 다시 만났고,
이번에는 "완화가 가능한지" 자체를 실제로 확인했다.

### 확인한 것

```
IAM 유저(KDH) → 그룹 Only_One → AdministratorAccess(계정 내 전체 권한)

aws organizations describe-organization         → AccessDeniedException
aws organizations list-policies --filter SERVICE_CONTROL_POLICY   → AccessDeniedException
aws organizations list-policies --filter RESOURCE_CONTROL_POLICY  → AccessDeniedException
```

계정 내 IAM 권한이 이미 최대치(`AdministratorAccess`)인데도 막힌다. 이건 IAM
권한 문제가 아니다 — `organizations:DescribeOrganization`/`ListPolicies` 같은
Organizations API는 **멤버 계정에서는 어떤 IAM 정책을 줘도 호출할 수 없고**,
조직의 관리(management) 계정이나 위임된 관리자만 호출할 수 있다. 이 계정
(`066107819912`)은 멤버 계정이므로, SCP/RCP를 보거나 고칠 방법이 이 계정 어떤
유저에게도 없다. D-031의 "가설"이 여기서 "확인된 구조적 제약"으로 바뀐다.

### 그래서 고른 것

D-031이 대안으로 적어 둔 넷 중 "가장 깨끗하다"고 짚었던 것 — Function URL
인증을 `NONE`(+ 공유 시크릿) 대신 **`AWS_IAM`으로 바꾼다.**

```
authorization_type = "AWS_IAM"

aws_lambda_permission {
  action                  = "lambda:InvokeFunctionUrl"
  principal                = "<호출을 허용할 IAM 역할 ARN>"
  function_url_auth_type  = "AWS_IAM"
}
```

익명(`Principal: "*"`) 리소스가 아니므로 D-031이 관찰한 차단 패턴(공개
Function URL에 대한 조직 정책)에 해당하지 않을 가능성이 높다. 그리고 무엇보다
**공유 키가 사라진다** — `X-O2-Key`는 애초에 "Dify가 SigV4를 못 하니 대신 쓰는
우회책"이었으므로(`o2warm/handlers/serve.py` docstring), SigV4가 되면 그 우회책
자체가 필요 없어진다. `o2hot/secrets.py`에 조회 API용 키 저장·조회 로직이
없는 이유가 이것이다 — `o2-warm-api`와 달리 인증을 코드가 하지 않는다.

기본 허용 principal은 Dify EC2 인스턴스 역할
(`arn:aws:iam::066107819912:role/o2-dev-dify-role`, `infra/06-agent/iam.tf`의
`aws_iam_role.dify`)이다. 06-agent를 remote state로 참조하지 않는다 —
`irsa.tf`가 클러스터를 이름으로 직접 조회하는 것과 같은 이유로, 여기서는
실측한 ARN 값을 변수 기본값으로 못 박았다. 그 역할 이름이 바뀌면 이 기본값도
함께 고쳐야 한다.

### 확인한 결과 — 경로는 열렸다

**가설이 맞았다.** `AWS_IAM` Function URL 은 이 계정에서 정상 동작한다.
D-031 이 `NONE` 에서 본 조직 차원의 403 이 여기서는 나오지 않는다.

| 테스트 | 결과 |
|---|---|
| 서명 없는 요청 | 403 (의도대로 차단) |
| 인터넷에서 SigV4 서명 | 200 |
| **Dify EC2 (`o2-dev-dify-role`) 에서 SigV4 서명** | **200** |
| `POST /v1/hot/datadog/query` 실제 역쿼리 | 200, 시계열 반환 (`by {pod_name}` 은 28 계열) |

호출자 ARN 은 함수 로그에 남는다
(`caller=arn:aws:sts::…:assumed-role/o2-dev-dify-role/i-…`).

여기까지 오는 데 **액션이 하나 더 필요하다는 것**이 걸림돌이었다.
`lambda:InvokeFunctionUrl` 만으로는 403 이고 `lambda:InvokeFunction` 도
함께 줘야 한다. 증상이 D-031 과 똑같아서 조직 정책으로 오해하기 쉽다 —
가려내는 방법과 시뮬레이터의 함정은 **T-014** 에 적었다.

### 아직 확인 못 한 것

여기서 검증한 것은 **호출 경로**이지 Dify 제품 기능이 아니다. Dify 의
Custom Tool(OpenAPI 3.0)이 SigV4 서명을 스스로 할 수 있는지는 아직
확인하지 않았다 — 위 200 은 EC2 에서 인스턴스 역할로 직접 서명해 얻은
것이다. Dify UI 가 SigV4 를 지원하지 않으면 같은 인스턴스에서 로컬로
서명해 중계하는 얇은 프록시가 필요하다. 자격증명은 이미 그 인스턴스에
있으므로(위 200 이 그 증거) 남은 것은 Dify 쪽 설정뿐이다.

### 배운 것

D-031의 "노출 여부는 설정이 아니라 요청으로 확인한다"는 여기서 한 겹 더
간다 — **"이 정책을 우리가 고칠 수 있는가"도 설정을 읽어서가 아니라 그
API를 실제로 불러서 확인해야 한다.** `AdministratorAccess`라는 IAM 정책
이름만 보고 "권한이 있다"고 판단했다면 이 조사는 여기서 끝나지 않았을
것이다.

---

## D-043. Dify 는 SigV4 를 못 한다 — 서명을 프록시로 분리한다

D-042 로 `o2-hot-api` 의 Function URL 을 `AWS_IAM` 으로 열었다. 남은 질문은
"그래서 Dify 가 그걸 부를 수 있는가" 였고, **못 부른다.**

### 사실

실행 중인 버전(1.16.1)의 소스를 직접 봤다. 문서가 아니라 컨테이너 안이다.

```python
# core/tools/entities/tool_entities.py:116
class ApiProviderAuthType(StrEnum):
    NONE = auto()
    API_KEY_HEADER = auto()
    API_KEY_QUERY = auto()
```

Custom Tool 이 쓸 수 있는 인증은 이 셋뿐이고, 툴 코드 전체에 `sigv4`·`aws4`·
`botocore.auth` 는 한 건도 없다. **UI 설정으로 풀 수 있는 문제가 아니다.**

### 그래서 무엇을 했나

같은 인스턴스에 작은 중계기(`06-agent/hot-proxy/`)를 둔다. Dify 는 평범한
HTTP 로 그것을 부르고, 서명은 중계기가 인스턴스 역할로 한다.

```
Dify api ──▶ ssrf_proxy(squid) ──▶ hot-proxy ──SigV4──▶ o2-hot-api
```

API Gateway + API 키로 가는 길도 있었다(D-031 의 대안 표). 그쪽은 Dify 가
네이티브로 붙지만 리소스와 과금이 늘고 인터넷 노출면이 하나 더 생긴다.
개인 계정이라 비용 쪽을 택했다.

**중계기가 키를 갖지 않는다.** IMDS 에서 임시 자격증명을 받고, boto3 가
갱신을 맡는다. 손으로 서명하면 이 갱신을 직접 해야 하는데, 만료는 한참
뒤에 403 으로만 드러나서 원인을 찾기 어렵다.

### 이 경로에서 걸린 것 둘

둘 다 **Dify 에서만 실패하고 직접 부르면 되는** 모양이라 원인이 잘 안 보인다.

`ssrf_proxy_network` 는 `internal: true` 다. 중계기를 거기만 붙이면 IMDS 에
못 닿아 자격증명을 못 받고 재시작을 반복한다. `default` 도 함께 붙여야 한다 —
Dify 의 api·worker 가 이미 그 모양인 데는 이유가 있었다.

Dify 의 툴 호출은 전부 squid 를 거치고(`core/tools/custom_tool/tool.py` 가
`ssrf_proxy.get/post` 를 쓴다), squid 는 사설 대역을 기본 차단한다. 다만
`deny to_private_networks` **앞에** `include dify_allow_private.conf` 가 있고
`SSRF_PROXY_ALLOW_PRIVATE_DOMAINS` 로 채워진다. 확장 지점이 이미 있었다.

### 확인한 것

squid 를 경유하는 실제 경로로 쟀다 — Dify 가 가는 길과 같다.

| 확인 | 결과 |
|---|---|
| api 컨테이너 → 중계기 (직접) | 200, Datadog 시계열 |
| **api 컨테이너 → squid → 중계기** | **200** |
| `/v1/hot/` 밖 경로 | 403 `forbidden_path` |
| 왕복 시간 | **0.6초** (툴 타임아웃 5초) |

### 남은 것

Dify 스튜디오에서 Custom Tool 을 만들어 워크플로에 넣는 일은 **화면에서**
한다. 붙여넣을 스키마는 `06-agent/hot-proxy/openapi.yaml` 에 있다.

### 배운 것

**제품이 무엇을 지원하는지는 문서가 아니라 그 버전의 코드에서 확인한다.**
"Dify 가 SigV4 를 지원하는가" 는 검색으로는 확실해지지 않았다 —
버전마다 다르고, 플러그인·Bedrock 노드 같은 다른 통합과 섞여 나온다.
돌고 있는 컨테이너에서 enum 하나를 읽는 편이 빠르고 정확했다.

---

## D-044. 인시던트 이력은 S3 Vectors 에 둔다

에이전트가 알림을 분석하고 나면 그 판단이 **어디에도 남지 않았다.**
`lambda/worker.py` 가 Dify 결과를 받고 `return {"ok": True}` 로 끝나 CloudWatch
로그에만 있었다. "이미 해결한 인시던트와 비슷한가" 를 판정하려면 쌓아야 한다.

### 후보 셋

| 후보 | 왜 아닌가 / 왜인가 |
|---|---|
| DynamoDB | **유사도 검색이 없다.** "키가 정확히 이것" 은 되지만 "비슷한 것" 을 못 찾는다. 스캔해서 애플리케이션에서 코사인을 도는 것은 저장소를 잘못 고른 것이다 |
| Dify 번들 weaviate | 이미 EC2 에서 돌고 있어 **신규 인프라가 0** 이다. 그런데 루트 볼륨에만 있고 `delete_on_termination = true` 다 — D-028 의 "인스턴스 교체 = 워크플로 전멸" 이 그대로 적용된다 |
| **S3 Vectors** | **채택.** EC2 밖이라 인스턴스 유실과 무관하다. 2025년 12월 GA, 서울 리전 가능, aws provider 6.x 에 리소스가 있다 |

번들 weaviate 도 S3 에 원본을 두면 재색인으로 복구할 수 있다. 다만 그 복구
절차를 사람이 기억하고 있어야 하고, **잊혀진 복구 절차는 없는 것과 같다.**
회의에서 EC2 유실 대비를 이유로 S3 Vectors 로 정했다.

이 규모(월 약 5,000건)에서 OpenSearch 는 월 수십 달러, S3 Vectors 는 월 1달러
미만이다. 벡터 저장소를 세우는 문턱 자체가 낮아진 것이 선택을 갈랐다.

### 검색을 Dify 가 아니라 Lambda 에서 한다

Dify 에는 S3 Vectors 커넥터가 없다. 붙이려면 임베딩·검색 Lambda 를 만들어
External Knowledge API 규격으로 노출해야 한다 — 부품이 둘 는다.

그런데 검색을 **Worker Lambda 안에서** 끝내면 그 둘이 전부 사라진다.

```
알림 → 임베딩(Bedrock) → S3 Vectors 검색 → past_cases 로 Dify 실행 → 저장
```

Dify 쪽 변경은 시작 노드에 텍스트 변수 하나(`past_cases`)를 늘리는 것뿐이고,
**Dify 는 벡터의 존재를 모른다.** 지식 검색 노드도 외부 지식 API 도 없다.
커넥터가 없다는 제약이 오히려 부품을 줄였다.

### 임베딩은 알림당 한 번

검색용 벡터와 저장용 벡터를 같은 것으로 쓴다. Dify 의 판단문을 저장 쪽에만
합쳐서 임베딩하고 싶어지는데, 하면 안 된다 — 검색은 "들어온 알림" 대 "과거
알림" 비교이고, 한쪽에만 판단문이 붙으면 두 텍스트의 성격이 달라져 유사도가
흐려진다. 판단 결과는 메타데이터와 S3 원본에만 넣는다.

정확도를 위한 선택인데 호출 수와 코드가 같이 절반이 됐다.

### 거리 임계값은 눈금이지 상수가 아니다

`MAX_DISTANCE = 0.35` 는 근거 있는 값이 아니다. 느슨하면 상관없는 사례가
프롬프트에 들어가 LLM 이 거기 끌려가고(`architecture.md` 7.4 "오판의 재학습"),
빡빡하면 재발을 놓친다. **놓치는 쪽이 잘못 엮는 쪽보다 싸므로** 보수적으로
시작하고, 실제 알림으로 재서 맞춘다.

같은 이유로 `human_verified` 필터는 지금 걸지 않는다. 검증 표시를 아무도 안
한 상태에서 걸면 결과가 늘 0건이고, **기능이 죽은 것을 눈치채기 어렵다.**
그때까지의 방어선은 프롬프트의 "과거 사례는 참고이지 정답이 아니다" 한 줄이다.

### 이력 기록은 두 파이프라인 중 하나에서만 켠다

`lambda_o2.tf` 의 두 번째 파이프라인이 **같은 zip 을 공유한다.** 그래서
이력 관련 환경변수를 `os.environ["..."]` 로 읽으면 그쪽이 import 에서
KeyError 로 죽는다 — 알림 경로 하나가 통째로 사라지는 사고다. `.get()` 으로
읽고, 변수가 없으면 이력만 꺼진 채 중계는 돈다.

O2 쪽을 켤 때 **환경변수만 복사해 붙이면 안 된다.** 두 파이프라인이 같은
Datadog 모니터를 받으면 `cycle_key` 가 같아서 서로의 인시던트를 덮어쓴다.
키에 파이프라인 구분을 먼저 넣는다.

### 실패해도 알림을 잃지 않는다

이력은 **보조 기능이다.** 두 지점 모두 예외를 밖으로 내보내지 않는다.

| 어디 | 실패하면 | 왜 |
|---|---|---|
| 검색 (Dify 호출 전) | `past_cases` 만 비우고 진행 | 과거 사례 하나 때문에 알림 분석 전체를 잃는 것은 손해다 |
| 저장 (Dify 호출 후) | 로그만 남기고 성공 반환 | 여기서 예외를 던지면 이미 성공한 Dify 를 재시도가 다시 부른다. LLM 비용이 두 배가 되고 인시던트가 중복된다 |
| 복구 시각 기록 (Ingress) | 로그만 남기고 200 | 200 을 못 주면 Datadog 이 알림을 재전송한다. **지표 결손이 알림 파이프라인 교란보다 싸다** |

`worker.py` 상단의 "실패는 반드시 예외로 알려야 한다" 는 **Dify 호출에만**
해당한다. 그 문장을 이력 코드에 확대 적용하면 위 표가 전부 뒤집힌다.

### MTTR 이 여기서 나온다

Datadog 은 한 장애에 `Triggered` 와 `Recovered` 를 두 번 보내고 `cycle_key` 가
둘을 묶는다. 기존 `ingress.py` 는 `Recovered` 를 즉시 버렸는데 — **분석이
필요 없는 것과 시각이 필요 없는 것은 다르다.** 시각만 `resolutions/` 에
남긴다. 두 파일의 차가 MTTR 이고, 에이전트 도입 전후 비교가 이 프로젝트의
평가 지표다.

### 남은 것

- `outcome.resolved` · `mttr_sec` · `root_cause_label` 이 비어 있다.
  `incidents/` 와 `resolutions/` 를 짝짓는 재색인 스크립트가 한 번에 채운다
- Athena. 원본이 `dt=` 로 파티션되어 있어 Glue 테이블만 얹으면 되지만
  건수가 적어 아직 필요 없다

---

## D-045. 검증 전에는 원인을 말하지 않는다

D-044 로 이력은 쌓이는데 `outcome` 이 통째로 비어 있었다. 알림이 왔다는 사실과
에이전트의 추측만 있고 **"그래서 진짜 뭐였고 어떻게 끝났는가" 가 없었다.**

이걸 채우면서 갈린 지점이 넷이다.

### 1. 에이전트 추측을 검색 코퍼스에 넣지 않는다

넣던 것을 뺐다. 저장할 때 벡터 메타데이터의 `summary` 가 이랬다.

```
[Triggered] 주문 생성 진행 중 → 1) 재발 — 과거 사례와 원인이 같은...
```

**Dify 가 추측한 원인이 그대로 들어가 있다.** 다음 알림에서 이것이 "과거 사례" 로
다시 읽히면 추측이 한 바퀴 돌아 사실이 된다. `architecture.md` 7.4 "오판의
재학습" 이 경고한 경로가 정확히 이것이다.

처음에는 프롬프트에 "과거 사례는 참고이지 정답이 아니다" 를 넣어 막았다.
**약한 방어다 — 규칙은 무시될 수 있다.** 데이터에서 빼면 무시할 수 없다.

| 상태 | 요약에 들어가는 것 |
|---|---|
| 미검증 | **사실만.** 제목 + 어떻게 끝났나 + 걸린 시간 |
| 검증됨 | 원인까지 (`root_cause_label`) |

```
[미검증] 주문 생성 큐 적체 · 12분 뒤 자동복구
[확인됨] 주문 생성 큐 적체 · db_lock_contention · 사람이 조치 · 23분
```

미검증 사례도 충분히 쓸모 있다. **"전에도 왔고 12분 뒤 저절로 돌아갔다" 는
100% 사실이고, 재발 판정에 필요한 정보가 그것이다.** 원인을 말할 자격이
검증 뒤에 생길 뿐이다.

부수 효과로 요약이 600자에서 60자가 됐다. 3건이면 1,800자가 180자다.

추측 전문은 S3 원본의 `agent.hypothesis` 에 남는다. **지우는 것이 아니라
검색 코퍼스에서 빼는 것이고**, 사람이 검증할 때 그것을 읽는다.

### 2. `resolved` 를 버리고 `state` 다섯 값을 쓴다

`architecture.md` 7.3 은 `resolved: true/false` 다. **boolean 으로는 "복구는
됐지만 고친 건 아니다" 를 표현할 수 없다.**

Datadog `Recovered` 는 "지표가 임계 아래로 돌아왔다" 일 뿐이고, 아래 넷이 전부
같은 신호로 온다.

- 진짜 고쳐졌다
- 저절로 돌아왔다
- 방송이 끝나 부하가 사라졌다
- 모니터를 껐거나 조건을 바꿨다

전부 `resolved: true` 로 적으면 **발표의 MTTR 이 거짓이 된다** — "에이전트
도입 후 MTTR 감소" 인데 실제로는 저절로 돌아온 것들의 평균이다.

| 값 | 뜻 | 누가 |
|---|---|---|
| `unresolved` | 복구 신호가 아직 없다 (**시작값**) | 자동 |
| `auto_recovered` | 지표는 돌아왔다. 아무도 안 고쳤다 | 자동 |
| `human_fixed` | 사람이 조치 | 사람 |
| `agent_fixed` | 에이전트가 런북 실행 | (실행기 생긴 뒤) |
| `false_alarm` | 오탐 | 사람 |

★ **자동 경로는 절대 `human_fixed` 를 쓰지 않는다.** 지금 에이전트는
`action_taken = "none"` 이다. 분석만 하고 아무것도 고치지 않는다.

시작값을 `unresolved` 로 둔 것도 의도다. **사실이고**(아직 안 끝났다), Recovered 가
영영 안 오면 그대로 남으므로 **"24시간 뒤 미해결로 표시" 같은 청소 작업이
필요 없어진다.** 안 해도 되는 일을 만들지 않았다.

`schema_version` 을 `1.1` 로 올렸다.

### 3. 원인 라벨은 통제 어휘다 (`labels.txt`)

자유 텍스트면 같은 원인이 "커넥션 풀 고갈" / "connection pool 문제" / "DB 커넥션
부족" 으로 갈린다. 그러면 **"이 원인이 N번 재발" 을 셀 수 없고**, 그 숫자가
없으면 런북을 무엇부터 쓸지 정할 근거가 없다.

라벨 하나가 런북 하나에 대응한다 (`runbooks/<label>.md`). 목록은 노션의
`공유_장애시나리오_v2.md` 와 실제로 겪은 `troubleshooting.md` 항목에서 뽑았다.

`other` 를 반드시 둔다. 없으면 사람이 억지로 비슷한 라벨을 고르고 집계가
거짓말이 된다. `other` 가 쌓이는 것 자체가 새 라벨 신호다.

**검증은 사람이 한다** (`scripts/verify.py`). 복구 시점에 Dify 를 한 번 더 부르는
방법도 있었지만 그건 추측을 한 번 더 하는 것이지 검증이 아니다.

### 4. Recovered 를 Ingress 가 아니라 Worker 가 처리한다

Ingress 는 Recovered 를 버리고 있었다. 할 일이 생겼으므로 넘긴다 —
**분석은 여전히 안 한다.** Dify 를 부르지 않으므로 LLM 비용도 워커 점유도 없다.

Ingress 에서 직접 처리하지 않는 이유는 그것이 VPC 밖의 가벼운 문지기여야 하기
때문이다(623ms, M-002). S3 읽기와 벡터 갱신은 무겁고, Ingress 가 늦어지면
Datadog 이 기다린다.

**임베딩을 다시 하지 않는다.** 저장할 때 메타데이터에 `s3_key` 를 넣어 뒀고
`GetVectors` 가 벡터값까지 돌려주므로 `cycle_key` 하나로 원본과 벡터를 모두
찾는다. 가장 비싼 구간(약 1.4초, M-002)을 통째로 건너뛴다.

#### 예외 정책이 저장 경로와 정반대다

| 어디 | 예외를 | 왜 |
|---|---|---|
| Triggered 저장 | **안 올린다** | Dify 가 이미 성공했다. 재시도하면 LLM 비용 두 배 + 인시던트 중복 |
| Recovered 적재 | **올린다** | LLM 을 안 부르고 멱등하다. 재시도가 공짜라 막히면 알려야 한다 |

**헷갈려서 통일하지 마라.** 비싼 쪽을 재시도하지 않고 싼 쪽만 재시도하는 것이
이 배치의 요점이다.

### 정한 눈금 셋

- **`$DATE_POSIX` 단위를 가정하지 않는다.** 초인지 밀리초인지 문서로 확정되지
  않아 값의 크기로 가른다. 틀리면 MTTR 이 1000배 어긋나는데 **그 숫자가
  그럴듯해 보여서 아무도 눈치채지 못한다**
- **flapping 은 첫 번째만 센다.** 이미 닫힌 건은 건너뛴다. 마지막 진동까지
  포함하면 MTTR 이 부풀어 오른다
- **런북 후보는 3회 반복.** 2회는 우연일 수 있다. 심각도가 높으면 1회로도 쓴다

### 남은 연결 — 승인과 이력

#102 의 Slack 승인 릴레이가 `slack_approvals` 에 `incident_id` 를 저장한다.
이 이력의 `incident_id` 도 `cycle_key` 이므로 **두 시스템은 같은 키로 이어질
수 있다.** `human_fixed` 를 사람이 손으로 표시하는 대신 승인 기록에서 끌어올 수
있게 되는 지점이다.

**다만 지금은 안 이어진다.** Dify 에 `cycle_key` 를 넘기지 않아서
(`worker.py` 가 라우팅용으로 소비하고 끝낸다) 승인 Lambda 의 `incident_id` 가
`"unknown"` 으로 떨어진다. 이으려면 Dify 입력 계약에 `cycle_key` 를 추가해야
한다 — `dify/README.md` 1절의 네 곳을 같이 고치는 그 작업이다.

## D-046. Runbook 조회도 D-043 과 같은 이유로 Lambda 릴레이를 쓴다

Runbook 테이블(`runbook.tf`)의 첫 초안은 읽기 권한(`GetItem`·`Query`)을
**`aws_iam_role.dify`(Dify EC2 인스턴스 역할)에 직접** 붙이는 모양이었다.
Node 11 이 그 역할로 DynamoDB 를 바로 두드린다는 전제였다. **적용 전
설계 검토에서 이 전제가 틀렸다는 게 드러났다.**

### 왜 틀렸나

D-043 이 이미 확인한 사실이 그대로 적용된다 — Dify 1.16.1 의 Custom
Tool/HTTP 요청 노드가 쓸 수 있는 인증은 `NONE`·`API_KEY_HEADER`·
`API_KEY_QUERY` 세 가지뿐이고, 어디에도 SigV4 서명 경로가 없다. DynamoDB
API 는 SigV4 서명 없이는 호출 자체가 안 된다.

즉 `aws_iam_role.dify` 에 `dynamodb:Query` 를 아무리 붙여봐야, **그 권한을
실제로 행사할 방법이 Node 11 에 없다.** Node 11 은 그 역할의 자격증명을
서명에 쓸 수 있는 도구가 아니라 평범한 HTTP 요청 노드이기 때문이다. IAM
문서만 보면 문제가 없어 보이지만, 워크플로 쪽에서 절대 쓰이지 않는
죽은 권한이 남는 것과 같다 — 그 자체로 사고는 아니지만, 다음 사람이
"이미 권한이 있으니 Node 11 이 직접 조회한다"고 잘못 읽을 근거가 된다.

### 그래서 무엇을 했나

D-043 의 `hot-proxy` 와 같은 모양을, 이번에는 EC2 인스턴스 안 프록시가
아니라 독립 Lambda 로 둔다(`runbook_lookup.tf`, `lambda/runbook_lookup.py`).

```
Dify (HTTP 요청 노드, x-api-key) ──▶ runbook_lookup Lambda ──Query──▶ DynamoDB
```

- Lambda 는 **자신의 실행 역할**로 `GetItem`·`Query` 만 갖는다
  (`aws_iam_role.dify` 는 이 권한을 더 이상 갖지 않는다 — `runbook.tf` 에서
  뺐다).
- Dify → Lambda 구간은 Function URL(`authorization_type = NONE`) + 코드
  내부 `x-api-key` 비교로 인증한다. `slack_approval.tf` 와 같은 모양이다.
- `hot-proxy` 와 달리 **수동 SigV4 서명이 필요 없다.** 대상이 이미
  AWS 서비스(DynamoDB)라서 Lambda 안에서 boto3 로 부르면 SDK 가 서명을
  알아서 한다. `hot-proxy` 는 대상이 *다른* Function URL(`AWS_IAM`)이라
  서명을 직접 만들어야 했던 것과 다르다 — 이번이 더 단순한 경우다.

### slack_approval.tf 와 같은 모양이지만 이유는 다르다

두 곳 다 "Lambda + Function URL + 코드 내부 헤더 검증" 이지만, 그 모양을
쓰는 이유가 다르다.

| | slack_approval.tf | runbook_lookup.tf |
|---|---|---|
| 문제 | Dify 의 동기 HTTP 노드와 Slack 의 비동기 콜백을 잇는다 | Dify 가 DynamoDB 를 직접 서명 호출할 수 없다 |
| 이 파일이 없다면 | 버튼 클릭을 받을 방법이 없다 | Node 11 이 애초에 테이블에 못 닿는다 |
| 근거 | (그 자체로 필요한 중계) | D-043 |

같은 부품을 다른 이유로 재사용한 것이라, "왜 또 Lambda 를 두나" 라는
질문이 나올 때 이 표를 본다.

### 적용 전에 잡았다

이 IAM 권한은 **한 번도 apply 된 적이 없다** — 설계 리뷰 중에 걸러졌다.
사후 대응이 아니라 사전 발견이라는 점을 남긴다. `runbook_lookup.py` 의
`x-api-key` 비교는 여기서 새로 `hmac.compare_digest` 로 썼다 (기존
`slack_approval_request.py` 는 평범한 `!=` 비교이고, 이번 범위에서는
손대지 않았다 — 둘 다 문제라기보다는 이 파일을 새로 쓰는 김에 상수 시간
비교로 시작한 것뿐이다).

---

## D-047. 채팅 분석은 Valkey 구독이 아니라 Chat Gateway에서 SQS로 직접 분기한다

D-016과 `architecture.md` D-15는 채팅 소비자가 WebSocket 브로드캐스트 하나뿐일 때
결정했다. 이제 채팅을 사용자 체감 장애의 조기 신호로 쓰는 두 번째 소비 목적이
생겼다. 과거 결정의 전제가 바뀌었다.

### Valkey Pub/Sub에서 가져오지 않는다

Pub/Sub은 구독자가 끊긴 동안의 메시지를 복구하지 못한다. 더 중요한 것은 기존
Valkey가 실시간 팬아웃과 재고 판정에 쓰인다는 점이다. 분석 Worker의 backlog와
재처리 요구를 같은 실패 영역에 넣지 않는다.

```text
Chat Gateway -> Valkey Pub/Sub -> WebSocket fanout
Chat Gateway -> dedicated SQS -> Lambda -> DynamoDB -> Incident Candidate
```

Valkey는 여전히 실시간 팬아웃의 정답이다. D-15를 폐기하는 것이 아니라 적용 범위를
팬아웃으로 좁힌다. 분석용 Collector가 Valkey를 구독하는 안은 운영 설계가 아니다.

### Agent가 아니라 Candidate까지만 만든다

채팅의 `느리다`는 말은 사용자 체감 증거이지 원인 증거가 아니다. 실제 사용자 증가와
자동화 요청 증가는 조치가 반대지만 클라이언트 생성 세션 키로는 둘을 가를 수 없다.
따라서 이번 경로는 `USER_PERCEIVED_LATENCY` Candidate를 만들고 다음으로 끝낸다.

```text
metric_status=NOT_CHECKED
root_cause=UNDETERMINED
agent_handoff_status=NOT_CONFIGURED
```

D-045의 원칙을 수집 단계부터 적용한 것이다. Datadog Pull과 Dify·Bedrock 호출은
Candidate 이후의 별도 경로다.

### Lambda와 DynamoDB를 쓴다

PoC 트래픽을 아직 측정하지 않았고 상시 Worker Pod가 필요하지 않다. SQS 연동 Lambda가
규칙 분류를 수행하고 DynamoDB가 멱등·시간창·고유 사용자·쿨다운을 소유한다. Dify는
동시 집계 상태의 원본이 아니다.

초기 임계치는 15초 안에 관련 메시지 4건, 고유 사용자 3명이다. 이것은 실측값이나
SLO가 아니라 Shadow Mode 비교를 위한 가설이다. 근거와 변경 게이트는
`chat-incident-candidate.md` 5·10절에 둔다.

### 원문은 60초 뒤 사라진다

분류하려면 Worker까지 원문이 필요하지만 저장 코퍼스로 만들지는 않는다. 원문은
암호화된 SQS 메시지에만 있고 보존 기간은 60초다. 처리 후 즉시 삭제하며 로그,
DynamoDB, Candidate, 원문 DLQ에는 넣지 않는다.

그 결과 Worker가 60초 넘게 멈추면 분석 신호가 유실될 수 있다. 고객 트랜잭션이 아닌
조기 탐지 보조 신호이므로 PoC에서는 재처리보다 개인정보 최소화를 우선한다.

### 구현 원본

- 처리 규칙과 완료 조건: `docs/chat-incident-candidate.md`
- 입력·출력 스키마: `docs/contracts.md` 5.6·5.7
- 기존 `chat.send` Kinesis 관측 이벤트: `docs/contracts.md` 5.3, 별도 경로

---

## D-048. Chat Signal Worker는 독립 `08-chat-signal` 스택에 둔다

Chat Signal SQS와 Candidate DynamoDB는 `03-data`가 소유하지만, 메시지를 실행하는
Lambda까지 데이터 스택에 넣으면 저장소 수명주기와 코드 배포 수명주기가 결합된다.
`04-platform`에 넣으면 Lambda 변경이 EKS·Helm provider 상태에 의존한다.

따라서 실행 리소스는 `08-chat-signal`로 분리하고 `03-data` remote state의 큐와
테이블만 참조한다.

```text
03-data:        SQS + DynamoDB
08-chat-signal: Lambda + execution IAM + SQS event source mapping
```

Phase 1B의 event source mapping은 변수로 켤 수 없고 코드에 `enabled = false`로
고정한다. 실수로 Lambda를 직접 호출해도 골격 handler는 모든 SQS `messageId`를
`batchItemFailures`로 반환한다. 따라서 Candidate 로직이 없는 상태에서 원문 메시지를
성공 처리하거나 삭제하지 않는다.

실행 역할은 다음 권한만 갖는다.

- Chat Signal SQS의 `ReceiveMessage`, `DeleteMessage`, `GetQueueAttributes`
- Candidate DynamoDB의 `GetItem`, `PutItem`, `UpdateItem`, `TransactWriteItems`
- 전용 CloudWatch Log Group의 `CreateLogStream`, `PutLogEvents`

골격은 SQS body를 파싱하거나 로그에 기록하지 않는다. Phase 3에서 실제 처리기를
넣더라도 `ReportBatchItemFailures`, 본문 비기록, 조건부/트랜잭션 쓰기 계약은 유지한다.

---

## D-049. Phase 4 Shadow는 생산자와 소비자를 독립 스위치로 제어한다

D-048의 `enabled = false` 하드코딩은 Candidate 처리기가 없던 Phase 1B에서 메시지
삭제를 막기 위한 임시 안전 게이트였다. Phase 3의 AC-001부터 AC-010까지 통과했으므로
Phase 4 Shadow에서는 다음 두 스위치를 독립적으로 둔다.

| 경계 | 스위치 | `off` | `on` |
|---|---|---|---|
| SQS -> Worker | `08-chat-signal.enable_event_source` | Lambda가 SQS를 소비하지 않음 | Event source mapping 활성화 |
| Chat Gateway -> SQS | `04-platform.chat_signal_mode` | 채팅을 SQS에 발행하지 않음 | `shadow` 발행 활성화 |

활성화는 `03-data -> 08-chat-signal -> 04-platform -> Chat Gateway 재시작` 순서로 한다.
소비자를 먼저 켜면 생산자가 꺼진 빈 큐에서 Worker를 검증할 수 있고, 잘못된 생산자가
원문을 쌓기 전에 IAM·환경 변수·Lambda 상태를 확인할 수 있다.

롤백은 반대로 생산자를 먼저 끈다. `chat_signal_mode=off` 적용 후 Chat Gateway를
재시작하고, 그 다음 `enable_event_source=false`를 적용한다. SQS와 DynamoDB는 삭제하지
않는다. 원문은 SQS 보존 정책에 따라 최대 60초 후 만료된다.

`04-platform`은 Chat Signal 외에 Karpenter·KEDA와 서비스별 Pod Identity도 소유한다.
따라서 Phase 4 적용 전에 Terraform plan에서 Chat Signal 대상 외 변경이 섞이지 않는지
확인해야 한다. 2026-08-23 plan에서는 Karpenter·KEDA 차이는 없었지만, 이전에 병합되고
미적용된 서비스별 IAM 분리가 함께 잡혔다. 이런 기존 변경을 Chat Signal 활성화라는
이유만으로 검토 없이 전체 apply하지 않는다.

이 결정은 D-048의 스택 분리와 최소 IAM 원칙을 유지하며, Phase 1B의 하드코딩된 비활성
게이트만 운영 가능한 변수형 게이트로 대체한다. Datadog Pull, Dify·Bedrock 호출,
자동 조치는 여전히 범위 밖이다.

---

## D-050. Agent 앞에서 source별 JSON을 공통 envelope로 정규화한다

Datadog 알림과 Chat Incident Candidate는 의미가 다르다. 전자는 모니터 임계치 초과이고,
후자는 아직 메트릭으로 확인하지 않은 사용자 체감 증거다. 둘의 원본 스키마를 하나로
강제로 합치면 Chat 값을 빈 `alert_title`·`alert_query`에 끼워 넣거나 Dify가 필드 유무로
source를 추측하게 된다.

따라서 Source Adapter 앞에서는 `datadog.alert.v1`과
`chat.incident_candidate.v1`을 유지하고, Agent Trigger Queue부터만
`agent.trigger.v1` 공통 envelope를 사용한다.

```text
Datadog alert --------> Datadog Source Adapter --+
                                                   +-> agent.trigger.v1 -> Agent Trigger SQS
Chat Candidate INSERT -> Chat Source Adapter -----+
```

공통 envelope의 `source`가 discriminator다. 식별·event time·멱등 키·guardrail은
공통 필드이고, 실제 증거는 source별 `evidence`가 소유한다. Chat evidence에는 원문,
사용자 키, 원문 해시가 없고 `root_cause=UNDETERMINED`를 유지한다.

초기 Chat 정책은 Candidate INSERT 한 번만 호출한다. Candidate 생성 Worker에서 Dify를
직접 호출하지 않고 DynamoDB Stream 뒤 Adapter로 분리한다. Dify 장애나 장시간 실행이
60초 원문 Queue와 Candidate 생성을 막지 않게 하기 위해서다.

Agent Worker는 envelope를 Dify의 `custom_alert_json`으로 전달한다. 2026-08-23 실환경의
게시 앱을 읽기 전용으로 조회해 이 입력 형태가 Dify 1.16.1에서 노출되고 graph에서 참조될
수 있음을 확인했다. 그 앱은 팀원이 노드를 구성 중인 앱이므로 신규 진입점 대상으로 쓰지
않는다. 전용 테스트 앱·전용 API key·export된 DSL로 contract-only smoke를 먼저 수행한다.

저장소의 기존 DSL은 배포본보다 오래됐고 기존 Worker DLQ도 비어 있지 않다. 두 문제는
전용 테스트 앱 실험과 격리하고, 기존 Datadog 경로를 공통 진입점으로 옮기는 시점에
해결한다. 전용 테스트 앱의 Code-only 계약 검증, 비활성 공통 Worker, 테스트 앱 Chat
Shadow E2E, Datadog dual-run 순서로 전환한다.

현재 권한 경계는 `READ_ONLY`이고 자동 조치는 금지한다. Dify HTTP 200만으로 성공 처리하지
않고 `data.status=succeeded`를 확인하며, 같은 `idempotency_key`는 LLM을 다시 실행하지
않는다.

Phase 1B transport는 SQS event source mapping과 Worker 실행 플래그를 모두 비활성으로
고정한다. 멱등 ledger는 외부 Dify 호출 전에 `IN_PROGRESS`를 조건부 획득하고 성공 뒤
`SUCCEEDED`로 확정한다. `SUCCEEDED`, `IN_PROGRESS`, `FAILED` 상태는 자동으로 재획득하지
않는다. 특히 네트워크 단절처럼 요청이 Dify에 도달했는지 알 수 없는 실패에서 자동
재호출하면 동일 Agent 실행을 두 번 만들 수 있으므로 fail-closed한다. 운영자가 Dify
실행 이력과 ledger를 확인한 뒤에만 DLQ 메시지를 재투입한다.

구현 원본:

- 기계 판독 Schema: `docs/contracts/agent-trigger-v1.schema.json`
- 필드와 예시: `docs/contracts.md` 5.8
- 단계·실패 격리·완료 게이트: `docs/agent-entrypoint.md`

---

## D-051. Karpenter·KEDA 를 넣는다 — 안전망이지 주력이 아니다

D-037 이 "스케일링 부품은 필요해질 때 넣는다" 로 미뤄 둔 것들이다. 그 결정을
뒤집는 것이 아니라 **거기 걸어 둔 조건이 충족됐다.** 부하 테스트로 파드당 한계를
재고 나서야(M-009 · M-010) 임계값을 추측이 아닌 값으로 걸 수 있게 됐다.

### 둘 다 2차 보정이다

| 계층 | 무엇 | 반응 시간 |
|---|---|---|
| 1차 (주력) | 큐시트 기반 사전 확장 (D-041) | 방송 시작 전 |
| 2차 (보정) | HPA · KEDA | 43~63초 |
| 4차 (최후) | Karpenter | 노드 Ready 39초 + ECR pull (M-008) |

방송 시작 스파이크는 30초 안에 끝난다. **어느 쪽도 첫 스파이크를 못 받는다.**
이 둘은 사전 확장이 빗나갔을 때, 예상보다 크거나 오래 지속되는 부하를 받는다.
이 문장이 없으면 다음 사람이 Karpenter 를 스파이크 해결책으로 믿고 사전 확장을
뺀다.

### NodePool 을 넷으로 좁힌 이유

후보는 `c6i`·`m6i` × `large`·`xlarge`, 온디맨드, amd64 다. 뺀 것마다 이유가 있다.

| 뺀 것 | 왜 |
|---|---|
| `t3` 계열 | baseline 이 노드당 400m 인데 Datadog 에이전트가 294~397m 를 쓴다. 부하가 없어도 스로틀된다 (M-008) |
| Spot | 회수당하면 WebSocket 이 끊긴다. 수천 명이 동시에 재연결하면 그것이 곧 장애다 (`architecture.md` 9.3) |
| arm64 | ECR 이미지가 amd64 단일 아키다 |

넷 중 **무엇을 띄울지는 Karpenter 가 정한다.** `weight` 도 우선순위도 걸지
않았다 — Pending 파드를 bin-pack 해서 들어가는 것 중 제일 싼 것을 고른다. 앱
파드 requests 가 두 자릿수 millicore 라 보통은 `c6i.large` 가, 메모리가 먼저
차면 `m6i.large` 가 뜬다. 실측 근거는 M-008 에 있다.

우선순위를 고정하지 않은 것이 의도다. 고정하면 메모리 바운드일 때 오히려 비싼
쪽에 갇힌다.

### 축소 정책은 WebSocket 때문에 느슨하다

| 설정 | 값 | 왜 기본값이 아닌가 |
|---|---|---|
| `expireAfter` | `Never` | 기본 720h 는 30일마다 노드를 교체한다. 그 교체가 방송 중에 걸리면 파드가 재배치되고 연결이 끊긴다. AMI 갱신은 관리형 노드그룹 쪽에서 사람이 창을 잡고 한다 |
| `consolidationPolicy` | `WhenEmpty` | `WhenEmptyOrUnderutilized` 는 방송 중에 노드를 합친다. 노는 노드는 돈 낭비지 장애가 아니다 |
| `consolidateAfter` | `2h` | 방송 한 편보다 길게 줘서 중간에 잠깐 빈 것으로 반납하지 않게 한다. 다시 사면 노드 준비가 또 든다 |
| `limits.cpu` | `8` | 비용 상한. 없으면 Pending 파드가 생기는 만큼 인스턴스가 계속 늘어난다. 개인 계정이라 반드시 건다 |

D-041 이 축소를 "cooldown 동안 정상 범위를 확인한 뒤" 로 정했는데 Karpenter 는
그 판단을 못 한다. 그래서 판단 대신 **시간**을 준 것이다.

### IAM 을 태그 조건으로 좁혔다

컨트롤러 IRSA 역할은 LBC 와 같은 패턴이다. 다만 노드 종료 권한에 태그 조건을
걸어 **자기가 만든 노드만** 건드리게 했다. 없으면 관리형 노드그룹 노드까지
종료할 수 있다. `PassRole` 도 노드 역할 하나로 못 박았다.

노드 역할은 새로 만들지 않고 기존 `o2-eks-node-role` 을 재사용한다. 이미 EKS
접근 항목에 `EC2_LINUX` 로 등록돼 있어 새 노드가 바로 조인한다.

중단 알림 큐(SQS + EventBridge)는 없어도 돌지만 스팟 회수 통보(2분)를 못 받는다.
지금 NodePool 이 온디맨드 전용이라 당장 쓰이지 않는데도 같이 만든 것은 SQS 비용이
사실상 0 이고, 나중에 스팟을 열 때 이것부터 빠뜨리면 조용히 깨지기 때문이다.

### KEDA 는 설치만 한다

`ScaledObject` 를 넣으려면 두 가지가 먼저 있어야 한다.

1. **파드당 안전 처리량 실측.** D-041 의 계산식에 들어가는 `safe_capacity_per_pod`
   를 추정값으로 채우지 않는다. 주문 경로는 아직 부하 테스트를 안 했다 —
   measurements.md 에 `api`(M-009)와 `chat-gateway`(M-010)만 있다
2. **매니페스트에서 `replicas` 제거.** KEDA 가 scale 을 소유하는데 `replicas` 가
   남아 있으면 KEDA 가 늘리고 Argo CD selfHeal 이 되돌리기를 무한 반복한다.
   **에러가 안 나서 알아채기 늦다** (D-004)

그리고 `ScaledObject` 는 애플리케이션 배포물이라 자리는 Argo CD 가 보는
O2-live-deploy 쪽이다. 이 저장소는 컨트롤러 설치까지만 한다.

### 넣고 나서 실제로 노드를 띄워 확인했다

Helm 이 뜨고 `EC2NodeClass` 가 `READY=True` 인 것만으로는 **세 가지가 검증되지
않는다.** 전부 노드를 실제로 띄울 때만 드러난다.

- `RunInstances` 권한과 `PassRole` 태그 조건이 맞는지
- 새 노드가 클러스터에 join 하는지 (EKS 접근 항목)
- 종료 권한의 태그 조건이 **자기 노드는 지울 수 있을 만큼** 넓은지 — 좁게 걸었으니
  반대로 못 지울 수 있다

2026-08-23 에 `requests.cpu = 2` 짜리 `pause` 파드로 셋 다 확인했다. 소요 비용
$0.014. 시간 값은 M-008 에 있다.

**설치와 검증을 같은 작업으로 묶는다.** 스파이크가 처음 오는 날 시도하면 그때가
장애다.
