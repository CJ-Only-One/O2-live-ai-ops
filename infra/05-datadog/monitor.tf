###############################################################################
# Monitor — failure-scenarios-transcript.md 의 5개 장애 시나리오
#
# 근거와 범위는 Confluence "Datadog 장애 대응 Alert 시스템 제안서"(2026-08-19,
# 2026-08-19 개정)에 있다. 이 파일은 그 문서의 구현 계획을 코드로 옮긴
# 것뿐이다 — 새 판단은 여기서 하지 않는다.
#
# 세 단계로 나뉜다 — "지표가 없으면 alert를 포기한다"가 아니라 "지금 되는
# 것과 계측을 새로 넣어야 되는 것을 구분해서 코드로 남긴다"는 게 개정판 원칙.
#
#   Phase 0  지금 바로 켜짐 — 기존 o2.warm.* 지표만 쓴다
#            order_latency_p95, cache_absorption_failure
#   Phase 1  코드 변경 없이 확인만 필요 — 이미 연결된 AWS 통합 지표
#            order_confirm_backlog_age (enable_queue_backlog_monitor)
#   Phase 2  신규 계측이 먼저 필요 — 리소스는 만들어 두되 기본 비활성
#            chat_ingest_surge          (chat-gateway 이벤트 싱크를 Kinesis로)
#            cache_hit_rate_pod_outlier (시나리오 1 — pod_name 태그 신설)
#            order_confirm_stall        (시나리오 6 — order.confirm 이벤트 신설)
#
# 시나리오 5(1차 조치 실패 후 자기교정)는 신규 Monitor가 없다 — 그 시나리오가
# 검증하는 것은 "알림 이후" 에이전트 쪽 상태 기계(기준값 기록 → 60초 후
# 재확인 → 실패 시 원복 → 재판단)이고, 이건 Datadog Monitor가 표현할 수
# 있는 종류의 로직이 아니다. 알림 자체는 시나리오 2와 같은
# order_latency_p95 를 그대로 재사용한다.
###############################################################################

locals {
  # Datadog 은 모니터 쿼리에서 대시보드용 템플릿 변수($service 등)를 못 쓴다
  # (dashboard.tf 의 local.scope 와는 다른 축 — 저건 대시보드 전용 문법이다).
  # 여기서는 var 값을 그대로 문자열에 박아 넣는다.
  monitor_env = var.environment

  # 알림 라우팅(Slack 등)은 이 스택 범위 밖이다 — 인프라팀이 별도 webhook
  # push 경로로 Datadog Monitor → 에이전트 연결을 구축 중이다. 여기서는
  # 임계치와 진단 안내가 담긴 Monitor 자체만 만든다. 라우팅이 정해지면
  # 각 Monitor의 message 본문에 그 수신자 핸들만 추가하면 된다.
  monitor_tags = ["team:o2", "managed-by:terraform", "stack:05-datadog"]
}

###############################################################################
# 시나리오 2 (조기 경보) — 특가 오픈 캐스케이드의 진짜 시작점
#
# 캐스케이드의 첫 도미노는 채팅 발화율이지 주문 API 가 아니다(트랜스크립트
# 시간축: 채팅 인입 20→210 msg/s 가 T+6s, chat-gateway CPU 포화가 T+18s —
# 12초 소요, 주문 p99 급등은 T+52s). chat.send 이벤트로 이 시작점을 잡는다는
# 설계다(contracts.md 5.1·5.3, service:chat-gateway 로 필터링한 rps_ratio).
#
# **이 Monitor 는 켜져 있다**(`terraform.tfvars` 의
# `enable_chat_ingest_monitor = true`). 아래는 그렇게 되기까지의 경위이고,
# 여기 적힌 사유가 낡은 채로 남아 몇 주를 불필요하게 꺼져 있었다.
#
# 2026-08-24 이전 이 자리에는 이런 사유가 적혀 있었다 —
#   "켜도 목적지가 stdout 뿐이다. Kinesis 로 가는 경로 자체가 아직 없고,
#    api 의 O2_EVENTS_SINK 같은 싱크 선택 로직도 없다."
#
# **그 서술은 그 사이 사실이 아니게 됐다.** `apps/chat-gateway/src/events.ts`
# 에 `KinesisClient`·`PutRecordCommand` 가 들어왔고(`:16`),
# `config.eventsSink === 'kinesis'` 분기가 있다(`:100`). 배포 환경변수도
# 설정돼 실제로 흐른다 — 7일 구간에서
# `o2.warm.rps{service:chat-gateway}` 와 `rps_ratio{service:chat-gateway}`
# 가 둘 다 시계열을 갖는다(2026-08-24 API 조회).
#
# **교훈은 이 Monitor 가 아니라 주석에 대한 것이다.** 비활성 사유는 조건이
# 해소되면 같이 고쳐야 한다. 안 고치면 "왜 꺼져 있지" 를 묻는 사람이 낡은
# 답을 읽고 그대로 덮는다. `enable_aggregator_lag_monitor` 도 같은 일을
# 겪었다(monitor_pipeline.tf).
#
# **임계값은 아직 근거가 없다.** `chat_rps_ratio_warning = 5` 는 옛
# 트랜스크립트의 예시 숫자(20→210 msg/s)이지 실측이 아니다. 그리고
# `rps_ratio` 는 EWMA 표본 30개(약 5분)가 쌓여야 값이 생기므로 **방송 시작
# 직후에는 조기 경보가 안 나온다.** S1 이 "특가 오픈 순간" 을 노린다면 이
# 워밍업 시간을 진행 순서에 넣어야 한다.
###############################################################################

resource "datadog_monitor" "chat_ingest_surge" {
  count = var.enable_chat_ingest_monitor ? 1 : 0

  name    = "[O2][시나리오 2] 채팅 인입 급증 — 캐스케이드 조기 경보"
  type    = "metric alert"
  message = <<-EOT
    채팅 인입(`chat.send`)이 평시 대비 ${var.chat_rps_ratio_warning}배를 넘었습니다.

    **왜 지금 알리는가** — 특가 오픈 캐스케이드는 채팅 발화율 급증에서
    시작해 chat-gateway CPU 포화 → WebSocket 재연결 폭증 → 주문 API 지연
    순으로 번집니다. 트랜스크립트 실측 사례는 12초 만에 chat-gateway가
    포화됐습니다. 이 alert는 그 연쇄의 첫 도미노를 잡기 위한 조기 경보이고,
    아직 사용자 영향(주문 지연)이 발생했다는 뜻은 아닙니다.

    **다음에 볼 것** — 1분 내외로 `order_latency_p95` 도 함께 울리면
    상류(채팅)가 원인일 가능성이 높습니다. 1차 조치 후보는 채팅 표시 상한
    하향입니다 — 주문 API 스케일아웃이나 Valkey 등급 상향은 원인이 아니므로
    효과가 없습니다(제안서 시나리오 2 "조치가 갈리는 지점").

    @webhook-o2-dify
  EOT

  query = "min(last_${var.chat_early_warning_window_minutes}m):avg:${var.metric_prefix}rps_ratio{service:chat-gateway,env:${local.monitor_env}} >= ${var.chat_rps_ratio_warning}"

  monitor_thresholds {
    # Datadog metric alert의 query 비교값은 critical(Alert) 임계와 일치해야 한다.
    # warning만 정의하면 /api/v1/monitor/validate가 "Alert status is required"를
    # 반환한다. 이 Monitor 자체가 조기 경보이므로 현재 단일 임계를 Alert로 쓴다.
    critical = var.chat_rps_ratio_warning
  }

  # EWMA 표본이 30개(~5분) 쌓이기 전에는 rps_ratio 자체가 없다(README 실측
  # 표) — no-data 를 굳이 경보하지 않는다. 방송 시작 직후엔 정상적인 공백이다.
  notify_no_data      = false
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["scenario:2", "service:chat-gateway", "role:leading-indicator"])
}

###############################################################################
# 시나리오 2 (실제 트리거) + 시나리오 5 (재사용) — 주문 응답 p95 지연
#
# 트랜스크립트에서 "여기서 알림이 옴"이라 표시된 지점이다. dashboard.tf 그룹1
# 이 이미 이 지표를 "알림 근거가 될 수 있는 넷" 중 하나로 지정해 뒀으므로,
# 같은 var(latency_p95_warning/critical)를 그대로 재사용한다 — 대시보드
# 색깔과 alert 임계가 갈리지 않게 하기 위해서다(variables.tf 원래 주석).
###############################################################################

resource "datadog_monitor" "order_latency_p95" {
  name    = "[O2][시나리오 2·5] 주문 응답 p95 지연"
  type    = "metric alert"
  message = <<-EOT
    주문 응답 p95(`trace.fastapi.request{service:api}`)가
    위험 임계를 넘었습니다.

    **이 alert가 커버하는 두 시나리오**
    - *특가 오픈 캐스케이드*: 원인이 채팅 발화율 급증일 수 있습니다 —
      `chat_ingest_surge` 가 1분 이내로 먼저 울렸는지 확인하세요(이 Monitor가
      아직 Phase 2 상태로 꺼져 있다면, 대신 대시보드의 채팅 지표를 직접
      확인합니다). 울렸다면 원인은 상류(채팅)이고, 조치는 채팅 표시 상한
      하향입니다.
    - *1차 조치가 틀렸을 가능성*: Valkey 커넥션 풀 고갈이 정석적인 1순위
      가설이지만, 조치(풀 상한 상향) 후 60초 뒤 개선율이 30% 미만이면 실패로
      판정하고 원복한 뒤 ReplicaLag 등 다른 원인을 재조사해야 합니다. 이
      기준값 기록·재확인·원복 로직은 이 Monitor가 아니라 에이전트
      오케스트레이션(D-028, `06-agent`) 쪽에 있습니다.

    @webhook-o2-dify
  EOT

  # trace.fastapi.request 의 Datadog API 단위는 second다. 사용자 계약과 변수는
  # ms를 유지하므로 비교 임계만 1000으로 나눈다(2026-08-24 recent point 확인).
  query = "min(last_${var.scenario_entry_window_minutes}m):p95:trace.fastapi.request{service:${var.default_service},env:${local.monitor_env}} >= ${var.latency_p95_critical / 1000}"

  monitor_thresholds {
    warning  = var.latency_p95_warning / 1000
    critical = var.latency_p95_critical / 1000
  }

  # dev 에는 주문 트래픽이 상시로 흐르지 않는다. 켜 두면 "지표가 안 온다" 가
  # 그대로 알람이 되어, 08-19~08-21 사흘 동안 No Data 와 Recovered 를 7번
  # 왕복했다. 고칠 것이 없는 알람이 매번 에이전트를 깨운다.
  #
  # 주문 경로가 실제로 돌기 시작하면 true 로 되돌린다 — 그때는 지표가 끊기는
  # 것이 진짜 장애 신호다.
  notify_no_data      = false
  no_data_timeframe   = 10
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["scenario:2", "scenario:5", "service:api", "role:page"])
}

###############################################################################
# 시나리오 4 — 캐시 흡수 실패
#
# (a) 무효화 폭주 vs (b) 콜드 미스는 이 Monitor가 못 가른다 — 트랜스크립트
# 원문대로 "같은 그래프"를 그린다. 여기서는 "캐시가 원본을 못 흡수하고
# 있다"까지만 잡고, 두 원인의 분기는 메시지 본문의 안내(안전한 실험: 로컬
# TTL 1→3초 10초간)로 넘긴다.
#
# hit_rate 단독 임계를 쓰지 않는 이유 — 표본이 적은 구간에서 hit_rate는
# confidence 가 낮아도 출렁인다(README "위젯이 비어 있을 때" 절). latency_p95
# 동반 상승을 AND 로 요구해 "캐시는 흔들리지만 사용자는 못 느끼는" 노이즈를
# 거른다.
###############################################################################

resource "datadog_monitor" "cache_hit_rate_low" {
  name    = "[O2][시나리오 4] 캐시 히트율 낮음 (서브 모니터)"
  type    = "metric alert"
  query   = "min(last_${var.scenario_entry_window_minutes}m):avg:${var.metric_prefix}cache_hit_rate{service:${var.default_service},env:${local.monitor_env}} < ${var.cache_hit_rate_critical}"
  message = "캐시 히트율이 임계치 미만입니다. 복합 모니터의 하위 조건으로 작동합니다."

  monitor_thresholds {
    critical = var.cache_hit_rate_critical
  }

  notify_no_data      = false
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["scenario:4", "service:api", "role:sub"])
}

resource "datadog_monitor" "latency_p95_high" {
  name    = "[O2][시나리오 4] 응답 p95 지연 높음 (서브 모니터)"
  type    = "metric alert"
  query   = "min(last_${var.scenario_entry_window_minutes}m):p95:trace.fastapi.request{service:${var.default_service},env:${local.monitor_env}} >= ${var.latency_p95_critical / 1000}"
  message = "응답 p95 지연 시간이 임계치를 초과했습니다. 복합 모니터의 하위 조건으로 작동합니다."

  monitor_thresholds {
    critical = var.latency_p95_critical / 1000
  }

  notify_no_data      = false
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["scenario:4", "service:api", "role:sub"])
}

###############################################################################
# 이 composite 만 게이트를 갖는다 — 서브 둘은 안 갖는다. D-056.
#
# 짧게: **서브 Monitor 는 알림 핸들이 없어 울리지 않고, composite 는 운다.**
# 그래서 끌 수 있어야 하는 것은 composite 뿐이다. 그리고 서브에 `count` 를
# 걸면 이 아래 `query` 의 `datadog_monitor.cache_hit_rate_low.id` 참조가
# 깨진다(`[0].id` 가 되고, 게이트가 꺼지면 참조 대상이 아예 없다).
#
# **기본값은 `true` 다 — 지금 동작을 바꾸지 않는다.** 시나리오 4(캐시 흡수
# 실패)는 새 명세에 대응 항목이 없을 뿐 이 시스템에서 여전히 실재하는
# 실패 모드다. "새 명세에 없다" 는 "지워도 된다" 를 뜻하지 않는다.
#
# **apply 할 때 주의** — `count` 가 붙으면서 주소가
# `datadog_monitor.cache_absorption_failure` 에서 `...[0]` 로 바뀐다.
# 그냥 apply 하면 Datadog 쪽 Monitor 가 **삭제 후 재생성**되어 ID 와 알림
# 이력이 바뀐다. 먼저 상태를 옮긴다:
#
#   terraform state mv 'datadog_monitor.cache_absorption_failure' #                      'datadog_monitor.cache_absorption_failure[0]'
###############################################################################

variable "enable_cache_absorption_monitor" {
  description = <<-EOT
    시나리오 4(캐시 흡수 실패) composite Monitor 활성화 여부. 기본 `true`.

    끄면 서브 Monitor 둘(`cache_hit_rate_low` · `latency_p95_high`)은 계정에
    그대로 남는다. **의도한 것이다** — 그 둘은 알림 핸들이 없어 울리지 않고,
    상태만 계속 계산한다. 대시보드에서 "그때 캐시가 어땠나" 를 되짚을 때
    쓸 수 있고, 다시 켤 때 임계 조정 없이 바로 붙는다.

    끌 상황은 하나뿐이다 — **데모 중 시나리오와 무관한 알림이 에이전트를
    깨우는 것을 막을 때.** 운영에서 끄지 않는다.
  EOT
  type        = bool
  default     = true
}

resource "datadog_monitor" "cache_absorption_failure" {
  count = var.enable_cache_absorption_monitor ? 1 : 0

  name    = "[O2][시나리오 4] 캐시 흡수 실패"
  type    = "composite"
  query   = "${datadog_monitor.cache_hit_rate_low.id} && ${datadog_monitor.latency_p95_high.id}"
  message = <<-EOT
    캐시 히트율이 ${var.cache_hit_rate_critical}(${var.cache_hit_rate_critical * 100}%) 아래로 떨어졌고,
    동시에 응답 p95가 위험 임계를 넘었습니다 — 캐시가 원본(MySQL)을
    흡수하지 못하고 있습니다.

    **원인은 둘 중 하나이고, 이 alert만으로는 못 가릅니다.**
    - (a) 무효화 폭주 — 상품 정보가 계속 바뀌어 캐시가 계속 지워짐
    - (b) 신규 유입 콜드 미스 — 새로 들어온 사용자가 많아 처음부터 캐시에 없음

    **오진하면**: (b)인데 (a)로 판단해 TTL 상향·무효화 억제 → 낡은 가격이
    오래 남습니다. (a)인데 (b)로 판단해 워밍·파드 증설 → 새 파드도 같이
    미스를 내 효과가 없습니다.

    **안전한 판별 실험**: 로컬 캐시 TTL 을 10초간 1초 → 3초로 올려봅니다.
    (a)면 즉시 회복(무효화보다 TTL이 오래 버팀), (b)면 거의 안 변합니다
    (없는 것은 TTL을 늘려도 없음). 어느 쪽이어도 최대 손해는 가격 반영이
    2초 늦는 것뿐입니다.

    @webhook-o2-dify
  EOT

  notify_no_data      = false
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["scenario:4", "service:api", "role:page"])
}

###############################################################################
# 시나리오 1 (Phase 2 — 기본 비활성) — 파드 단위 캐시 스큐
#
# 트랜스크립트가 "알림으로 절대 안 잡힌다"고 말하는 이유는 정확했다 —
# `o2.warm.cache_hit_rate` 가 `service`·`env` 두 태그만 갖고 파드 단위
# 분해가 없어서다. 파드 3개가 정상, 1개만 고장이면 평균은 75%로 멀쩡해
# 보인다. 하지만 이건 "알림 불가능"이 아니라 "지금 이 지표로는 불가능"이다
# — pod 식별자를 태그에 추가하면 잡을 수 있다.
#
# 활성화에 필요한 계측(이 Terraform 스택 범위 밖):
#   1. `o2-sdk-for-event`(외부 저장소) 봉투에 `pod_name` 필드 추가.
#      K8s가 `HOSTNAME` 환경변수를 파드 이름으로 채워 주므로 앱 코드 변경은
#      거의 없다 — SDK `_envelope()` 한 곳만 고치면 된다
#   2. `06-datastream/warm/src/o2warm`(이 저장소): `cache_hit_rate` 계산에만
#      `pod_name` 태그를 추가한다. 20개 스칼라 전체에 붙이지 않는다 —
#      서비스 3개 × pod 수만큼 시계열이 곱해져 커스텀 메트릭 요금이 튄다
#      (README "비용" 절). 파드 수가 작으므로(t3.small 노드그룹, api 파드
#      한 자릿수) 이 지표 하나에 한정하면 증가분은 무시할 만하다
#
# 쿼리는 임계 비교가 아니라 Datadog outlier 탐지(`outliers()`)를 쓴다 —
# "평균이 나쁘다"가 아니라 "나머지와 다른 파드가 하나 있다"가 이 시나리오의
# 정확한 증상이라서다. DBSCAN 파라미터(허용 오차 2.5)는 실측 pod별 분산을
# 본 적이 없어 잠정치다 — 켜기 전에 파드 수·정상 변동폭을 보고 조정한다.
###############################################################################

variable "enable_pod_cache_outlier_monitor" {
  description = <<-EOT
    시나리오 1(파드 단위 캐시 스큐) Monitor 활성화 여부. 기본 `false`.

    `o2.warm.cache_hit_rate` 에 `pod_name` 태그가 실려야 동작한다 — 지금은
    SDK 봉투에 그 필드가 없다(모니터 정의 위 주석 참고). 계측이 들어가고
    Metrics Explorer 에서 `by {pod_name}` 분해가 실제로 나오는 것을 확인한
    뒤 `true` 로 켠다.
  EOT
  type        = bool
  default     = false
}

variable "pod_cache_outlier_tolerance" {
  description = <<-EOT
    outlier 탐지(DBSCAN) 허용 오차. 값이 작을수록 민감하게(더 쉽게 outlier로)
    잡는다. 파드별 정상 변동폭을 모르는 상태의 잠정치 — 켜기 전에 실측
    분산을 보고 조정한다.
  EOT
  type        = number
  default     = 2.5
}

resource "datadog_monitor" "cache_hit_rate_pod_outlier" {
  count = var.enable_pod_cache_outlier_monitor ? 1 : 0

  name    = "[O2][시나리오 1] 파드 단위 캐시 히트율 이상치"
  type    = "query alert"
  message = <<-EOT
    캐시 히트율이 유독 낮은 파드가 있습니다 — 전체 평균은 정상으로 보일 수
    있습니다.

    **왜 이런 일이 생기나** — Valkey Pub/Sub 은 at-most-once 입니다. 구독자가
    순간 끊겨 있으면 무효화 메시지가 유실되고 재전송이 없습니다. 특히
    스케일아웃으로 새로 뜬 파드는 그 이전의 무효화를 못 받아 옛 값을 계속
    반환합니다 — 응답은 200 OK 라 에러율에도 안 잡힙니다.

    **확인할 것**
    - 이상치로 잡힌 파드의 생성 시각이 최근 무효화 발행 시각보다 뒤인지
    - `product.update` 발행 수 대비 그 파드의 수신 수가 적은지

    **조치**: 해당 파드 재시작 또는 전체 로컬 캐시 플러시. 근본 대응은
    재연결 시 전체 플러시(설계에 있음)와 TTL 안전망입니다.

    @webhook-o2-dify
  EOT

  query = "avg(last_10m):outliers(avg:${var.metric_prefix}cache_hit_rate{service:${var.default_service},env:${local.monitor_env}} by {pod_name}, 'DBSCAN', ${var.pod_cache_outlier_tolerance}) > 0"

  notify_no_data      = false
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["scenario:1", "service:api", "role:page", "phase:2"])
}

###############################################################################
# 시나리오 5 (재분석) — 파드 단위 지연 이상치
#
# 위 캐시 이상치 Monitor 와 **같은 쿼리이고 지표 이름만 다르다.** 일부러
# 그렇게 뒀다 — 파드 하나가 service 평균에 묻히는 문제는 캐시든 지연이든
# 같은 모양이고, 같은 모양은 같은 도구로 잡는 편이 읽기 쉽다.
#
# **이건 진입 알림이 아니다.** 진입은 `order_latency_p95`(service 단위)가
# 하고, 이 Monitor 는 그 다음 질문 — "1차 조치가 안 들었는데, 전부 느린 건가
# 파드 하나인가" — 에 답한다. 명세의 자기 교정 루프가 재분석 단계에서 읽는
# 증거가 바로 이 축이다.
#
# 왜 우회할 수 없었나 — APM 쪽에 파드 축이 있으면 이 계측이 통째로
# 불필요했다. 실측(M-015) 결과 `trace.fastapi.request` 의 태그 아홉 개에
# `pod_name` 이 없다. `.hits` 에 붙는 `kube_node`·`host` 는 호스트 태그가
# 상속된 것이지 파드 단위가 아니다. 그래서 06-datastream 에서 만든다.
#
# **방향을 구분하지 않는다는 것을 알고 쓴다.** `outliers()` 의 DBSCAN 은
# "무리에서 떨어진 것" 을 잡지 "느린 것" 을 잡지 않는다. 파드 하나가 유독
# **빠를** 때도 걸린다. 캐시 쪽 Monitor 가 이미 같은 성질을 갖고 있고,
# 방향을 넣으려면 임계를 별도로 정해야 하는데 그 임계의 근거가 아직 없다
# (파드별 정상 분산을 안 쟀다 — `pod_cache_outlier_tolerance` 주석과 같은
# 상태다). 오탐 방향이 "느리지 않은데 깨웠다" 이므로 위험하지 않고,
# 메시지에서 먼저 확인하도록 안내한다. 실측이 생기면 그때 조인다.
###############################################################################

variable "enable_pod_latency_outlier_monitor" {
  description = <<-EOT
    시나리오 5(파드 단위 지연 이상치) Monitor 활성화 여부. 기본 `false`.

    `o2.warm.latency_p95` 에 `pod_name` 태그가 실려야 동작한다. 계측은
    06-datastream 의 3단(`sketch` → `metrics` → `datadog`)에 들어가 있고,
    **파드가 2개 이상 떠 있는 상태**에서
    `avg:o2.warm.latency_p95{*} by {pod_name}` 이 파드 수만큼 갈리는 것을
    확인한 뒤 켠다.

    갈리지 않으면 3단 중 어딘가에서 태그가 빠진 것이다. 봉투에 `pod_name`
    이 없으면 파드 축이 통째로 비는데, **그 경우에도 위젯은 오류가 아니라
    시계열 하나(service 단위 값)만 보여준다** — T-023 이 겪은 모양이다.
  EOT
  type        = bool
  default     = false
}

variable "pod_latency_outlier_tolerance" {
  description = <<-EOT
    파드 지연 outlier 탐지(DBSCAN) 허용 오차. 기본은 캐시 쪽과 같은 2.5 다.

    같은 값으로 시작하는 것이 근거 있는 선택이라서가 아니라, **다른 값을
    고를 근거가 없기 때문**이다. 파드별 지연의 정상 분산을 아직 안 쟀다.
    재면 `measurements.md` 에 남기고 여기를 고친다.
  EOT
  type        = number
  default     = 2.5
}

resource "datadog_monitor" "latency_p95_pod_outlier" {
  count = var.enable_pod_latency_outlier_monitor ? 1 : 0

  name    = "[O2][시나리오 5] 파드 단위 응답 지연 이상치"
  type    = "query alert"
  message = <<-EOT
    응답 지연이 유독 다른 파드 하나가 있습니다 — service 단위 p95 는 나머지
    파드에 희석돼 임계 안에 머물 수 있습니다.

    **먼저 방향을 봅니다.** 이 탐지는 "무리에서 떨어진 파드" 를 잡지
    "느린 파드" 를 잡지 않습니다. 대시보드에서 `trace.fastapi.request`
    를 `by {pod_name}` 으로 펼쳐, 잡힌 파드가 **위로** 떨어졌는지 확인하세요.
    아래로 떨어진 것이면 조치할 것이 없습니다.

    **왜 이런 일이 생기나**
    - 그 파드만 CPU 를 유독 많이 씁니다 —
      `avg:kubernetes.cpu.usage.total{kube_namespace:o2-dev} by {pod_name}`
      을 정상 파드와 나란히 봅니다. **조임 비율(`cfs.*`)은 보지 마십시오.**
      이 클러스터는 CPU limit 을 일부러 안 걸어서 그 지표가 없습니다(D-064)
    - 그 파드만 캐시가 식어 있다 — `cache_hit_rate_pod_outlier` 가 같은
      파드를 지목했는지 봅니다. 같으면 원인은 캐시 쪽입니다
    - 그 파드가 방금 떴다 — 표본 5건 미만인 파드는 애초에 이 축에
      실리지 않지만(`LATENCY_POD_MIN_SAMPLES`), 갓 데워지는 중일 수 있습니다

    **조치**: 해당 파드만 재시작하거나 스케줄에서 뺍니다. service 전체를
    건드리기 전에 이 축을 먼저 보는 것이 이 Monitor 의 목적입니다.

    @webhook-o2-dify
  EOT

  query = "avg(last_10m):outliers(p95:trace.fastapi.request{service:${var.default_service},env:${local.monitor_env}} by {pod_name}, 'DBSCAN', ${var.pod_latency_outlier_tolerance}) > 0"

  notify_no_data      = false
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["scenario:5", "service:api", "role:page", "phase:2"])
}

###############################################################################
# 시나리오 6 — 주문 확정 큐 적체 (기본 비활성)
#
# 큐 이름은 03-data/sqs.tf 의 aws_sqs_queue.order 를 실측 확인한 값이다
# (`o2-dev-order`). 이 계정엔 Datadog AWS 통합이 이미 연결돼 있지만
# (CloudFormation DatadogIntegration-*), SQS 네임스페이스가 실제로 수집
# 중인지는 DD_APP_KEY 없이 이 세션에서 확인하지 못했다. 확인 전까지는
# `enable_queue_backlog_monitor = false` 로 이 리소스 자체가 안 만들어진다
# — 없는 지표에 조용히 죽는 Monitor를 걸지 않는다는 원칙을 여기서 지킨다.
#
# 확인 방법(Datadog 콘솔 또는 API): Metrics Explorer에서
# `aws.sqs.approximate_age_of_oldest_message` 검색 → queuename:o2-dev-order
# 태그로 시계열이 잡히는지 확인.
###############################################################################

resource "datadog_monitor" "order_confirm_backlog_age" {
  count = var.enable_queue_backlog_monitor ? 1 : 0

  name    = "[O2][시나리오 6] 주문 확정 큐 적체"
  type    = "metric alert"
  message = <<-EOT
    주문 확정 큐(`${var.order_confirm_queue_name}`)의 가장 오래된 미처리
    메시지가 ${var.queue_backlog_age_critical_seconds}초 이상 대기 중입니다.

    **이 alert의 의미** — 접수(`order.create`)는 성공했지만 확정 처리가
    밀리고 있다는 뜻입니다. 응답 시간·에러율은 정상으로 보일 수 있습니다
    (접수 자체는 실제로 성공했기 때문) — 이 큐 지표가 유일한 조기 신호입니다.

    **원인이 셋으로 갈리고 조치가 반대인 것이 있습니다.**
    - 처리 워커가 부족하다 → 늘린다
    - 워커가 DB에서 막혀 있다 → **늘리면 더 막힌다**
    - 메시지 자체가 처리 불가라 계속 되돌아온다 → 따로 빼낸다(DLQ)

    안전한 1차 진단: 워커를 하나만 늘려 20초 관찰합니다. 부족한 거면 즉시
    빠지고, DB에 막힌 거면 안 빠집니다.

    **주의**: 큐를 뚫은 뒤에도 "재고는 차감됐는데 주문 기록이 없는" 건이
    남을 수 있습니다. 그 건들을 전부 확정할지, 일부만 확정할지는 기술
    판단이 아니라 비즈니스 판단이므로 에이전트가 자동으로 결정하지 않고
    승인을 요청합니다.

    @webhook-o2-dify
  EOT

  query = "min(last_5m):avg:aws.sqs.approximate_age_of_oldest_message{queuename:${var.order_confirm_queue_name}} >= ${var.queue_backlog_age_critical_seconds}"

  monitor_thresholds {
    warning  = var.queue_backlog_age_warning_seconds
    critical = var.queue_backlog_age_critical_seconds
  }

  # AWS 통합 지표는 ~10분 주기라(README 관례상 언급된 값과 별개로 이
  # 조직 실측은 Confluence "Datadog 수집 데이터 현황" 참고) no-data 윈도우를
  # 그에 맞춰 넉넉히 잡는다. 너무 짧으면 매 수집 주기마다 no-data 오탐이 난다.
  notify_no_data      = true
  no_data_timeframe   = 20
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["scenario:6", "service:order-worker", "role:page"])
}

###############################################################################
# 시나리오 6 (Phase 2 — 기본 비활성) — 접수 대비 확정 정지 감지
#
# order_confirm_backlog_age(위)는 "큐가 밀리기 시작했다"를 SQS 쪽에서
# 잡는 우회 신호다. 이 Monitor 는 비즈니스 이벤트 쪽에서 같은 증상을 직접
# 잡는다 — 그러려면 신규 이벤트가 필요하다.
#
# 지금 계약(contracts.md 5.1)에는 `order.create`(접수)와 `order.cancel`
# (워커 실패)만 있고 확정 성공 이벤트가 없다. 대칭을 맞추면 된다 — 워커가
# 실패 시 이미 `order.cancel` 을 내고 있으므로(같은 코드 경로), 성공 시
# `order.confirm` 을 내는 것은 특별히 새로운 계측이 아니라 이미 있는 훅의
# 반대쪽을 채우는 것이다.
#
# 활성화에 필요한 작업(이 Terraform 스택 범위 밖):
#   1. `o2-sdk-for-event`(외부 저장소, 백데이터 파트 소관): `EVENT_NAMES` 에
#      `order.confirm` 추가 — contracts.md 5.4가 이미 이런 추가용으로
#      "이름만 추가하는 PR을 열어 둔다"는 절차를 예정해 뒀다(chat.send 사례와
#      동일 패턴)
#   2. `06-datastream/warm/src/o2warm/contract.py`(이 저장소): 새 이름을
#      `EVENT_NAMES`/`EVENT_ORDER_CONFIRM` 상수로 반영 — 여기 값은 SDK 값의
#      드리프트 감지용 사본이라, SDK가 안 바뀌면 여기도 못 바꾼다(파일 상단
#      주석)
#   3. `apps/order-worker`: 확정 커밋 성공 지점에 `order.confirm` 발행 추가
#
# **`rps` 는 이벤트 종류로 못 가른다.** `datadog.py` 의 `build_series()`
# 를 실제로 읽어보면 `rps`·`event_count` 같은 스칼라는 `service`·`env` 만
# 태그로 갖고, `event` 태그가 붙는 건 `failure_rate` 하나뿐이다(라인 62-91).
# 즉 `order.confirm` 이 생겨도 `rps{service:order-worker}` 만으로는 그게
# `order.cancel` 인지 `order.confirm` 인지 못 가른다.
#
#   4. (위 3개에 더해) `06-datastream/warm/src/o2warm/datadog.py`:
#      `failure_rate` 와 같은 패턴으로 `event_rate`(또는 이벤트별 카운트)를
#      `event` 태그로 쪼개 내보내는 series 를 추가한다. 카디널리티는
#      failure_rate 와 동일한 근거로 안전하다 — event 종류가 6→7개로
#      고정이라서다
#
# 정밀한 비율(confirm/create) 기반 alert 대신 단순 "정지" 조건(create는
# 계속되는데 confirm이 완전히 멈춤)을 쓴다 — 비율 기반 포뮬러는 이 세션에서
# 실제 계정으로 문법을 검증하지 못해 확신이 낮다. 이 신규 이벤트의 더 큰
# 가치는 이 Monitor보다도, 3막(재고는 차감됐는데 주문 기록이 없는 정확한
# 건수)에서 에이전트가 Cold Path 로 셀 수 있게 되는 것이다(제안서 참고) —
# 이 Monitor 는 부차적인 실시간 신호다.
###############################################################################

variable "enable_order_confirm_stall_monitor" {
  description = <<-EOT
    시나리오 6 보조 Monitor(`order_confirm_stall`) 활성화 여부. 기본 `false`.
    `order.confirm` 이벤트가 실제로 발행·집계되기 시작한 뒤에 켠다(모니터
    정의 위 주석 참고) — 이 이벤트는 아직 계약에 없다.
  EOT
  type        = bool
  default     = false
}

resource "datadog_monitor" "order_create_active" {
  name    = "[O2][시나리오 6] 주문 생성 진행 중 (서브 모니터)"
  type    = "metric alert"
  query   = "min(last_10m):avg:${var.metric_prefix}event_rate{service:${var.default_service},env:${local.monitor_env},event:order.create} > 0"
  message = "주문 생성이 발생하고 있습니다. 복합 모니터의 하위 조건으로 작동합니다."

  monitor_thresholds {
    critical = 0
  }

  notify_no_data      = false
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["scenario:6", "service:order-worker", "role:sub"])
}

resource "datadog_monitor" "order_confirm_inactive" {
  name    = "[O2][시나리오 6] 주문 확정 정지됨 (서브 모니터)"
  type    = "metric alert"
  query   = "max(last_10m):avg:${var.metric_prefix}event_rate{service:order-worker,env:${local.monitor_env},event:order.confirm} <= 0"
  message = "주문 확정이 발생하지 않고 있습니다. 복합 모니터의 하위 조건으로 작동합니다."

  monitor_thresholds {
    critical = 0
  }

  notify_no_data      = false
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["scenario:6", "service:order-worker", "role:sub"])
}

resource "datadog_monitor" "order_confirm_stall" {
  count = var.enable_order_confirm_stall_monitor ? 1 : 0

  name    = "[O2][시나리오 6] 주문 확정 정지"
  type    = "composite"
  query   = "${datadog_monitor.order_create_active.id} && ${datadog_monitor.order_confirm_inactive.id}"
  message = <<-EOT
    주문 접수(`order.create`)는 계속되는데 확정(`order.confirm`)이 완전히
    멈췄습니다.

    이 신호는 `order_confirm_backlog_age`(SQS 큐 나이) 보다 늦게 잡힐 수
    있습니다 — 그 Monitor가 먼저 울렸는지 같이 확인하세요. 두 Monitor가
    함께 울리면 확정 처리가 완전히 정지된 것이 비즈니스 이벤트 쪽에서도
    교차 확인된 것입니다.

    @webhook-o2-dify
  EOT

  notify_no_data      = false
  require_full_window = true
  renotify_interval   = 0

  tags = concat(local.monitor_tags, ["scenario:6", "service:order-worker", "role:page", "phase:2"])
}
