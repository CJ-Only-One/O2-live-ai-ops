data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

# 네트워크 스택 출력값을 참조한다.
# VPC ID/서브넷 ID를 하드코딩하지 않는 이유:
#  - 네트워크 스택을 재생성해도 EKS 스택이 자동으로 새 값을 따라감
#  - 팀원이 VPC를 실수로 하드코딩해 다른 VPC에 노드를 띄우는 사고 방지
data "terraform_remote_state" "network" {
  backend = "s3"

  config = {
    bucket = var.network_state_bucket
    key    = var.network_state_key
    region = var.region
  }
}

locals {
  vpc_id             = data.terraform_remote_state.network.outputs.vpc_id
  vpc_cidr           = data.terraform_remote_state.network.outputs.vpc_cidr
  private_subnet_ids = data.terraform_remote_state.network.outputs.private_app_subnet_ids
  public_subnet_ids  = data.terraform_remote_state.network.outputs.public_subnet_ids
}
