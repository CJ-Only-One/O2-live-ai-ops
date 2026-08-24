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

# ── Session Manager (계정 전역) ───────────────────────────────────
# idle 은 AWS 상한이 60분이라 더 못 올린다.
# 6시간 연속 작업은 max_duration 360 + tunnel.sh 의 keepalive 조합으로 만든다.
manage_session_preferences   = true
session_idle_timeout_minutes = 60
session_max_duration_minutes = 360

# 시나리오 4의 role:page composite만 READ_PATH Incident에 연결한다(D-072).
# 하위 sub monitor 두 개와 주문 지연 monitor는 중복·오분류를 피하려고 제외한다.
incident_datadog_monitor_map = {
  "21940250" = {
    symptom_family    = "LATENCY"
    suspected_surface = "READ_PATH"
    service           = "api"
  }
}
