variable "team" {
  description = "팀 식별자. 태그로만 사용"
  type        = string
  default     = "o2"
}

variable "project" {
  description = "리소스 prefix. 소문자/하이픈만"
  type        = string
  default     = "o2"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", var.project))
    error_message = "소문자, 숫자, 하이픈만 허용."
  }
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "cluster_name" {
  description = <<-EOT
    EKS 클러스터 이름. 노드 보안 그룹을 찾는 데만 쓴다.
    EKS 파드가 Dify 를 호출할 수 있게 인그레스를 그 SG 로 좁힌다.
    03-data 와 같은 패턴이다.
  EOT
  type        = string
  default     = "o2-eks"
}

variable "network_state_bucket" {
  description = "network 스택의 S3 backend 버킷"
  type        = string
}

variable "network_state_key" {
  type    = string
  default = "network/terraform.tfstate"
}

# ── 호스트 ────────────────────────────────────────────────────────

variable "instance_type" {
  description = <<-EOT
    Dify 셀프호스트는 컨테이너 9개를 띄운다 —
    api, worker, web, sandbox, ssrf_proxy, nginx, plugin_daemon,
    postgres, redis, 그리고 벡터 DB(weaviate).

    공식 최소 요구는 2 vCPU / 4 GiB 이고, 그 값은 "뜨기는 한다" 수준이다.
    워커가 문서 인덱싱을 돌면 4 GiB 에서 OOM 이 난다. t3.large(2 vCPU / 8 GiB)
    가 실사용 하한이다.

    t3.small(EKS 노드와 같은 등급)로 내리지 말 것. 2 GiB 로는 postgres 와
    weaviate 만으로도 부족하다.
  EOT
  type        = string
  default     = "t3.large"
}

variable "root_volume_size" {
  description = <<-EOT
    GiB. Dify 이미지 전체가 약 10 GiB, 여기에 postgres·weaviate 데이터와
    업로드 문서가 쌓인다. 60 이면 개발용으로 여유가 있다.

    ★ 데이터가 이 루트 볼륨에만 있다. 인스턴스를 교체하면 워크플로가
    전부 사라진다. 보존이 필요해지면 별도 EBS 를 붙이고 /opt/dify/volumes
    를 그쪽으로 옮긴다 (README 참조).
  EOT
  type        = number
  default     = 60
}

variable "dify_ref" {
  description = <<-EOT
    클론할 Dify git ref. main 은 언제든 깨질 수 있으므로 릴리스 태그로
    고정하는 편이 낫다.

    apply 전 확인:
      curl -s https://api.github.com/repos/langgenius/dify/releases/latest \
        | jq -r .tag_name
  EOT
  type        = string
  default     = "main"
}

variable "enable_bedrock_access" {
  description = <<-EOT
    Dify 가 모델 공급자로 Bedrock 을 쓸 때 필요한 권한을 인스턴스 역할에
    붙인다. 외부 LLM API(OpenAI 등)만 쓸 거면 false 로 두고 API 키는
    Dify UI 에서 넣는다.
  EOT
  type        = bool
  default     = true
}

# ── 알림 중계 Lambda ─────────────────────────────────────────────

variable "alert_secret_name" {
  description = <<-EOT
    Datadog 알림 중계 Lambda 가 실행 시점에 읽는 **Secrets Manager 시크릿 이름**.

    이 스택은 시크릿을 만들지 않고 이름만 참조한다. 값을 Terraform 으로
    넣으면 state 에 평문으로 남기 때문이다 (06-datastream 의
    `datadog_secret_name` 과 같은 패턴).

    시크릿은 apply 전에 손으로 한 번 만든다. 키 두 개가 필요하다:

      dify-api-key    Dify 앱의 서비스 API 키 (app- 로 시작)
      webhook-secret  Datadog webhook 커스텀 헤더 x-dd-secret 과 같은 값
                      (openssl rand -hex 32)

      aws secretsmanager create-secret --name o2/dev/dify-alert \
        --secret-string '{"dify-api-key":"app-...","webhook-secret":"..."}' \
        --region ap-northeast-2

    회전할 때는 이 시크릿과 Datadog webhook 의 커스텀 헤더를 함께 바꾼다.
    한쪽만 바꾸면 Lambda 가 403 을 내고 알림이 조용히 사라진다.
  EOT
  type        = string
  default     = "o2/dev/dify-alert"
}

variable "alert_secret_name_o2" {
  description = <<-EOT
    O2 Dify 앱 전용 알림 중계 파이프라인이 읽는 Secrets Manager 시크릿 이름.

    alert_secret_name(alert-triage 앱용)과 시크릿을 공유하지 않는다 — 공유하면
    한쪽 앱의 API 키를 바꿀 때마다 다른 쪽이 깨진다. lambda_o2.tf 가 이 이름으로
    별도 Ingress/Worker 쌍을 만든다.

    시크릿은 apply 전에 손으로 한 번 만든다. 키 형식은 alert_secret_name 과 같다:

      aws secretsmanager create-secret --name o2/dev/dify-alert-o2 \
        --secret-string '{"dify-api-key":"app-...","webhook-secret":"..."}' \
        --region ap-northeast-2
  EOT
  type        = string
  default     = "o2/dev/dify-alert-o2"
}

variable "alert_relay_max_concurrency" {
  description = <<-EOT
    알림 중계 Lambda 의 예약 동시성. **폭주 상한이다.**

    라이브 방송이 시작되면 CPU·DB 커넥션·응답시간 모니터가 한꺼번에 울린다.
    상한이 없으면 알림 수만큼 AI 워크플로가 돌고 그대로 토큰 요금이 된다.
    상한에 걸린 호출은 버려지지만, 알림이 동시에 5개를 넘는 상황이면
    이미 Lambda 가 아니라 모니터 조건을 고쳐야 하는 상태다.
  EOT
  type        = number
  default     = 5
}

# ── Agent 공통 진입점 ────────────────────────────────────────────

variable "agent_entry_secret_name" {
  description = <<-EOT
    전용 Agent Entry contract-test Dify 앱의 API key를 보관한 Secrets Manager 이름.

    SecretString은 Terraform으로 만들거나 읽지 않는다. 값은 다음 key 하나를 가진다:

      dify-api-key  전용 테스트 앱의 Service API key

    Phase 1B Worker는 이 이름만 참조하고 AGENT_ENTRY_EXECUTION_ENABLED=false라
    자동으로 값을 사용하지 않는다.
  EOT
  type        = string
  default     = "o2/dev/dify-agent-entry-contract-test"
}

variable "agent_entry_worker_max_concurrency" {
  description = "전용 Dify 테스트 앱을 보호하는 Generic Worker 예약 동시성 상한"
  type        = number
  default     = 2

  validation {
    condition     = var.agent_entry_worker_max_concurrency >= 2 && var.agent_entry_worker_max_concurrency <= 10
    error_message = "Lambda SQS scaling 하한과 운영 안전 범위를 고려해 2 이상 10 이하로 둔다."
  }
}

variable "agent_entry_idempotency_ttl_seconds" {
  description = "성공·실패 멱등성 상태 보존 기간. DLQ 14일보다 길어 replay 중 중복 호출을 막는다."
  type        = number
  default     = 2592000 # 30일

  validation {
    condition     = var.agent_entry_idempotency_ttl_seconds >= 1209600
    error_message = "DLQ 최대 보존 기간 14일 이상이어야 한다."
  }
}

variable "agent_entry_execution_enabled" {
  description = "Phase 3 합성 Queue E2E에서만 true로 바꾸는 Generic Worker 실행 게이트"
  type        = bool
  default     = false
}

variable "agent_entry_event_source_enabled" {
  description = "Phase 3 합성 Queue E2E에서만 true로 바꾸는 SQS event source 게이트"
  type        = bool
  default     = false
}

variable "agent_entry_allowed_idempotency_keys" {
  description = "Phase 3에서 Dify 호출을 허용할 합성 Chat idempotency key. 활성화 시 정확히 1개"
  type        = set(string)
  default     = []

  validation {
    condition = alltrue([
      for value in var.agent_entry_allowed_idempotency_keys :
      can(regex("^chat:cand_[0-9A-HJKMNP-TV-Z]{26}$", value))
    ])
    error_message = "Phase 3 allowlist는 chat:cand_<ULID> 형식만 허용한다."
  }
}

# ── Incident Correlator (Phase 3B: 비활성) ───────────────────────

variable "incident_correlator_max_concurrency" {
  description = "Signal Queue를 직렬에 가깝게 처리하는 Correlator 예약 동시성 상한"
  type        = number
  default     = 2

  validation {
    condition     = var.incident_correlator_max_concurrency >= 2 && var.incident_correlator_max_concurrency <= 10
    error_message = "Lambda SQS scaling 하한과 상태 경합 상한을 고려해 2 이상 10 이하로 둔다."
  }
}

variable "incident_correlator_execution_enabled" {
  description = "Phase 3C 합성 상관관계 E2E에서만 true로 바꾸는 Correlator 실행 게이트"
  type        = bool
  default     = false
}

variable "incident_correlator_event_source_enabled" {
  description = "Phase 3C 합성 상관관계 E2E에서만 true로 바꾸는 Signal Queue event source 게이트"
  type        = bool
  default     = false
}

variable "incident_correlation_window_seconds" {
  description = "두 source event time을 같은 OPEN Incident 후보로 볼 시간창. Phase 3C 실측 전 기본값 0"
  type        = number
  default     = 0

  validation {
    condition     = var.incident_correlation_window_seconds >= 0 && floor(var.incident_correlation_window_seconds) == var.incident_correlation_window_seconds
    error_message = "correlation window는 0 이상의 정수 초여야 한다. 0이면 Correlator를 활성화할 수 없다."
  }
}

variable "incident_correlator_allowed_idempotency_keys" {
  description = "Phase 3C에서 상태 접근을 허용할 합성 source idempotency key. 활성화 시 1~3개"
  type        = set(string)
  default     = []

  validation {
    condition = alltrue([
      for value in var.incident_correlator_allowed_idempotency_keys :
      can(regex("^(chat:cand_[0-9A-HJKMNP-TV-Z]{26}|datadog:[^,:]{1,128}:(Triggered|Re-Triggered|Recovered|Warn|No Data|Renotify))$", value))
    ])
    error_message = "Correlator allowlist는 합성 chat:cand_<ULID> 또는 datadog:<cycle>:<transition> 형식만 허용한다."
  }
}

variable "incident_chat_surface_map" {
  description = "Chat suspected_surface를 source 독립 상관관계 차원으로 바꾸는 고정 mapping"
  type = map(object({
    symptom_family    = string
    suspected_surface = string
    service           = string
  }))
  default = {
    READ_PATH = {
      symptom_family    = "LATENCY"
      suspected_surface = "READ_PATH"
      service           = "api"
    }
  }
}

variable "incident_datadog_monitor_map" {
  description = "Datadog monitor_id를 상관관계 차원으로 바꾸는 명시 mapping. Phase 3B 기본값은 비어 있음"
  type = map(object({
    symptom_family    = string
    suspected_surface = string
    service           = string
  }))
  default = {}
}

# ── Slack 승인 중계 Lambda ───────────────────────────────────────

variable "slack_approval_secret_name" {
  description = <<-EOT
    Slack 승인 중계 Lambda 가 실행 시점에 읽는 **Secrets Manager 시크릿 이름**.

    alert_secret_name 과 같은 이유로 값이 아니라 이름만 참조한다. 시크릿은
    apply 전에 손으로 한 번 만든다. 키 네 개가 필요하다:

      slack-bot-token       Bot User OAuth Token (xoxb-...)
      slack-channel-id      알림 보낼 채널 ID (C로 시작, 채널 이름 아님)
      slack-signing-secret  Slack App Basic Information 의 Signing Secret
      approval-api-key      임의로 정하는 값. Dify 의 SLACK_APPROVAL_API_KEY
                             환경변수와 반드시 같아야 한다

      aws secretsmanager create-secret --name o2/dev/slack-approval \
        --secret-string '{"slack-bot-token":"xoxb-...","slack-channel-id":"C...","slack-signing-secret":"...","approval-api-key":"..."}' \
        --region ap-northeast-2
  EOT
  type        = string
  default     = "o2/dev/slack-approval"
}

# ── Runbook Lookup Lambda ────────────────────────────────────────

variable "runbook_lookup_secret_name" {
  description = <<-EOT
    Runbook Lookup Lambda 가 실행 시점에 읽는 **Secrets Manager 시크릿 이름**.

    값이 아니라 이름만 참조한다. 시크릿은 apply 전에 손으로 한 번 만든다.
    키 하나가 필요하다:

      runbook-lookup-api-key   임의로 정하는 값. Dify 의
                                RUNBOOK_LOOKUP_API_KEY 환경변수와 반드시 같아야 한다

      aws secretsmanager create-secret --name o2/dev/runbook-lookup \
        --secret-string '{"runbook-lookup-api-key":"..."}' \
        --region ap-northeast-2
  EOT
  type        = string
  default     = "o2/dev/runbook-lookup"
}

# ── Session Manager ──────────────────────────────────────────────

variable "manage_session_preferences" {
  description = <<-EOT
    Session Manager 세션 설정(SSM-SessionManagerRunShell)을 이 스택이 소유한다.

    ★ 계정 전역이다. EKS 노드 접속을 포함한 모든 세션에 적용되고,
    destroy 하면 계정 기본값으로 돌아간다. 세션 설정을 다른 스택도
    필요로 하게 되면 false 로 두고 계정 베이스라인 쪽으로 옮긴다.
  EOT
  type        = bool
  default     = true
}

variable "session_idle_timeout_minutes" {
  description = <<-EOT
    무통신 상태가 이만큼 지속되면 세션을 끊는다.

    ★ AWS 상한이 60 이다. "6시간 유휴 허용" 은 불가능하다.
    긴 스튜디오 작업을 끊기지 않게 하는 것은 이 값이 아니라
    tunnel.sh 의 keepalive 다 — 주기적으로 트래픽을 흘려 유휴 자체를
    만들지 않는다. 그러면 실제 상한은 session_max_duration_minutes 가 된다.
  EOT
  type        = number
  default     = 60

  validation {
    condition     = var.session_idle_timeout_minutes >= 1 && var.session_idle_timeout_minutes <= 60
    error_message = "1 이상 60 이하. AWS 상한이 60분이다."
  }
}

variable "session_max_duration_minutes" {
  description = <<-EOT
    활동 여부와 무관하게 세션을 끊는 절대 상한. 360 = 6시간.

    무제한으로 두지 않는다. 터널을 켜둔 채 노트북을 덮으면 세션이
    영원히 남고, 그게 정상인지 아닌지 알 방법이 없다.
  EOT
  type        = number
  default     = 360

  validation {
    condition     = var.session_max_duration_minutes >= 1 && var.session_max_duration_minutes <= 1440
    error_message = "1 이상 1440 이하 (24시간)."
  }
}
