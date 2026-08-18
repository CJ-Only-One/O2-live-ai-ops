#!/usr/bin/env bash
# Dify 콘솔을 로컬로 당겨온다. 퍼블릭 노출 없이 스튜디오 작업용.
#   ./tunnel.sh          -> http://localhost:17080
#
# ★ 포트를 바꾸지 말 것. 서버의 NEXT_PUBLIC_SOCKET_URL 이 17080 으로 고정돼 있어
#   다른 포트로 열면 실시간 동기화(socket.io)만 조용히 안 된다.
#
# 유휴 타임아웃(최대 60분)에 걸리지 않게 keepalive 를 함께 돌린다.
# 그래서 실제 세션 상한은 session_max_duration_minutes(기본 360분)이다.
set -euo pipefail

cd "$(dirname "$0")"
LOCAL_PORT="${1:-17080}"
KEEPALIVE_INTERVAL="${KEEPALIVE_INTERVAL:-300}" # 초. 유휴 상한 60분보다 충분히 짧게

ID=$(terraform output -raw instance_id)
REGION=$(terraform output -raw ssm_session_command | awk '{print $NF}')

# 터널이 살아 있는 동안만 도는 keepalive.
# 응답 내용은 보지 않는다. 패킷이 오간다는 사실만 있으면 유휴가 아니다.
keepalive() {
  while sleep "$KEEPALIVE_INTERVAL"; do
    curl -fsS -o /dev/null --max-time 10 "http://localhost:$LOCAL_PORT/" || true
  done
}

keepalive &
KEEPALIVE_PID=$!
# 터널이 죽으면 keepalive 도 같이 죽인다. 안 그러면 백그라운드에 남는다.
trap 'kill "$KEEPALIVE_PID" 2>/dev/null || true' EXIT

echo "http://localhost:$LOCAL_PORT  (Ctrl-C 로 종료)"
aws ssm start-session \
  --target "$ID" \
  --document-name AWS-StartPortForwardingSession \
  --parameters "{\"portNumber\":[\"80\"],\"localPortNumber\":[\"$LOCAL_PORT\"]}" \
  --region "$REGION"
