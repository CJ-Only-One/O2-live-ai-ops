###############################################################################
# 인프라 · 쿠버네티스 운영 대시보드
#
# `dashboard.tf`(비즈니스 관측)와 담당이 다르다. 저긴 이벤트 스트림에서
# 계산한 비즈니스 지표, 여긴 Datadog Agent 가 kubelet/cAdvisor/kube-state
# -metrics/APM 에서 직접 긁어오는 원시 인프라 지표다 (`04-platform/datadog.tf`
# 의 Helm values 가 이 지표들을 켠다).
#
# 위에서 아래로 읽는 순서:
#
#   1. 리소스 사용률   ← 파드가 자기 몫(request/limit)을 넘기고 있는가
#   2. 파드 생명주기    ← 뭔가 죽고 있는가, 왜 죽는가
#   3. 노드 · 프로브    ← 그 파드가 애초에 뜰 자리·헬스체크는 정상인가
#   4. HTTP 트래픽     ← 결국 사용자가 받는 응답은 어떤가 (APM)
#
# 4번이 맨 아래인 이유는 배치 순서 문제가 아니다 — 1~3번은 "왜"를 좁히는
# 축이고, 4번은 "그래서 지금 사용자가 겪는 결과"다. 인프라가 멀쩡한데
# 4번이 무너지면 원인은 이 대시보드 밖(외부 의존성·애플리케이션 로직)에
# 있다는 뜻이다.
###############################################################################

locals {
  # 인프라 지표는 Datadog Agent 가 붙이는 태그(kube_cluster_name·kube_namespace)로
  # 자른다. 비즈니스 대시보드의 service/env 축과는 다른 축이다 — 하나의
  # 서비스가 여러 파드로 뜨고, 하나의 네임스페이스에 여러 서비스가 있다.
  infra_scope = "$kube_cluster_name,$kube_namespace"

  # APM(트레이스) 지표는 datadog.tf 의 apm.portEnabled 가 만드는 trace.* 계열이다.
  # 이 축은 비즈니스 대시보드와 같은 service/env 를 재사용한다 — 같은 이름
  # 규칙을 쓰는 것이 D-0xx 류 실수(축이 갈려서 화면이 비는 것)를 막는다.
  #
  # **span 이름은 프레임워크가 정한다.** 앱이 FastAPI라서 ddtrace 가 span 을
  # `fastapi.request` 로 붙이고, 그래서 메트릭도 `trace.fastapi.request.*` 다.
  # `trace.http.request.*` 는 이 org 에 존재하지 않는다 — 다른 프레임워크
  # (예: 순수 WSGI)를 가정한 이름이었다. 앱이 바뀌면 이 이름도 같이 바뀐다.
  apm_scope = "$service,$env"

  # 이벤트 검색 문법은 메트릭의 `{tag:value,...}` 와 다르다 — 공백으로 구분한
  # `tag:value` 토큰을 나열한다. `source:` 는 단수형이다(`sources:` 로 쓰면
  # 0건). kube_cluster_name·kube_namespace 는 kubelet 이 이벤트에 실제로
  # 붙이는 태그라 필터로 쓸 수 있지만, **`reason:unhealthy` 같은 태그는 없다**
  # — 프로브 실패 사유는 이벤트 `text` 안의 문자열("**Unhealthy**: ...")로만
  # 온다. 그래서 텍스트 검색 토큰을 같이 넣는다.
  infra_event_scope = "kube_cluster_name:$kube_cluster_name kube_namespace:$kube_namespace"
}

resource "datadog_dashboard" "infra" {
  title       = "O2 라이브커머스 — 인프라 · 쿠버네티스 운영"
  layout_type = "ordered"
  reflow_type = "auto"

  description = join(" ", [
    "Datadog Agent 가 kubelet·cAdvisor·kube-state-metrics·APM 에서 직접 수집한 원시 인프라 지표.",
    "비즈니스 지표(실패율·재시도율 등)는 이 화면에 없다 — `O2 라이브커머스 — 비즈니스 관측` 대시보드를 본다.",
    "담당 경계는 데이터 출처로 나뉜다 — 여긴 Datadog Agent, 그쪽은 집계 Lambda.",
  ])

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

  template_variable {
    name     = "service"
    prefix   = "service"
    defaults = [var.default_service]
  }

  template_variable {
    name     = "env"
    prefix   = "env"
    defaults = [var.environment]
  }

  #############################################################################
  # 0. 읽는 법
  #############################################################################

  widget {
    note_definition {
      background_color = "yellow"
      font_size        = "14"
      text_align       = "left"
      vertical_align   = "top"
      show_tick        = false

      content = <<-EOT
        **1~3번은 kube_cluster_name·kube_namespace 로 자른다.** 상단 템플릿
        변수에서 바꾼다 — service/env 축이 아니다.

        **4번(HTTP)만 service·env 축이다.** 비즈니스 대시보드와 같은 축을
        재사용해서 두 화면을 오갈 때 같은 서비스를 보게 했다.

        **임계선(마커)은 잠정치다.** `variables.tf` 의 인프라 임계 변수에서
        고친다. 평시 분포를 며칠 보기 전까지는 색깔 참고용일 뿐 알림 기준이
        아니다 — Monitor 는 아직 만들지 않았다.
      EOT
    }
  }

  #############################################################################
  # 1. 리소스 사용률 — 파드가 자기 몫을 넘기고 있는가
  #############################################################################

  widget {
    group_definition {
      title       = "1. 리소스 사용률"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # 절대 사용량이 아니라 "요청 대비 몇 %" 를 본다. 스케줄러가 준
          # request 를 넘기고 있다면 노드 자원 경쟁의 첫 신호다.
          title       = "CPU 사용률 — Request 대비 (%)"
          title_size  = "16"
          show_legend = true

          request {
            display_type = "line"
            formula {
              formula_expression = "query1 / query2 * 100"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "avg:kubernetes.cpu.usage.total{${local.infra_scope}} by {pod_name}"
                aggregator  = "avg"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query2"
                query       = "avg:kubernetes.cpu.requests{${local.infra_scope}} by {pod_name}"
                aggregator  = "avg"
              }
            }
          }

          marker {
            display_type = "warning dashed"
            value        = "y = ${var.cpu_request_pct_warning}"
            label        = "request 초과"
          }

          yaxis {
            min          = "0"
            include_zero = true
          }
        }
      }

      widget {
        timeseries_definition {
          # limit 을 넘기면 OOMKilled 다. request 초과는 경쟁이지만
          # limit 초과는 파드가 죽는다 — 그래서 마커를 100 에 둔다.
          title          = "메모리 사용률 — Limit 대비 (%)"
          title_size     = "16"
          show_legend    = true
          legend_layout  = "auto"
          legend_columns = ["avg", "min", "max", "value", "sum"]

          request {
            display_type = "line"
            formula {
              formula_expression = "query1 / query2 * 100"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "avg:kubernetes.memory.usage{${local.infra_scope}} by {pod_name}"
                aggregator  = "avg"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query2"
                query       = "avg:kubernetes.memory.limits{${local.infra_scope}} by {pod_name}"
                aggregator  = "avg"
              }
            }
          }

          marker {
            display_type = "error dashed"
            value        = "y = 100"
            label        = "limit — OOMKilled 위험"
          }

          yaxis {
            min          = "0"
            include_zero = true
          }
        }
      }

      widget {
        note_definition {
          # 실측(2026-08-19): 이 org 에 `kubernetes.cpu.cfs.*` 가 메트릭
          # 메타데이터 검색에조차 안 잡혔다. cAdvisor 는 컨테이너에 CPU
          # **limit**(CFS 쿼터)이 걸려 있어야 이 값을 만드는데, 당시 클러스터의
          # 파드가 전부 `kube_qos:burstable`(request 만 있고 limit 없음)이라
          # 쿼터 자체가 없었다.
          #
          # **갱신(2026-08-24): 지표는 이제 존재한다. 다만 이 위젯에는 여전히
          # 안 잡히고, 앞으로도 안 잡힌다(D-064).** KEDA 를 넣으면서(D-051)
          # 그 Helm 차트가 자기 파드에 `limits.cpu` 를 걸었고, 그것만으로
          # 시계열이 생겼다.
          #
          #   avg:kubernetes.cpu.cfs.throttled.periods{*} by {kube_namespace}
          #     -> kube_namespace:keda        (series 7, 전부 KEDA 파드)
          #     -> kube_namespace:o2-dev      (없음)
          #
          # 이 위젯의 scope 는 `$kube_namespace`(= o2-dev)이므로 결론은 안
          # 바뀐다 — **비어 있는 것이 여전히 정상이다.** 바뀐 것은 사유다.
          # "이 org 에 그런 지표가 없다" 가 아니라 "우리 앱 파드에 limit 이
          # 없다" 가 맞다. 아래 note 의 문장도 같이 고쳤다.
          #
          # 이 구분이 중요한 이유 — 명세 S2 는 느린 파드를 **정상 파드와
          # 비교**해서 찾는다. 그러려면 정상 파드에도 넉넉한 limit 이 있어야
          # 분모가 생기고, 시계열이 둘 이상이어야 `outliers()` 가 이상치를
          # 낼 수 있다. KEDA 파드는 그 비교의 대상이 아니다.
          #
          # **그리고 넣지 않기로 확정됐다 — D-064.** `O2-live-deploy` 는 모든
          # 디플로이먼트에서 CPU limit 을 일부러 안 건다(스로틀링이 지연을
          # 만든다). 응답 지연을 재는 시스템에서 지연을 만드는 설정을 켜는
          # 것은 앞뒤가 안 맞고, 그 판단이 옳다.
          #
          # **그래서 이 위젯은 앞으로도 빈다.** 지우지 않고 두는 이유는
          # `$kube_namespace` 가 템플릿 변수라 `keda` 로 바꾸면 값이 나오고,
          # "왜 비어 있나" 의 답이 위젯 옆에 있는 편이 낫기 때문이다.
          #
          # **파드별 CPU 는 위의 사용률 위젯**(`kubernetes.cpu.usage.total`
          # `by {pod_name}`)**으로 본다.** 조임 비율은 못 내지만 정상 파드와
          # 다른 파드를 지목하는 데는 충분하다.
          background_color = "gray"
          font_size        = "12"
          text_align       = "left"
          vertical_align   = "top"
          show_tick        = false

          content = <<-EOT
            **아래 위젯은 항상 비어 있다. 그렇게 두기로 했다 (D-064).**
            이 네임스페이스의 컨테이너에는 CPU `limit` 이 없고 앞으로도
            걸지 않는다 — 스로틀링이 곧 지연이라, 지연을 재는 시스템에
            지연을 만드는 설정을 켤 수 없다.

            **파드별 CPU 는 위의 "CPU 사용률" 위젯으로 본다.**
            조임 비율 대신 정상 파드와의 사용량 차이로 지목한다.

            (`keda` 네임스페이스로 바꾸면 값이 나온다 — 그쪽 Helm 차트가
            자기 파드에 limit 을 걸어 둔다.)
          EOT
        }
      }

      widget {
        timeseries_definition {
          # request 는 지키고 있어도 CFS 쿼터에 몰려 스로틀링될 수 있다.
          # CPU 사용률만 보면 이 상태를 놓친다 — 사용률은 낮은데 응답은 느려진다.
          title       = "CPU Throttling 비율 (%)"
          title_size  = "16"
          show_legend = true

          request {
            display_type = "line"
            formula {
              formula_expression = "query1 / query2 * 100"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "avg:kubernetes.cpu.cfs.throttled.periods{${local.infra_scope}} by {pod_name}"
                aggregator  = "avg"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query2"
                query       = "avg:kubernetes.cpu.cfs.periods{${local.infra_scope}} by {pod_name}"
                aggregator  = "avg"
              }
            }
          }

          marker {
            display_type = "warning dashed"
            value        = "y = ${var.cpu_throttling_warning}"
            label        = "스로틀링 경고"
          }

          yaxis {
            min          = "0"
            include_zero = true
          }
        }
      }

      widget {
        timeseries_definition {
          # 노드 레벨 디스크다 — 파드가 몰리면 사용률이 오른다.
          # system.io 는 core check 라 Agent 옵션을 따로 켤 필요가 없다.
          title       = "Disk I/O Utilization (KB/s)"
          title_size  = "16"
          show_legend = true

          request {
            q            = "avg:system.io.rkb_s{${local.infra_scope}} by {device}"
            display_type = "line"
            style {
              palette = "cool"
            }
          }

          request {
            q            = "avg:system.io.wkb_s{${local.infra_scope}} by {device}"
            display_type = "line"
            style {
              palette = "warm"
            }
          }

          yaxis {
            min          = "0"
            include_zero = true
          }
        }
      }

      widget {
        timeseries_definition {
          # 송신은 양수, 수신은 음수로 겹쳐 그린다 — 위아래 대칭이 무너지면
          # 한쪽 방향만 튄 것이라 원인(업로드 폭주 vs 다운로드 폭주)을 바로 가른다.
          title       = "Network I/O Total (2m avg)"
          title_size  = "16"
          show_legend = true

          request {
            display_type = "area"
            formula {
              formula_expression = "query1"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "avg:kubernetes.network.tx_bytes{${local.infra_scope}} by {pod_name}"
                aggregator  = "avg"
              }
            }
          }

          request {
            display_type = "area"
            formula {
              formula_expression = "-query2"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query2"
                query       = "avg:kubernetes.network.rx_bytes{${local.infra_scope}} by {pod_name}"
                aggregator  = "avg"
              }
            }
          }
        }
      }
    }
  }

  #############################################################################
  # 2. 파드 생명주기 — 뭔가 죽고 있는가, 왜 죽는가
  #############################################################################

  widget {
    group_definition {
      title       = "2. 파드 생명주기"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          title          = "Pod Restart Count"
          title_size     = "16"
          show_legend    = true
          legend_layout  = "auto"
          legend_columns = ["avg", "min", "max", "value"]

          request {
            q            = "sum:kubernetes_state.container.restarts{${local.infra_scope}} by {pod_name}"
            display_type = "bars"
            style {
              palette = "dog_classic"
            }
          }
        }
      }

      widget {
        timeseries_definition {
          # updated/available/unavailable 이 desired 와 벌어지면 롤아웃이
          # 멈춘 것이다 — Deployment 오브젝트 자체가 알려주는 유일한 위젯.
          title       = "Replicas"
          title_size  = "16"
          show_legend = true

          request {
            q            = "avg:kubernetes_state.deployment.replicas_updated{${local.infra_scope}} by {kube_deployment}"
            display_type = "line"
          }

          request {
            q            = "avg:kubernetes_state.deployment.replicas_available{${local.infra_scope}} by {kube_deployment}"
            display_type = "line"
          }

          request {
            q            = "avg:kubernetes_state.deployment.replicas_unavailable{${local.infra_scope}} by {kube_deployment}"
            display_type = "line"
          }

          request {
            q            = "avg:kubernetes_state.deployment.replicas_desired{${local.infra_scope}} by {kube_deployment}"
            display_type = "line"
          }

          yaxis {
            min          = "0"
            include_zero = true
          }
        }
      }

      widget {
        timeseries_definition {
          # Pending 은 "스케줄이 안 된다" 다 — 자원 부족·노드 셀렉터 불일치·
          # PVC 바인딩 대기 등, 컨테이너가 뜨기도 전에 막힌 상태다.
          title       = "Pods Pending Count"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:kubernetes_state.pod.status_phase{${local.infra_scope},phase:pending}.as_count()"
            display_type = "bars"
            style {
              palette = "orange"
            }
          }

          yaxis {
            min          = "0"
            include_zero = true
          }
        }
      }

      widget {
        query_table_definition {
          # 종료된 컨테이너의 reason 태그(error·oomkilled·completed 등) 별
          # 집계다. "재시작이 늘었다"만으로는 원인을 못 좁힌다 — 이유가 있어야
          # OOM 인지 애플리케이션 크래시인지 갈린다.
          title      = "Pod Restart Reason"
          title_size = "16"

          request {
            q          = "sum:kubernetes_state.container.status_report.count.terminated{${local.infra_scope}} by {pod_name,kube_namespace,reason}"
            aggregator = "sum"
            limit      = 10
            order      = "desc"
          }
        }
      }

      widget {
        query_table_definition {
          # 뜨지 못한 채 대기 중인 컨테이너의 reason(errimagepull·
          # imagepullbackoff·containercreating 등). 재시작 테이블과 인과가
          # 다르다 — 이쪽은 "이미지가 안 당겨진다" 류라 배포·레지스트리 쪽이다.
          title      = "Pod Waiting Reason"
          title_size = "16"

          request {
            q          = "sum:kubernetes_state.container.status_report.count.waiting{${local.infra_scope}} by {pod_name,kube_namespace,reason}"
            aggregator = "sum"
            limit      = 10
            order      = "desc"
          }
        }
      }
    }
  }

  #############################################################################
  # 3. 노드 · 프로브 — 그 파드가 뜰 자리·헬스체크는 정상인가
  #############################################################################

  widget {
    group_definition {
      title       = "3. 노드 · 프로브"
      layout_type = "ordered"

      widget {
        query_table_definition {
          title      = "Ready pods per node"
          title_size = "16"

          request {
            q          = "sum:kubernetes_state.pod.ready{${local.infra_scope}} by {host,pod_name}"
            aggregator = "sum"
            limit      = 20
            order      = "desc"
          }
        }
      }

      widget {
        # 프로브 실패는 게이지 메트릭이 아니라 Kubernetes 이벤트로 온다.
        # `04-platform/datadog.tf` 의 kubernetesEvents.filteringEnabled 가
        # 실패·스케줄링·노드 이상만 거르므로 여기 뜨는 것은 전부 봐야 할 신호다.
        #
        # **`reason:unhealthy` 태그는 존재하지 않는다** — kubelet 이 보내는
        # 이벤트에 그런 태그가 안 붙는다(실측 확인). "Unhealthy: Readiness
        # probe failed ..." 처럼 이벤트 `text` 안에만 문자열로 남는다. 그래서
        # 태그가 아니라 텍스트 검색 토큰(`"Unhealthy"`)으로 잡는다. `source:`
        # 는 단수형이다 — `sources:` 로 쓰면 이 org 기준 0건이 나온다.
        event_stream_definition {
          title      = "Probe Failed Events"
          title_size = "16"
          query      = "source:kubernetes \"Unhealthy\" ${local.infra_event_scope}"
          event_size = "s"
        }
      }
    }
  }

  #############################################################################
  # 4. HTTP 트래픽 — 결국 사용자가 받는 응답 (APM)
  #############################################################################

  widget {
    group_definition {
      title       = "4. HTTP 트래픽 (APM)"
      layout_type = "ordered"

      widget {
        note_definition {
          background_color = "gray"
          font_size        = "12"
          text_align       = "left"
          vertical_align   = "top"
          show_tick        = false

          content = <<-EOT
            이 그룹만 `service`·`env` 축이다 — `apm.portEnabled` 로 받는
            `trace.fastapi.request.*` 계열. 1~3번(kube_cluster_name·kube_namespace)과
            축이 다르므로 같은 화면이라도 상단 두 축을 같이 맞출 필요는 없다.

            **span 이름은 프레임워크가 정한다.** 이 org 엔 `trace.http.request.*`
            가 없다 — 앱이 FastAPI 라서 ddtrace 가 span 을 `fastapi.request`
            로 붙인다. 다른 프레임워크로 바뀌면 이 이름도 같이 바뀐다.
          EOT
        }
      }

      widget {
        query_value_definition {
          title       = "HTTP Requests Per Second"
          title_size  = "16"
          autoscale   = true
          custom_unit = "reqs"

          request {
            q          = "sum:trace.fastapi.request.hits{${local.apm_scope}}.as_rate()"
            aggregator = "avg"
          }
        }
      }

      widget {
        query_value_definition {
          # `trace.fastapi.request.errors` 서브메트릭 자체가 이 org 엔 없다
          # (5xx 가 한 번도 안 나서 — ddtrace 는 실제로 값이 발생해야 그
          # 서브메트릭을 만든다). 대신 상태코드별 히트 수(`hits.by_http_status`)
          # 에서 5xx 만 걸러 분자로 쓴다. 5xx 가 없으면 분자가 0 이라 성공률
          # 100% 로 나온다 — 이건 위젯 오류가 아니라 있는 그대로다.
          title      = "Http Response Success Rate (non-5xx)"
          title_size = "16"
          autoscale  = false
          precision  = 0

          request {
            aggregator = "avg"
            formula {
              formula_expression = "(query1 - query2) / query1 * 100"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "sum:trace.fastapi.request.hits{${local.apm_scope}}.as_count()"
                aggregator  = "sum"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query2"
                query       = "sum:trace.fastapi.request.hits.by_http_status{${local.apm_scope},http.status_code:5*}.as_count()"
                aggregator  = "sum"
              }
            }

            conditional_formats {
              comparator = ">="
              value      = 99
              palette    = "white_on_green"
            }
            conditional_formats {
              comparator = ">="
              value      = 95
              palette    = "white_on_yellow"
            }
            conditional_formats {
              comparator = "<"
              value      = 95
              palette    = "white_on_red"
            }
          }
        }
      }

      widget {
        timeseries_definition {
          title          = "Http Requests Rates"
          title_size     = "16"
          show_legend    = true
          legend_layout  = "auto"
          legend_columns = ["avg", "min", "max", "sum", "value"]

          request {
            q            = "sum:trace.fastapi.request.hits{${local.apm_scope}} by {resource_name}.as_rate()"
            display_type = "line"
          }

          yaxis {
            min          = "0"
            include_zero = true
          }
        }
      }

      widget {
        timeseries_definition {
          # 5xx 는 우리 쪽 원인일 확률이 높다 — 4xx(사용자 오류)와 섞으면
          # "우리가 고칠 수 있는 에러"의 신호가 묻힌다.
          title       = "HTTP 5xx Count"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:trace.fastapi.request.hits.by_http_status{${local.apm_scope},http.status_code:5*}.as_count()"
            display_type = "bars"
            style {
              palette = "warm"
            }
          }

          yaxis {
            min          = "0"
            include_zero = true
          }
        }
      }

      widget {
        timeseries_definition {
          # `trace.http.request.duration` 은 이 org 에 없다. ddtrace 가 만드는
          # 실제 응답시간 지표는 `exec_time.by_service` 다 — 초 단위라 ms 로
          # 보려면 1000 을 곱한다(나눈 게 아니다. 이전 버전은 duration 이
          # 나노초라고 가정해 1e6 으로 나눴는데, 애초에 그 메트릭이 없었다).
          title       = "Http Requests Durations (ms)"
          title_size  = "16"
          show_legend = true

          request {
            display_type = "line"
            formula {
              formula_expression = "query1 * 1000"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "avg:trace.fastapi.request.exec_time.by_service{${local.apm_scope}} by {resource_name}"
                aggregator  = "avg"
              }
            }
          }

          yaxis {
            min          = "0"
            include_zero = true
          }
        }
      }

      widget {
        timeseries_definition {
          # `.errors` 서브메트릭이 없는 것과 같은 이유로, "5xx Count" 위젯과는
          # 다르게 4xx 도 함께 잡는다 — 이쪽은 "5xx만"이 아니라 "에러로 잡히는
          # 전체"를 보는 위젯이라, 상태코드별 히트를 4xx+5xx 로 더해서 만든다.
          title          = "Http Requests Errors"
          title_size     = "16"
          show_legend    = true
          legend_layout  = "auto"
          legend_columns = ["avg", "min", "max", "sum", "value"]

          request {
            display_type = "bars"
            formula {
              formula_expression = "query1 + query2"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query1"
                query       = "sum:trace.fastapi.request.hits.by_http_status{${local.apm_scope},http.status_code:4*}.as_count()"
                aggregator  = "sum"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "query2"
                query       = "sum:trace.fastapi.request.hits.by_http_status{${local.apm_scope},http.status_code:5*}.as_count()"
                aggregator  = "sum"
              }
            }
          }

          yaxis {
            min          = "0"
            include_zero = true
          }
        }
      }
    }
  }
}

output "dashboard_infra_url" {
  description = "인프라 대시보드 주소"
  value       = "${local.dd_app_url}/dashboard/${datadog_dashboard.infra.id}"
}
