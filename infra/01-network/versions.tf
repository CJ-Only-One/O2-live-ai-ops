terraform {
  # 1.10+ : S3 backend 네이티브 락(use_lockfile) 지원 → DynamoDB 락 테이블 불필요
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # ── 팀 협업 전제: 로컬 state 금지 ─────────────────────────────
  backend "s3" {
    bucket       = "o2-tfstate-066107819912"
    key          = "network/terraform.tfstate"
    region       = "ap-northeast-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  # FinOps 담당자가 Cost Explorer에서 태그 기반으로 쪼개볼 수 있도록 전 리소스 공통 태깅
  default_tags {
    tags = local.common_tags
  }
}
