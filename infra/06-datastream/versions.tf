terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source = "hashicorp/aws"

      # 다른 스택(01·02·03·04)은 `~> 6.0` 을 쓴다. 이 스택만 5.x 인 것은
      # 리소스 30개가 이미 5.x 로 apply 되어 있기 때문이다. 올리려면
      # 6.0 upgrade guide 를 보고 plan 이 비는 것을 확인한 뒤 따로 올린다.
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }

  backend "s3" {
    bucket = "o2-tfstate-066107819912"

    # `datastore/` 가 아니다. 그쪽은 03-data(RDS·Valkey·SQS)가 쓴다.
    # 이 키가 원래 주인이고, 03-data 가 뒤에 와서 비켜 간 것이다. (D-015 · D-025)
    key = "data/terraform.tfstate"

    region = "ap-northeast-2"

    # 다른 스택은 use_lockfile 을 쓰지만 여기는 DynamoDB 락을 유지한다.
    # 이미 이 방식으로 잠긴 state 라 바꾸면 락이 두 곳으로 갈린다.
    dynamodb_table = "o2-tflock"
    encrypt        = true
  }
}

provider "aws" {
  region = "ap-northeast-2"

  # 태그를 바꾸면 리소스 30개 전부에 diff 가 뜬다. 이관 시점의 값을 그대로 둔다.
  default_tags {
    tags = {
      Project   = "o2"
      ManagedBy = "Terraform"
      Team      = "data"
    }
  }
}
