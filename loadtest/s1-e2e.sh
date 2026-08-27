#!/usr/bin/env bash
set -euo pipefail

# S1(채팅 총량 과부하) end-to-end 실행기.
#
# 한 번에 다 돌리지 않는다. 모니터 창이 5분이라 한 사이클 틀리면 디버깅이
# 5분씩 먹는다. 단계를 나눠 놓고 각 단계가 자기 전제를 스스로 검사한다.
#
#   s1-e2e.sh preflight   실행 디렉터리를 만들고 잔여 상태·전제를 검사한다
#   s1-e2e.sh baseline    붕괴 전 구간의 전파 p95·차단률을 기록한다
#   s1-e2e.sh inject      k6 부하를 백그라운드로 띄운다
#   s1-e2e.sh watch       Agent 가 채널 제한을 걸 때까지 지켜본다
#   s1-e2e.sh apply       사람이 직접 건다 (강도 실측 · Agent 없는 축소 시연)
#   s1-e2e.sh mark <이름> 사람이 아는 시각을 타임라인에 박는다 (승인 요청/승인)
#   s1-e2e.sh verify      적용 시각 이후 구간만으로 복구를 판정한다
#   s1-e2e.sh clear       채널 제한을 풀고 지연이 재발하는지 본다
#   s1-e2e.sh teardown    잔여 상태를 확인하고 타임라인을 낸다
#   s1-e2e.sh selftest    판정 규칙만 검사한다 (클러스터 불필요)
#
# **판정은 이 스크립트가 독립으로 한다.** Agent 판정은 Slack/Dify 에서 따로
# 보고 대조한다. Agent 가 자기 조치를 자기가 채점하면 검증이 아니다.
#
# 숫자는 하나도 기본값을 주지 않는다. 미측정값이 기본값으로 박히면 다음
# 사람이 그걸 실측으로 읽는다 (AGENTS.md "숫자를 지어내지 않는다").

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_DIR="${ROOT_DIR}/loadtest/results"
CURRENT_LINK="${RESULTS_DIR}/s1-current"
# 실행기 권한과 런북이 o2-dev 로 고정돼 있다. 환경변수로 열면 검증하지 않은
# 네임스페이스에 실험이 나간다 (s2-canary.sh 와 같은 이유).
NAMESPACE="o2-dev"
ACTION="${1:-help}"

die() { echo "오류: $*" >&2; exit 1; }
need() { [ -n "${!1:-}" ] || die "$1 이 필요합니다. ${2:-}"; }

run_dir() {
  RUN_DIR="${RUN_DIR:-$(cat "${CURRENT_LINK}" 2>/dev/null || true)}"
  [ -n "${RUN_DIR}" ] && [ -d "${RUN_DIR}" ] || die "실행 디렉터리가 없습니다. 먼저 preflight 를 돌리세요."
}

mark() { printf '%s\t%s\t%s\n' "$(date +%s)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >>"${RUN_DIR}/timeline.tsv"; }
at()   { awk -F'\t' -v e="$1" '$3==e{v=$1} END{print v}' "${RUN_DIR}/timeline.tsv"; }

# Valkey 읽기. 전용 클라이언트를 새로 띄우지 않고 chat-gateway 파드에 이미
# 들어 있는 ioredis 와 접속 정보를 그대로 빌린다. get/keys 외에는 거부한다 —
# 검증 스크립트가 상태를 바꾸면 그 뒤 측정이 전부 오염된다.
valkey() {
  kubectl exec -n "${NAMESPACE}" deploy/chat-gateway -- node -e '
const Redis = require("ioredis");
const [cmd, ...args] = process.argv.slice(1);
if (!["get", "keys"].includes(cmd)) { console.error("read-only"); process.exit(2); }
const r = new Redis({
  host: process.env.VALKEY_HOST, port: Number(process.env.VALKEY_PORT || 6379),
  tls: process.env.VALKEY_TLS === "true" ? {} : undefined,
});
r[cmd](...args)
  .then((v) => { console.log(Array.isArray(v) ? v.join("\n") : (v ?? "")); process.exit(0); })
  .catch((e) => { console.error(e.message); process.exit(1); });
' "$@"
}

# Agent 가 검증에 쓰는 것과 같은 소스(Hot Proxy)를 읽는다. 지표 파이프라인을
# 따로 만들면 둘이 다를 때 어느 쪽이 틀린 건지 못 가린다.
#
# ponytail: o2.chat.propagation 에 broadcast_id 태그가 아직 없어서(①) 이 값은
# 전체 방송 합산이다. 방송 축이 붙기 전에는 방송 하나만 띄운 채로 돌려야
# 한다. 태그가 붙으면 여기에 group_by 를 넘긴다.
# 지표 조회 경로 둘. Hot Proxy 는 Dify 호스트 안에서 도는 SigV4 중계기라
# 노트북에서는 안 닿는다. 그 경우 같은 Lambda 를 직접 부른다 — Agent 가
# 읽는 것과 같은 논리 지표 Adapter 라 값이 갈리지 않는다.
hot_raw() {
  local body="{\"metric\":\"$1\",\"service\":\"chat-gateway\",\"env\":\"${DD_ENV:-dev}\",\"window_seconds\":$2}"
  if [ -n "${HOT_PROXY_URL:-}" ]; then
    curl -fsS -X POST "${HOT_PROXY_URL}/v1/hot/datadog/metric" \
      -H 'content-type: application/json' -H "X-O2-Proxy-Key: ${O2_HOT_PROXY_KEY}" -d "${body}"
    return
  fi
  local out
  out="$(mktemp)"
  aws lambda invoke --function-name "${HOT_API_FUNCTION:-o2-hot-api}" \
    --cli-binary-format raw-in-base64-out \
    --payload "{\"requestContext\":{\"http\":{\"method\":\"POST\",\"path\":\"/v1/hot/datadog/metric\"}},\"body\":$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "${body}")}" \
    "${out}" >/dev/null || { rm -f "${out}"; return 1; }
  python3 -c 'import json,sys
d=json.load(open(sys.argv[1]))
if d.get("statusCode")!=200: raise SystemExit(1)
print(d["body"] if isinstance(d["body"],str) else json.dumps(d["body"]))' "${out}"
  local rc=$?
  rm -f "${out}"
  return "${rc}"
}

# 값이 없거나 호출이 실패하면 빈 문자열이다. 여기서 죽지 않는 이유는,
# 부르는 쪽이 "표본이 없다"와 "그래서 판정을 안 한다"를 스스로 말해야
# 하기 때문이다. 결측을 0 으로 바꾸는 것보다 빈 값이 안전하다.
hot_value() {
  hot_raw "$1" "$2" 2>/dev/null |
    python3 -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
print(d["value"] if d.get("status")=="OK" and d.get("value") is not None else "")' 2>/dev/null || true
}

# Hot API 계약상 창은 60~3600초다. 밖이면 조회 자체가 거부된다.
check_window() {
  [ "$1" -ge 60 ] && [ "$1" -le 3600 ] || die "$2 는 60~3600 초여야 합니다(Hot API 계약): $1"
}

# 복구 판정. 규칙 둘 다 만족해야 한다 (scenario-experiment.md 1.1).
#   ① 계약 기준 복귀 AND 조치 직전 기준선 대비 개선 — 자연 회복을 조치
#      효과로 기록하지 않기 위해서다.
#   ② 조치가 실제로 부하를 낮췄나 — 처리량이 감당선 안으로 들어와야 한다.
#
# **차단률은 판정 축이 아니다.** `limit_channel_volume` 은 정상 사용자 발화를
# 일부러 거부하는 것이 작동 원리라, 조치가 설계대로 들을수록 차단률은 오히려
# 오른다. 성공 기준에 두면 조치가 자기 성공 조건과 싸운다. 사람이 승인할 때
# 알고 감수하는 **대가**이지 자동 판정이 재는 회복 지표가 아니다.
# 런북도 2026-08-26 에 success_criteria 에서 빼고 승인 정보로 옮겼다.
# 여기서는 계속 **측정해서 기록**한다 — 승인 화면이 사람에게 제시한 예상
# 영향과 실제가 같았는지 대조하려면 숫자가 남아 있어야 한다.
#
# 런북은 `logic: OR` 이다(부하 없이 데모해도 죽지 않게 하는 안전망). 측정용인
# 이 스크립트는 **AND** 로 본다 — 하나만 맞아도 통과시키면 잰 의미가 없다.
judge() { # p95_post p95_pre_apply items_post / 기준은 환경변수
  awk -v p="$1" -v pre="$2" -v it="$3" \
      -v pmax="${RECOVERY_P95_MAX_MS}" -v imax="${ITEMS_PER_SEC_MAX}" '
    BEGIN {
      slo  = (p <= pmax)
      gain = (p < pre)
      cap  = (it <= imax)
      printf "p95 %.1fms (기준 %.1f, 조치직전 %.1f) 처리량 %.0f item/s (상한 %.0f)\n", p, pmax, pre, it, imax
      printf "  SLO복귀=%s 기준선개선=%s 처리량복귀=%s\n", slo?"O":"X", gain?"O":"X", cap?"O":"X"
      exit (slo && gain && cap) ? 0 : 1
    }'
}

case "${ACTION}" in

preflight)
  # 여기서 막는 것들은 전부 "안 막으면 30분 뒤에 알게 되는" 것들이다.
  need WS_URL "예: wss://<현재-ALB>"
  need BROADCAST_ID
  # Hot Proxy 를 쓰면 URL·키가 둘 다 필요하고, 없으면 Lambda 를 직접 부른다.
  [ -z "${HOT_PROXY_URL:-}" ] || need O2_HOT_PROXY_KEY
  command -v k6 >/dev/null || die "k6 가 없습니다."

  kubectl config current-context
  kubectl get deploy api chat-gateway -n "${NAMESPACE}" -o wide

  # 직전 실행 잔여. 반복 실행에서 제일 자주 밟는다.
  #
  # 대상 방송에 걸려 있으면 중단한다 — 제한된 상태를 재면 붕괴점이 아니다.
  # 다른 방송 것은 경고만 한다. 클러스터를 나눠 쓰므로 남이 실험 중일 수
  # 있고, 남의 상태 때문에 내 측정이 막힐 이유는 없다. 다만 안 보이게
  # 넘기지도 않는다 — 조치에는 만료가 없어서 아무도 안 지우면 영원히 남는다.
  [ -z "$(valkey get "cfg:channel_limit:${BROADCAST_ID}")" ] ||
    die "대상 방송(${BROADCAST_ID})에 제한이 이미 걸려 있습니다. clear 로 지우고 시작하세요."
  leftover="$(valkey keys 'cfg:channel_limit:*')"
  [ -z "${leftover}" ] || {
    echo "경고: 다른 방송에 제한이 남아 있습니다 — 소유자 확인 없이 지우지 마세요."
    printf '  %s\n' ${leftover}
  }
  leftover="$(valkey keys 'chat:total:*')"
  [ -z "${leftover}" ] || echo "경고: 총량 카운터가 남아 있습니다(60초 뒤 만료): ${leftover}"

  # 차단률은 warm 의 chat.send 집계에서 나온다. 이 스위치가 꺼져 있으면
  # o2.warm.channel_limited_rate 가 영원히 비고 차단률 모니터가 안 뜬다.
  kubectl get deploy chat-gateway -n "${NAMESPACE}" \
    -o jsonpath='{range .spec.template.spec.containers[*].env[?(@.name=="EMIT_CHAT_EVENTS")]}{.value}{end}' |
    grep -qx true || echo "경고: EMIT_CHAT_EVENTS 가 true 가 아닙니다 — warm 차단률 지표가 비게 됩니다."

  # Hot Proxy 도달 확인. 값이 비어도 된다(부하 전이라 표본이 없다) —
  # 여기서 보는 것은 URL·키가 맞는지라 응답 자체를 본다.
  hot_raw chat_propagation_p95_ms 300 >/dev/null || die "Hot Proxy 호출 실패 (URL·키 확인)."

  # 런북이 active 이고 승인 등급인지. 조회 URL 이 없으면 건너뛴다.
  if [ -n "${RUNBOOK_LOOKUP_URL:-}" ]; then
    curl -fsS "${RUNBOOK_LOOKUP_URL}?rca_type=chat_channel_overload" \
      -H "x-api-key: ${RUNBOOK_LOOKUP_KEY:?RUNBOOK_LOOKUP_URL 을 주면 KEY 도 필요합니다}" |
      python3 -c 'import json,sys; d=json.load(sys.stdin); a=(d.get("actions") or [{}])[0]
print("런북:", d.get("status"), "risk:", a.get("risk_level"), "limit:", ((a.get("parameters_schema") or {}).get("limit") or {}).get("source"))
sys.exit(0 if d.get("status")=="active" else 1)' || die "chat_channel_overload 런북이 active 가 아닙니다."
  else
    echo "건너뜀: 런북 상태 확인 (RUNBOOK_LOOKUP_URL 없음)"
  fi
  # S1 전제는 "알려진 장애"다. 유사 사례가 없으면 Agent 가 신규로 분류해
  # 다른 가지를 탄다. 벡터 검색 결과는 여기서 못 보므로 사람이 확인한다.
  echo "확인 필요: chat_channel_overload 유사 사례가 History 에 있는지 (infra/06-agent/scripts/seed_history.py)"

  RUN_DIR="${RESULTS_DIR}/s1-$(date +%Y%m%d-%H%M%S)"
  mkdir -p "${RUN_DIR}"
  printf '%s\n' "${RUN_DIR}" >"${CURRENT_LINK}"
  : >"${RUN_DIR}/timeline.tsv"
  mark preflight_ok
  echo "실행 디렉터리: ${RUN_DIR}"
  ;;

baseline)
  # 붕괴 전 형상. 복구 판정의 절대 기준이 아니라 "어디로 돌아가야 하는가"다.
  run_dir
  need BASELINE_WINDOW_S "예: 300 — 모니터 창과 맞춘다"
  check_window "${BASELINE_WINDOW_S}" BASELINE_WINDOW_S
  p95="$(hot_value chat_propagation_p95_ms "${BASELINE_WINDOW_S}")"
  block="$(hot_value block_rate "${BASELINE_WINDOW_S}")"
  [ -n "${p95}" ] || die "전파 p95 표본이 없습니다. 정상 부하를 먼저 흘리세요(샘플링 0.1%)."
  printf '%s\n' "{\"p95_ms\":${p95},\"block_rate\":${block:-null},\"window_s\":${BASELINE_WINDOW_S}}" >"${RUN_DIR}/baseline.json"
  mark baseline
  cat "${RUN_DIR}/baseline.json"
  ;;

inject)
  run_dir
  # 값은 전부 실측에서 온다. broadcast.js 가 발화자당 개인 한도 초과 여부까지
  # 스스로 검사하므로 여기서 다시 세지 않는다.
  need VIEWERS; need SENDERS; need SPIKE_RPS; need SPIKE_S; need PLATEAU_RPS
  need CHAT_P95_MAX_MS; need HOLD_S
  [ "${HOLD_S}" -ge 600 ] || die "HOLD_S 가 ${HOLD_S}s 입니다. 알림(5분 창)→진단→승인→적용이 부하 중에 끝나야 하므로 최소 600 이상으로 두세요."

  echo "Datadog 모니터 Downtime 을 지금 해제했는지 확인하세요. (측정 중에는 켜 둔다)"
  # 첫 파동이 끝나는 시각을 watch 가 알아야 한다 — 고원 구간에 걸린 조치만
  # 판정 대상이다. 그래서 램프와 파동 길이를 파일로 남긴다.
  RAMP_S="${RAMP_S:-30}"
  printf '%s\n' "{\"ramp_s\":${RAMP_S},\"spike_s\":${SPIKE_S},\"hold_s\":${HOLD_S}}" >"${RUN_DIR}/waveform.json"
  mark inject
  nohup k6 run \
    -e PROFILE=s1 -e WS_URL="${WS_URL}" -e BROADCAST_ID="${BROADCAST_ID}" \
    -e VIEWERS="${VIEWERS}" -e SENDERS="${SENDERS}" \
    -e SPIKE_RPS="${SPIKE_RPS}" -e SPIKE_S="${SPIKE_S}" -e PLATEAU_RPS="${PLATEAU_RPS}" \
    -e RAMP_S="${RAMP_S}" -e HOLD_S="${HOLD_S}" -e CHAT_P95_MAX_MS="${CHAT_P95_MAX_MS}" \
    --summary-export "${RUN_DIR}/k6-summary.json" \
    "${ROOT_DIR}/loadtest/broadcast.js" >"${RUN_DIR}/k6.log" 2>&1 &
  echo "$!" >"${RUN_DIR}/k6.pid"
  echo "k6 pid $(cat "${RUN_DIR}/k6.pid") · 로그 ${RUN_DIR}/k6.log"
  ;;

watch)
  # 채널 제한 키가 생기는 순간이 조치 적용 시각이다. 그 시점의 지표를 바로
  # 찍어 둔다 — 이것이 "조치 직전 기준선"이고, 나중에 다시 재면 이미 조치
  # 효과가 섞여 못 쓴다.
  #
  # ponytail: 지금은 Valkey 키만 본다. ④(모니터 webhook·monitor map)가
  # 들어오면 여기에 Incident 스냅샷 폴링을 붙여 T_alert·T_verified 를 자동으로
  # 채운다. 그전까지는 mark 로 사람이 박는다.
  run_dir
  need WATCH_TIMEOUT_S "예: 1800"
  need BROADCAST_ID
  need PREMISE_FAIL_RATE_MAX "조치 전 chat.send 실패율 상한. 이걸 넘으면 개인 한도가 이미 터진 것이라 S1 전제가 아니다"
  deadline=$(( $(date +%s) + WATCH_TIMEOUT_S ))
  # 고원이 시작되는 시각. 첫 파동에 걸린 조치는 판정 대상이 아니다 —
  # 단발 스파이크는 어떤 조치로도 못 막고, 그 구간이 섞이면 "조치 효과"와
  # "파동이 저절로 끝난 것"을 못 가른다.
  #
  # k6 기동 시간만큼 실제 고원 시작은 이보다 몇 초 뒤다. 경계에 아슬아슬하게
  # 걸린 실행은 통과해도 의심하고 다시 돌린다.
  injected="$(at inject)"
  [ -n "${injected}" ] && [ -f "${RUN_DIR}/waveform.json" ] || die "inject 기록이 없습니다. 부하를 먼저 띄우세요."
  plateau_at=$(( injected + $(python3 -c 'import json;w=json.load(open("'"${RUN_DIR}"'/waveform.json"));print(w["ramp_s"]+w["spike_s"])') ))
  misses=0
  while :; do
    # 폴링 중 kubectl 이 한 번 흔들렸다고 30분짜리 실행을 버리지 않는다.
    # 연속 실패면 그때 죽는다 — 조용히 "아직 안 걸렸다"로 읽히면 안 된다.
    if ! limit="$(valkey get "cfg:channel_limit:${BROADCAST_ID}" 2>/dev/null)"; then
      misses=$(( misses + 1 ))
      [ "${misses}" -lt 3 ] || die "Valkey 조회가 3회 연속 실패했습니다."
      sleep 10; continue
    fi
    misses=0
    if [ -n "${limit}" ]; then
      now="$(date +%s)"
      [ "${now}" -ge "${plateau_at}" ] ||
        die "첫 파동 구간($(( plateau_at - now ))s 남음)에 제한이 걸렸습니다. 지속 고원이 완화 대상이므로 이 실행은 판정에 쓰지 않습니다."
      mark apply
      # 조치 직전 형상. 승인 화면이 근거로 내건 값(현재 채팅량·전파 지연)과
      # 같은 축이고, 나중에 다시 재면 조치 효과가 섞여 못 쓴다.
      pre="$(hot_value chat_propagation_p95_ms 300)"
      rps="$(hot_value rps 300)"
      fail="$(hot_value failure_rate 300)"
      printf '%s\n' "{\"limit\":${limit},\"p95_pre_apply_ms\":${pre:-null},\"chat_rps_pre_apply\":${rps:-null},\"fail_rate_pre_apply\":${fail:-null}}" >"${RUN_DIR}/apply.json"
      # 조치 전 실패는 개인 한도(RATE_LIMITED)뿐이다 — 채널 제한은 방금
      # 켜졌고 k6 는 길이 초과를 만들지 않는다. 이 값이 높으면 "전원이 개인
      # 한도 안인데 인원이 많아 총량이 넘는다"는 전제가 이미 깨진 것이다.
      [ -n "${fail}" ] || die "조치 직전 실패율 표본이 없습니다. 전제를 확인할 수 없으므로 이 실행은 판정에 쓰지 않습니다."
      awk -v f="${fail}" -v m="${PREMISE_FAIL_RATE_MAX}" 'BEGIN{exit (f<=m)?0:1}' ||
        die "조치 전 chat.send 실패율이 ${fail} 입니다(상한 ${PREMISE_FAIL_RATE_MAX}). 개인 한도가 이미 걸린 부하라 S1 이 아닙니다 — SENDERS 를 늘리고 다시 하세요."
      echo "적용 확인: limit=${limit} (분당 방송 전체 건수) · 조치직전 p95=${pre:-없음} · 채팅량=${rps:-없음}/s"
      break
    fi
    # 대상 키는 뺀다. get 과 keys 사이에 조치가 들어오면(폴링 간격 10초 안에
    # 실제로 일어난다) 대상 방송인데도 "다음 바퀴에 잡히는" 대신 여기서
    # 죽는다. 2026-08-27 실행이 그렇게 날아갔다.
    other="$(valkey keys 'cfg:channel_limit:*' | grep -v "^cfg:channel_limit:${BROADCAST_ID}$" || true)"
    [ -z "${other}" ] || die "다른 방송에 제한이 걸렸습니다: ${other}. 대상 방송(${BROADCAST_ID})이 아니면 실패입니다."
    [ "$(date +%s)" -lt "${deadline}" ] || die "제한이 걸리지 않은 채 ${WATCH_TIMEOUT_S}s 가 지났습니다."
    sleep 10
  done
  ;;

apply)
  # 사람이 직접 제한을 건다. 쓰는 곳 둘이다.
  #   1) 강도별 차단률·회복폭 실측 — Agent 없이 노브만 스윕한다
  #   2) 축소 시연 — Agent 가 조치를 내고 사람이 실행하는 백업 경로
  # watch 와 같은 apply.json 을 남기므로 그 뒤 verify·clear 는 그대로 쓴다.
  run_dir
  need CHAT_GATEWAY_ADMIN_URL; need CHANNEL_LIMIT_ADMIN_KEY; need BROADCAST_ID
  need LIMIT "분당 방송 전체 발화 상한. 카운터가 60초 고정 창이라 단위가 분당이다"
  [ -z "$(at apply)" ] || die "이미 조치가 걸린 실행입니다. 같은 인시던트에서 두 번 걸지 않습니다."
  curl -fsS -X POST "${CHAT_GATEWAY_ADMIN_URL}" \
    -H "x-admin-key: ${CHANNEL_LIMIT_ADMIN_KEY}" -H 'content-type: application/json' \
    -d "{\"broadcast_id\":\"${BROADCAST_ID}\",\"action\":\"set\",\"limit\":${LIMIT}}"
  echo
  mark apply
  pre="$(hot_value chat_propagation_p95_ms 300)"
  rps="$(hot_value rps 300)"
  fail="$(hot_value failure_rate 300)"
  printf '{"limit":%s,"p95_pre_apply_ms":%s,"chat_rps_pre_apply":%s,"fail_rate_pre_apply":%s,"applied_by":"manual"}\n' \
    "${LIMIT}" "${pre:-null}" "${rps:-null}" "${fail:-null}" >"${RUN_DIR}/apply.json"
  cat "${RUN_DIR}/apply.json"
  ;;

mark)
  # 사람만 아는 시각(Slack 승인 요청·승인)을 타임라인에 넣는다. MTTR 을
  # "사람 대기"와 "Agent 순수 처리"로 쪼개는 값이 여기서 나온다.
  run_dir
  event="${2:?사용법: $0 mark <approval_request|approval_granted|...>}"
  mark "${event}"
  # 승인 화면이 근거로 내건 값(현재 채팅량·전파 지연)을 그 시각에 따로
  # 찍어 둔다. 나중에 Slack 카드에 적힌 숫자와 이걸 대조한다 — Agent 가
  # 사람에게 보여준 근거가 실제와 같았는지는 따로 확인해야 한다.
  if [ "${event}" = "approval_request" ]; then
    p95="$(hot_value chat_propagation_p95_ms 300)"
    rps="$(hot_value rps 300)"
    printf '{"p95_ms":%s,"chat_rps":%s}\n' "${p95:-null}" "${rps:-null}" >"${RUN_DIR}/approval.json"
    cat "${RUN_DIR}/approval.json"
  fi
  tail -1 "${RUN_DIR}/timeline.tsv"
  ;;

verify)
  run_dir
  need VERIFY_WINDOW_S "예: 300 — 60 미만이면 warm 집계 창 하나가 튄 것으로 판정이 뒤집힌다"
  need RECOVERY_P95_MAX_MS; need ITEMS_PER_SEC_MAX; need BROADCAST_ID
  check_window "${VERIFY_WINDOW_S}" VERIFY_WINDOW_S
  applied="$(at apply)"
  [ -n "${applied}" ] || die "apply 시각이 없습니다. watch 를 먼저 돌리세요."
  elapsed=$(( $(date +%s) - applied ))
  [ "${elapsed}" -ge "${VERIFY_WINDOW_S}" ] ||
    die "적용 후 ${elapsed}s 밖에 안 지났습니다. 창 전체가 적용 시각 이후여야 하므로 $(( VERIFY_WINDOW_S - elapsed ))s 더 기다리세요."

  p95="$(hot_value chat_propagation_p95_ms "${VERIFY_WINDOW_S}")"
  block="$(hot_value block_rate "${VERIFY_WINDOW_S}")"
  items="$(hot_value items_per_sec "${VERIFY_WINDOW_S}")"
  pre="$(python3 -c 'import json;print(json.load(open("'"${RUN_DIR}"'/apply.json"))["p95_pre_apply_ms"])')"
  # 차단률은 판정에 안 쓰지만 기록한다 — 비어도 판정은 계속한다.
  [ -n "${p95}" ] && [ -n "${items}" ] && [ "${pre}" != "None" ] ||
    die "표본이 비었습니다(p95=${p95:-없음} items=${items:-없음} pre=${pre}). 결측을 0 으로 바꿔 판정하지 않습니다."

  # 런북 반복 금지. 검증에 실패했는데 같은 조치가 다시 나가면 그것 자체가
  # 불변조건 위반이라 실행 전체를 실패로 본다.
  applied_limit="$(python3 -c 'import json;print(json.load(open("'"${RUN_DIR}"'/apply.json"))["limit"])')"
  now_limit="$(valkey get "cfg:channel_limit:${BROADCAST_ID}")"
  if [ -z "${now_limit}" ]; then
    die "제한이 사라졌습니다(적용값 ${applied_limit}). 검증 창이 끝나기 전에 원복됐으므로 이 실행은 판정에 쓰지 않습니다."
  elif [ "${now_limit}" != "${applied_limit}" ]; then
    die "제한값이 ${applied_limit} → ${now_limit} 로 바뀌었습니다. 같은 조치가 다시 실행된 것이라 이 실행은 실패입니다."
  fi

  # judge 의 종료 코드가 판정이다. 파이프로 tee 에 넘기면 파이프라인
  # 종료 코드가 tee 것이 되어 무조건 통과한다 — 그래서 먼저 받아 적는다.
  verdict="$(judge "${p95}" "${pre}" "${items}")" && ok=0 || ok=1
  # 사용자 영향은 판정 축이 아니라 기록이다. 승인 화면이 사람에게 제시한
  # 예상 영향과 실제가 같았는지 나중에 대조하려면 남아 있어야 한다.
  verdict="${verdict}
  실제 차단률 ${block:-표본없음} (판정 축 아님 · 승인 시 감수한 대가)"
  printf '%s\n' "${verdict}" | tee "${RUN_DIR}/verdict.txt"
  if [ "${ok}" -eq 0 ]; then
    mark recovered; echo "판정: RESOLVED"
  else
    mark not_recovered
    echo "판정: 미달 — 같은 조치를 다시 실행하지 않는다(런북 반복 금지). Agent 가 재실행하는지 지켜보세요."
    exit 1
  fi
  ;;

clear)
  # Phase 6. 원복도 같은 라우트다 — action 만 다르다.
  run_dir
  need CHAT_GATEWAY_ADMIN_URL; need CHANNEL_LIMIT_ADMIN_KEY; need BROADCAST_ID
  need RELAPSE_WINDOW_S "예: 300 — 해제 후 지연이 다시 오르는지 보는 창"
  check_window "${RELAPSE_WINDOW_S}" RELAPSE_WINDOW_S
  # "트래픽 안정화 후 해제"가 Phase 6 의 조건이다. 복구 판정 전에 풀면
  # 조치 효과 구간이 잘려 나가 검증 자체가 없어진다.
  [ -n "$(at recovered)" ] || die "복구 판정(verify)이 통과하기 전에는 해제하지 않습니다."
  curl -fsS -X POST "${CHAT_GATEWAY_ADMIN_URL}" \
    -H "x-admin-key: ${CHANNEL_LIMIT_ADMIN_KEY}" -H 'content-type: application/json' \
    -d "{\"broadcast_id\":\"${BROADCAST_ID}\",\"action\":\"clear\"}"
  echo
  mark clear
  echo "해제 후 ${RELAPSE_WINDOW_S}s 관측…"
  sleep "${RELAPSE_WINDOW_S}"
  p95="$(hot_value chat_propagation_p95_ms "${RELAPSE_WINDOW_S}")"
  echo "해제 후 p95=${p95:-없음} (기준 ${RECOVERY_P95_MAX_MS:-미지정})"
  printf '%s\n' "{\"p95_after_clear_ms\":${p95:-null},\"window_s\":${RELAPSE_WINDOW_S}}" >"${RUN_DIR}/relapse.json"
  ;;

teardown)
  run_dir
  left="$(valkey keys 'cfg:channel_limit:*')"
  [ -z "${left}" ] || die "제한이 남아 있습니다: ${left}"
  pid="$(cat "${RUN_DIR}/k6.pid" 2>/dev/null || true)"
  [ -z "${pid}" ] || ! kill -0 "${pid}" 2>/dev/null || echo "경고: k6(${pid})가 아직 돕니다."

  # 부하 생성기가 먼저 막혔으면 위의 지표는 서버 상태가 아니라 노트북 상태다.
  [ ! -f "${RUN_DIR}/k6-summary.json" ] || python3 - "${RUN_DIR}/k6-summary.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1])).get("metrics", {})
def c(name): return (m.get(name) or {}).get("count", 0)
print(f"k6: 연결 {c('ws_opened')} 실패 {c('ws_failed')} 조기종료 {c('ws_closed_early')} 깨진프레임 {c('chat_bad_frames')}")
if c("ws_failed") or c("ws_closed_early"):
    print("  경고: 부하 생성기 쪽 손실이 있습니다. 서버 지표를 그대로 믿지 마세요.")
PY

  # Phase 6 기록. 실행값·승인자·사용자 영향·복구 결과를 한 파일에 남긴다.
  # History 적재는 Agent 가 하고, 이것은 그 대조본이다.
  python3 - "${RUN_DIR}" "${APPROVER:-미기입}" <<'PY' >"${RUN_DIR}/record.json"
import json, os, sys
d, approver = sys.argv[1], sys.argv[2]
def load(name):
    p = os.path.join(d, name)
    return json.load(open(p)) if os.path.exists(p) else None
tl = {}
for line in open(os.path.join(d, "timeline.tsv")):
    epoch, iso, event = line.rstrip("\n").split("\t")
    tl[event] = iso
verdict = os.path.join(d, "verdict.txt")
print(json.dumps({
    "broadcast_id": os.environ.get("BROADCAST_ID"),
    "applied": load("apply.json"),
    "approval_evidence": load("approval.json"),
    "baseline": load("baseline.json"),
    "relapse_after_clear": load("relapse.json"),
    "approver": approver,
    "result": "RESOLVED" if "recovered" in tl else "NOT_RECOVERED",
    "verdict": open(verdict).read().strip() if os.path.exists(verdict) else None,
    "timeline": tl,
}, ensure_ascii=False, indent=2))
PY
  echo "기록: ${RUN_DIR}/record.json"

  echo "--- 타임라인"
  cat "${RUN_DIR}/timeline.tsv"
  echo "--- 구간"
  awk -F'\t' '{t[$3]=$1} END{
    if (t["inject"] && t["apply"])     printf "탐지+진단+승인+적용: %ds\n", t["apply"]-t["inject"]
    if (t["approval_request"] && t["approval_granted"]) printf "  그중 사람 대기: %ds\n", t["approval_granted"]-t["approval_request"]
    if (t["apply"] && t["recovered"])  printf "적용→복구 확인: %ds\n", t["recovered"]-t["apply"]
  }' "${RUN_DIR}/timeline.tsv"
  echo "다음 실행 전에 Datadog 모니터가 OK 로 돌아왔는지 직접 확인하세요 — ALERT 로 남으면 다음 실행에서 Agent 가 안 깨어납니다."
  ;;

selftest)
  # 판정 규칙만 검사한다. 클러스터도 부하도 필요 없다.
  RECOVERY_P95_MAX_MS=800 ITEMS_PER_SEC_MAX=20000
  export RECOVERY_P95_MAX_MS ITEMS_PER_SEC_MAX
  judge 500 1200 18000 >/dev/null   || die "정상 복구가 통과해야 합니다"
  ! judge 900 1200 18000 >/dev/null || die "SLO 미복귀가 통과했습니다"
  ! judge 500 400 18000 >/dev/null  || die "기준선 대비 악화가 통과했습니다(자연 회복 오인)"
  ! judge 500 1200 40000 >/dev/null || die "처리량 미복귀가 통과했습니다"
  # 차단률이 높아도 판정은 통과해야 한다 — 조치가 잘 들수록 오르는 값이라
  # 성공 조건에 두면 조치가 자기 성공과 싸운다(런북 2026-08-26 변경과 같은 축).
  judge 500 1200 18000 >/dev/null   || die "차단률과 무관하게 판정돼야 합니다"
  # verify 가 판정을 받아 적는 방식 그대로. 파이프로 넘기면 종료 코드가
  # 마지막 명령 것이 되어 미달이 통과로 뒤집힌다 — 그 회귀를 여기서 막는다.
  v="$(judge 900 1200 0.01 18000)" && rc=0 || rc=1
  [ "${rc}" -eq 1 ] && [ -n "${v}" ] || die "판정 결과가 종료 코드로 전달되지 않습니다"
  echo "selftest OK"
  ;;

*)
  sed -n '3,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  ;;
esac
