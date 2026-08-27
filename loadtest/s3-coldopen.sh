#!/usr/bin/env bash
# 발표 도입부용 S3 녹화 러너 — 라이브 화면만으로 "불만이 올라왔다가 멎는" 그림을 만든다.
#
#   평시 채팅 → 타임세일 오픈 → 결제 실패와 불만 도배 → (Agent가 PG-B로 우회)
#   → 결제 성공 → 불만이 저절로 멎음
#
# 이 스크립트가 하는 일은 셋뿐이다. **장애를 넣고, 사람 트래픽을 만들고, 끝나면
# 원래대로 돌린다.** PG-B 전환은 하지 않는다 — 그것은 승인을 받은 Agent가 하는
# 일이고, 여기서 대신 하면 녹화물은 연극이 된다.
#
# 불만 채팅은 반응형으로만 만든다(`COMPLAINT_ON_FAILURE_RATIO`). 자기 주문이 실제로
# 실패한 VU가 불만을 쓰고, 복구 뒤에는 확률이 선형 감소한다. 고정 발화
# (`CHAT_INCIDENT_RPS`)를 쓰면 우회 뒤에도 불만이 그대로 쏟아져 결말이 안 나온다.
#
# 사용 예:
#
#   BASE_URL=https://<ALB> WS_URL=wss://<ALB> \
#   PG_STUB_ADMIN_URL=https://<ALB>/api/admin/pg-stub PG_STUB_ADMIN_KEY=... \
#   PG_DELAY_MS=<실측> PG_FAIL_RATE=<실측> \
#   ORDER_RATE=<실측> ORDER_PRE_ALLOCATED_VUS=<실측> ORDER_MAX_VUS=<실측> \
#   CHAT_BASE_RPS=<실측> CHAT_SALE_RPS=<실측> \
#   CHAT_PRE_ALLOCATED_VUS=<실측> CHAT_MAX_VUS=<실측> \
#   RUN_DURATION=14m loadtest/s3-coldopen.sh
#
# 시작 전에 사람이 확인할 것 (스크립트가 대신 못 본다):
#
#   - verified PG-A 사례가 History에 있고 pg_external_failure 런북이 active인가
#     (없으면 1차 실행이 되어 ESCALATED로 끝난다 — 그건 이 녹화물이 아니다)
#   - Dify 워크플로의 PG_PROVIDER_SWITCH_URL 값이 채워져 있는가
#     (비어 있으면 조치가 mock으로 떨어져 결제가 안 낫는다)
#   - Slack L3 승인을 누를 사람이 대기 중인가 (화면 밖 일이지만 안 누르면 안 끝난다)

set -euo pipefail

BASE_URL="${BASE_URL:?BASE_URL 필요. 예: https://<ALB>}"
WS_URL="${WS_URL:?WS_URL 필요. 예: wss://<ALB>}"
PG_STUB_ADMIN_URL="${PG_STUB_ADMIN_URL:?PG_STUB_ADMIN_URL 필요}"
PG_STUB_ADMIN_KEY="${PG_STUB_ADMIN_KEY:?PG_STUB_ADMIN_KEY 필요}"
PG_DELAY_MS="${PG_DELAY_MS:?PG_DELAY_MS 필요. 스윕으로 확정한 값}"
PG_FAIL_RATE="${PG_FAIL_RATE:?PG_FAIL_RATE 필요. 스윕으로 확정한 값}"
ORDER_RATE="${ORDER_RATE:?ORDER_RATE 필요}"
ORDER_PRE_ALLOCATED_VUS="${ORDER_PRE_ALLOCATED_VUS:?ORDER_PRE_ALLOCATED_VUS 필요}"
ORDER_MAX_VUS="${ORDER_MAX_VUS:?ORDER_MAX_VUS 필요}"
CHAT_BASE_RPS="${CHAT_BASE_RPS:?CHAT_BASE_RPS 필요}"
CHAT_SALE_RPS="${CHAT_SALE_RPS:?CHAT_SALE_RPS 필요}"
CHAT_PRE_ALLOCATED_VUS="${CHAT_PRE_ALLOCATED_VUS:?CHAT_PRE_ALLOCATED_VUS 필요}"
CHAT_MAX_VUS="${CHAT_MAX_VUS:?CHAT_MAX_VUS 필요}"

# Agent 한 바퀴(알림 창 + 진단 + 승인 + 전환 + 검증 대기)보다 길어야 한다.
# 짧으면 회복 장면이 찍히기 전에 부하가 끝난다.
RUN_DURATION="${RUN_DURATION:?RUN_DURATION 필요. 예: 14m}"

# 평시 채팅 구간. 이 길이가 곧 k6의 CHAT_LEAD_SECONDS다 — 이 시간 동안은
# 상품 문의 채팅만 흐르고 주문은 아직 시작하지 않는다.
CALM_SECONDS="${CALM_SECONDS:-40}"
# 타임세일 오픈 후 결제가 멀쩡히 되는 구간. 성공 토스트를 먼저 보여줘야
# 뒤의 실패가 대비로 읽힌다. 진입 시드 4건도 이 구간 뒤로 밀린다 — 아직 아무도
# 실패하지 않았는데 불만이 먼저 오면 시나리오 전제가 거꾸로 찍힌다.
HEALTHY_SECONDS="${HEALTHY_SECONDS:-20}"
COMPLAINT_ON_FAILURE_RATIO="${COMPLAINT_ON_FAILURE_RATIO:-0.3}"
RECOVERY_COMPLAINT_DECAY_SECONDS="${RECOVERY_COMPLAINT_DECAY_SECONDS:-60}"

BROADCAST_ID="${BROADCAST_ID:-bc_1042}"
# 기본값은 seed.py에서 PENDING으로 들어가는 상품이다 — 화면에서 "아직 특가가
# 시작되지 않았습니다"가 구매 가능으로 바뀌는 순간이 타임세일 오픈 장면이 된다.
SALE_SKU="${SALE_SKU:-88216}"
# 녹화 도중 SOLD_OUT이 나면 결제 실패가 아니라 품절로 화면이 갈린다.
SALE_STOCK="${SALE_STOCK:-1000000}"
NAMESPACE="${NAMESPACE:-o2-dev}"

command -v k6 >/dev/null || { echo "k6가 없다"; exit 1; }
command -v kubectl >/dev/null || { echo "kubectl이 없다"; exit 1; }

if [ "$CALM_SECONDS" -lt 19 ]; then
  # k6가 CHAT_LEAD_SECONDS >= 17을 강제한다. 아래에서 2초를 빼 쓰므로 19가 하한이다.
  echo "CALM_SECONDS는 19 이상이어야 한다(k6의 CHAT_LEAD_SECONDS 하한 17 + 오픈 선행 2초)"
  exit 1
fi

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

# 상품 상태와 재고를 바꾼다. 재고 원본은 Valkey의 stock:{sku}이고 상태 원본은
# MySQL이라 둘 다 건드려야 한다(seed.py와 같은 규약).
product_state() {
  kubectl exec -i -n "$NAMESPACE" deploy/api -- python - "$SALE_SKU" "$@" <<'PY'
import sys

from app.db.session import SessionLocal
from app.db.valkey import valkey
from app.models.product import Product

sku_id = int(sys.argv[1])
state = sys.argv[2] if len(sys.argv) > 2 else None
stock = sys.argv[3] if len(sys.argv) > 3 else None

with SessionLocal() as db:
    product = db.query(Product).filter(Product.sku_id == sku_id).one()
    if state is None:
        # 읽기 모드 — 원복에 쓸 현재 값을 그대로 뱉는다.
        # valkey 클라이언트가 decode_responses=True 라 문자열로 온다.
        print(f"{product.state} {valkey.get(f'stock:{sku_id}')}")
    else:
        product.state = state
        db.commit()
        valkey.set(f"stock:{sku_id}", stock)
        print(f"{state} {stock}")
PY
}

pg_stub() {
  curl -fsS -X POST "$PG_STUB_ADMIN_URL" \
    -H "x-admin-key: $PG_STUB_ADMIN_KEY" \
    -H 'content-type: application/json' \
    -d "$1" >/dev/null
}

ORIGINAL=""
TORN_DOWN=false
teardown() {
  $TORN_DOWN && return 0
  TORN_DOWN=true
  echo
  # Ctrl-C 로 들어온 경우 k6 가 아직 살아 있다. 부하를 남긴 채 주입만 풀면
  # 화면에는 장애가 아닌 정상 트래픽이 계속 흐른다.
  if [ -n "${K6_PID:-}" ] && kill -0 "$K6_PID" 2>/dev/null; then
    log "정리 — k6 종료"
    kill "$K6_PID" 2>/dev/null || true
    wait "$K6_PID" 2>/dev/null || true
  fi
  log "정리 — PG 주입 해제"
  pg_stub '{"action":"clear"}' || log "PG 주입 해제 실패. 손으로 확인해라"
  if [ -n "$ORIGINAL" ]; then
    log "정리 — 상품 $SALE_SKU 원복 ($ORIGINAL)"
    # shellcheck disable=SC2086
    product_state $ORIGINAL >/dev/null || log "상품 원복 실패. 손으로 확인해라"
  fi
  log "정리 끝. PG-B로 전환된 상태면 /api/admin/pg-provider-switch 로 되돌린다"
}
trap teardown EXIT INT TERM

ORIGINAL="$(product_state)"
log "상품 $SALE_SKU 현재 상태: $ORIGINAL (끝나면 이 값으로 되돌린다)"

log "부하 시작 — 평시 채팅 ${CALM_SECONDS}초 뒤 타임세일 오픈, 복구 불만 감쇠 ${RECOVERY_COMPLAINT_DECAY_SECONDS}초, 총 $RUN_DURATION"
k6 run \
  -e BASE_URL="$BASE_URL" -e WS_URL="$WS_URL" \
  -e BROADCAST_ID="$BROADCAST_ID" -e SKU_ID="$SALE_SKU" \
  -e DURATION="$RUN_DURATION" \
  -e CHAT_LEAD_SECONDS="$CALM_SECONDS" \
  -e RATE="$ORDER_RATE" \
  -e PRE_ALLOCATED_VUS="$ORDER_PRE_ALLOCATED_VUS" -e MAX_VUS="$ORDER_MAX_VUS" \
  -e CHAT_BASE_RPS="$CHAT_BASE_RPS" -e CHAT_SALE_RPS="$CHAT_SALE_RPS" \
  -e CHAT_INCIDENT_RPS=0 \
  -e INCIDENT_SEED_DELAY_SECONDS="$((HEALTHY_SECONDS + 4))" \
  -e COMPLAINT_ON_FAILURE_RATIO="$COMPLAINT_ON_FAILURE_RATIO" \
  -e RECOVERY_COMPLAINT_DECAY_SECONDS="$RECOVERY_COMPLAINT_DECAY_SECONDS" \
  -e CHAT_PRE_ALLOCATED_VUS="$CHAT_PRE_ALLOCATED_VUS" -e CHAT_MAX_VUS="$CHAT_MAX_VUS" \
  loadtest/s3-payment.js &
K6_PID=$!

# 주문은 CHAT_LEAD_SECONDS에 시작한다. 오픈이 1초라도 늦으면 첫 주문들이
# NOT_STARTED(409)로 떨어져 k6 임계(orders_unexpected_response==0)가 깨진다.
sleep "$((CALM_SECONDS - 2))"
log "타임세일 오픈 — $SALE_SKU ON_SALE, 재고 $SALE_STOCK"
product_state ON_SALE "$SALE_STOCK" >/dev/null

sleep "$((HEALTHY_SECONDS + 2))"
log "PG-A 장애 주입 — delay_ms=$PG_DELAY_MS fail_rate=$PG_FAIL_RATE"
pg_stub "{\"action\":\"set\",\"delay_ms\":${PG_DELAY_MS},\"fail_rate\":${PG_FAIL_RATE}}"
log "여기서부터 결제 실패와 불만 채팅이 오른다. 조치는 Agent가 한다 — 손대지 마라"

wait "$K6_PID"
log "부하 종료"
