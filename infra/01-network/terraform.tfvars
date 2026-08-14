# 목표: 테스트 페이지 1개를 EKS에 띄우고 CI/CD로 배포되는지 확인.
# 그 외 전부 비활성.

team        = "o2"
project     = "o2"
environment = "dev"
region      = "ap-northeast-2"

# 2 AZ. EKS 컨트롤플레인 최소 요건이라 1개로 줄일 수 없다.
# 나중에 늘릴 때는 반드시 "리스트 끝에 append". 중간 삽입 시
# cidrsubnet 인덱스가 밀려 기존 서브넷이 재생성된다.
availability_zones = ["ap-northeast-2a", "ap-northeast-2c"]
vpc_cidr           = "10.0.0.0/16"

eks_cluster_name = "o2-eks"
owner            = "o2"

enable_nat_gateway             = true
single_nat_gateway             = true
enable_ecr_interface_endpoints = false

# private-data 서브넷 + DB/Cache 서브넷 그룹. 03-data 가 이것을 참조한다.
# CIDR 인덱스가 12,13 으로 고정이라 켜도 기존 서브넷에 영향이 없고,
# 서브넷 자체는 과금 대상이 아니다.
enable_data_tier = true

enable_flow_logs = false # 소비할 주체 없음
