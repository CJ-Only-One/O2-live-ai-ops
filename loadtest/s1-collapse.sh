#!/usr/bin/env bash
set -euo pipefail

# S1 채팅 팬아웃 붕괴점 측정 — 연결 수를 계단으로 올리며 **서버측** 전파 p95를 본다.
#
# `run.sh` 와 뭐가 다른가: run.sh 의 표에 있는 전파 p95 는 k6 가 잰 값이고,
# 거기에는 부하 생성기의 이벤트 루프 지연이 섞인다. 2026-08-25 실측에서 같은
# 부하의 서버측 p95 가 186ms 인데 k6 값은 1,252ms 였다(T-041). 붕괴점을 그
# 값으로 정하면 서버가 아니라 노트북 한계를 기록하게 된다.
#
# 그래서 이 스크립트는 판정 지표를 `o2.chat.propagation` 하나로 고정하고,
# Agent 가 읽는 것과 같은 Hot 논리 지표 Adapter 로 읽는다.
#
#   WS_URL=ws://<ALB> BROADCAST_ID=bc_s1meas CHAT_RPS=20 \
#   HOLD_S=420 SAMPLE_WINDOW_S=120 loadtest/s1-collapse.sh 2000 3000 4000
#
# 계단마다: 램프 → 유지 → **마지막 SAMPLE_WINDOW_S 구간만** 서버 지표로 읽는다.
# 창 전체가 그 계단 안에 들어가야 앞 계단 값이 섞이지 않는다.
#
# ponytail: 비율·rate 지표(items_per_sec·block_rate)는 창 끝에서 0 이나 1.0 이
# 나오는 문제가 있어(T-040) 여기서 읽지 않는다. 고쳐지면 열에 추가한다.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="o2-dev"

die() { echo "오류: $*" >&2; exit 1; }
need() { [ -n "${!1:-}" ] || die "$1 이 필요합니다. ${2:-}"; }

STEPS=("$@")
[ ${#STEPS[@]} -gt 0 ] || die "사용법: $0 <VIEWERS 계단...>   예: $0 2000 3000 4000"

need WS_URL "예: ws://<현재-ALB>"
need BROADCAST_ID
need CHAT_RPS "계단마다 고정할 발화율. 아이템/s = VIEWERS × CHAT_RPS"
need HOLD_S "계단 유지 초"
need SAMPLE_WINDOW_S "판정에 쓸 마지막 구간. Hot API 계약상 60~3600"
RAMP_S="${RAMP_S:-30}"

[ "${SAMPLE_WINDOW_S}" -ge 60 ] && [ "${SAMPLE_WINDOW_S}" -le 3600 ] ||
  die "SAMPLE_WINDOW_S 는 60~3600 초여야 합니다(Hot API 계약)."
# 창이 계단 안에 다 들어가야 한다. 여유 60초는 지표 도달 지연 몫이다.
[ "${HOLD_S}" -ge $(( SAMPLE_WINDOW_S + 60 )) ] ||
  die "HOLD_S 는 SAMPLE_WINDOW_S + 60 이상이어야 창이 계단 안에 들어갑니다."
command -v k6 >/dev/null || die "k6 가 없습니다."

# Hot 논리 지표. Hot Proxy 는 Dify 호스트 안에서 도는 SigV4 중계기라 노트북에서
# 안 닿는다 — 같은 Lambda 를 직접 부른다.
hot_p95() {
  local out; out="$(mktemp)"
  aws lambda invoke --function-name "${HOT_API_FUNCTION:-o2-hot-api}" \
    --cli-binary-format raw-in-base64-out \
    --payload "{\"requestContext\":{\"http\":{\"method\":\"POST\",\"path\":\"/v1/hot/datadog/metric\"}},\"body\":\"{\\\"metric\\\":\\\"chat_propagation_p95_ms\\\",\\\"service\\\":\\\"chat-gateway\\\",\\\"env\\\":\\\"${DD_ENV:-dev}\\\",\\\"window_seconds\\\":$1}\"}" \
    "${out}" >/dev/null 2>&1 || { rm -f "${out}"; return 0; }
  python3 -c '
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: raise SystemExit(0)
try: b=json.loads(d.get("body") or "{}")
except Exception: raise SystemExit(0)
print((b.get("value") if b.get("status")=="OK" and b.get("value") is not None else ""), str(b.get("sample_count") or 0), sep="\t")
' "${out}"
  rm -f "${out}"
}

cg_cpu() {
  kubectl top pod -n "${NAMESPACE}" -l app.kubernetes.io/name=chat-gateway --no-headers 2>/dev/null |
    awk '{gsub(/m$/,"",$2); s+=$2} END{print s"m"}'
}

RUN_DIR="${ROOT_DIR}/loadtest/results/s1-collapse-$(date +%Y%m%d-%H%M%S)"
mkdir -p "${RUN_DIR}"
TABLE="${RUN_DIR}/table.tsv"
printf 'VIEWERS\t아이템/s\t서버p95(ms)\t표본수\tcg CPU\tk6종료\n' | tee "${TABLE}"

K6_PID=""
cleanup() { [ -z "${K6_PID}" ] || kill "${K6_PID}" 2>/dev/null || true; }
trap cleanup EXIT

echo "경고: 부하가 채팅 모니터를 깨웁니다. 실행 게이트가 켜져 있으면 Agent 가 조치를 낼 수 있습니다."
echo "      측정만 할 거면 Datadog Downtime 을 먼저 거세요. 결과: ${RUN_DIR}"
echo

for v in "${STEPS[@]}"; do
  echo "=== VIEWERS=${v} (아이템/s = $(( v * CHAT_RPS ))) ==="
  # 대상 방송에 제한이 걸려 있으면 붕괴점이 아니라 제한된 상태를 재게 된다.
  [ -z "$(kubectl exec -n "${NAMESPACE}" deploy/chat-gateway -- node -e '
const R=require("ioredis");const r=new R({host:process.env.VALKEY_HOST,port:Number(process.env.VALKEY_PORT||6379),tls:process.env.VALKEY_TLS==="true"?{}:undefined});
r.get("cfg:channel_limit:"+process.argv[1]).then(v=>{console.log(v??"");process.exit(0)}).catch(()=>process.exit(0));
' "${BROADCAST_ID}" 2>/dev/null)" ] || die "대상 방송에 채널 제한이 걸려 있습니다. 지우고 다시 하세요."

  k6 run -e WS_URL="${WS_URL}" -e BROADCAST_ID="${BROADCAST_ID}" \
    -e VIEWERS="${v}" -e CHAT_RPS="${CHAT_RPS}" -e RAMP_S="${RAMP_S}" -e HOLD_S="${HOLD_S}" \
    -e CHAT_P95_MAX_MS=100000 \
    --summary-export="${RUN_DIR}/k6-${v}.json" \
    "${ROOT_DIR}/loadtest/broadcast.js" >"${RUN_DIR}/k6-${v}.log" 2>&1 &
  K6_PID=$!

  # 계단 끝 SAMPLE_WINDOW_S 만 남기고 기다린다.
  sleep $(( RAMP_S + HOLD_S - SAMPLE_WINDOW_S ))
  cpu="$(cg_cpu)"
  # read 는 개행 없이 끝나면 종료 코드 1 이다. set -e 아래에서 그게 스크립트를
  # 죽이고 trap 이 k6 까지 죽인다 — 값은 이미 담겼는데 실행만 사라진다.
  read -r p95 samples < <(hot_p95 "${SAMPLE_WINDOW_S}") || true

  wait "${K6_PID}" 2>/dev/null && rc=0 || rc=$?
  K6_PID=""
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "${v}" "$(( v * CHAT_RPS ))" "${p95:-표본없음}" "${samples:-0}" "${cpu}" "${rc}" | tee -a "${TABLE}"

  # k6 임계(연결 실패·조기 종료·깨진 프레임) 초과면 생성기 쪽이 먼저 막힌 것이다.
  # 그 위 계단은 서버가 아니라 노트북을 재게 되므로 멈춘다.
  [ "${rc}" -eq 0 ] || { echo "k6 임계 초과 — 생성기 한계입니다. 여기서 멈춥니다(로그: ${RUN_DIR}/k6-${v}.log)"; break; }
done

echo
echo "표: ${TABLE}"
echo "판정: 서버 p95 가 앞 계단 대비 뚜렷이 꺾이는 지점이 붕괴점이다."
echo "      끝까지 안 꺾이면 부하를 더 올리거나 chat-gateway replicas 를 줄여서 다시 잰다."
