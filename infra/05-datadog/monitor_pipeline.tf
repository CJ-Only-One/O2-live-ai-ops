###############################################################################
# 파이프라인 생존·지연 Monitor
#
# `monitor.tf` 는 **서비스가 아픈 것**을 잡는다. 이 파일은 **관측 경로 자체가
# 죽은 것**을 잡는다. 둘은 다른 종류다 — 앞의 것이 조용한 이유가 "정상이라서"
# 인지 "지표가 안 와서" 인지 구분할 수단이 없으면 대시보드 전체가 무의미해진다.
#
# 근거는 D-052. 요약하면:
#
#   - 인입·집계·전송이 전부 예외를 삼킨다(가용성 우선, 옳은 선택이다)
#   - 그 stderr 는 `04-platform` 의 `logs.enabled = false` 라 Datadog 에 안 온다
#   - 그래서 파이프라인이 통째로 멈춰도 대시보드는 조용하다
#
# **실제 트래픽 지표에 no-data 를 걸면 안 된다.** 한산할 때 장애와 구분되지
# 않아서 결국 꺼진다 — `monitor.tf` 의 `order_latency_p95` 가 사흘 동안 7번
# 왕복하고 꺼진 것이 그 사례다. 그래서 생존 신호는 06-datastream 의 카나리가
# **스스로 만든 트래픽** 위에 세운다.
###############################################################################

variable "canary_service" {
  description = <<-EOT
    파이프라인 카나리의 service 태그. `06-datastream` 의
    `output.canary_service_tag` 와 같아야 한다.

    다르면 이 Monitor 가 영구 No Data 가 되고, 그러면 **생존 감시가 죽었다는
    것을 생존 감시가 알려주지 못하는** 상태가 된다.
  EOT
  type        = string
  default     = "o2-canary"
}

variable "canary_no_data_minutes" {
  description = <<-EOT
    카나리 신호가 이 시간(분) 동안 없으면 파이프라인이 끊긴 것으로 본다.

    카나리 주입 간격(`06-datastream` 의 `canary_interval_minutes`, 기본 1분)
    보다 넉넉해야 한다. 집계 윈도우 10초 + Datadog 수집 지연을 감안해도
    15분이면 "일시적 지연" 이 아니라 "끊김" 이라고 볼 수 있다.
  EOT
  type        = number
  default     = 15
}

###############################################################################
# 파이프라인 끊김 — 카나리 신호 소실
#
# **이 Monitor 의 본체는 임계가 아니라 `notify_no_data` 다.** 카나리가 도는
# 한 `rps` 는 항상 0보다 크므로 임계 조건은 사실상 안 걸린다. 시계열이
# **사라지는 것** 자체가 알림 조건이다.
#
# 어디가 끊겼는지는 이 알림이 말해주지 않는다. 그건 아래 구간별 Monitor 와
# `aws.lambda.*` 의 일이다. 이 알림은 "끊겼다" 만 말한다 — 그리고 그것이
# 지금 완전히 비어 있는 자리다.
###############################################################################

resource "datadog_monitor" "warm_pipeline_stalled" {
  name    = "[O2][파이프라인] warm 경로 끊김 — 카나리 신호 소실"
  type    = "metric alert"
  message = <<-EOT
    합성 카나리 이벤트가 ${var.canary_no_data_minutes}분 동안 집계 결과로
    나오지 않았습니다. **인입 → 집계 → Datadog 전송 중 어딘가가 끊겼습니다.**

    **이건 서비스 장애 알림이 아닙니다.** 관측 경로가 죽었다는 뜻이고, 그동안
    다른 모든 비즈니스 Monitor 가 조용한 이유는 "정상이라서" 가 아니라
    "지표가 안 와서" 입니다. 다른 알림을 신뢰하기 전에 이것부터 봅니다.

    **볼 순서** — 카나리는 1분마다 `stream-business` 에 레코드를 하나 넣습니다.
    그 레코드가 `o2.warm.rps{service:${var.canary_service}}` 로 나와야 정상입니다.

    1. `o2-canary` Lambda 가 도는가 (EventBridge 스케줄, Lambda 오류)
    2. `stream-business` 에 레코드가 들어가는가 (Kinesis 인입)
    3. `o2-agg` 가 도는가 (이벤트 소스 매핑 활성, Lambda 오류·스로틀)
    4. 집계 결과가 Datadog 으로 가는가 (`datadog.submit()` 은 실패를 삼킵니다 —
       API 키 회전이 대표적인 원인입니다. `o2/dev/datadog-new` 를 씁니다)

    **집계기는 실패해도 예외를 안 냅니다.** 4번에서 끊기면 DynamoDB 에는
    데이터가 쌓이는데 Datadog 만 비는 모양이 됩니다 — 그때 warm-api 의
    `/metrics` 를 직접 찔러 보면 어느 쪽인지 갈립니다.

    @webhook-o2-dify
  EOT

  # 임계는 안 걸리게 둔다. rps 가 존재하는 한 항상 0보다 크다.
  # 실제 동작하는 것은 notify_no_data 다.
  query = "avg(last_${var.canary_no_data_minutes}m):avg:${var.metric_prefix}rps{service:${var.canary_service},env:${local.monitor_env}} <= 0"

  monitor_thresholds {
    critical = 0
  }

  notify_no_data    = true
  no_data_timeframe = var.canary_no_data_minutes

  # require_full_window 를 켜면 안 된다. 카나리는 1분에 한 번이라 10초 윈도우
  # 대부분이 비어 있고, 전체 윈도우를 요구하면 평상시에도 평가가 안 된다.
  require_full_window = false

  # 끊긴 상태가 이어지면 다시 알린다. 이 알림은 "고칠 때까지 유효" 하다.
  renotify_interval = 60

  tags = concat(local.monitor_tags, ["scope:pipeline", "role:page", "signal:canary"])
}

###############################################################################
# 집계기 지연 — Kinesis 를 못 따라간다 (기본 비활성)
#
# **실측(M-014)에서 실제로 관측된 상태다.** 2026-08-23 부하 중
# `IteratorAge` 가 17초 → 102초로 올랐고, 그동안 오류는 0 이었다. 즉
# "실패" 가 아니라 "밀림" 이라 어떤 오류 기반 알림에도 안 걸린다.
#
# 이게 왜 중요한가 — 명세의 자기 교정 루프가 **조치 후 90초 뒤 재확인**을
# 전제로 한다. 집계가 100초 밀려 있으면 그때 읽는 값은 조치 이전 값이다.
# **에이전트가 자기 조치의 효과를 반대로 판정한다.**
#
# **확인했다. 켠다.** 2026-08-24, Datadog API 로 조회한 결과(M-015):
#
#   sum:aws.lambda.invocations{*} by {functionname}   → series 12 (o2-agg 포함)
#   avg:aws.lambda.iterator_age{*} by {functionname}  → functionname:o2-agg 있음
#   sum:aws.lambda.errors{*} by {functionname}        → series 12
#
# 이것이 이 Monitor 를 껐던 유일한 사유였다. 사유가 해소됐으므로 기본값을
# `true` 로 바꾼다. **사유가 낡은 채로 남으면 안 된다** — `chat_ingest_surge`
# 가 "Kinesis 경로가 아직 없다" 는 낡은 사유를 달고 몇 주를 꺼져 있었다(F-3).
#
# **다만 데이터포인트가 성기다.** 24시간 구간에서 `invocations`·`errors` 는
# 288 포인트(5분 간격이 꽉 참)인데 `iterator_age` 는 18 포인트뿐이다.
# CloudWatch 가 스트림이 실제로 움직일 때만 이 지표를 내보내기 때문이고,
# M-014 의 "48시간 중 42시간이 6시간당 5건" 분포와 정확히 일치한다.
#
# 그래서 아래 두 Monitor 의 `notify_no_data` 는 **반드시 false 여야 한다.**
# 켜면 한산한 밤마다 울리고, `order_latency_p95` 가 사흘 만에 꺼진 것과
# 똑같은 일이 벌어진다. 생존 감시는 위의 카나리 몫이고, 이 둘은 "밀린다"
# 와 "터진다" 만 잡는다 — D-052 가 굳이 역할을 나눠 둔 이유가 그것이다.
###############################################################################

variable "enable_aggregator_lag_monitor" {
  description = <<-EOT
    집계기 지연(`warm_aggregator_lag`)·오류(`warm_aggregator_errors`)
    Monitor 활성화 여부. 기본 `true`.

    **변수 하나가 리소스 둘을 건다.** 밀림과 터짐은 원인이 이어져 있어
    (오류 → 재시도 누적 → 지연) 따로 켤 일이 없다.

    2026-08-24 이전에는 기본 `false` 였다. 사유는 "`aws.lambda.*` 가 이
    조직에 수집되는지 확인하지 못했다" 였고, 그날 Datadog API 조회로
    수집이 확인됐다(M-015). 사유가 사라졌으므로 기본값을 뒤집었다.

    끌 이유가 생긴다면 그것은 **오탐**일 것이다. 그때는 이 변수를 끄기
    전에 `aggregator_lag_critical_seconds` 를 먼저 본다 — 90초는 임의값이
    아니라 자기 교정 루프의 재확인 대기와 같은 값이라, 이 값을 올리는 것은
    "밀려도 괜찮다" 가 아니라 "루프를 다시 설계했다" 를 뜻한다.
  EOT
  type        = bool
  default     = true
}

variable "aggregator_lag_warning_seconds" {
  description = <<-EOT
    집계기 지연 경고 임계(초). 기본 30.

    검증 루프가 90초 대기를 쓰므로, 그 3분의 1 지점에서 미리 알린다.
    실측 근거는 M-014 — 부하 중 102초까지 올라갔다.
  EOT
  type        = number
  default     = 30
}

variable "aggregator_lag_critical_seconds" {
  description = <<-EOT
    집계기 지연 위험 임계(초). 기본 90.

    **검증 루프 대기 시간과 같은 값이다.** 이 선을 넘으면 에이전트가 조치
    직후에 읽는 값이 조치 이전 값이 되어 자기 교정 판정이 뒤집힌다.
  EOT
  type        = number
  default     = 90
}

resource "datadog_monitor" "warm_aggregator_lag" {
  count = var.enable_aggregator_lag_monitor ? 1 : 0

  name    = "[O2][파이프라인] 집계기가 스트림을 못 따라간다"
  type    = "metric alert"
  message = <<-EOT
    `o2-agg` 의 `IteratorAge` 가 ${var.aggregator_lag_critical_seconds}초를
    넘었습니다. 집계기가 Kinesis 인입 속도를 못 따라가고 있습니다.

    **오류가 아니라 지연입니다.** Lambda 오류율은 0 일 수 있고, 실제로
    실측(M-014) 당시 0 이었습니다. 그래서 오류 기반 알림에는 안 걸립니다.

    **무엇이 깨지나** — warm 지표가 이 시간만큼 과거를 보여줍니다. 명세의
    자기 교정 루프는 조치 후 90초 뒤 재확인을 전제로 하는데, 집계가 그만큼
    밀려 있으면 **에이전트가 조치 이전 값을 조치 이후 값으로 읽습니다.**
    개선을 악화로, 악화를 개선으로 판정할 수 있습니다.

    **원인 후보** — `stream-business` 는 샤드 1개이고 이벤트 소스 매핑의
    `parallelization_factor` 도 1 입니다. 소비자가 사실상 직렬이라 인입이
    한 소비자의 처리량을 넘으면 구조적으로 밀립니다.

    - 부하 시험 중이면 정상적인 밀림입니다. 시험이 끝나면 따라잡는지 봅니다
    - 상시로 밀리면 샤드 수나 `parallelization_factor` 를 올려야 합니다
    - 집계 Lambda 의 `Duration` 이 함께 올랐는지 봅니다 — 그쪽이면 처리
      비용 문제입니다

    @webhook-o2-dify
  EOT

  # aws.lambda.iterator_age 의 단위는 밀리초다.
  query = "min(last_5m):avg:aws.lambda.iterator_age{functionname:o2-agg} >= ${var.aggregator_lag_critical_seconds * 1000}"

  monitor_thresholds {
    warning  = var.aggregator_lag_warning_seconds * 1000
    critical = var.aggregator_lag_critical_seconds * 1000
  }

  # AWS 통합 지표는 수집 주기가 길다. 인입이 없으면 이 지표도 안 온다 —
  # 그건 정상이므로 no-data 를 경보하지 않는다. 끊김 감지는 카나리 몫이다.
  notify_no_data      = false
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["scope:pipeline", "role:page", "signal:iterator-age"])
}

###############################################################################
# 집계기 오류 (기본 비활성 — 위와 같은 이유)
#
# 카나리는 "끊겼다" 를, 지연 Monitor 는 "밀린다" 를 잡는다. 이건 "터진다" 다.
# 집계 Lambda 가 예외로 죽으면 Kinesis 배치가 재시도되고, 재시도가 쌓이면
# 그 다음에 지연으로 번진다 — 이쪽이 먼저 울려야 원인이 짧다.
###############################################################################

resource "datadog_monitor" "warm_aggregator_errors" {
  count = var.enable_aggregator_lag_monitor ? 1 : 0

  name    = "[O2][파이프라인] 집계 Lambda 오류"
  type    = "metric alert"
  message = <<-EOT
    `o2-agg` 가 오류를 내고 있습니다. Kinesis 배치가 재시도되고, 재시도가
    쌓이면 `IteratorAge` 지연으로 번집니다.

    **집계기는 Datadog 전송 실패는 삼키지만 집계 자체의 실패는 안 삼킵니다.**
    그래서 여기 잡히는 것은 계산·저장 쪽 문제입니다 — 봉투 형식 변화,
    DynamoDB 스로틀, 메모리 부족이 흔한 원인입니다.

    로그는 `/aws/lambda/o2-agg` 에 있습니다.

    @webhook-o2-dify
  EOT

  query = "sum(last_5m):sum:aws.lambda.errors{functionname:o2-agg}.as_count() > 0"

  monitor_thresholds {
    critical = 0
  }

  notify_no_data      = false
  require_full_window = false
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["scope:pipeline", "role:page", "signal:lambda-errors"])
}
