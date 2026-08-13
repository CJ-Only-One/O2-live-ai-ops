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

# CI/CD 자격증명은 infra/00-cicd 스택이 소유한다.
# 배포는 Argo CD(GitOps)라 CI가 클러스터에 접근할 필요가 없다. (docs/decisions.md D-009)

cluster_public_access_cidrs = ["0.0.0.0/0"]
