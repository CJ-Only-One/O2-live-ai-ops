# 클러스터 "안"을 채우는 스택이다.
#
# 01~03이 만드는 AWS 리소스는 클러스터를 지웠다 만들어도 살아남지만,
# 클러스터 안의 것들(Argo CD, 네임스페이스, 파드)은 함께 사라진다.
# 그것들을 코드로 남겨 클러스터가 새로 생길 때마다 자동 복원되게 한다.
#
# 02-eks 와 한 스택에 둘 수 없는 이유:
#   helm 프로바이더는 설정 시점에 클러스터 주소와 토큰이 필요한데,
#   클러스터를 만드는 apply와 같은 스택이면 첫 실행에서 "아직 모르는 값"이라
#   깨진다. 그래서 스택을 나누고 remote state로 넘겨받는다.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    helm = {
      source = "hashicorp/helm"
      # 3.x에서 kubernetes 설정 블록 문법이 바뀌었다. 2.x 문법으로 작성했으므로 고정한다.
      version = "~> 2.17"
    }
    # CRD를 같은 apply에서 설치한 뒤 ExternalSecret을 적용하려면,
    # 계획 시점에 CRD 스키마를 요구하지 않는 provider가 필요하다.
    kubectl = {
      source  = "gavinbunney/kubectl"
      version = "~> 1.19"
    }
  }

  backend "s3" {
    # 팀이 이미 쓰는 버킷이다. 00-cicd 만 다른 버킷에 있는데 이쪽으로 합쳐야 한다.
    bucket       = "o2-tfstate-066107819912"
    key          = "platform/terraform.tfstate"
    region       = "ap-northeast-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Team        = var.team
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
      Stack       = "platform"
      CostCenter  = var.project
    }
  }
}

# 02-eks 의 출력을 받아온다. 클러스터를 소유하지 않고 참조만 하므로
# 그쪽 state와 충돌하지 않는다.
data "terraform_remote_state" "eks" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = var.eks_state_key
    region = var.region
  }
}

locals {
  cluster_name = data.terraform_remote_state.eks.outputs.cluster_name
  lbc_role_arn = data.terraform_remote_state.eks.outputs.lbc_role_arn
}

data "aws_eks_cluster" "this" {
  name = local.cluster_name
}

# 이 토큰은 실행하는 IAM 주체의 것이다. 그 주체에게 클러스터 접근 권한
# (access entry)이 없으면 helm 프로바이더가 인증에 실패한다.
# 그래서 아래에서 access entry를 먼저 만든다.
data "aws_eks_cluster_auth" "this" {
  name = local.cluster_name
}

provider "helm" {
  kubernetes {
    host                   = data.aws_eks_cluster.this.endpoint
    cluster_ca_certificate = base64decode(data.aws_eks_cluster.this.certificate_authority[0].data)
    token                  = data.aws_eks_cluster_auth.this.token
  }
}

# External Secrets CRD는 ESO Helm chart가 설치한다. kubernetes_manifest는 plan 시점에
# 아직 없는 CRD의 OpenAPI 스키마를 읽으려 해 첫 apply가 실패하므로 사용하지 않는다.
provider "kubectl" {
  host                   = data.aws_eks_cluster.this.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.this.certificate_authority[0].data)
  token                  = data.aws_eks_cluster_auth.this.token
  load_config_file       = false
}

# ── 클러스터 접근 권한 ────────────────────────────────────────
# 클러스터가 새로 생기면 access entry도 초기화된다. 손으로 다시 만들지 않도록
# 코드로 남긴다. 원래는 02-eks(클러스터 소유자)에 있는 편이 맞지만,
# 그 스택은 다른 사람이 관리 중이라 합류 전까지 여기서 관리한다.
resource "aws_eks_access_entry" "admin" {
  for_each = toset(var.cluster_admin_arns)

  cluster_name  = local.cluster_name
  principal_arn = each.value
  type          = "STANDARD"
}

resource "aws_eks_access_policy_association" "admin" {
  for_each = toset(var.cluster_admin_arns)

  cluster_name  = local.cluster_name
  principal_arn = each.value
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"

  access_scope {
    type = "cluster"
  }

  depends_on = [aws_eks_access_entry.admin]
}
