# 04-platform

클러스터 **안**을 채우는 스택. 클러스터가 새로 생길 때마다 이 스택을 적용하면
Argo CD와 그 위의 모든 것이 자동으로 복원된다.

## 무엇이 자동화되나

| | 이전 | 지금 |
|---|---|---|
| 클러스터 접근 권한 | 손으로 `aws eks create-access-entry` | `cluster_admin_arns` 변수 |
| Argo CD 설치 | README 절차를 손으로 따라감 | `helm_release` |
| Argo Application 등록 | `kubectl apply` 수동 | `argocd-apps` 차트 |
| Load Balancer Controller | `terraform output` 을 복사해 실행 | `helm_release` |
| Datadog EKS 메트릭·APM | 미설치 | `helm_release` (API/App Key는 Kubernetes Secret) |
| 앱의 DB·큐·이벤트 배선 | 매니페스트에 손으로 적음 | `app_data_access.tf` · `app_events.tf` |

## 헬름 릴리스가 둘인 이유

`argo-cd` 가 CRD를 설치하고, `argocd-apps` 가 Application을 만든다.

처음에는 `argo-cd` 차트의 `extraObjects` 에 Application을 함께 넣었으나 실패했다.
헬름은 렌더링한 객체를 적용 전에 클러스터 API와 대조하는데, 그 시점에는
아직 CRD가 없기 때문이다.

```
no matches for kind "Application" in version "argoproj.io/v1alpha1"
```

**같은 릴리스에서 CRD를 설치하면서 그 CRD의 인스턴스를 만들 수는 없다.**
`argocd-apps` 는 정확히 이 용도의 얇은 차트다.

## 적용

### 첫 적용은 두 단계다

`helm` 프로바이더는 클러스터에 인증할 수 있어야 동작하는데, 그 권한을 주는
access entry를 같은 스택이 만든다. 그래서 첫 실행에서는 권한을 먼저 만들고
나머지를 적용한다.

```bash
cd infra/04-platform
terraform init

# 1) 접근 권한만 먼저
terraform apply -target=aws_eks_access_entry.admin \
                -target=aws_eks_access_policy_association.admin

# 2) 나머지 (Argo CD, Application, LBC)
terraform apply
```

두 번째부터는 `terraform apply` 한 번이면 된다.

이 어색함은 access entry를 `02-eks`(클러스터 소유자)로 옮기면 사라진다.
그 스택은 현재 다른 사람이 관리 중이라 합류 후에 정리한다.

### 클러스터를 다시 만들었을 때

```bash
terraform apply -target=aws_eks_access_entry.admin \
                -target=aws_eks_access_policy_association.admin
terraform apply
```

state에는 이전 클러스터의 Argo CD 릴리스가 남아 있지만, 실제 클러스터에는
없으므로 Terraform이 다시 설치한다. 릴리스가 꼬이면 `terraform state rm
helm_release.argocd` 후 다시 apply 한다.

## 확인

```bash
terraform output kubeconfig_command   # 사람이 kubectl을 쓸 때만 필요
terraform output argocd_ui_command
terraform output argocd_initial_password_command
```

**첫 로그인 후 비밀번호를 바꾸고 `argocd-initial-admin-secret` 을 삭제할 것.**
Argo CD는 클러스터 전체에 대한 배포 권한을 가지므로 이 계정이 뚫리면 전부 뚫린다.

## Datadog EKS 메트릭 설치

Datadog은 `enable_datadog` 으로 켠다 (현재 `terraform.tfvars` 에서 켜져 있다).
API/App Key 원문은 Terraform state나 Kubernetes
매니페스트에 넣지 않는다. AWS Secrets Manager의 JSON Secret(`o2/dev/datadog-new`)에만
보관하고, External Secrets Operator(ESO)가 `datadog/datadog-secret`으로 동기화한다.
따라서 EKS/platform stack을 destroy한 뒤 다시 apply해도 원본 키를 다시 입력할 필요가 없다.

### 최초 1회: 키와 AWS Secrets Manager 원본 만들기

1. Datadog의 **Organization Settings > API Keys**에서 `o2-eks-agent` 같은 Agent 전용
   API Key를 새로 만든다. `AWS-Integration` 키는 AWS 계정 연동용이므로 사용하지 않는다.
2. **Organization Settings > Application Keys**에서 App Key를 새로 만든다. 이 키는 EKS
   control plane monitoring에 필요하다.
3. AWS Secrets Manager 콘솔에서 **Other type of secret**을 선택하고 다음 두 key/value를
   입력한다. 이름은 `o2/dev/datadog-new`으로 한다. 기본 AWS managed key를 쓸 경우 별도 KMS
   권한은 필요 없다.

| Key | Value |
|---|---|
| `api-key` | 새로 만든 `o2-eks-agent` API Key |
| `app-key` | 새로 만든 Datadog App Key |

이 Secret은 `04-platform` Terraform이 소유하지 않는다. 플랫폼을 destroy해도 원본 키가
유지되도록 한 의도적인 분리다.

그 다음 `terraform.tfvars`에 아래 한 줄을 추가하고 적용한다.

```hcl
enable_datadog = true
```

```bash
terraform init
terraform plan
terraform apply
```

설치 구성은 ESO, EKS Pod Identity, 노드·파드·컨테이너 메트릭(kubelet/cAdvisor),
Kubernetes 상태 메트릭, 제한된 Kubernetes 이벤트, EKS control plane(API Server,
Controller Manager, Scheduler)을 수집한다.

**APM 은 켜져 있다** (D-026). 파드 지표는 "api 가 느리다" 까지만 말하고 그 안에서
Valkey 냐 MySQL 이냐를 가르지 못하기 때문이다. UDS 가 아니라 hostPort 8126 으로
받고, 애플리케이션은 `DD_AGENT_HOST` 를 `status.hostIP` 로 주입받는다.

로그와 프로세스 목록은 계속 끈다. 데이터량이 곧 요금이고, 지금 필요한 것은 로그
본문이 아니라 구간별 시간이다.

```bash
kubectl -n datadog get pods
kubectl get clustersecretstore aws-secrets-manager
kubectl -n datadog get externalsecret datadog
kubectl -n datadog get secret datadog-secret
kubectl -n datadog exec deploy/datadog-cluster-agent -- agent clusterchecks
```

마지막 명령 출력에 `kube_apiserver_metrics`, `kube_controller_manager`,
`kube_scheduler`가 나타나면 EKS control plane 수집까지 정상이다. Datadog UI에서는
Infrastructure > Kubernetes 또는 Containers에서 `kube_cluster_name:o2-eks`로
필터링한다.

키 교체 시에는 Secrets Manager에서 값을 변경한다. ESO는 최대 1시간 이내에 Kubernetes
Secret을 갱신한다. 환경변수로 키를 읽는 Agent에 새 키를 반영하려면 동기화 확인 후 아래를
실행한다.

```bash
kubectl -n datadog rollout restart daemonset/datadog
kubectl -n datadog rollout restart deployment/datadog-cluster-agent
```

## 배포되는 것

Argo CD가 [`O2-live-deploy`](https://github.com/CJ-Only-One/O2-live-deploy)를
감시하며, 거기 있는 매니페스트대로 `o2-dev` 네임스페이스를 채운다.
이미지 태그는 앱 저장소의 `app.yml` 이 자동으로 갱신한다.

## 앱 배선 (`app_data_access.tf` · `app_events.tf`)

파드가 데이터 계층과 이벤트 스트림에 닿는 경로를 여기서 만든다.

| 만드는 것 | 내용 |
|---|---|
| ConfigMap `o2-data` | RDS·Valkey 엔드포인트, SQS 큐 URL, `O2_EVENTS_SINK` |
| Secret `o2-db` | `DB_PASSWORD` — RDS 관리형 시크릿을 ESO 가 동기화 |
| Secret `o2-events` | `O2_EVENTS_SALT` — `user_key` HMAC salt (D-027) |
| IAM | SQS 접근, Kinesis `PutRecords`, ESO 의 시크릿 읽기 |
| ServiceAccount + Pod Identity | `api` · `order-worker` · `chat-gateway` |

엔드포인트는 `03-data` 의 remote state 에서 읽는다. 데이터 스택을 다시 만들어도
이 스택만 apply 하면 따라간다.

**`enable_app_events` 를 켜기 전에** Secrets Manager 에 `o2/dev/events-salt` 가
있어야 한다. 없으면 data source 가 plan 단계에서 깨진다 — Datadog 키와 같은 방식이다.

## 아직 안 들어간 것

- `metrics-server` — **`02-eks/addons.tf` 에 들어갔다.** 그 스택을 apply 해야 반영된다
- `aws-ebs-csi-driver` — 넣지 않는다. PVC 를 쓰는 파드가 없다 (D-037)
- KEDA — 보류. 방송 시각을 아는 데모에서는 cron scaler 와 `kubectl scale` 이
  하는 일이 같다. 스케일링 동작 자체를 시연 대상으로 삼을 때 넣는다 (D-037)
- Argo CD 외부 노출(Ingress) — 지금은 `port-forward` 로만 접근
- SSO(dex), Slack 알림 — `enable_dex` 를 켜고 `configs.cm` 에 설정 추가
