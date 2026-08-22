terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }

  backend "s3" {
    bucket       = "o2-tfstate-066107819912"
    key          = "chat-signal/terraform.tfstate"
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
      Stack       = "chat-signal"
      CostCenter  = var.project
    }
  }
}
