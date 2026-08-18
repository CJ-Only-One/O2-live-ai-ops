# Datadog 안을 채우는 스택이다.
#
# AWS 리소스를 만들지 않는다. 그래서 aws 프로바이더가 없다 — 이 스택이
# 소유하는 것은 Datadog 쪽 객체(대시보드·Monitor)뿐이다. Datadog Agent 는
# `04-platform` 이 Helm 으로 넣고, 비즈니스 메트릭은 `06-datastream` 의
# 집계 Lambda 가 직접 푸시한다. 여기는 **보는 쪽**만 담당한다.
#
# 왜 04-platform 과 한 스택에 두지 않는가:
#   그쪽은 클러스터 접근(helm·kubectl 프로바이더)이 필요해서 클러스터가
#   살아 있어야 plan 이 된다. 대시보드는 클러스터와 무관하므로 묶으면
#   클러스터가 없을 때 대시보드도 못 고치게 된다.

terraform {
  required_version = ">= 1.10"

  required_providers {
    datadog = {
      source  = "DataDog/datadog"
      version = "~> 3.0"
    }
  }

  backend "s3" {
    bucket = "o2-tfstate-066107819912"

    # `datadog/` 이 아니라 `observability/` 다. 스택 번호도 쓰지 않는다.
    # 번호는 의존 순서라 바뀔 수 있고(D-025 에서 05는 media 예약이었다),
    # 키가 바뀌면 state 가 갈린다. 역할로 이름을 둔다.
    key = "observability/terraform.tfstate"

    region       = "ap-northeast-2"
    encrypt      = true
    use_lockfile = true
  }
}

# API·APP 키를 여기에 적지 않는다. 프로바이더가 DD_API_KEY / DD_APP_KEY
# 환경변수를 직접 읽는다. 변수로 받으면 값이 plan 파일과 셸 히스토리에
# 남고, Secrets Manager data source 로 읽으면 **state 에 평문으로 남는다**
# (data source 결과도 state 에 저장된다). D-026 과 같은 이유다.
#
#   $env:DD_API_KEY = "..."   # o2/dev/datadog 의 api-key
#   $env:DD_APP_KEY = "..."   # o2/dev/datadog 의 app-key
provider "datadog" {
  api_url = var.datadog_api_url
}
