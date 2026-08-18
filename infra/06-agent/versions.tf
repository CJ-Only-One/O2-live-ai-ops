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

    # agent/ 가 아니라 dify/ 다. "agent" 는 AI 에이전트 백데이터 파트가
    # 쓸 가능성이 있는 이름이고, 키가 겹치면 서로의 리소스를 자기 것으로
    # 인식해 지운다 (docs/decisions.md D-015 와 같은 사고).
    # 이 스택이 소유하는 것은 Dify 호스트 하나뿐이므로 그대로 이름 짓는다.
    key = "dify/terraform.tfstate"

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
      Stack       = "agent"
      CostCenter  = var.project
    }
  }
}
