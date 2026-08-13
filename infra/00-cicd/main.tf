# 파이프라인이 AWS에 접근하기 위한 최소 구성이다.
# 01~03이 만드는 런타임 인프라와 성격이 달라 스택을 나눴고,
# 번호가 00인 이유는 나머지 전부보다 먼저 있어야 하기 때문이다
# (이것이 없으면 tf.yml이 01조차 apply하지 못한다).
#
# 최초 1회는 로컬에서 적용한다. state를 둘 곳도, 역할도 없는 상태에서
# 파이프라인이 스스로를 만들 수는 없다.
#
#   cd infra/00-cicd
#   eval "$(aws configure export-credentials --profile default --format env)"
#   terraform init && terraform apply

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # state에는 RDS 비밀번호 같은 값이 평문으로 들어가므로 로컬에 두지 않는다.
  # 로컬에 두면 팀이 공유할 수 없고, CI 러너는 매번 새 머신이라 state가 비어
  # 이미 존재하는 리소스를 다시 만들려다 실패한다.
  #
  # key는 스택 이름으로 나눈다. 02·03이 01의 출력을 remote state로 참조할 때
  # 이 경로를 그대로 쓴다.
  #
  # 버킷은 손으로 만들었다 — state를 보관할 곳을 만드는 데 state가 필요한
  # 순환을 피하기 위해서다. 이 스택 하나만 그렇고 나머지는 처음부터 S3를 쓴다.
  backend "s3" {
    # 팀 공용 버킷. 처음에는 이 버킷의 존재를 모르고 별도 버킷을 만들었으나,
    # 한 프로젝트의 state가 두 곳에 흩어지면 백업·권한·수명주기를 두 벌
    # 관리해야 하고 새로 온 사람이 한쪽만 보고 전부인 줄 알기 쉽다.
    # 키 이름은 다른 스택(network/, eks/, platform/)의 규칙을 따른다.
    bucket = "o2-tfstate-066107819912"
    key    = "cicd/terraform.tfstate"
    region = "ap-northeast-2"

    encrypt = true
    # Terraform 1.10부터 S3 자체 잠금을 지원한다.
    # 예전처럼 DynamoDB 테이블을 따로 둘 필요가 없다.
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "github_org" {
  type    = string
  default = "CJ-Only-One"
}

variable "github_repo" {
  type    = string
  default = "O2-live-ai-ops"
}

# GitHub의 immutable subject claim에 쓰이는 숫자 ID다.
# 이 조직은 sub가 "repo:CJ-Only-One@315606307/O2-live-ai-ops@1331684285:..."
# 형태로 나온다. 확인 방법:
#   gh api /repos/CJ-Only-One/O2-live-ai-ops/actions/oidc/customization/sub
variable "github_org_id" {
  type    = string
  default = "315606307"
}

variable "github_repo_id" {
  type    = string
  default = "1331684285"
}

variable "services" {
  description = "ECR 저장소를 만들 서비스 목록. apps/ 에 서비스를 추가하면 여기에도 넣는다."
  type        = list(string)
  default     = ["api"]
}

locals {
  # 이름이 바뀌어도(immutable ID) 이름 그대로여도 매칭되도록 둘 다 받는다.
  # 두 형태 모두 이 저장소 하나로 고정되므로 범위가 넓어지지는 않는다.
  repo_subs = [
    "repo:${var.github_org}/${var.github_repo}",
    "repo:${var.github_org}@${var.github_org_id}/${var.github_repo}@${var.github_repo_id}",
  ]
}

# ── OIDC 프로바이더 ───────────────────────────────────────────
# 계정당 하나만 존재할 수 있는 계정 단위 리소스다.
# 여러 저장소가 공유하므로, 소유자를 한 곳으로 정해두지 않으면
# 어느 스택을 destroy할 때 다른 스택이 함께 깨진다. 이 저장소가 소유한다.
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # GitHub이 루트 CA를 바꿔도 STS가 검증해주므로 이 값은 형식상 남겨둔다.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# ── 애플리케이션 배포용 역할 ──────────────────────────────────
# app.yml이 쓴다. ECR push 외에는 아무것도 못 한다.
resource "aws_iam_role" "app" {
  name        = "o2-live-github-app"
  description = "app.yml - build image and push to ECR"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        # main 브랜치에서만 빌릴 수 있다. 이미지를 밀 수 있는 역할이므로
        # 아무 브랜치에서나 빌릴 수 있게 두면 임의의 이미지가 올라간다.
        StringLike = {
          "token.actions.githubusercontent.com:sub" = [
            for s in local.repo_subs : "${s}:ref:refs/heads/main"
          ]
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "app_ecr" {
  name = "ecr-push"
  role = aws_iam_role.app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # 로그인 토큰 발급은 리소스를 특정할 수 없어 * 로 둘 수밖에 없다.
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:CompleteLayerUpload",
          "ecr:InitiateLayerUpload",
          "ecr:PutImage",
          "ecr:UploadLayerPart",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
        ]
        Resource = [for r in aws_ecr_repository.service : r.arn]
      },
    ]
  })
}

# ── Terraform용 역할 ─────────────────────────────────────────
# apply는 각자 로컬에서 자기 자격증명으로 한다(D-005). CI는 PR에서 plan만
# 돌리므로 이 역할은 읽기 전용이면 충분하다.
#
# 예전에는 AdministratorAccess였다. 그런데 `terraform plan` 은 임의 코드를
# 실행할 수 있다 — external data source, 커스텀 provider가 plan 단계에서 돈다.
# 그 상태로 PR 하나면 계정 관리자 자격을 얻을 수 있었다. (D-011)
#
# app 역할과 반드시 분리한다 — 자주 도는 앱 워크플로가 이 권한을 쓰면
# 토큰 유출 시 잃는 범위가 인프라 전체로 넓어진다.
resource "aws_iam_role" "tf" {
  name        = "o2-live-github-tf"
  description = "tf.yml - infrastructure plan only (read-only)"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          # PR의 plan 잡 하나뿐이다. apply 잡은 없앴으므로
          # environment:infra 는 아무도 쓰지 않는 경로였다.
          "token.actions.githubusercontent.com:sub" = [
            for s in local.repo_subs : "${s}:pull_request"
          ]
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "tf_readonly" {
  role       = aws_iam_role.tf.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# ── 서비스별 ECR 저장소 ──────────────────────────────────────

# o2/api 는 폐기한 테스트 저장소가 만들어 둔 것을 import로 넘겨받았다.
# import 블록은 state에 들어온 뒤 역할이 끝나 제거했다. (docs/decisions.md 참고)

resource "aws_ecr_repository" "service" {
  for_each = toset(var.services)
  name     = "o2/${each.value}"

  image_scanning_configuration {
    scan_on_push = true # 취약점 스캔은 공짜다. 끌 이유가 없다.
  }
}

# 태그가 커밋 SHA라 이미지가 무한히 쌓인다. 오래된 것은 정리한다.
resource "aws_ecr_lifecycle_policy" "service" {
  for_each   = aws_ecr_repository.service
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "최근 30개만 남긴다"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 30
      }
      action = { type = "expire" }
    }]
  })
}

output "app_role_arn" {
  description = "GitHub Secrets의 AWS_APP_ROLE_ARN 에 넣을 값"
  value       = aws_iam_role.app.arn
}

output "tf_role_arn" {
  description = "GitHub Secrets의 AWS_TF_ROLE_ARN 에 넣을 값"
  value       = aws_iam_role.tf.arn
}

output "ecr_repository_urls" {
  value = { for k, r in aws_ecr_repository.service : k => r.repository_url }
}
