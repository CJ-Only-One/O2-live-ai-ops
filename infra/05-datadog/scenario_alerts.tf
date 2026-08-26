###############################################################################
# S1·S2·S3 조기 감지 Alert
#
# `monitor.tf` 는 옛 트랜스크립트 5개 시나리오(번호 1·2·4·5·6)의 구현이다.
# 이 파일은 **확정된 S1·S2·S3 세트**를 위한 것이고, 목적이 하나 더 있다 —
# **사용자 영향이 나기 전에 원인 축에서 먼저 잡는다.**
#
# ## 왜 기존 Monitor 로 안 되나
#
# | 시나리오 | 기존 Monitor | 못 잡는 이유 |
# |---|---|---|
# | S1 | `chat_ingest_surge` | **인입(발화 수)만 본다.** 장애는 `발화 수 × 접속자 수` 이고, 주입 설계는 연결 축으로 올린다(scenario-experiment.md 2.2, M-010 해석 2). 발화율을 안 올리는 주입에서는 안 운다 |
# | S2 | `order_latency_p95` | 임계 1,000ms 에 5분 full window. 서버측 평시 p95 는 6ms(M-016)라 **꼬리가 다 무너진 뒤에야** 운다 |
# | S3 | 없음 | 결제·PG 축 Monitor 가 하나도 없다. `failure_rate_*` 는 대시보드 색깔 전용이다(terraform.tfvars) |
#
# ## 라우팅 규칙 — 시나리오당 진입 알림 하나
#
# 2026-08-26: Correlator가 운영 모드로 열렸다(`incident_operational_handoff_approved
# =true`, `09-incident/terraform.tfvars`). 옛 직결 경로(`@webhook-o2-dify` →
# `o2-dify-ingress` → Lambda 비동기 큐 → `o2-dify-worker` → Dify, 상관관계 계층
# 없음)와 새 경로(`@webhook-o2-incident-entry` → Datadog Source Adapter → Signal
# Queue → Incident Correlator → Agent Invocation Queue → Generic Worker → Dify)를
# **같은 Monitor에 동시에 붙이지 않는다** — 둘 다 붙이면 한 장애에 에이전트가 두 번
# 깨어난다(T-017과 같은 문제). 시나리오별 유일한 진입 Monitor는 이제 새 경로만
# 쓴다: S1 `s1_chat_fanout_volume`, S2 `s2_api_tail_latency`.
#
# 나머지(evidence 축, 예: `chat_propagation_p95`·`chat_block_rate`)는 같은
# `@webhook-o2-incident-entry`를 붙여 Correlator에 corroborating evidence로
# 들어가게 하되, `incident_datadog_monitor_map`에서 `evidence_role`을
# `CORROBORATING`으로 등록해 진입(entry) 판정 자체는 갖지 않게 한다.
#
# ## 임계값의 출처를 구분한다
#
# `docs/measurements.md` 에 실측이 있는 것과 없는 것을 섞지 않는다. 아래 표의
# "출처" 가 `M-0NN` 이면 실측이고, `정책값` 이면 **안 쟀다.** 정책값은 첫 S1·S2·S3
# 실험에서 실제 분포를 재고 `measurements.md` 의 해당 절에 행을 추가한 뒤 갱신한다.
###############################################################################

###############################################################################
# 공통 — distribution percentile 활성화
#
# T-031: Datadog distribution 은 percentile 집계가 **기본으로 꺼져 있다.**
# `include_percentiles = true` 를 관리하지 않는 metric 은 `avg:` 는 되고
# `p95:` 는 series 0 이다. 오류가 아니라 조용한 No Data 라 알아채기 늦다.
#
# S3 의 `pg_latency_p95` 가 이 metric 을 쓰므로 여기서 같이 켠다.
# `chat_propagation_metric.tf` 와 같은 패턴이다.
#
# ★ `tags` 는 **조회 가능한 축을 이 목록으로 제한한다.** 앱이 보내는 태그
#   전부를 적어야 한다 — 빠뜨린 축은 기존 위젯에서도 사라진다.
#   api(`app/core/telemetry.py`)는 공통 태그 4개 + `operation`,
#   chat-gateway(`src/telemetry.ts:92`)는 공통 태그 + `operation` 을 보낸다.
#
# ★ 이 metric 에 이미 콘솔/API 로 만든 설정이 있으면 apply 가 409 로 실패한다.
#   그때는 `chat_propagation_metric.tf` 처럼 `import` 블록을 붙여 인수한다.
###############################################################################

resource "datadog_metric_tag_configuration" "operation_duration" {
  count = var.enable_operation_duration_percentiles ? 1 : 0

  metric_name         = "o2.app.operation.duration"
  metric_type         = "distribution"
  tags                = ["env", "service", "version", "operation", "pod_name"]
  include_percentiles = true
}

###############################################################################
# S1 — 채팅 총량 초과 (진입: fanout 총량)
#
# `o2.app.fanout.items` 가 **`발화 수 × 접속자 수` 그 자체다.**
# `apps/chat-gateway/src/main.ts:113` 이 틱마다 실제 전송한 아이템 수를 센다.
# M-010 의 `아이템/s` 열과 같은 값이고, 그 표가 이 Monitor 의 임계 근거다.
#
# | 아이템/s | 전파 p95 | 출처 |
# |---|---|---|
# | 20,000 | 267ms | M-010 — **2파드 기준 안전선** |
# | 40,000 | 479~1,286ms | M-010 — 무너지는 지점 |
#
# warning 은 안전선, critical 은 그 사이다. **30,000 은 안 쟀다** — 20,000 과
# 40,000 사이를 잰 표본이 없다. 첫 S1 실험에서 계단을 잘게 올려 붕괴가 시작되는
# 실제 값을 찾고 이 값을 갈아치운다.
#
# 창이 2분인 것은 `chat_ingest_surge` 와 같은 이유다 — 주문 p95 가 무너지기 전에
# 울어야 조기 경보다.
###############################################################################

resource "datadog_monitor" "s1_chat_fanout_volume" {
  count = var.enable_scenario_alerts ? 1 : 0

  name = "[O2][S1] 채팅 팬아웃 총량 — 채널 감당선 접근"
  type = "metric alert"

  query = "avg(last_${var.scenario_early_window_minutes}m):sum:o2.app.fanout.items{service:chat-gateway,env:${local.monitor_env},result:delivered}.as_rate() >= ${var.s1_fanout_items_critical}"

  message = <<-EOT
    채팅 전파 총량이 초당 ${var.s1_fanout_items_critical} 아이템을 넘었습니다.

    **이 값이 무엇인가** — `발화 수 × 접속자 수` 입니다. 채팅 한 건이 접속자
    전원에게 가므로 전달량은 곱으로 불어납니다. 인입(발화 수)만 보면 이 폭증을
    놓칩니다 — 발화율이 그대로여도 시청자가 늘면 총량은 넘습니다.

    **근거** — M-010 실측에서 2파드 안전선은 20,000 아이템/s(전파 p95 267ms)이고
    40,000 에서 무너졌습니다(p95 479~1,286ms). 지금은 그 사이입니다.

    **다음에 볼 것** — `[O2][S1] Chat 전파 p95 지연` 이 함께 오르면 이미 사용자가
    겪고 있습니다. 조치 후보는 채널 총량 상한(`limit_channel_volume`)이고,
    **비가역입니다** — 거부된 발화와 떠난 시청자는 안 돌아옵니다. 승인을 받으세요.

  EOT

  monitor_thresholds {
    warning  = var.s1_fanout_items_warning
    critical = var.s1_fanout_items_critical
  }

  # 방송이 없으면 팬아웃도 0 이다. 정상적인 공백이라 경보하지 않는다.
  notify_no_data      = false
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["env:${local.monitor_env}", "scenario:s1", "service:chat-gateway", "role:entry"])
}

# 전파 실패는 지연과 다른 축이다 — 느린 것이 아니라 **못 간 것**이다.
# `main.ts:89` 이 백프레셔로 버린 아이템을 센다. evidence 축이라 webhook 은 없다.
resource "datadog_monitor" "s1_chat_fanout_dropped" {
  count = var.enable_scenario_alerts ? 1 : 0

  name = "[O2][S1] 채팅 전파 유실"
  type = "metric alert"

  query = "max(last_${var.scenario_early_window_minutes}m):sum:o2.app.fanout.items{service:chat-gateway,env:${local.monitor_env},result:dropped}.as_rate() > ${var.s1_fanout_dropped_critical}"

  message = <<-EOT
    채팅 전파가 초당 ${var.s1_fanout_dropped_critical} 건 넘게 버려지고 있습니다.

    지연이 아니라 **유실**입니다. M-010 전 구간에서 전달률이 99.9% 아래로 내려간
    적이 없으므로, 이 값이 0 이 아니면 실측 범위 밖입니다.

    `CHAT_PROPAGATION_DROP` evidence 로 S1 판단에 씁니다.
  EOT

  monitor_thresholds {
    critical = var.s1_fanout_dropped_critical
  }

  notify_no_data      = false
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["env:${local.monitor_env}", "scenario:s1", "service:chat-gateway", "role:impact"])
}

###############################################################################
# S2 — 카나리 느린 파드 (진입: 서비스 꼬리 지연)
#
# **p95 가 아니라 p99 다.** 파드 하나가 느릴 때 그 파드의 몫이 전체의 5% 미만이면
# p95 는 안 움직이고 p99 만 움직인다(`o2warm/metrics.py:426` 의 같은 지적).
# 조기 감지의 핵심이 여기다 — 꼬리가 먼저 벌어진다.
#
# **파드 축으로 나누지 않는다.** 확정안이 "1차는 넓게 조사하고 2차에 세부"를
# 요구한다. 파드별 이상치(`latency_p95_pod_outlier`)는 재진단 단계의 재료이므로
# 진입 알림이 되면 안 된다 — 그래서 그쪽 webhook 을 뗐다(monitor.tf).
#
# 임계는 **정책값이다. 안 쟀다.**
#   - 평시 서버측 p95 = 6ms (M-016, 10 RPS). p99 의 평시 분포는 표본이 없다
#   - 계약 상한 = p95 800ms · p99 2,000ms (architecture.md 12.1)
# 둘 사이에서 골랐다. **계약을 깨기 전에 우는 것**이 이 Monitor 의 정의다.
# M-009 의 숫자(p95 314ms @300RPS 등)는 ALB 경유 클라이언트 관점이라 서버측
# span metric 인 여기에는 그대로 못 쓴다.
#
# `trace.fastapi.request` 의 Datadog API 단위는 **second** 다(M-016). 변수는 ms 를
# 유지하고 비교 임계만 1000 으로 나눈다 — `order_latency_p95` 와 같은 처리다.
###############################################################################

resource "datadog_monitor" "s2_api_tail_latency" {
  count = var.enable_scenario_alerts ? 1 : 0

  name = "[O2][S2] API 꼬리 지연 — p99 조기 감지"
  type = "metric alert"

  query = "max(last_${var.scenario_early_window_minutes}m):p99:trace.fastapi.request{service:${var.default_service},env:${local.monitor_env}} >= ${var.s2_tail_latency_p99_critical_ms / 1000}"

  message = <<-EOT
    API 응답 p99 가 ${var.s2_tail_latency_p99_critical_ms}ms 를 넘었습니다.

    **p95 가 아니라 p99 를 보는 이유** — 파드 하나만 느린 상황에서 그 파드의 몫이
    전체의 5% 미만이면 p95 는 움직이지 않습니다. 꼬리가 먼저 벌어집니다.

    **먼저 넓게 보세요.** 지표만 보면 흔한 용량 부족처럼 보이고, 실제로 조여진
    파드는 상한에 막혀 CPU 를 **적게** 씁니다 — 1차 지표에서는 한가한 파드입니다.
    범용 지연 런북(증설)은 가역이고 예산 안이므로 자동 실행 대상입니다.

    **증설로 p50 만 좋아지고 p99 가 그대로면 그것이 새 증거입니다.** 같은 조치를
    반복하지 말고 파드별로 쪼개 다시 보세요(`o2.apm.request.duration by pod_name`).

    @webhook-o2-dify
  EOT

  monitor_thresholds {
    warning  = var.s2_tail_latency_p99_warning_ms / 1000
    critical = var.s2_tail_latency_p99_critical_ms / 1000
  }

  # dev 에 상시 트래픽이 없다. `order_latency_p95` 가 08-19~08-21 사흘 동안
  # No Data 와 Recovered 를 7번 왕복한 것과 같은 이유로 끈다.
  notify_no_data      = false
  no_data_timeframe   = 10
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["env:${local.monitor_env}", "scenario:s2", "service:${var.default_service}", "role:entry"])
}

###############################################################################
# S3 — PG 외부 장애 (진입: 결제 처리 지연)
#
# **시나리오 진입점은 채팅이다.** 채팅 경로 8.0~8.7초 대 Datadog 트리거
# 63.6~68.4초(`docs/agent-entrypoint.md`). 이 Monitor 는 그 대조군이자 보강이지
# 1차 진입을 대체하지 않는다.
#
# 그리고 **지표는 "느리다" 까지만 말한다.** `failure_code` 가 `PG_TIMEOUT` 으로
# 몰려 있다는 것은 에이전트가 원시 이벤트를 파야(`query_athena`) 나온다.
# 그것이 S3 의 주제이므로 여기서 원인을 단정하는 Monitor 를 만들지 않는다.
#
# `apps/api/app/services/payment.py:157` 이 `pg_latency_ms` 를
# `o2.app.operation.duration{operation:payment.process}` 로 보낸다. 평시 PG 스텁
# 지연은 0ms(`PgStubConfig.delay_ms` 기본값)다.
#
# 임계는 **정책값이다. 안 쟀다.** 결제가 주문 응답의 일부이므로 계약 상한
# p95 800ms(architecture.md 12.1) 안에서 PG 가 차지할 수 있는 몫으로 잡았다.
# 값 단위는 ms 다 — DogStatsD 로 ms 를 그대로 보내므로 환산하지 않는다.
###############################################################################

resource "datadog_monitor" "s3_pg_latency_p95" {
  count = var.enable_scenario_alerts ? 1 : 0

  name = "[O2][S3] 결제 처리 지연 — PG 왕복 p95"
  type = "metric alert"

  query = "max(last_${var.scenario_entry_window_minutes}m):p95:o2.app.operation.duration{service:${var.default_service},env:${local.monitor_env},operation:payment.process} >= ${var.s3_pg_latency_p95_critical_ms}"

  message = <<-EOT
    결제 처리(`payment.process`) p95 가 ${var.s3_pg_latency_p95_critical_ms}ms 를 넘었습니다.

    **이 알림이 말하는 것은 "느리다" 까지입니다.** 우리가 느린 것인지 외부 PG 가
    느린 것인지는 이 값으로 갈리지 않습니다. 원시 이벤트에서 `failure_code` 분포와
    `pg_latency_ms` 가 전체 지연에서 차지하는 몫을 확인하세요.

    **조치 후보를 다 써도 안 되면 멈추세요.** 커넥션 풀을 넓히거나 타임아웃을
    조정해도 외부 PG 자체가 느린 것은 그대로입니다. 한도에 닿으면 무엇을 해봤고
    왜 안 됐는지를 정리해 사람에게 넘기는 것이 정답입니다.

    @webhook-o2-dify
  EOT

  monitor_thresholds {
    warning  = var.s3_pg_latency_p95_warning_ms
    critical = var.s3_pg_latency_p95_critical_ms
  }

  notify_no_data      = false
  no_data_timeframe   = 10
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["env:${local.monitor_env}", "scenario:s3", "service:${var.default_service}", "role:entry"])
}

# 결제 실패율. evidence 축이라 webhook 은 없다 — 위 지연 Monitor 가 진입이다.
#
# 분모는 **전체 시도**다(`business_event{event:payment.process}`). 실패 코드
# 분포로 나누지 않는 것은 D-069 가 S1 차단률에서 정한 것과 같은 이유다.
resource "datadog_monitor" "s3_payment_failure_rate" {
  count = var.enable_scenario_alerts ? 1 : 0

  name = "[O2][S3] 결제 실패율"
  # 비율(나눗셈) 쿼리도 `metric alert` 다 — `cache_hit_rate_low` 가 같은 모양으로
  # 이미 배포돼 있다. `query alert` 는 `outliers()`·`anomalies()` 쪽에서 쓴다.
  type = "metric alert"

  query = "max(last_${var.scenario_entry_window_minutes}m):sum:o2.app.failure{service:${var.default_service},env:${local.monitor_env},event:payment.process}.as_count() / sum:o2.app.business_event{service:${var.default_service},env:${local.monitor_env},event:payment.process}.as_count() >= ${var.s3_payment_failure_rate_critical}"

  message = <<-EOT
    결제 실패율이 ${var.s3_payment_failure_rate_critical} 를 넘었습니다.

    `PAYMENT_FAILURE_RATE` evidence 로 `PAYMENT_DEGRADATION` 판단에 씁니다
    (명세 §3 taxonomy).

    분모는 실패 코드 분포가 아니라 **전체 결제 시도**입니다.
  EOT

  monitor_thresholds {
    warning  = var.s3_payment_failure_rate_warning
    critical = var.s3_payment_failure_rate_critical
  }

  notify_no_data      = false
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["env:${local.monitor_env}", "scenario:s3", "service:${var.default_service}", "role:impact"])
}
