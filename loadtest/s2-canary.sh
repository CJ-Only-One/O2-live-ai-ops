#!/usr/bin/env bash
set -euo pipefail

# S2 느린 파드 주입기. 운영 Deployment를 Kustomize base로 읽고, 실측으로 정한
# CPU/probe 값만 로컬 patch한 뒤 적용한다. 숫자를 주지 않으면 apply하지 않는다.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OVERLAY_DIR="${ROOT_DIR}/../O2-live-deploy/experiments/s2-api-canary"
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

  [[ "${CANARY_CPU_LIMIT}" =~ ^[1-9][0-9]*m$|^[0-9]+([.][0-9]+)?$ ]] ||
    die "CANARY_CPU_LIMIT 형식이 잘못됐습니다: ${CANARY_CPU_LIMIT}"
  [[ "${CANARY_READINESS_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] ||
    die "CANARY_READINESS_TIMEOUT_SECONDS는 양의 정수여야 합니다."
  [[ "${CANARY_READINESS_FAILURE_THRESHOLD}" =~ ^[1-9][0-9]*$ ]] ||
    die "CANARY_READINESS_FAILURE_THRESHOLD는 양의 정수여야 합니다."
}

render() {
  require_inputs
  # overlay가 운영 Deployment를 상위 디렉터리에서 base로 읽는다. 기본 load
  # restrictor는 상위 참조를 막으므로 이 한 번만 완화한다. 원격 URL은 없고
  # 경로도 위에서 고정해 사용자 입력으로 바뀌지 않는다.
  kubectl kustomize "${OVERLAY_DIR}" --load-restrictor LoadRestrictionsNone |
    kubectl patch --local -f - --type=strategic -o yaml -p "{
      \"spec\": {\"template\": {\"spec\": {\"containers\": [{
        \"name\": \"api\",
        \"resources\": {\"limits\": {\"cpu\": \"${CANARY_CPU_LIMIT}\"}},
        \"readinessProbe\": {
          \"timeoutSeconds\": ${CANARY_READINESS_TIMEOUT_SECONDS},
          \"failureThreshold\": ${CANARY_READINESS_FAILURE_THRESHOLD}
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
