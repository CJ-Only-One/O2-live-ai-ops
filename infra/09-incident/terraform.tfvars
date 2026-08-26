team        = "o2"
project     = "o2"
environment = "dev"
region      = "ap-northeast-2"

alert_secret_name_o2 = "o2/dev/dify-alert-o2"

incident_datadog_monitor_map = {
  "22078624" = {
    evidence_role            = "PRIMARY"
    evidence_type            = "SERVICE_TAIL_LATENCY"
    incident_family          = "READ_PATH_DEGRADATION"
    symptom_family           = "LATENCY"
    suspected_surface        = "READ_PATH"
    service                  = "api"
    minimum_samples          = 1
    freshness_seconds        = 300
    severity_level           = "WARNING"
    strong_exception_allowed = false
  }
  "21940248" = {
    evidence_role            = "CORROBORATING"
    evidence_type            = "SERVICE_TAIL_LATENCY"
    incident_family          = "READ_PATH_DEGRADATION"
    symptom_family           = "LATENCY"
    suspected_surface        = "READ_PATH"
    service                  = "api"
    minimum_samples          = 1
    freshness_seconds        = 300
    severity_level           = "WARNING"
    strong_exception_allowed = false
  }
  # 2026-08-26: S1 진입 전환 — infra/05-datadog terraform state에서 확인한 실제
  # monitor ID(지어낸 값 아님). s1_chat_fanout_volume가 유일한 진입(PRIMARY)이고
  # 옛 @webhook-o2-dify는 뗐다(scenario_alerts.tf 라우팅 규칙 참고, 중복 호출 방지).
  # chat_propagation_p95/chat_block_rate는 role:impact 태그대로 CORROBORATING만.
  #
  # ★ 아래 셋의 symptom_family는 반드시 같아야 한다. 이 값이 correlation key에
  #   들어가기 때문이다(incident_correlator.py:524, 명세 4절):
  #
  #     environment # incident_family # symptom_family # service # suspected_surface
  #
  #   처음에는 monitor가 재는 지표 종류대로 AVAILABILITY / LATENCY / ERROR_RATE로
  #   각각 달랐다. 분류 자체는 정직했지만 **키가 셋으로 갈려 서로 다른 Incident가
  #   됐고**, 각 Incident에 역할이 하나씩만 있어 primary+corroborating이 한 곳에
  #   모이는 일이 영원히 없었다. 명세 2-7의 승격 조건을 구조적으로 못 만족한다.
  #   증상은 "S1이 PROVISIONAL만 쌓이고 Agent가 안 깨어난다" 하나다.
  #
  #   이 필드는 **monitor가 무엇을 재는지가 아니라, 그 monitor가 어느 Incident의
  #   증거인지**를 뜻한다. monitor 고유의 측정 축은 evidence_type이 이미 담고 있다
  #   (COMPOSITE_CONDITION / CHAT_PROPAGATION_P95 / CHAT_NORMAL_USER_BLOCK_RATE).
  #   따라서 한 Incident에 묶일 monitor들은 이 값을 공유해야 한다.
  #
  #   S1의 사용자 증상은 **전파가 밀리는 것**이므로 LATENCY로 통일한다. 복구 판정
  #   기준도 전파 p95다(scenario-experiment.md 1.2 S1). 팬아웃 총량은 그 지연을
  #   일으키는 부하 축이지 별개 증상이 아니다.
  "22078626" = { # s1_chat_fanout_volume, [O2][S1] 채팅 팬아웃 총량 — 채널 감당선 접근
    evidence_role            = "PRIMARY"
    evidence_type            = "COMPOSITE_CONDITION" # 발화 수 x 접속자 수 합성값, 전용 enum 없음
    incident_family          = "CHAT_DEGRADATION"
    symptom_family           = "LATENCY"
    suspected_surface        = "CHAT"
    service                  = "chat-gateway"
    minimum_samples          = 1
    freshness_seconds        = 120 # scenario_early_window_minutes 기본값(2분)
    severity_level           = "HIGH"
    strong_exception_allowed = false
  }
  "22076983" = { # chat_propagation_p95, [O2][S1] Chat 전파 p95 지연
    evidence_role            = "CORROBORATING"
    evidence_type            = "CHAT_PROPAGATION_P95"
    incident_family          = "CHAT_DEGRADATION"
    symptom_family           = "LATENCY"
    suspected_surface        = "CHAT"
    service                  = "chat-gateway"
    minimum_samples          = 1
    freshness_seconds        = 300 # avg(last_5m)
    severity_level           = "HIGH"
    strong_exception_allowed = false
  }
  "22076982" = { # chat_block_rate, [O2][S1] Chat 정상 사용자 차단률
    evidence_role            = "CORROBORATING"
    evidence_type            = "CHAT_NORMAL_USER_BLOCK_RATE"
    incident_family          = "CHAT_DEGRADATION"
    symptom_family           = "LATENCY"
    suspected_surface        = "CHAT"
    service                  = "chat-gateway"
    minimum_samples          = 1
    freshness_seconds        = 300 # avg(last_5m)
    severity_level           = "HIGH"
    strong_exception_allowed = false
  }
}

incident_correlation_window_seconds = 420
incident_recovery_window_seconds    = 300
incident_cooldown_seconds           = 300
incident_reopen_window_seconds      = 1800

incident_shadow_mode                  = false
incident_operational_handoff_approved = true

datadog_source_adapter_execution_enabled   = true
datadog_source_adapter_allowed_monitor_ids = ["21940248", "22078624", "22078626", "22076983", "22076982"]
datadog_source_adapter_not_before_epoch    = 1787634074
incident_correlator_execution_enabled      = true
incident_correlator_event_source_enabled   = true
