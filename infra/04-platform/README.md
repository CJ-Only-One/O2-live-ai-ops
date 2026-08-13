# 04-platform

클러스터 **안**을 채우는 스택. 클러스터가 새로 생길 때마다 이 스택을 적용하면
Argo CD와 그 위의 모든 것이 자동으로 복원된다.

## 무엇이 자동화되나

| | 이전 | 지금 |
|---|---|---|
| 클러스터 접근 권한 | 손으로 `aws eks create-access-entry` | `cluster_admin_arns` 변수 |
| Argo CD 설치 | README 절차를 손으로 따라감 | `helm_release` |
| Argo Application 등록 | `kubectl apply -f bootstrap/...` | 차트의 `extraObjects` |
| Load Balancer Controller | `terraform output` 을 복사해 실행 | `helm_release` |

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

## 배포되는 것

Argo CD가 [`O2-live-deploy`](https://github.com/CJ-Only-One/O2-live-deploy)를
감시하며, 거기 있는 매니페스트대로 `o2-dev` 네임스페이스를 채운다.
이미지 태그는 앱 저장소의 `app.yml` 이 자동으로 갱신한다.

## 아직 안 들어간 것

- `metrics-server` — 없으면 HPA 불가. `02-eks` 의 애드온 목록에 추가하는 편이 맞다
- `aws-ebs-csi-driver` — 없으면 PVC 불가. 마찬가지
- External Secrets Operator — 결제 연동 시 PG사 키를 다루려면 필수
- Argo CD 외부 노출(Ingress) — 지금은 `port-forward` 로만 접근
- SSO(dex), Slack 알림 — `enable_dex` 를 켜고 `configs.cm` 에 설정 추가
