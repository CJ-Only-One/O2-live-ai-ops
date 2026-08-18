data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# 네트워크 스택 출력값을 참조한다. 02-eks, 03-data 와 같은 패턴이다.
data "terraform_remote_state" "network" {
  backend = "s3"

  config = {
    bucket = var.network_state_bucket
    key    = var.network_state_key
    region = var.region
  }
}

# EKS 파드에서 Dify 를 호출할 수 있게 인그레스를 노드 SG 로 좁힌다.
# 03-data 와 같은 이유로 remote state 대신 data source 로 읽는다.
data "aws_eks_cluster" "this" {
  name = var.cluster_name
}

# 노드그룹과 같은 AL2023 을 쓴다. 운영 대상이 두 종류가 되면 패치와
# 트러블슈팅이 두 배가 된다.
data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

locals {
  name   = "${var.project}-${var.environment}-dify"
  vpc_id = data.terraform_remote_state.network.outputs.vpc_id

  # 앱 서브넷에 둔다. 데이터 서브넷은 RDS/ElastiCache 전용이고
  # 라우팅에 NAT 가 없을 수 있다 — Dify 는 이미지 pull 과 LLM 호출에
  # 아웃바운드가 필요하다.
  subnet_id = data.terraform_remote_state.network.outputs.private_app_subnet_ids[0]

  node_security_group_id = data.aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}
