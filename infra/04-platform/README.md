# 04-platform

클러스터 **안**을 채우는 스택. 클러스터가 새로 생길 때마다 이 스택을 적용하면
Argo CD와 그 위의 모든 것이 자동으로 복원된다.

## 무엇이 자동화되나

| | 이전 | 지금 |
|---|---|---|
| 클러스터 접근 권한 | 손으로 `aws eks create-access-entry` | `cluster_admin_arns` 변수 |
| Argo CD 설치 | README 절차를 손으로 따라감 | `helm_release` |
| Argo Application 등록 | `kubectl apply -f bootstrap/...` | `argocd-apps` 차트 |
| Load Balancer Controller | `terraform output` 을 복사해 실행 | `helm_release` |

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

접속 주소는 **`http`** 다. `server.insecure` 로 설치해 서버가 평문으로 서빙하므로,
`https` 로 붙으면 TLS 핸드셰이크가 깨져 연결이 끊긴다.

```bash
kubectl port-forward -n argocd svc/argocd-server 8080:80   # → http://localhost:8080
```

비밀번호는 설치할 때마다 랜덤으로 새로 생성된다. 클러스터를 자주 다시 만드는
지금 방식에서는 사실상 매번 로테이션되므로, 사람이 정한 값으로 바꾸지 않고
**그때그때 조회해서 쓴다.** `argocd-initial-admin-secret` 은 삭제하지 않는다.

다만 5명이 `admin` 계정 하나를 공유하므로 누가 무엇을 했는지 남지 않는다.
실사용자를 받기 전에는 `enable_dex` 를 켜고 GitHub SSO로 옮길 것.

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
