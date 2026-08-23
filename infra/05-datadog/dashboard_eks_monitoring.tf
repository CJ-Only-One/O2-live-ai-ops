resource "datadog_dashboard" "aws_infrastructure_eks_monitoring_o2_eks" {
  description = "AWS EC2 인프라 기본 메트릭 및 EKS 컨트롤 플레인 모니터링 대시보드 (ap-northeast-2, o2-eks 클러스터)"
  layout_type = "ordered"
  reflow_type = "fixed"
  tags        = ["ai:created_with_ai"]
  template_variable {
    available_values = ["ap-northeast-2a", "ap-northeast-2c"]
    default          = "*"
    name             = "availability_zone"
    prefix           = "availability-zone"
  }
  template_variable {
    available_values = ["argocd", "datadog", "external-secrets", "kube-system", "o2-dev"]
    default          = "*"
    name             = "kube_namespace"
    prefix           = "kube_namespace"
  }
  title = "AWS Infrastructure & EKS Monitoring - o2-eks"
  widget {
    group_definition {
      background_color = "blue"
      layout_type      = "ordered"
      show_title       = true
      title            = "AWS EC2 Infrastructure"
      widget {
        query_value_definition {
          custom_unit = "%"
          precision   = 1
          request {
            conditional_formats {
              comparator = ">"
              palette    = "white_on_red"
              value      = 80
            }
            conditional_formats {
              comparator = ">"
              palette    = "white_on_yellow"
              value      = 50
            }
            conditional_formats {
              comparator = ">="
              palette    = "white_on_green"
              value      = 0
            }
            formula {
              formula_expression = "query1"
            }
            query {
              metric_query {
                aggregator  = "avg"
                data_source = "metrics"
                name        = "query1"
                query       = "avg:aws.ec2.cpuutilization{$availability_zone}"
              }
            }
          }
          title = "Avg EC2 CPU Utilization (%)"
        }
        widget_layout {
          height = 2
          width  = 3
          x      = 0
          y      = 0
        }
      }
      widget {
        query_value_definition {
          autoscale = true
          request {
            conditional_formats {
              comparator = ">"
              palette    = "white_on_red"
              value      = 0
            }
            conditional_formats {
              comparator = "<="
              palette    = "white_on_green"
              value      = 0
            }
            formula {
              formula_expression = "query1"
            }
            query {
              metric_query {
                aggregator  = "max"
                data_source = "metrics"
                name        = "query1"
                query       = "sum:aws.ec2.status_check_failed{$availability_zone}"
              }
            }
          }
          title = "EC2 Status Check Failed"
        }
        widget_layout {
          height = 2
          width  = 3
          x      = 3
          y      = 0
        }
      }
      widget {
        query_value_definition {
          autoscale = true
          precision = 2
          request {
            formula {
              formula_expression = "query1"
              number_format {
                unit {
                  canonical {
                    unit_name = "byte_in_decimal_bytes_family"
                  }
                }
              }
            }
            query {
              metric_query {
                aggregator  = "avg"
                data_source = "metrics"
                name        = "query1"
                query       = "avg:aws.ec2.network_in{$availability_zone}"
              }
            }
          }
          title = "Network In (avg)"
        }
        widget_layout {
          height = 2
          width  = 3
          x      = 6
          y      = 0
        }
      }
      widget {
        query_value_definition {
          autoscale = true
          precision = 2
          request {
            formula {
              formula_expression = "query1"
              number_format {
                unit {
                  canonical {
                    unit_name = "byte_in_decimal_bytes_family"
                  }
                }
              }
            }
            query {
              metric_query {
                aggregator  = "avg"
                data_source = "metrics"
                name        = "query1"
                query       = "avg:aws.ec2.network_out{$availability_zone}"
              }
            }
          }
          title = "Network Out (avg)"
        }
        widget_layout {
          height = 2
          width  = 3
          x      = 9
          y      = 0
        }
      }
      widget {
        timeseries_definition {
          legend_columns = ["avg", "max", "min", "value"]
          legend_layout  = "auto"
          marker {
            display_type = "error dashed"
            label        = "High CPU"
            value        = "y = 80"
          }
          request {
            display_type = "line"
            formula {
              formula_expression = "query1"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "avg:aws.ec2.cpuutilization{$availability_zone} by {host}"
              }
            }
            style {
              line_type  = "solid"
              line_width = "normal"
              palette    = "cool"
            }
          }
          show_legend = true
          title       = "EC2 CPU Utilization by Instance"
          yaxis {
            include_zero = true
            max          = "100"
            min          = "0"
          }
        }
        widget_layout {
          height = 3
          width  = 6
          x      = 0
          y      = 2
        }
      }
      widget {
        timeseries_definition {
          legend_columns = ["avg", "max", "value"]
          legend_layout  = "auto"
          request {
            display_type = "line"
            formula {
              alias              = "Network In"
              formula_expression = "query1"
            }
            formula {
              alias              = "Network Out"
              formula_expression = "query2"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "avg:aws.ec2.network_in{$availability_zone} by {host}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query2"
                query       = "avg:aws.ec2.network_out{$availability_zone} by {host}"
              }
            }
            style {
              line_type  = "solid"
              line_width = "normal"
              palette    = "cool"
            }
          }
          show_legend = true
          title       = "EC2 Network In/Out by Instance"
        }
        widget_layout {
          height = 3
          width  = 6
          x      = 6
          y      = 2
        }
      }
      widget {
        timeseries_definition {
          legend_columns = ["avg", "max", "value"]
          legend_layout  = "auto"
          request {
            display_type = "bars"
            formula {
              alias              = "Read Ops"
              formula_expression = "query1"
            }
            formula {
              alias              = "Write Ops"
              formula_expression = "query2"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "avg:aws.ec2.ebsread_ops{$availability_zone} by {host}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query2"
                query       = "avg:aws.ec2.ebswrite_ops{$availability_zone} by {host}"
              }
            }
            style {
              palette = "purple"
            }
          }
          show_legend = true
          title       = "EBS Read/Write Ops by Instance"
        }
        widget_layout {
          height = 3
          width  = 6
          x      = 0
          y      = 5
        }
      }
      widget {
        timeseries_definition {
          legend_layout = "auto"
          request {
            display_type = "bars"
            formula {
              alias              = "Total Failed"
              formula_expression = "query1"
            }
            formula {
              alias              = "Instance Failed"
              formula_expression = "query2"
            }
            formula {
              alias              = "System Failed"
              formula_expression = "query3"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "max:aws.ec2.status_check_failed{$availability_zone} by {host}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query2"
                query       = "max:aws.ec2.status_check_failed_instance{$availability_zone} by {host}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query3"
                query       = "max:aws.ec2.status_check_failed_system{$availability_zone} by {host}"
              }
            }
            style {
              palette = "warm"
            }
          }
          show_legend = true
          title       = "EC2 Status Check Failed by Instance"
        }
        widget_layout {
          height = 3
          width  = 6
          x      = 6
          y      = 5
        }
      }
    }
    widget_layout {
      height = 9
      width  = 12
      x      = 0
      y      = 0
    }
  }
  widget {
    group_definition {
      background_color = "orange"
      layout_type      = "ordered"
      show_title       = true
      title            = "EKS Control Plane (o2-eks)"
      widget {
        query_value_definition {
          autoscale = true
          request {
            formula {
              formula_expression = "query1"
            }
            query {
              metric_query {
                aggregator  = "sum"
                data_source = "metrics"
                name        = "query1"
                query       = "sum:aws.eks.apiserver_request_total{clustername:o2-eks}.as_count()"
              }
            }
          }
          title = "API Server Total Requests"
        }
        widget_layout {
          height = 2
          width  = 3
          x      = 0
          y      = 0
        }
      }
      widget {
        query_value_definition {
          autoscale = true
          request {
            conditional_formats {
              comparator = ">"
              palette    = "white_on_red"
              value      = 0
            }
            conditional_formats {
              comparator = "<="
              palette    = "white_on_green"
              value      = 0
            }
            formula {
              formula_expression = "query1"
            }
            query {
              metric_query {
                aggregator  = "sum"
                data_source = "metrics"
                name        = "query1"
                query       = "sum:aws.eks.apiserver_request_total_5xx{clustername:o2-eks}.as_count()"
              }
            }
          }
          title = "API Server 5xx Errors"
        }
        widget_layout {
          height = 2
          width  = 3
          x      = 3
          y      = 0
        }
      }
      widget {
        query_value_definition {
          autoscale = true
          request {
            conditional_formats {
              comparator = ">"
              palette    = "white_on_red"
              value      = 5
            }
            conditional_formats {
              comparator = ">"
              palette    = "white_on_yellow"
              value      = 0
            }
            conditional_formats {
              comparator = "<="
              palette    = "white_on_green"
              value      = 0
            }
            formula {
              formula_expression = "query1"
            }
            query {
              metric_query {
                aggregator  = "last"
                data_source = "metrics"
                name        = "query1"
                query       = "avg:aws.eks.scheduler_pending_pods{clustername:o2-eks}"
              }
            }
          }
          title = "Scheduler Pending Pods"
        }
        widget_layout {
          height = 2
          width  = 3
          x      = 6
          y      = 0
        }
      }
      widget {
        query_value_definition {
          autoscale = true
          precision = 2
          request {
            formula {
              formula_expression = "query1"
              number_format {
                unit {
                  canonical {
                    unit_name = "byte_in_binary_bytes_family"
                  }
                }
              }
            }
            query {
              metric_query {
                aggregator  = "last"
                data_source = "metrics"
                name        = "query1"
                query       = "avg:aws.eks.etcd_mvcc_db_total_size_in_use_in_bytes{clustername:o2-eks}"
              }
            }
          }
          title = "etcd DB Size"
        }
        widget_layout {
          height = 2
          width  = 3
          x      = 9
          y      = 0
        }
      }
      widget {
        timeseries_definition {
          legend_columns = ["avg", "max", "value"]
          legend_layout  = "auto"
          request {
            display_type = "bars"
            formula {
              alias              = "Total"
              formula_expression = "query1"
            }
            formula {
              alias              = "4xx"
              formula_expression = "query2"
            }
            formula {
              alias              = "5xx"
              formula_expression = "query3"
            }
            formula {
              alias              = "429 Throttled"
              formula_expression = "query4"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "sum:aws.eks.apiserver_request_total{clustername:o2-eks}.as_count()"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query2"
                query       = "sum:aws.eks.apiserver_request_total_4xx{clustername:o2-eks}.as_count()"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query3"
                query       = "sum:aws.eks.apiserver_request_total_5xx{clustername:o2-eks}.as_count()"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query4"
                query       = "sum:aws.eks.apiserver_request_total_429{clustername:o2-eks}.as_count()"
              }
            }
            style {
              palette = "semantic"
            }
          }
          show_legend = true
          title       = "API Server Requests (Total / 4xx / 5xx / 429)"
        }
        widget_layout {
          height = 3
          width  = 6
          x      = 0
          y      = 2
        }
      }
      widget {
        timeseries_definition {
          legend_columns = ["avg", "max", "value"]
          legend_layout  = "auto"
          request {
            display_type = "line"
            formula {
              alias              = "GET p99"
              formula_expression = "query1"
            }
            formula {
              alias              = "LIST p99"
              formula_expression = "query2"
            }
            formula {
              alias              = "PUT p99"
              formula_expression = "query3"
            }
            formula {
              alias              = "POST p99"
              formula_expression = "query4"
            }
            formula {
              alias              = "DELETE p99"
              formula_expression = "query5"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "avg:aws.eks.apiserver_request_duration_seconds_get_p99{clustername:o2-eks}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query2"
                query       = "avg:aws.eks.apiserver_request_duration_seconds_list_p99{clustername:o2-eks}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query3"
                query       = "avg:aws.eks.apiserver_request_duration_seconds_put_p99{clustername:o2-eks}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query4"
                query       = "avg:aws.eks.apiserver_request_duration_seconds_post_p99{clustername:o2-eks}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query5"
                query       = "avg:aws.eks.apiserver_request_duration_seconds_delete_p99{clustername:o2-eks}"
              }
            }
            style {
              line_type  = "solid"
              line_width = "normal"
              palette    = "cool"
            }
          }
          show_legend = true
          title       = "API Server Request Duration p99 by Verb"
          yaxis {
            include_zero = true
            label        = "seconds"
          }
        }
        widget_layout {
          height = 3
          width  = 6
          x      = 6
          y      = 2
        }
      }
      widget {
        timeseries_definition {
          legend_columns = ["avg", "max", "value"]
          legend_layout  = "auto"
          request {
            display_type = "line"
            formula {
              alias              = "Total Pending"
              formula_expression = "query1"
            }
            formula {
              alias              = "Unschedulable"
              formula_expression = "query2"
            }
            formula {
              alias              = "Backoff"
              formula_expression = "query3"
            }
            formula {
              alias              = "Gated"
              formula_expression = "query4"
            }
            formula {
              alias              = "ActiveQ"
              formula_expression = "query5"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "avg:aws.eks.scheduler_pending_pods{clustername:o2-eks}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query2"
                query       = "avg:aws.eks.scheduler_pending_pods_unschedulable{clustername:o2-eks}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query3"
                query       = "avg:aws.eks.scheduler_pending_pods_backoff{clustername:o2-eks}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query4"
                query       = "avg:aws.eks.scheduler_pending_pods_gated{clustername:o2-eks}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query5"
                query       = "avg:aws.eks.scheduler_pending_pods_activeq{clustername:o2-eks}"
              }
            }
            style {
              line_type  = "solid"
              line_width = "normal"
              palette    = "warm"
            }
          }
          show_legend = true
          title       = "Scheduler Pending Pods by Reason"
          yaxis {
            include_zero = true
          }
        }
        widget_layout {
          height = 3
          width  = 6
          x      = 0
          y      = 5
        }
      }
      widget {
        timeseries_definition {
          legend_columns = ["avg", "max", "value"]
          legend_layout  = "auto"
          request {
            display_type = "line"
            formula {
              alias              = "etcd In-Use Size"
              formula_expression = "query1"
            }
            formula {
              alias              = "API Server Storage Size"
              formula_expression = "query2"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "avg:aws.eks.etcd_mvcc_db_total_size_in_use_in_bytes{clustername:o2-eks}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query2"
                query       = "avg:aws.eks.apiserver_storage_size_bytes{clustername:o2-eks}"
              }
            }
            style {
              line_type  = "solid"
              line_width = "normal"
              palette    = "purple"
            }
          }
          show_legend = true
          title       = "etcd DB Size & Inflight API Requests"
        }
        widget_layout {
          height = 3
          width  = 6
          x      = 6
          y      = 5
        }
      }
    }
    widget_layout {
      height = 9
      width  = 12
      x      = 0
      y      = 9
    }
  }
  widget {
    note_definition {
      background_color = "yellow"
      content          = <<-EOF
      ## EKS Pod-Level Metrics
      
      현재 **Kubernetes Agent 레벨 메트릭** (`kubernetes.pods.*`, `container.cpu.*`, `container.memory.*`)이 수집되지 않고 있습니다.
      
      Pod CPU/Memory, 컨테이너 리소스 사용량 등의 상세 메트릭을 수집하려면 EKS 클러스터에 **Datadog Agent (DaemonSet)**를 설치해야 합니다.
      
      **설치 방법:**
      1. [Helm Chart](https://docs.datadoghq.com/containers/kubernetes/installation/?tab=helm)로 Datadog Agent 배포
      2. `datadog-agent` DaemonSet이 각 노드에서 실행되면 자동으로 Pod/Container 메트릭 수집
      3. 수집 시작 후 이 대시보드에 Pod 메트릭 위젯 추가 가능
      EOF
      font_size        = "14"
      has_padding      = true
      text_align       = "left"
      tick_edge        = "left"
      tick_pos         = "50%"
      vertical_align   = "top"
    }
    widget_layout {
      height = 3
      width  = 12
      x      = 0
      y      = 18
    }
  }
  widget {
    group_definition {
      background_color = "green"
      layout_type      = "ordered"
      show_title       = true
      title            = "EKS Pod / Container Metrics (o2-eks)"
      widget {
        query_value_definition {
          autoscale = true
          request {
            conditional_formats {
              comparator = ">"
              palette    = "white_on_green"
              value      = 0
            }
            formula {
              formula_expression = "query1"
            }
            query {
              metric_query {
                aggregator  = "last"
                data_source = "metrics"
                name        = "query1"
                query       = "sum:kubernetes.pods.running{kube_cluster_name:o2-eks,$kube_namespace}"
              }
            }
          }
          title = "Running Pods"
        }
        widget_layout {
          height = 2
          width  = 3
          x      = 0
          y      = 0
        }
      }
      widget {
        query_value_definition {
          autoscale = true
          request {
            conditional_formats {
              comparator = ">"
              palette    = "white_on_red"
              value      = 10
            }
            conditional_formats {
              comparator = ">"
              palette    = "white_on_yellow"
              value      = 0
            }
            conditional_formats {
              comparator = "<="
              palette    = "white_on_green"
              value      = 0
            }
            formula {
              formula_expression = "query1"
            }
            query {
              metric_query {
                aggregator  = "last"
                data_source = "metrics"
                name        = "query1"
                query       = "sum:kubernetes.containers.restarts{kube_cluster_name:o2-eks,$kube_namespace}"
              }
            }
          }
          title = "Container Restarts (total)"
        }
        widget_layout {
          height = 2
          width  = 3
          x      = 3
          y      = 0
        }
      }
      widget {
        query_value_definition {
          autoscale = true
          precision = 2
          request {
            formula {
              formula_expression = "query1"
              number_format {
                unit {
                  canonical {
                    unit_name = "nanocore"
                  }
                }
              }
            }
            query {
              metric_query {
                aggregator  = "avg"
                data_source = "metrics"
                name        = "query1"
                query       = "sum:container.cpu.usage{kube_cluster_name:o2-eks,$kube_namespace}"
              }
            }
          }
          title = "Total Pod CPU Usage"
        }
        widget_layout {
          height = 2
          width  = 3
          x      = 6
          y      = 0
        }
      }
      widget {
        query_value_definition {
          autoscale = true
          precision = 2
          request {
            formula {
              formula_expression = "query1"
              number_format {
                unit {
                  canonical {
                    unit_name = "byte_in_binary_bytes_family"
                  }
                }
              }
            }
            query {
              metric_query {
                aggregator  = "avg"
                data_source = "metrics"
                name        = "query1"
                query       = "sum:container.memory.usage{kube_cluster_name:o2-eks,$kube_namespace}"
              }
            }
          }
          title = "Total Pod Memory Usage"
        }
        widget_layout {
          height = 2
          width  = 3
          x      = 9
          y      = 0
        }
      }
      widget {
        timeseries_definition {
          legend_columns = ["avg", "max", "value"]
          legend_layout  = "auto"
          request {
            display_type = "area"
            formula {
              formula_expression = "query1"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "sum:container.cpu.usage{kube_cluster_name:o2-eks,$kube_namespace} by {kube_namespace}"
              }
            }
            style {
              palette = "semantic"
            }
          }
          show_legend = true
          title       = "Container CPU Usage by Namespace"
        }
        widget_layout {
          height = 3
          width  = 6
          x      = 0
          y      = 2
        }
      }
      widget {
        timeseries_definition {
          legend_columns = ["avg", "max", "value"]
          legend_layout  = "auto"
          request {
            display_type = "area"
            formula {
              formula_expression = "query1"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "sum:container.memory.usage{kube_cluster_name:o2-eks,$kube_namespace} by {kube_namespace}"
              }
            }
            style {
              palette = "semantic"
            }
          }
          show_legend = true
          title       = "Container Memory Usage by Namespace"
        }
        widget_layout {
          height = 3
          width  = 6
          x      = 6
          y      = 2
        }
      }
      widget {
        timeseries_definition {
          legend_columns = ["avg", "max", "value"]
          legend_layout  = "auto"
          request {
            display_type = "line"
            formula {
              formula_expression = "top(query1, 10, \"mean\", \"desc\")"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "sum:container.cpu.usage{kube_cluster_name:o2-eks,$kube_namespace} by {pod_name}"
              }
            }
            style {
              line_type  = "solid"
              line_width = "normal"
              palette    = "cool"
            }
          }
          show_legend = true
          title       = "Container CPU Usage by Pod (Top 10)"
        }
        widget_layout {
          height = 3
          width  = 6
          x      = 0
          y      = 5
        }
      }
      widget {
        timeseries_definition {
          legend_columns = ["avg", "max", "value"]
          legend_layout  = "auto"
          request {
            display_type = "line"
            formula {
              formula_expression = "top(query1, 10, \"mean\", \"desc\")"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "sum:container.memory.usage{kube_cluster_name:o2-eks,$kube_namespace} by {pod_name}"
              }
            }
            style {
              line_type  = "solid"
              line_width = "normal"
              palette    = "warm"
            }
          }
          show_legend = true
          title       = "Container Memory Usage by Pod (Top 10)"
        }
        widget_layout {
          height = 3
          width  = 6
          x      = 6
          y      = 5
        }
      }
      widget {
        timeseries_definition {
          legend_columns = ["avg", "max", "value"]
          legend_layout  = "auto"
          request {
            display_type = "line"
            formula {
              alias              = "Rx"
              formula_expression = "query1"
            }
            formula {
              alias              = "Tx"
              formula_expression = "query2"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "sum:kubernetes.network.rx_bytes{kube_cluster_name:o2-eks,$kube_namespace} by {kube_namespace}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query2"
                query       = "sum:kubernetes.network.tx_bytes{kube_cluster_name:o2-eks,$kube_namespace} by {kube_namespace}"
              }
            }
            style {
              line_type  = "solid"
              line_width = "normal"
              palette    = "cool"
            }
          }
          show_legend = true
          title       = "Pod Network Rx/Tx by Namespace"
        }
        widget_layout {
          height = 3
          width  = 6
          x      = 0
          y      = 8
        }
      }
      widget {
        timeseries_definition {
          legend_columns = ["avg", "max", "value"]
          legend_layout  = "auto"
          request {
            display_type = "bars"
            formula {
              formula_expression = "query1"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "sum:kubernetes.containers.restarts{kube_cluster_name:o2-eks,$kube_namespace} by {pod_name}"
              }
            }
            style {
              palette = "warm"
            }
          }
          show_legend = true
          title       = "Container Restarts by Pod"
        }
        widget_layout {
          height = 3
          width  = 6
          x      = 6
          y      = 8
        }
      }
    }
    widget_layout {
      height = 12
      width  = 12
      x      = 0
      y      = 21
    }
  }
}
