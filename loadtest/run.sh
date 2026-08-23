#!/usr/bin/env bash
# 계단마다 k6 를 돌리면서 파드 CPU·메모리를 같이 샘플링해 표 하나로 낸다.
#
# k6 는 증상(p95, 실패율)만 본다. 어느 자원이 바닥나서 그렇게 됐는지는 안 나온다.
# 그 귀속을 붙이는 게 이 스크립트의 전부다. 손으로 하면 스크립트 3개 ×
# 계단 6개 = 18번 시간대를 맞춰야 하고, 한 번 어긋나면 표 전체가 틀린다.
#
#   ALB=k8s-o2dev-frontend-...elb.amazonaws.com
#
#   BASE_URL=http://$ALB loadtest/run.sh read-path.js RATE    10 25 50 100 200 400
#   WS_URL=ws://$ALB     loadtest/run.sh broadcast.js VIEWERS 500 1000 2000 4000
#
# 결과는 loadtest/results/<타임스탬프>/ 에 남는다. 표는 그대로 measurements.md 로 옮긴다.
#
# 읽는 법 (CPU limit 을 일부러 안 걸었으므로 판정이 깔끔하다):
#   메모리가 limit 근처 + 파드 재시작  -> OOMKill. limit 올리거나 파드 늘린다
#   CPU 가 계단을 올려도 안 늘고 평평  -> CPU 포화. 인스턴스 승급
#   둘 다 여유인데 p95 만 상승          -> 앱 내부. **인스턴스 키워도 안 풀린다**
#
# 마지막 경우가 제일 중요하다. 돈 써도 안 고쳐지는 것을 여기서 거른다.
# 원인(이벤트 루프 블로킹 / Valkey RTT / DB 커넥션 풀)까지는 이 표가 못 준다.
# 후보를 셋에서 하나로 줄여줄 뿐이고, 그다음은 Datadog APM 트레이스다.

set -euo pipefail

SCRIPT="${1:?사용법: run.sh <k6 스크립트> <환경변수명> <계단...>}"
VAR="${2:?계단으로 바꿀 환경변수 이름. 예: RATE, VIEWERS}"
shift 2
STEPS=("$@")
[ ${#STEPS[@]} -gt 0 ] || { echo "계단 값을 하나 이상 줘라"; exit 1; }

NS="${NS:-o2-dev}"
# 부하를 받는 것만 본다. frontend·mediamtx 는 이 테스트에서 안 움직인다.
TRACK="${TRACK:-api chat-gateway order-worker}"
SAMPLE_SEC="${SAMPLE_SEC:-5}"

# AWS CLI v2 는 터미널에서 출력을 less 로 넘긴다. 스크립트 중간에 페이저가
# 뜨면 사람이 q 를 누를 때까지 멈춘다.
export AWS_PAGER=""

REGION="${REGION:-ap-northeast-2}"
VALKEY_NODE="${VALKEY_NODE:-o2-dev-valkey-001}"
# 읽기 경로의 inventory.check 와 채팅의 chat.send 가 같은 스트림을 쓴다.
KINESIS_STREAM="${KINESIS_STREAM:-stream-business}"
START_TS=$(date -u +%Y-%m-%dT%H:%M:%S)

cd "$(dirname "$0")/.."
OUT="loadtest/results/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"

echo "결과: $OUT"
echo "네임스페이스: $NS   추적: $TRACK"
echo

# 영점. 부하 없는 상태의 사용량을 안 찍어두면 나중에 그 CPU 가 앱 건지
# Datadog 에이전트 건지 구분 못 한다.
echo "== idle 영점 =="
kubectl top pods -n "$NS" | tee "$OUT/idle-pods.txt"
kubectl top nodes | tee "$OUT/idle-nodes.txt"
echo

for step in "${STEPS[@]}"; do
  echo "=== $VAR=$step ==="
  raw="$OUT/step-$step"

  # kubectl top 은 metrics-server 해상도가 약 15초라 5초 간격이면 값이
  # 반복된다. 그래도 상관없다 — 뒤에서 최댓값만 쓴다.
  (
    while :; do
      ts=$(date +%s)
      kubectl top pods -n "$NS" --no-headers 2>/dev/null | sed "s/^/$ts /" >> "$raw.pods"
      kubectl top nodes --no-headers 2>/dev/null | sed "s/^/$ts /" >> "$raw.nodes"
      # 부하 생성기가 먼저 포화하면 측정이 통째로 무효다. 서버만 보면
      # "서버가 느려졌다"와 "k6 가 못 따라갔다"를 구분 못 한다.
      pid=$(pgrep -x k6 | head -1)
      [ -n "$pid" ] && ps -o %cpu=,rss= -p "$pid" 2>/dev/null | sed "s/^/$ts /" >> "$raw.k6"
      sleep "$SAMPLE_SEC"
    done
  ) &
  sampler=$!
  trap 'kill $sampler 2>/dev/null || true' EXIT

  set +e
  # p(99) 는 기본 요약에 없다. 명시하지 않으면 표의 p99 열이 통째로 빈다.
  env "$VAR=$step" k6 run \
    --summary-trend-stats='avg,min,med,max,p(95),p(99)' \
    --summary-export="$raw.json" "loadtest/$SCRIPT" > "$raw.log" 2>&1
  k6_rc=$?
  set -e

  kill $sampler 2>/dev/null || true
  wait $sampler 2>/dev/null || true
  trap - EXIT

  # 재시작 = OOMKill 신호. 표에는 안 들어가지만 여기서 놓치면 안 된다.
  kubectl get pods -n "$NS" --no-headers | awk '$4+0 > 0 {print "  재시작:", $1, $4"회"}'

  set +e
  python3 loadtest/summarize.py "$OUT" "$VAR" "$step" "$k6_rc" "$TRACK"
  sum_rc=$?
  set -e

  # k6 임계(연결 실패·조기 종료·checks·dropped)와 전달률 판정을 둘 다 본다.
  # 전달률은 지표 두 개를 나눠야 나와서 k6 임계로 표현이 안 된다.
  if [ $k6_rc -ne 0 ] || [ $sum_rc -ne 0 ]; then
    echo
    echo "임계 초과. 여기가 포화점이다 — 위 계단은 큐 대기 시간만 나온다."
    echo "  상세: $raw.log"
    break
  fi

  # 다음 계단 전에 파드를 쉬게 둔다. 앞 계단의 큐가 남은 채로 시작하면
  # 그 지연이 다음 계단 값에 섞인다.
  sleep 20
done

# Valkey·Kinesis 는 두 스크립트가 **같이** 쓴다. 파드에 여유가 있는데 지연이
# 늘면 범인이 여기다. CloudWatch 는 해상도 60초에 지연이 1~2 분이라 계단마다
# 물으면 빈 값이 나온다 — 전 구간을 한 번에 받아 타임스탬프로 맞춘다.
echo
echo "== 공유 자원 (CloudWatch, 전 구간) =="
END_TS=$(date -u +%Y-%m-%dT%H:%M:%S)
for m in EngineCPUUtilization CurrConnections CacheHits CacheMisses; do
  printf '  Valkey %-22s ' "$m"
  aws cloudwatch get-metric-statistics --region "$REGION" \
    --namespace AWS/ElastiCache --metric-name "$m" \
    --dimensions Name=CacheClusterId,Value="$VALKEY_NODE" \
    --start-time "$START_TS" --end-time "$END_TS" --period 60 --statistics Maximum \
    --query 'max(Datapoints[].Maximum)' --output text 2>/dev/null || echo "-"
done | tee "$OUT/valkey.txt"

# 1 샤드는 1,000 records/sec 가 상한이다. 넘으면 SDK 가 조용히 버린다.
printf '  Kinesis %-21s ' "쓰기 스로틀"
aws cloudwatch get-metric-statistics --region "$REGION" \
  --namespace AWS/Kinesis --metric-name WriteProvisionedThroughputExceeded \
  --dimensions Name=StreamName,Value="$KINESIS_STREAM" \
  --start-time "$START_TS" --end-time "$END_TS" --period 60 --statistics Sum \
  --query 'sum(Datapoints[].Sum)' --output text 2>/dev/null || echo "-"

echo
python3 loadtest/summarize.py "$OUT" --table "$TRACK"

# 지우는 것은 사람이 한다. 측정 스크립트가 데이터를 지우면, 측정할 생각이 없던
# 사람이 run.sh 를 열어보다 실제 기준선을 날린다.
cat <<'REMIND'

== 끝나고 할 것 ==

1. 평시 기준(baseline)을 지운다.
   집계 Lambda 가 EWMA 로 "평시 rps" 를 학습하는데, 부하 구간이 거기 섞인다.
   스파이크 가드는 samples >= 30 일 때만 걸리므로 처음 30 개 창은 그대로 학습된다.
   안 지우면 평시 기준이 부하 수준으로 박혀 조기 경보가 영영 안 울린다.

   aws dynamodb scan --table-name o2-agent-context --region ap-northeast-2 \
     --filter-expression "sk = :s" \
     --expression-attribute-values '{":s":{"S":"BASELINE#RPS"}}' \
     --query 'Items[].pk.S' --output text
   # 나온 pk 마다:
   #   aws dynamodb delete-item --table-name o2-agent-context --region ap-northeast-2 \
   #     --key '{"pk":{"S":"<pk>"},"sk":{"S":"BASELINE#RPS"}}'
   # delete-item 은 성공해도 출력이 없다. 위 scan 을 다시 돌려 0 건인지 본다.

2. Datadog Downtime 을 푼다. 대상 모니터가 전부 OK 인지 보고 푼다 —
   No Data 나 ALERT 상태에서 끝나면 그 순간 알림이 나간다.

3. 표를 docs/measurements.md 로 옮긴다. 인덱스 한 줄도 같이 (CI 가 막는다).

REMIND
