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

    # media/ 다. 다른 스택과 겹치지 않는다 — 키가 겹치면 서로의 리소스를
    # 자기 것으로 인식해 지운다 (docs/decisions.md D-015).
    key = "media/terraform.tfstate"

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
      Stack       = "media"
      CostCenter  = var.project
    }
  }
}
