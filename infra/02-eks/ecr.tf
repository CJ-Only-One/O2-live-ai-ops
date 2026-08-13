resource "aws_ecr_repository" "app" {
  name                 = "${var.project}/testpage"
  image_tag_mutability = "IMMUTABLE" # 커밋 SHA 태그 재사용 방지. 배포 추적성 확보

  image_scanning_configuration {
    scan_on_push = true
  }

  # 3주 프로젝트 종료 시 이미지가 남아 destroy를 막지 않도록
  force_delete = true
}

# CI가 커밋마다 이미지를 밀어넣으므로 방치하면 계속 쌓인다.
# $0.10/GB-월이라 금액은 작지만, 정리 정책이 없는 레지스트리는
# Phase 3 부하테스트 반복 배포 때 수십 GB가 된다.
resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      },
    ]
  })
}
