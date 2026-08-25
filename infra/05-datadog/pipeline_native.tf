###############################################################################
# AWS 공식 통합 기반 스트림/Lambda/SQS/Firehose 운영 경로
#
# ★ 이 파일의 Monitor 는 **사람이 보는 알림이다.** `@webhook-o2-dify` 를 붙이지
#   않는다(D-088).
#
#   DLQ 에 메시지가 쌓였거나 Firehose 전달이 실패했거나 rollout 이 멈춘 것은
#   AI 에이전트가 조치할 대상이 아니다 — 런북에 대응 액션이 없고, 있어도
#   자동 조치가 위험한 축이다. 그런데 부하 실험 중에는 큐가 밀리면서 이것들이
#   같이 울고, 그때마다 에이전트가 깨어나 시나리오와 무관한 판단을 시작한다
#   (T-017, scenario-readiness.md 5절).
#
#   에이전트를 깨우는 것은 `scenario_alerts.tf` 의 시나리오 진입 Monitor 뿐이다.
###############################################################################

variable "pipeline_dlq_names" {
  description = "업무·Agent 경로에서 실제 메시지를 보존하는 모든 DLQ 이름"
  type        = set(string)
  default = [
    "o2-agg-dlq",
    "o2-dev-order-dlq",
    "o2-dev-agent-trigger-dlq",
    "o2-dev-agent-invocation-dlq",
    "o2-dev-alert-dlq",
    "o2-dev-alert-dlq-o2",
    "o2-dev-chat-candidate-source-adapter-dlq",
  ]
}

variable "pipeline_queue_names" {
  description = "backlog와 oldest age를 보는 실제 처리 큐"
  type        = set(string)
  default = [
    "o2-dev-order",
    "o2-dev-chat-signal",
    "o2-dev-agent-trigger",
    "o2-dev-agent-invocation",
  ]
}

variable "pipeline_firehose_names" {
  type    = set(string)
  default = ["o2-business-to-s3", "o2-client-to-s3"]
}

resource "datadog_monitor" "pipeline_dlq_not_empty" {
  for_each = var.pipeline_dlq_names

  name    = "[O2][DLQ] ${each.value} 메시지 존재"
  type    = "metric alert"
  message = <<-EOT
    `${each.value}`에 재시도를 소진한 메시지가 있습니다. 원인을 확인한 뒤
    원본 큐 계약에 맞춰 redrive 하십시오. DLQ 메시지를 확인하기 전에 삭제하지 않습니다.
  EOT

  query = "max(last_5m):max:aws.sqs.approximate_number_of_messages_visible{queuename:${each.value}} > 0"

  monitor_thresholds { critical = 0 }
  notify_no_data      = false
  require_full_window = false
  tags                = concat(local.monitor_tags, ["scope:pipeline", "signal:dlq"])
}

resource "datadog_monitor" "firehose_delivery_failure" {
  for_each = var.pipeline_firehose_names

  name    = "[O2][Firehose] ${each.value} S3 전달 실패"
  type    = "metric alert"
  message = "`${each.value}`의 S3 전달 실패가 발생했습니다. error output prefix와 Firehose IAM을 확인합니다."
  query   = "min(last_5m):min:aws.firehose.delivery_to_s_3success{deliverystreamname:${each.value}} < 1"

  monitor_thresholds { critical = 1 }
  notify_no_data      = false
  require_full_window = false
  tags                = concat(local.monitor_tags, ["scope:pipeline", "signal:firehose-failure"])
}

resource "datadog_monitor" "deployment_rollout_stalled" {
  name    = "[O2][Kubernetes] Deployment rollout 정체"
  type    = "metric alert"
  message = "10분 동안 unavailable replica가 남아 있습니다. rollout status와 Kubernetes 이벤트를 확인합니다."
  query   = "min(last_10m):max:kubernetes_state.deployment.replicas_unavailable{kube_namespace:${var.kube_namespace}} by {kube_deployment} > 0"

  monitor_thresholds { critical = 0 }
  notify_no_data      = false
  require_full_window = true
  tags                = concat(local.monitor_tags, ["scope:kubernetes", "signal:rollout"])
}

resource "datadog_dashboard" "pipeline_native" {
  title       = "O2 — 스트림 · Lambda · SQS 신뢰도"
  layout_type = "ordered"
  reflow_type = "auto"
  description = "AWS 공식 통합 지표와 애플리케이션 원자 지표를 함께 보는 운영 대시보드."

  widget {
    group_definition {
      title       = "Application atomic metrics"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          title = "Cache hit rate by pod"
          request {
            formula { formula_expression = "hits / total" }
            query {
              metric_query {
                data_source = "metrics"
                name        = "hits"
                query       = "sum:o2.app.cache_access{env:${var.environment},result:hit} by {pod_name}.as_count()"
                aggregator  = "sum"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "total"
                query       = "sum:o2.app.cache_access{env:${var.environment}} by {pod_name}.as_count()"
                aggregator  = "sum"
              }
            }
          }
        }
      }

      widget {
        timeseries_definition {
          title = "Business failure rate by event"
          request {
            formula { formula_expression = "failed / total" }
            query {
              metric_query {
                data_source = "metrics"
                name        = "failed"
                query       = "sum:o2.app.business_event{env:${var.environment},result:failed} by {event}.as_count()"
                aggregator  = "sum"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "total"
                query       = "sum:o2.app.business_event{env:${var.environment}} by {event}.as_count()"
                aggregator  = "sum"
              }
            }
          }
        }
      }

      widget {
        timeseries_definition {
          title = "Chat fanout delivered / dropped items"
          request { q = "sum:o2.app.fanout.items{env:${var.environment}} by {result}.as_rate()" }
        }
      }

      widget {
        timeseries_definition {
          title = "DB pool connections by service / pod / role"
          request { q = "max:o2.app.db.pool.active{env:${var.environment}} by {service,pod_name,operation}" }
          request { q = "max:o2.app.db.pool.idle{env:${var.environment}} by {service,pod_name,operation}" }
          request { q = "max:o2.app.db.pool.overflow{env:${var.environment}} by {service,pod_name,operation}" }
        }
      }

      widget {
        timeseries_definition {
          title = "Order batch size by pod"
          request { q = "avg:o2.app.batch.size{env:${var.environment},service:order-worker} by {pod_name}" }
        }
      }

      widget {
        timeseries_definition {
          title = "Order batch duration avg by pod"
          request { q = "avg:o2.app.operation.duration{env:${var.environment},service:order-worker,operation:order.batch} by {pod_name}" }
        }
      }

      widget {
        timeseries_definition {
          title = "Inventory read duration avg by pod"
          request { q = "avg:o2.app.operation.duration{env:${var.environment},service:api,operation:inventory.read} by {pod_name}" }
        }
      }
    }
  }

  widget {
    group_definition {
      title       = "Lambda — o2-agg"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          title = "Invocation / Error / Throttle"
          request { q = "sum:aws.lambda.invocations{functionname:o2-agg}.as_count()" }
          request { q = "sum:aws.lambda.errors{functionname:o2-agg}.as_count()" }
          request { q = "sum:aws.lambda.throttles{functionname:o2-agg}.as_count()" }
        }
      }
      widget {
        timeseries_definition {
          title = "Duration / Iterator age"
          request { q = "max:aws.lambda.duration{functionname:o2-agg}" }
          request { q = "max:aws.lambda.iterator_age{functionname:o2-agg}" }
        }
      }
    }
  }

  widget {
    group_definition {
      title       = "Kinesis"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          title = "Incoming records"
          request { q = "sum:aws.kinesis.incoming_records{*} by {streamname}.as_count()" }
        }
      }
      widget {
        timeseries_definition {
          title = "Read / Write throttling"
          request { q = "sum:aws.kinesis.read_provisioned_throughput_exceeded{*} by {streamname}.as_count()" }
          request { q = "sum:aws.kinesis.write_provisioned_throughput_exceeded{*} by {streamname}.as_count()" }
        }
      }
    }
  }

  widget {
    group_definition {
      title       = "SQS / DLQ"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          title = "Queue backlog"
          request { q = "max:aws.sqs.approximate_number_of_messages_visible{*} by {queuename}" }
        }
      }
      widget {
        timeseries_definition {
          title = "Oldest message age"
          request { q = "max:aws.sqs.approximate_age_of_oldest_message{*} by {queuename}" }
        }
      }
    }
  }

  widget {
    group_definition {
      title       = "Firehose / S3 freshness"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          title = "DeliveryToS3 data freshness"
          request { q = "max:aws.firehose.delivery_to_s_3data_freshness{*} by {deliverystreamname}" }
        }
      }
      widget {
        timeseries_definition {
          title = "Delivered records / success"
          request { q = "sum:aws.firehose.delivery_to_s_3records{*} by {deliverystreamname}.as_count()" }
          request { q = "min:aws.firehose.delivery_to_s_3success{*} by {deliverystreamname}" }
        }
      }
      widget {
        timeseries_definition {
          title = "Canary source → aggregate → Datadog freshness"
          request { q = "max:o2.warm.pipeline_freshness_seconds{service:o2-canary,env:${var.environment}}" }
        }
      }
    }
  }
}

output "dashboard_pipeline_native_url" {
  value = "${local.dd_app_url}/dashboard/${datadog_dashboard.pipeline_native.id}"
}
