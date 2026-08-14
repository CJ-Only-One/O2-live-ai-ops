data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# 네트워크 스택 출력값을 참조한다. 02-eks 와 같은 패턴이다.
# VPC ID/서브넷을 하드코딩하면 네트워크를 재생성했을 때 조용히 어긋난다.
data "terraform_remote_state" "network" {
  backend = "s3"

  config = {
    bucket = var.network_state_bucket
    key    = var.network_state_key
    region = var.region
  }
}

# 노드가 붙어 있는 보안 그룹을 알아야 RDS/Valkey 인그레스를 그것으로 좁힐 수 있다.
# 02-eks 는 자체 SG 를 만들지 않고 EKS 가 자동 생성한 클러스터 SG 를 쓴다.
data "aws_eks_cluster" "this" {
  name = var.cluster_name
}

locals {
  name     = "${var.project}-${var.environment}"
  vpc_id   = data.terraform_remote_state.network.outputs.vpc_id
  vpc_cidr = data.terraform_remote_state.network.outputs.vpc_cidr

  db_subnet_group_name    = data.terraform_remote_state.network.outputs.db_subnet_group_name
  cache_subnet_group_name = data.terraform_remote_state.network.outputs.elasticache_subnet_group_name

  # 관리형 노드그룹의 파드와 노드가 모두 이 SG 를 단다.
  node_security_group_id = data.aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}

# 01-network 의 enable_data_tier 가 false 면 서브넷 그룹이 없다.
# 그 상태로 apply 하면 RDS 생성 단계에서 알아보기 어려운 오류가 나므로
# 여기서 먼저 멈추고 무엇을 해야 하는지 알려준다.
resource "terraform_data" "require_data_tier" {
  lifecycle {
    precondition {
      condition     = local.db_subnet_group_name != null && local.cache_subnet_group_name != null
      error_message = "01-network 의 terraform.tfvars 에서 enable_data_tier = true 로 바꾸고 먼저 apply 할 것."
    }
  }
}
