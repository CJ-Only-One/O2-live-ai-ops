###############################################################################
# 시연용 요약 대시보드 — "관측 → 감지 → 대응" 한 화면
#
# 기존 대시보드와의 차이:
#   dashboard.tf                 비즈니스 지표 (출처별 운영 화면)
#   dashboard_infra.tf           인프라 자원   (출처별 운영 화면)
#   dashboard_eks_monitoring.tf  클러스터 상세
#   dashboard_scenarios.tf       실험 순서별 합성 화면 — S1·S2·S3 를 이름으로 부른다
#   **이 파일**                  발표용 압축 화면 — 20 위젯, 한 번의 스크롤
#
# ★ 이름 규칙: **위젯 제목에 시나리오 번호·시나리오 이름을 쓰지 않는다.**
#
#   dashboard_scenarios.tf 는 실험 진행자용이라 "S1", "결제 처리 지연" 처럼
#   실험 대본의 언어로 부른다. 이 화면은 대본을 모르는 사람에게 보여주는
#   화면이다. 특정 시나리오를 위해 만든 계측이 아니라 **어느 서비스에나 있는
#   신호를 그대로 읽고 있다**는 것이 요점이므로, 증상의 이름으로만 부른다.
#
#     쓰지 않는다        대신 쓴다
#     ----------------   --------------------------------
#     S1 / 채팅 전파     실시간 전파 지연
#     S2 / API 꼬리      응답 지연 (p99 꼬리)
#     S3 / 결제 · PG     작업별 처리 지연  (operation 태그로 자연히 갈린다)
#
#   시나리오가 늘거나 바뀌어도 이 파일은 고칠 것이 없어야 한다. 고쳐야 한다면
#   그건 지표가 시나리오에 붙어 있다는 뜻이고, 그때는 지표 쪽을 본다.
#
# ★ 여기 있는 쿼리는 전부 2026-08-26 에 `/api/v1/query` 로 series > 0 을
#   확인한 것이다. 빈 위젯은 "정상" 과 구분되지 않으므로 발표 화면에 두지
#   않는다. 확인 과정에서 뺀 것들을 남겨 둔다 — 다시 넣으려 할 때 참고한다.
#
#     o2.warm.cache_hit_rate / latency_p95 / event_count   24시간 0 series
#     o2.agent_entry.shadow / shadow_e2e                   0 series
#     o2.app.order_create                                  0 series
#     trace.fastapi.request.errors                         이 org 에 없다
#                                                          (dashboard_infra.tf 593행)
#     o2.app.business_event by {event_type}                태그가 N/A 로만 온다
#     o2.app.failure by {operation}                        태그가 N/A 로만 온다
#
# ★ 단위 함정 두 개. 둘 다 실측으로 확인했다.
#     `trace.fastapi.request`      **second** (scenario_alerts.tf 172행, M-016)
#     `aws.lambda.iterator_age`    **millisecond**
#   그래서 이 화면의 ms·s 표기는 전부 곱하거나 나눈 값이다. 안 고치면 세 자리가
#   어긋난 채로 위젯은 오류 없이 초록으로 뜬다.
###############################################################################

locals {
  # `service` 를 템플릿 변수로 두는 이유는 화면을 범용으로 "보이게" 하려는 것이
  # 아니라, 실제로 서비스가 늘어날 때 이 파일을 안 고치려는 것이다.
  demo_apm_scope  = "env:$env,service:$service"
  demo_env_scope  = "env:$env"
  demo_kube_scope = "kube_namespace:$kube_namespace"

  # 감지 → 대응 경로의 Lambda 들. 함수 이름은 배포 산출물이라 여기서만 적는다.
  demo_fn_entry = "o2-dify-ingress,o2-dify-worker"
  demo_fn_read  = "o2-hot-api,o2-warm-api"
  demo_fn_act   = "o2-dev-dify-runbook-lookup,o2-dev-dify-scale-executor,o2-dev-dify-slack-approval-request"
  demo_fn_all   = "o2-dify-ingress,o2-dify-worker,o2-hot-api,o2-warm-api,o2-agg,o2-dev-dify-runbook-lookup,o2-dev-dify-scale-executor"
}

resource "datadog_dashboard" "demo_overview" {
  title       = "O2 — 실시간 서비스 관측·자동 대응"
  layout_type = "ordered"
  reflow_type = "auto"

  description = join(" ", [
    "라이브 커머스 트래픽을 지연·트래픽·오류·포화의 네 신호로 읽고,",
    "그 신호가 자동 대응 루프까지 실제로 도달했는지를 같은 화면에서 확인한다.",
    "맨 위 숫자 4개가 상태, 아래 그룹 4개가 근거다.",
  ])

  template_variable {
    name     = "env"
    prefix   = "env"
    defaults = [var.environment]
  }

  template_variable {
    name     = "service"
    prefix   = "service"
    defaults = [var.default_service]
  }

  template_variable {
    name     = "kube_namespace"
    prefix   = "kube_namespace"
    defaults = [var.kube_namespace]
  }

  #############################################################################
  # 최상단 — 상태 4개
  #
  # query_value 는 "지금 값" 이라 발표 중 눈이 먼저 가는 자리다. 네 개를 고른
  # 기준은 **서로 다른 층을 대표하는가** 다. 같은 층에서 둘을 고르면 하나가
  # 나빠질 때 둘 다 빨개져서 정보가 늘지 않는다.
  #
  #   전파 지연  사용자가 실제로 겪는 것
  #   응답 지연  서버가 겪는 것
  #   관측 지연  우리가 그것을 아는 데 걸리는 것
  #   실패 적체  아무도 처리하지 않고 쌓인 것
  #############################################################################

  widget {
    query_value_definition {
      # 부하가 없으면 이 지표는 발행되지 않는다 — 평시 "No data" 가 정상이다.
      # 없는 것을 0 으로 칠하면 "빠르다" 로 오독되므로 fill 하지 않는다.
      title       = "실시간 전파 지연 p95"
      title_size  = "16"
      custom_unit = "ms"
      precision   = 0
      autoscale   = false

      request {
        aggregator = "last"
        formula {
          formula_expression = "query1"
        }
        query {
          metric_query {
            data_source = "metrics"
            name        = "query1"
            query       = "p95:o2.chat.propagation{${local.demo_env_scope}}"
          }
        }
        conditional_formats {
          comparator = ">="
          value      = var.chat_propagation_p95_critical_ms
          palette    = "white_on_red"
        }
        conditional_formats {
          comparator = ">="
          value      = var.chat_propagation_p95_critical_ms / 2
          palette    = "white_on_yellow"
        }
        conditional_formats {
          comparator = "<"
          value      = var.chat_propagation_p95_critical_ms / 2
          palette    = "white_on_green"
        }
      }
    }
  }

  widget {
    query_value_definition {
      title       = "응답 지연 p99 (꼬리)"
      title_size  = "16"
      custom_unit = "ms"
      precision   = 0
      autoscale   = false

      request {
        aggregator = "last"
        formula {
          formula_expression = "query1 * 1000"
        }
        query {
          metric_query {
            data_source = "metrics"
            name        = "query1"
            query       = "p99:trace.fastapi.request{${local.demo_apm_scope}}"
          }
        }
        conditional_formats {
          comparator = ">="
          value      = var.s2_tail_latency_p99_critical_ms
          palette    = "white_on_red"
        }
        conditional_formats {
          comparator = ">="
          value      = var.s2_tail_latency_p99_warning_ms
          palette    = "white_on_yellow"
        }
        conditional_formats {
          comparator = "<"
          value      = var.s2_tail_latency_p99_warning_ms
          palette    = "white_on_green"
        }
      }
    }
  }

  widget {
    query_value_definition {
      # 90초가 경계인 이유: 조치 후 90초 뒤 재확인이 자기 교정 루프의 전제다.
      # 집계가 그보다 밀려 있으면 Agent 는 조치 **이전** 값을 읽고, 자기 조치의
      # 효과를 반대로 판정한다. 느린 것이 아니라 틀리는 것이다.
      title       = "관측 지연 (집계 밀림)"
      title_size  = "16"
      custom_unit = "s"
      precision   = 0
      autoscale   = false

      request {
        aggregator = "last"
        formula {
          formula_expression = "query1 / 1000"
        }
        query {
          metric_query {
            data_source = "metrics"
            name        = "query1"
            query       = "max:aws.lambda.iterator_age{functionname:o2-agg}"
          }
        }
        conditional_formats {
          comparator = ">="
          value      = 90
          palette    = "white_on_red"
        }
        conditional_formats {
          comparator = ">="
          value      = 30
          palette    = "white_on_yellow"
        }
        conditional_formats {
          comparator = "<"
          value      = 30
          palette    = "white_on_green"
        }
      }
    }
  }

  widget {
    query_value_definition {
      # DLQ 는 0 이 아니면 곧바로 이상이다 — 재시도를 다 쓰고 떨어진 것들이다.
      # 큐 이름을 나열하지 않고 `*dlq*` 로 잡는 이유는 큐가 늘 때 이 위젯이
      # 조용히 뒤처지지 않게 하려는 것이다.
      title       = "처리 못한 실패 적체"
      title_size  = "16"
      custom_unit = "건"
      precision   = 0
      autoscale   = false

      request {
        aggregator = "max"
        formula {
          formula_expression = "query1"
        }
        query {
          metric_query {
            data_source = "metrics"
            name        = "query1"
            query       = "sum:aws.sqs.approximate_number_of_messages_visible{queuename:*dlq*}"
          }
        }
        conditional_formats {
          comparator = ">"
          value      = 0
          palette    = "white_on_red"
        }
        conditional_formats {
          comparator = "<="
          value      = 0
          palette    = "white_on_green"
        }
      }
    }
  }

  #############################################################################
  # 1. 서비스가 지금 어떤가
  #############################################################################

  widget {
    group_definition {
      title       = "1. 서비스 — 지연 · 트래픽 · 오류"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # p50 을 같이 그리는 이유는 꼬리와 몸통을 구분하기 위해서다. 둘이 같이
          # 오르면 전체 포화, 꼬리만 오르면 일부 경로·일부 파드다. 조치가 갈린다.
          title       = "응답 지연 분포 (p50 · p95 · p99)"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p50:trace.fastapi.request{${local.demo_apm_scope}} * 1000"
            display_type = "line"
            style {
              palette = "grey"
            }
          }
          request {
            q            = "p95:trace.fastapi.request{${local.demo_apm_scope}} * 1000"
            display_type = "line"
          }
          request {
            q            = "p99:trace.fastapi.request{${local.demo_apm_scope}} * 1000"
            display_type = "line"
            style {
              palette = "warm"
            }
          }
          marker {
            display_type = "error dashed"
            label        = "계약 상한 p99"
            value        = "y = ${var.s2_tail_latency_p99_critical_ms}"
          }
        }
      }

      widget {
        timeseries_definition {
          # 상태코드는 개수가 아니라 **비율의 모양**으로 본다. 트래픽이 같이
          # 빠지면 4xx 가 줄어도 좋아진 것이 아니다 — 그래서 rate 로 그린다.
          title       = "요청량과 응답 상태"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:trace.fastapi.request.hits.by_http_status{${local.demo_apm_scope}} by {http.status_class}.as_rate()"
            display_type = "bars"
          }
        }
      }

      widget {
        timeseries_definition {
          # `operation` 태그로 갈린다. 어떤 작업이 있는지를 화면이 알 필요가 없고,
          # 새 작업이 계측되면 선이 하나 늘 뿐이다 — 이 파일은 안 고친다.
          title       = "작업별 처리 지연 p95"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p95:o2.app.operation.duration{${local.demo_env_scope}} by {operation}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          # 사용자가 실제로 겪는 지연. 서버 응답이 멀쩡해도 여기가 무너지면
          # 방송은 끊긴 것으로 보인다 — 위 세 위젯과 독립적으로 읽어야 한다.
          title       = "실시간 전파 지연 p95"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p95:o2.chat.propagation{${local.demo_env_scope}} by {broadcast_id}"
            display_type = "line"
          }
          marker {
            display_type = "error dashed"
            label        = "감지 임계"
            value        = "y = ${var.chat_propagation_p95_critical_ms}"
          }
        }
      }
    }
  }

  #############################################################################
  # 2. 원인이 어느 층인가
  #############################################################################

  widget {
    group_definition {
      title       = "2. 원인 계층 — 의존성과 자원"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # 위층(응답 지연)이 올랐을 때 여기가 조용하면 원인은 애플리케이션이나
          # 자원이고, 여기가 같이 오르면 하위 저장소다. 이 화면의 분기점이다.
          title       = "의존 계층 지연 p95 — DB · 캐시"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p95:trace.pymysql.query{${local.demo_env_scope}} * 1000"
            display_type = "line"
          }
          request {
            q            = "p95:trace.redis.command{${local.demo_env_scope}} * 1000"
            display_type = "line"
            style {
              palette = "cool"
            }
          }
        }
      }

      widget {
        timeseries_definition {
          # 적중률이 떨어지면 그 부하는 그대로 DB 로 간다. 위 위젯의 MySQL 선이
          # 왜 올랐는지를 여기서 먼저 확인한다.
          title       = "캐시 적중률"
          title_size  = "16"
          show_legend = true

          request {
            formula {
              formula_expression = "hit / total * 100"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "hit"
                query       = "sum:o2.app.cache_access{${local.demo_env_scope},result:hit}.as_count()"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "total"
                query       = "sum:o2.app.cache_access{${local.demo_env_scope}}.as_count()"
              }
            }
            display_type = "line"
          }
          marker {
            display_type = "warning dashed"
            label        = "감지 임계"
            value        = "y = ${var.cache_hit_rate_critical * 100}"
          }
        }
      }

      widget {
        timeseries_definition {
          # `overflow` 가 0 을 넘으면 풀이 모자라 임시 커넥션을 만들고 있다는
          # 뜻이다. 지연이 오르기 전에 먼저 움직이는 신호라 같이 둔다.
          title       = "커넥션 풀 — 사용 · 유휴 · 초과"
          title_size  = "16"
          show_legend = true

          request {
            q            = "max:o2.app.db.pool.active{${local.demo_env_scope}}"
            display_type = "area"
          }
          request {
            q            = "max:o2.app.db.pool.idle{${local.demo_env_scope}}"
            display_type = "line"
          }
          request {
            q            = "max:o2.app.db.pool.overflow{${local.demo_env_scope}}"
            display_type = "line"
            style {
              palette = "warm"
            }
          }
        }
      }

      widget {
        timeseries_definition {
          # `kubernetes.cpu.usage.total` 은 nanocore, `requests` 는 core 다.
          # 1e9 로 나누지 않으면 축이 열 자리로 뜨고 100% 선이 바닥에 붙는다.
          #
          # 파드가 아니라 배포 단위로 묶는다 — 발표 화면에서 파드 이름은 읽히지
          # 않고, 조치(스케일)도 배포 단위로 일어난다.
          title       = "배포별 CPU 사용률 (요청량 대비)"
          title_size  = "16"
          show_legend = true

          request {
            formula {
              formula_expression = "used / 1000000000 / requested * 100"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "used"
                query       = "avg:kubernetes.cpu.usage.total{${local.demo_kube_scope}} by {kube_deployment}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "requested"
                query       = "avg:kubernetes.cpu.requests{${local.demo_kube_scope}} by {kube_deployment}"
              }
            }
            display_type = "line"
          }
          marker {
            display_type = "warning dashed"
            label        = "요청량 100%"
            value        = "y = 100"
          }
        }
      }

      widget {
        timeseries_definition {
          # 스케일 조치의 결과가 눈에 보이는 유일한 위젯이다. 조치 직후 desired 가
          # 먼저 오르고 ready 가 따라 오른다 — 그 간격이 조치가 실제로 걸린 시간이다.
          title       = "배포별 파드 수 — 준비 완료 / 목표"
          title_size  = "16"
          show_legend = true

          request {
            q            = "max:kubernetes_state.deployment.replicas_ready{${local.demo_kube_scope}} by {kube_deployment}"
            display_type = "line"
          }
          request {
            q            = "max:kubernetes_state.deployment.replicas_desired{${local.demo_kube_scope}} by {kube_deployment}"
            display_type = "line"
            style {
              line_type = "dashed"
            }
          }
        }
      }
    }
  }

  #############################################################################
  # 3. 이 화면을 믿을 수 있는가
  #############################################################################

  widget {
    group_definition {
      title       = "3. 관측 경로 — 위 숫자를 믿어도 되는가"
      layout_type = "ordered"

      widget {
        note_definition {
          background_color = "gray"
          font_size        = "13"
          text_align       = "left"
          vertical_align   = "center"
          show_tick        = false

          content = join(" ", [
            "**빈 위젯은 정상이 아니다.**",
            "위 1·2 그룹이 조용한 것과 이 그룹이 조용한 것은 뜻이 다르다 —",
            "전자는 서비스가 멀쩡한 것이고, 후자는 우리가 아무것도 못 보고 있는 것이다.",
            "판독은 항상 이 그룹부터 한다.",
          ])
        }
      }

      widget {
        timeseries_definition {
          # freshness 는 "마지막으로 집계된 창이 얼마나 오래됐나" 이고,
          # iterator_age 는 "읽지 못한 레코드가 얼마나 밀렸나" 다. 원인이 스트림
          # 쪽인지 집계 쪽인지가 두 선의 어긋남으로 갈린다.
          title       = "집계 신선도와 밀림"
          title_size  = "16"
          show_legend = true

          request {
            q            = "max:o2.warm.pipeline_freshness_seconds{${local.demo_env_scope}}"
            display_type = "line"
          }
          request {
            q            = "max:aws.lambda.iterator_age{functionname:o2-agg} / 1000"
            display_type = "line"
            style {
              palette = "warm"
            }
          }
          marker {
            display_type = "error dashed"
            label        = "재확인 창 90초"
            value        = "y = 90"
          }
        }
      }

      widget {
        timeseries_definition {
          # 인입(스트림) → 적재(아카이브) 가 같이 있어야 "안 들어온 것" 과
          # "들어왔는데 안 쌓인 것" 이 갈린다.
          title       = "스트림 인입과 아카이브 적재"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:aws.kinesis.incoming_records{*} by {streamname}.as_count()"
            display_type = "bars"
          }
          request {
            q            = "avg:aws.firehose.delivery_to_s_3success{*} * 100"
            display_type = "line"
            style {
              palette = "cool"
            }
          }
        }
      }

      widget {
        timeseries_definition {
          # 집계 결과에 붙는 신뢰도. 표본이 얇으면 값은 나오지만 믿을 수 없고,
          # 그 상태로 Agent 가 판단하면 근거 없이 조치한다.
          title       = "집계 신뢰도"
          title_size  = "16"
          show_legend = true

          request {
            q            = "avg:o2.warm.confidence{${local.demo_env_scope}} by {service}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          # 맨 위 숫자의 내역. 어느 큐가 막혔는지는 여기서만 보인다.
          title       = "실패 적체 — 대기열별"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:aws.sqs.approximate_number_of_messages_visible{queuename:*dlq*} by {queuename}"
            display_type = "bars"
          }
        }
      }
    }
  }

  #############################################################################
  # 4. 감지가 대응까지 갔는가
  #
  # 이 그룹이 이 화면의 이유다. 위 세 그룹은 어느 관측 스택에나 있다. 여기는
  # **신호가 사람을 거치지 않고 조치까지 도달했는지**를 보여준다.
  #
  # 네 위젯이 위에서 아래로 한 번의 흐름이다:
  #   알림을 받았다 → 지표를 읽었다 → 조치했다 → (경로가 깨지지 않았다)
  #
  # Monitor 요약 위젯을 일부러 넣지 않았다. Monitor 이름에는 시나리오 번호가
  # 들어 있어서, 그 위젯 하나 때문에 화면 전체의 이름 규칙이 깨진다.
  #############################################################################

  widget {
    group_definition {
      title       = "4. 감지 → 대응 — 신호가 조치까지 갔는가"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # ingress 는 웹훅을 받아 큐에 넣고 즉시 반환하고, worker 가 실제 호출을
          # 한다. 두 막대의 개수가 어긋나면 큐에서 잃고 있다는 뜻이다.
          title       = "① 알림 수신과 처리"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:aws.lambda.invocations{functionname IN (${local.demo_fn_entry})} by {functionname}.as_count()"
            display_type = "bars"
          }
        }
      }

      widget {
        timeseries_definition {
          # Agent 가 판단 근거를 실제로 조회했다는 증거. 알림만 받고 조회가 없으면
          # 그 판단은 프롬프트만 보고 한 것이다.
          title       = "② Agent 의 지표 조회"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:aws.lambda.invocations{functionname IN (${local.demo_fn_read})} by {functionname}.as_count()"
            display_type = "bars"
          }
        }
      }

      widget {
        timeseries_definition {
          # 조회(runbook) 와 실행(executor) 과 승인 요청(approval) 을 한 위젯에
          # 둔다. 조회만 있고 실행이 없으면 적용할 Runbook 을 못 찾은 것이고,
          # 승인 요청만 있으면 사람 대기 중이다 — 셋의 조합으로 읽는다.
          title       = "③ 조치 — 조회 · 실행 · 승인 요청"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:aws.lambda.invocations{functionname IN (${local.demo_fn_act})} by {functionname}.as_count()"
            display_type = "bars"
          }
        }
      }

      widget {
        timeseries_definition {
          # 이 막대가 0 이 아니면 위 ①②③ 의 숫자를 믿을 수 없다. 대응이 안 된
          # 것과 대응 경로가 깨진 것은 다른 문제이고, 조치도 다르다.
          title       = "④ 대응 경로 오류"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:aws.lambda.errors{functionname IN (${local.demo_fn_all})} by {functionname}.as_count()"
            display_type = "bars"
            style {
              palette = "warm"
            }
          }
        }
      }
    }
  }
}

output "demo_overview_dashboard_url" {
  description = "발표용 요약 대시보드 주소."
  value       = "${local.dd_app_url}/dashboard/${datadog_dashboard.demo_overview.id}"
}
