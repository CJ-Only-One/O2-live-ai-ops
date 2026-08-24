###############################################################################
# APM span-derived metrics
#
# pod_name은 APM additional primary tag 후보가 아니므로 표준
# trace.fastapi.request 메트릭을 pod_name으로 나눌 수 없다. 하지만 수집된
# span에는 pod_name이 실제 태그로 들어온다. span-based distribution metric은
# 그 태그를 group_by로 승격하므로 primary tag 변경 없이 파드별 percentile을
# 계산할 수 있다.
###############################################################################

resource "datadog_spans_metric" "api_request_duration" {
  name = "o2.apm.request.duration"

  compute {
    aggregation_type    = "distribution"
    include_percentiles = true
    path                = "@duration"
  }

  filter {
    query = "service:api env:${var.environment} operation_name:fastapi.request -resource_name:\"GET /api/readyz\" -resource_name:\"GET /api/healthz\""
  }

  group_by {
    path     = "pod_name"
    tag_name = "pod_name"
  }

  group_by {
    path     = "service"
    tag_name = "service"
  }

  group_by {
    path     = "env"
    tag_name = "env"
  }

  group_by {
    path     = "version"
    tag_name = "version"
  }
}

resource "datadog_spans_metric" "api_db_duration" {
  name = "o2.apm.db.duration"

  compute {
    aggregation_type    = "distribution"
    include_percentiles = true
    path                = "@duration"
  }

  filter {
    query = "service:api env:${var.environment} operation_name:pymysql.query"
  }

  group_by {
    path     = "pod_name"
    tag_name = "pod_name"
  }

  group_by {
    path     = "service"
    tag_name = "service"
  }

  group_by {
    path     = "env"
    tag_name = "env"
  }

  group_by {
    path     = "version"
    tag_name = "version"
  }
}
