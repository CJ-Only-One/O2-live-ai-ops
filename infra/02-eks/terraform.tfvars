team        = "o2"
project     = "o2"
environment = "dev"
region      = "ap-northeast-2"

cluster_name = "o2-eks"

# 표준 지원 버전만 사용할 것.
# 1.33은 2026-07-29 표준 지원 종료 -> $0.60/hr (6배)
# apply 전 확인:
#   aws eks describe-cluster-versions --region ap-northeast-2 \
#     --query 'clusterVersions[?versionStatus==`STANDARD_SUPPORT`].[clusterVersion,endOfStandardSupportDate]' --output table
kubernetes_version = "1.35"

network_state_bucket = "o2-tfstate-066107819912"
network_state_key    = "network/terraform.tfstate"

# 테스트 페이지만 띄우는 최소 구성
node_instance_types = ["t3.small"]
node_capacity_type  = "ON_DEMAND"
node_desired_size   = 2
node_min_size       = 2
node_max_size       = 3

# CI/CD는 나중에. true로 바꾸고 github_repository만 채우면 apply 30초로 붙는다.
enable_github_oidc = false
github_repository  = ""

cluster_public_access_cidrs = ["0.0.0.0/0"]
