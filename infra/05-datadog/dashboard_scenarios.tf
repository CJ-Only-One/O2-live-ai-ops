###############################################################################
# AI Agent 시나리오 이상 탐지 대시보드
#
# docs/scenario-experiment.md 의 S1·S2·S3 를 한 화면에서 재현·판독한다.
# 기존 business/infra 대시보드는 출처별 운영 화면이고, 이 화면은 실험 순서별
# 합성 화면이다. 존재하지 않는 지표를 쿼리해 빈 위젯을 정상처럼 보이게 하지
# 않는다. 아직 없는 지표는 첫 note에 명시한다.
###############################################################################

locals {
  scenario_chat_scope = "service:chat-gateway,env:$env"
  scenario_api_scope  = "service:api,env:$env"
  scenario_kube_scope = "kube_cluster_name:$kube_cluster_name,kube_namespace:$kube_namespace"
}

resource "datadog_dashboard" "scenarios" {
  title       = "O2 AI Agent — S1·S2·S3 이상 탐지"
  layout_type = "ordered"
  reflow_type = "auto"

  description = join(" ", [
    "AI Agent 시나리오 실험의 진입·감별·검증 지표를 한 화면에 모은다.",
    "S1은 chat-gateway, S2·S3는 api를 고정 조회하며 env와 Kubernetes 범위만 템플릿 변수로 바꾼다.",
    "복구 판정은 반드시 Warm PRE/POST snapshot과 함께 수행한다.",
  ])

  template_variable {
    name     = "env"
    prefix   = "env"
    defaults = [var.environment]
  }

  template_variable {
    name     = "kube_cluster_name"
    prefix   = "kube_cluster_name"
    defaults = [var.kube_cluster_name]
  }

  template_variable {
    name     = "kube_namespace"
    prefix   = "kube_namespace"
    defaults = [var.kube_namespace]
  }

  widget {
    note_definition {
      background_color = "yellow"
      font_size        = "14"
      text_align       = "left"
      vertical_align   = "top"
      show_tick        = false

      content = <<-EOT
        **읽는 순서:** 0. 관측 경로 신뢰 → 1. S1 → 2. S2 → 3. S3.

        **현재 결측:** S1 복구 판정에 필요한 `channel_block_rate`와
        `chat_fanout_p95_ms`는 아직 발행되지 않는다. 없는 메트릭 쿼리는
        Datadog이 오류 대신 빈 화면을 주므로 위젯을 만들지 않았다.

        **S3 주의:** `hold_read_path_degraded`의 관리 API 200은 플래그 저장
        성공이다. 사용자를 차단하지 않으므로 `block_rate`로 조치 성공을
        판정하지 않는다. 읽기 지연·실패·CPU와 Warm의 조치 상태 및
        `inventory.check` 발생률을 PRE/POST로 비교해야 한다.

        **빈 위젯은 정상 판정이 아니다.** 맨 위 카나리·집계 지연·오류와
        각 그룹의 `event_count`·`confidence`를 먼저 확인한다.
      EOT
    }
  }

  #############################################################################
  # 0. 데이터 경로 신뢰성
  #############################################################################

  widget {
    group_definition {
      title       = "0. 먼저 확인 — 이 화면을 믿을 수 있는가"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          title       = "Warm 카나리 — 1분마다 0.1 RPS가 있어야 함"
          show_legend = true
          request {
            # 카나리 생존 신호는 UI의 $env 선택값에 의존하지 않는다.
            # Terraform 배포 환경과 동일한 env로 고정해 대시보드가 조용히 비지 않게 한다.
            q            = "avg:${var.metric_prefix}rps{service:o2-canary,env:${var.environment}}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "집계 지연 — 90초면 Agent 검증 창 파괴"
          show_legend = true
          request {
            q            = "max:aws.lambda.iterator_age{functionname:o2-agg}"
            display_type = "line"
          }
          marker {
            display_type = "error dashed"
            label        = "검증 불가 90초"
            value        = "y = 90000"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "집계 Lambda 오류"
          show_legend = true
          request {
            q            = "sum:aws.lambda.errors{functionname:o2-agg}.as_count()"
            display_type = "bars"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "서비스별 지표 신뢰도"
          show_legend = true
          request {
            q            = "avg:${var.metric_prefix}confidence{env:$env} by {service}"
            display_type = "line"
          }
        }
      }
    }
  }

  #############################################################################
  # S1 — 채팅 총량 초과
  #############################################################################

  widget {
    group_definition {
      title       = "1. S1 — 채팅 총량 초과 · 대가 게이트"
      layout_type = "ordered"

      widget {
        note_definition {
          background_color = "orange"
          font_size        = "13"
          text_align       = "left"
          vertical_align   = "top"
          show_tick        = false
          content          = "**탐지:** RPS와 평시 대비 배수가 먼저 상승한다. **감별:** 순 사용자도 함께 늘면 넓은 정상 사용자 부하, RPS만 오르고 집중도가 높거나 간격 CV가 낮으면 소수 자동화 가능성이 크다. 복구 판정에는 아직 없는 fanout p95와 채널 차단률이 추가로 필요하다."
        }
      }

      widget {
        timeseries_definition {
          title       = "채팅 인입 — RPS · 평시 대비 배수"
          show_legend = true
          request {
            q            = "sum:o2.app.business_event{${local.scenario_chat_scope},event:chat.send}.as_rate()"
            display_type = "line"
          }
          request {
            q            = "anomalies(sum:o2.app.business_event{${local.scenario_chat_scope},event:chat.send}.as_rate(), 'agile', 3, direction='above', interval=60, alert_window='last_5m', seasonality='hourly')"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "채팅 참여 폭 — 순 사용자 수"
          show_legend = true
          request {
            q            = "avg:${var.metric_prefix}distinct_users{${local.scenario_chat_scope}}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "집중도 — 상위 1% · 상위 5계정"
          show_legend = true
          request {
            q            = "avg:${var.metric_prefix}top1pct_share{${local.scenario_chat_scope}}"
            display_type = "line"
          }
          request {
            q            = "avg:${var.metric_prefix}top5_share{${local.scenario_chat_scope}}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "요청 간격 CV — 낮을수록 기계적"
          show_legend = true
          request {
            q            = "avg:${var.metric_prefix}interval_cv_top{${local.scenario_chat_scope}}"
            display_type = "line"
          }
          request {
            q            = "avg:${var.metric_prefix}interval_cv{${local.scenario_chat_scope}}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "채팅 실패율 — 이벤트 계약 이상 포함"
          show_legend = true
          request {
            q            = "sum:o2.app.failure{${local.scenario_chat_scope}} by {event}.as_count() / sum:o2.app.business_event{${local.scenario_chat_scope}} by {event}.as_count()"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "chat-gateway CPU · 메모리 by pod"
          show_legend = true
          request {
            q            = "avg:kubernetes.cpu.usage.total{${local.scenario_kube_scope},kube_deployment:chat-gateway} by {pod_name}"
            display_type = "line"
          }
          request {
            q            = "avg:kubernetes.memory.usage{${local.scenario_kube_scope},kube_deployment:chat-gateway} by {pod_name}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "채팅 이벤트 수 — 결측 판별"
          show_legend = true
          request {
            q            = "sum:o2.app.business_event{${local.scenario_chat_scope}}.as_count()"
            display_type = "bars"
          }
        }
      }
    }
  }

  #############################################################################
  # S2 — 느린 파드
  #############################################################################

  widget {
    group_definition {
      title       = "2. S2 — 느린 파드 · 자기 교정 게이트"
      layout_type = "ordered"

      widget {
        note_definition {
          background_color = "blue"
          font_size        = "13"
          text_align       = "left"
          vertical_align   = "top"
          show_tick        = false
          content          = "**진입:** 서비스 p95 상승. **재분석:** p95를 pod_name으로 갈라 한 파드만 느린지 확인한다. 전체 p99는 느린 파드 비중이 5% 미만일 때 필요하다. CPU·throttling·Ready·replica는 원인 보강이며 서비스 지연을 대신하지 않는다."
        }
      }

      widget {
        timeseries_definition {
          title       = "API 서비스 지연 — p50 · p95 · p99"
          show_legend = true
          request {
            q            = "p50:trace.fastapi.request{${local.scenario_api_scope}} * 1000"
            display_type = "line"
          }
          request {
            q            = "p95:trace.fastapi.request{${local.scenario_api_scope}} * 1000"
            display_type = "line"
          }
          request {
            q            = "p99:trace.fastapi.request{${local.scenario_api_scope}} * 1000"
            display_type = "line"
          }
          marker {
            display_type = "warning dashed"
            label        = "p95 경고"
            value        = "y = ${var.latency_p95_warning}"
          }
          marker {
            display_type = "error dashed"
            label        = "p95 위험"
            value        = "y = ${var.latency_p95_critical}"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "API 파드별 p95 — 이상 파드 식별"
          show_legend = true
          request {
            q            = "p95:o2.apm.request.duration{${local.scenario_api_scope}} by {pod_name} / 1000000"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "API 파드별 CPU"
          show_legend = true
          request {
            q            = "avg:kubernetes.cpu.usage.total{${local.scenario_kube_scope},kube_deployment:api} by {pod_name}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "API 파드별 CPU throttling"
          show_legend = true
          request {
            formula {
              formula_expression = "100 * throttled / total"
              alias              = "throttling %"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "throttled"
                query       = "avg:kubernetes.cpu.cfs.throttled.periods{${local.scenario_kube_scope},kube_deployment:api} by {pod_name}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "total"
                query       = "avg:kubernetes.cpu.cfs.periods{${local.scenario_kube_scope},kube_deployment:api} by {pod_name}"
              }
            }
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "API replicas — 격리·원복 확인"
          show_legend = true
          request {
            q            = "avg:kubernetes_state.deployment.replicas_desired{${local.scenario_kube_scope},kube_deployment:api}"
            display_type = "line"
          }
          request {
            q            = "avg:kubernetes_state.deployment.replicas_available{${local.scenario_kube_scope},kube_deployment:api}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "API 파드 Ready · Restart"
          show_legend = true
          request {
            q            = "sum:kubernetes_state.pod.ready{${local.scenario_kube_scope},kube_deployment:api} by {pod_name}"
            display_type = "line"
          }
          request {
            q            = "sum:kubernetes_state.container.restarts{${local.scenario_kube_scope},kube_deployment:api} by {pod_name}"
            display_type = "bars"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "API 이벤트 수 · 신뢰도"
          show_legend = true
          request {
            q            = "sum:o2.app.business_event{${local.scenario_api_scope}}.as_count()"
            display_type = "bars"
          }
          request {
            q            = "avg:${var.metric_prefix}confidence{${local.scenario_api_scope}}"
            display_type = "line"
          }
        }
      }
    }
  }

  #############################################################################
  # S3 — 읽기 급증, 사람/자동화 미확정
  #############################################################################

  widget {
    group_definition {
      title       = "3. S3 — 읽기 급증 · 정보 게이트"
      layout_type = "ordered"

      widget {
        note_definition {
          background_color = "purple"
          font_size        = "13"
          text_align       = "left"
          vertical_align   = "top"
          show_tick        = false
          content          = "**포화 판단:** API RPS·지연·실패·CPU를 함께 본다. **정보 게이트:** 순 사용자·UA/IP 다양성·집중도·간격 CV가 서로 모순되면 사람/자동화를 확정하지 않는다. `hold_read_path_degraded`는 사용자 차단이 아니라 부가 이벤트 생략이므로 block_rate가 성공 지표가 아니다."
        }
      }

      widget {
        timeseries_definition {
          title       = "읽기 부하 — API RPS · 평시 대비 배수"
          show_legend = true
          request {
            q            = "sum:trace.fastapi.request.hits{${local.scenario_api_scope}}.as_rate()"
            display_type = "line"
          }
          request {
            q            = "anomalies(sum:trace.fastapi.request.hits{${local.scenario_api_scope}}.as_rate(), 'agile', 3, direction='above', interval=60, alert_window='last_5m', seasonality='hourly')"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "읽기 영향 — p95 · p99 · 실패율"
          show_legend = true
          request {
            q            = "p95:trace.fastapi.request{${local.scenario_api_scope}} * 1000"
            display_type = "line"
          }
          request {
            q            = "p99:trace.fastapi.request{${local.scenario_api_scope}} * 1000"
            display_type = "line"
          }
          request {
            q            = "sum:o2.app.failure{${local.scenario_api_scope}}.as_count() / sum:o2.app.business_event{${local.scenario_api_scope}}.as_count()"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "API CPU · 메모리 by pod"
          show_legend = true
          request {
            q            = "avg:kubernetes.cpu.usage.total{${local.scenario_kube_scope},kube_deployment:api} by {pod_name}"
            display_type = "line"
          }
          request {
            q            = "avg:kubernetes.memory.usage{${local.scenario_kube_scope},kube_deployment:api} by {pod_name}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "사용자·UA·IP 다양성"
          show_legend = true
          request {
            q            = "avg:${var.metric_prefix}distinct_users{${local.scenario_api_scope}}"
            display_type = "line"
          }
          request {
            q            = "avg:${var.metric_prefix}ua_diversity{${local.scenario_api_scope}}"
            display_type = "line"
          }
          request {
            q            = "avg:${var.metric_prefix}ip_diversity{${local.scenario_api_scope}}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "집중도·간격 규칙성 — 원인 확정 금지 근거"
          show_legend = true
          request {
            q            = "avg:${var.metric_prefix}top1pct_share{${local.scenario_api_scope}}"
            display_type = "line"
          }
          request {
            q            = "avg:${var.metric_prefix}interval_cv_top{${local.scenario_api_scope}}"
            display_type = "line"
          }
          request {
            q            = "avg:${var.metric_prefix}interval_cv{${local.scenario_api_scope}}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "클릭 동반 비율 · 캐시 · 폴백"
          show_legend = true
          request {
            q            = "avg:${var.metric_prefix}click_ratio{${local.scenario_api_scope}}"
            display_type = "line"
          }
          request {
            q            = "sum:o2.app.cache_access{${local.scenario_api_scope},result:hit}.as_count() / sum:o2.app.cache_access{${local.scenario_api_scope}}.as_count()"
            display_type = "line"
          }
          request {
            q            = "sum:o2.app.fallback{${local.scenario_api_scope}}.as_count() / sum:o2.app.fallback_attempt{${local.scenario_api_scope}}.as_count()"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "APM 읽기 경로 RPS · 5xx"
          show_legend = true
          request {
            q            = "sum:trace.fastapi.request.hits{service:api,env:$env} by {resource_name}.as_rate()"
            display_type = "line"
          }
          request {
            q            = "sum:trace.fastapi.request.hits.by_http_status{service:api,env:$env,http.status_code:5*}.as_count()"
            display_type = "bars"
          }
        }
      }
    }
  }
}

output "dashboard_scenarios_url" {
  description = "AI Agent S1·S2·S3 이상 탐지 대시보드"
  value       = "${local.dd_app_url}${datadog_dashboard.scenarios.url}"
}
