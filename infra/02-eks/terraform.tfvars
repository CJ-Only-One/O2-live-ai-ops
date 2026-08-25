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

# t3 계열로 돌아가지 않는다. baseline 0.4 vCPU 를 Datadog 에이전트(노드당 300m)가
# 거의 다 먹어서, 부하가 없는데도 노드가 20% 에 클램프됐다. 크기를 올려도 t3 는
# baseline 이 vCPU 수에만 걸려 있어 안 풀린다 (t3.medium 도 400m). 관측을 켜 둘
# 거면 비버스터블이어야 한다.
#
# m6i.large 로 재고 c6i.large 로 내렸다. 둘 다 Intel Xeon 8375C · 3.5GHz · 2 vCPU 로
# **CPU 가 동일**하고 메모리만 8 → 4 GiB 다. 측정에서 메모리 실사용이 allocatable 의
# 18% 였고 requests 도 53% 라 8 GiB 는 안 쓰던 부분이다 (M-009 · M-010).
# 월 $170 → $138.
#
# Graviton(c6g.large, 월 $111)이 더 싸지만 ECR 이미지가 단일 아키(amd64)이고
# CI 에 platforms 지정이 없다. 재빌드와 서드파티 검증 비용이 절약액보다 크다.
node_instance_types = ["c6i.large"]
node_capacity_type  = "ON_DEMAND"
# AZ 하나가 죽어도 남은 AZ 에 전부 들어가야 한다. 2 대일 때 한쪽을 잃으면
# 옮겨갈 요청량(1030m·2128Mi)이 남은 노드 여유(230m·416Mi)를 넘어 파드가
# Pending 으로 남았다 (2026-08-25 실측). AZ 당 2 대로 둔다.
#
# desired_size 는 lifecycle 의 ignore_changes 에 있어 terraform 이 안 바꾼다.
# 실제로 대수를 올리는 것은 min_size 다.
node_desired_size = 4
node_min_size     = 4
node_max_size     = 6

# CI/CD 자격증명은 infra/00-cicd 스택이 소유한다.
# 배포는 Argo CD(GitOps)라 CI가 클러스터에 접근할 필요가 없다. (docs/decisions.md D-009)

cluster_public_access_cidrs = ["0.0.0.0/0"]

# Karpenter 용 IAM·SQS·EventBridge. Helm 설치는 04-platform 의 enable_karpenter.
# 켜는 순서: 02-eks 먼저, 그다음 04-platform. 끄는 순서는 반대다.
enable_karpenter = true
