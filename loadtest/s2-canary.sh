#!/usr/bin/env bash
set -euo pipefail

# S2 느린 파드 주입기. 클러스터의 현재 main Deployment를 읽어 canary를 만들고,
# 실측으로 정한 CPU/probe 값만 로컬 patch한 뒤 적용한다. 로컬 Git base를 쓰면
# Argo가 먼저 새 이미지를 배포한 순간 서로 다른 버전이 섞이므로 live 상태가
# 유일한 원본이다. 숫자를 주지 않으면 apply하지 않는다.
# 실행기 RBAC과 Runbook이 o2-dev로 고정돼 있다. 환경변수로 바꿀 수 있게 하면
# 검증하지 않은 네임스페이스에 실험 리소스를 만들 수 있으므로 고정한다.
NAMESPACE="o2-dev"
ACTION="${1:-render}"

die() {
  echo "오류: $*" >&2
  exit 1
}

require_inputs() {
  : "${CANARY_CPU_LIMIT:?CANARY_CPU_LIMIT이 필요합니다. 예: 실측으로 정한 125m}"
  : "${CANARY_READINESS_TIMEOUT_SECONDS:?CANARY_READINESS_TIMEOUT_SECONDS가 필요합니다.}"
  : "${CANARY_READINESS_FAILURE_THRESHOLD:?CANARY_READINESS_FAILURE_THRESHOLD가 필요합니다.}"
  # 2026-08-26 real test로 재현: readinessProbe만 넓히면 livenessProbe는 기본
  # 타임아웃 그대로라, CPU 스로틀 아래서 liveness가 먼저 타임아웃돼 kubelet이
  # 파드를 통째로 재시작시킨다("Unready"가 아니라 "죽었다 살아난다") — 그때마다
  # Service에서 빠졌다 들어왔다 하며 지연이 요동친다. readiness와 같은 여유를 준다.
  : "${CANARY_LIVENESS_TIMEOUT_SECONDS:?CANARY_LIVENESS_TIMEOUT_SECONDS가 필요합니다.}"

  [[ "${CANARY_CPU_LIMIT}" =~ ^[1-9][0-9]*m$|^[0-9]+([.][0-9]+)?$ ]] ||
    die "CANARY_CPU_LIMIT 형식이 잘못됐습니다: ${CANARY_CPU_LIMIT}"
  [[ "${CANARY_READINESS_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] ||
    die "CANARY_READINESS_TIMEOUT_SECONDS는 양의 정수여야 합니다."
  [[ "${CANARY_READINESS_FAILURE_THRESHOLD}" =~ ^[1-9][0-9]*$ ]] ||
    die "CANARY_READINESS_FAILURE_THRESHOLD는 양의 정수여야 합니다."
  [[ "${CANARY_LIVENESS_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] ||
    die "CANARY_LIVENESS_TIMEOUT_SECONDS는 양의 정수여야 합니다."
}

render() {
  require_inputs
  command -v jq >/dev/null || die "jq가 필요합니다. macOS: brew install jq"

  # 현재 main의 이미지·환경변수·Secret·ServiceAccount·probe를 그대로 복제한다.
  # API 서버가 붙인 identity/status와 Argo tracking annotation은 새 리소스에
  # 복사하면 안 된다. main ReplicaSet끼리만 쓰는 AZ 제약도 canary 하나에는
  # 적용하지 않고, part-of 기반 hostname 분산 제약은 유지한다.
  kubectl get deployment api -n "${NAMESPACE}" -o json |
    jq '
      del(
        .metadata.annotations,
        .metadata.creationTimestamp,
        .metadata.generation,
        .metadata.managedFields,
        .metadata.resourceVersion,
        .metadata.selfLink,
        .metadata.uid,
        .status
      )
      | .metadata.name = "api-canary"
      | .metadata.namespace = "o2-dev"
      | .metadata.labels = ((.metadata.labels // {}) + {"app.kubernetes.io/name": "api-canary"})
      | .spec.replicas = 1
      | .spec.selector.matchLabels["app.kubernetes.io/name"] = "api-canary"
      | .spec.template.metadata.labels["app.kubernetes.io/name"] = "api-canary"
      | .spec.template.spec.topologySpreadConstraints = [
          (.spec.template.spec.topologySpreadConstraints // [])[]
          | select((.labelSelector.matchLabels["app.kubernetes.io/name"] // "") != "api")
        ]
    ' |
    kubectl patch --local -f - --type=strategic -o yaml -p "{
      \"spec\": {\"template\": {\"spec\": {\"containers\": [{
        \"name\": \"api\",
        \"resources\": {\"limits\": {\"cpu\": \"${CANARY_CPU_LIMIT}\"}},
        \"readinessProbe\": {
          \"timeoutSeconds\": ${CANARY_READINESS_TIMEOUT_SECONDS},
          \"failureThreshold\": ${CANARY_READINESS_FAILURE_THRESHOLD}
        },
        \"livenessProbe\": {
          \"timeoutSeconds\": ${CANARY_LIVENESS_TIMEOUT_SECONDS}
        }
      }]}}}
    }"
}

case "${ACTION}" in
  render)
    render
    ;;
  apply)
    # 실제 변경 전에 대상과 main의 현재 상태를 사람이 확인할 수 있게 출력한다.
    kubectl get deployment api -n "${NAMESPACE}" -o wide
    render | kubectl apply -f -
    kubectl rollout status deployment/api-canary -n "${NAMESPACE}" --timeout=180s
    kubectl get endpointslice -n "${NAMESPACE}" -l kubernetes.io/service-name=api -o wide
    ;;
  remove)
    kubectl delete deployment api-canary -n "${NAMESPACE}" --ignore-not-found
    kubectl get endpointslice -n "${NAMESPACE}" -l kubernetes.io/service-name=api -o wide
    ;;
  status)
    kubectl get deployment api api-canary -n "${NAMESPACE}" -o wide
    kubectl get pod -n "${NAMESPACE}" -l o2.cj.io/api-service-member=true -o wide
    ;;
  *)
    die "사용법: $0 {render|apply|remove|status}"
    ;;
esac
