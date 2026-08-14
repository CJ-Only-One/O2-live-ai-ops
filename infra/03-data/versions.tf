terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "s3" {
    bucket = "o2-tfstate-066107819912"

    # data/ 가 아니다. 그 키는 AI 에이전트 백데이터 파트가 쓰고 있고,
    # 같은 키를 쓰면 서로의 리소스를 자기 것으로 인식해 지운다. (docs/decisions.md D-015)
    key = "datastore/terraform.tfstate"

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
      Stack       = "data"
      CostCenter  = var.project
    }
  }
}
