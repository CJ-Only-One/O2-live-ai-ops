team        = "o2"
project     = "o2"
environment = "dev"
region      = "ap-northeast-2"

cluster_name = "o2-eks"

network_state_bucket = "o2-tfstate-066107819912"
network_state_key    = "network/terraform.tfstate"

# ── 호스트 ────────────────────────────────────────────────────────
# 컨테이너 9개 + postgres + weaviate. 4 GiB 는 인덱싱에서 OOM 이 난다.
# EKS 노드와 같은 t3.small 로 내리지 말 것.
instance_type    = "t3.large" # 2 vCPU / 8 GiB
root_volume_size = 60

# main 은 언제든 깨진다. apply 전에 릴리스 태그를 확인해 고정할 것:
#   curl -s https://api.github.com/repos/langgenius/dify/releases/latest \
#     | jq -r .tag_name
dify_ref = "1.16.1"

# Bedrock 을 모델 공급자로 쓸 때만 true.
# 외부 LLM API 만 쓸 거면 false 로 두고 키는 Dify UI 에서 넣는다.
enable_bedrock_access = true

# 운영 Incident Worker는 현재 배포된 운영 Dify workflow key를 유지한다.
agent_entry_secret_name = "o2/dev/dify-alert-o2"

# ── Session Manager (계정 전역) ───────────────────────────────────
# idle 은 AWS 상한이 60분이라 더 못 올린다.
# 6시간 연속 작업은 max_duration 360 + tunnel.sh 의 keepalive 조합으로 만든다.
manage_session_preferences   = true
session_idle_timeout_minutes = 60
session_max_duration_minutes = 360

# 2026-08-25 운영 Incident handoff 승인. 운영 모드에서는 합성 Incident allowlist를 비운다.
agent_entry_execution_enabled            = true
agent_entry_event_source_enabled         = true
agent_entry_operational_handoff_approved = true
agent_entry_allowed_incident_ids         = []

# Agent Worker가 Valkey 원본 상태를 읽는 인증 GET. 키 값은 SSM SecureString에 둔다.
agent_read_path_status_url = "http://k8s-o2dev-frontend-0af27d967f-1008618203.ap-northeast-2.elb.amazonaws.com/api/admin/read-path-degraded"

# ── S2 실험 게이트 ────────────────────────────────────────────────
# RB-API-LATENCY-001(1차 증설)과 RB-API-POD-RESOURCE-SKEW(격리)는 승격 증거가
# 아직 없어 draft 다. Lookup 은 draft 를 안 돌려주므로, S2 시연 동안에만 정확히
# 이 두 개를 조회 예외로 연다. Lambda 가 매 호출마다 만료를 검사한다.
#
# 2026-08-26 20:4x 기록 — 값 자체는 그날 09:59:44 에 라이브 Lambda 에 이미
# 들어가 있었는데 tfvars 에는 없었다. 그 상태에서 누가 06-agent 를 apply 하면
# terraform 이 "코드에 없으니 지운다"로 판단해 실험 도중에 게이트를 끈다
# (실제로 plan 이 그 변경을 냈다). 라이브를 코드에 받아적어 드리프트를 없앤다.
#
# 실험이 끝나면 enabled = false 로 내리고 나머지 둘을 기본값으로 되돌린다.
s2_experiment_runbook_enabled  = true
s2_experiment_id               = "s2-20260827T074450"
s2_experiment_expires_at_epoch = 1787827490 # 2026-08-27 19:44:50 KST
