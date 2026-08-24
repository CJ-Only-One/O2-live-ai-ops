###############################################################################
# 비즈니스 관측 대시보드
#
# 위에서 아래로 읽는 순서가 곧 진단 순서다.
#
#   1. 사용자가 지금 불편한가        ← 판단은 여기서 끝나는 경우가 많다
#   2. 부하가 평시와 다른가
#   3. 실패의 내부 구조는 어떤가
#   4. 원인이 무엇인가 (감별)
#   5. 이 화면 자체를 믿을 수 있는가
#
# **5번이 있는 이유:** 빈 위젯은 "정상"이 아니다. 트래픽이 없어서일 수도,
# 파이프라인이 죽어서일 수도 있다. 그 구분을 화면 안에서 할 수 있어야 한다.
#
# 위젯에 쓰는 메트릭은 `o2warm/metrics.py` 의 DATADOG_SCALARS 에 있는 것만이다.
# 목록에 없는 값(`baseline_rps`, `latency_p99`, `failure_codes`,
# `top_contributors`)은 Datadog 으로 가지 않는다. 맵이거나 고카디널리티라
# 태그로 펼치면 요금이 터진다 — 그것들은 DynamoDB 에서 Agent 가 읽는다.
###############################################################################

locals {
  p = var.metric_prefix

  # 모든 위젯이 템플릿 변수로 범위를 좁힌 뒤 조회한다. 싼 축(태그)으로
  # 먼저 자르고 보는 것이 조회 설계의 기본이다.
  scope = "$service,$env"
}

resource "datadog_dashboard" "business" {
  title       = "O2 라이브커머스 — 비즈니스 관측"
  layout_type = "ordered"
  reflow_type = "auto"

  description = join(" ", [
    "이벤트 스트림에서 계산한 비즈니스 지표.",
    "인프라 지표(CPU·메모리·파드)는 Datadog Agent 가 따로 보내며 이 화면에 없다.",
    "담당 경계는 데이터 출처로 나뉜다 — 인프라는 Agent, 이벤트는 집계 Lambda.",
  ])

  # ── 범위 축 ────────────────────────────────────────────────
  # service 는 Metric·Log·Trace 를 묶는 세로축이다. 이름 규칙이 흔들리면
  # 연결의 근거가 사라지므로 대시보드도 같은 축을 쓴다.
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
        **임계치 색깔은 잠정치다.** 평시 분포를 아직 모른다 — 며칠 보고
        `variables.tf` 에서 고친다. 일반론이 아니라 우리 서비스 조건에서
        나와야 하는 값이다.

        **위젯이 비었다고 정상이 아니다.** 세 가지 경우가 있고 의미가 다르다.
        (1) 그 10초 창에 이벤트가 없었다 — 맨 아래 `event_count` 로 확인
        (2) 표본이 적어 지표를 계산할 수 없었다 — `confidence` 로 확인
        (3) 전송이 깨졌다 — `datadog_series` 가 0 인지 Lambda 로그를 본다

        지표는 0 이 아니라 **없음**으로 온다. 표본이 없어서 0 인 것과 실제로
        0 인 것을 구분하기 위한 설계다.

        **"감별" 그룹에는 알림을 걸지 않는다.** 받았을 때 할 행동이 정해진
        지표만 알림이 되고, 나머지는 여기서 본다.
      EOT
    }
  }

  #############################################################################
  # 1. 사용자 영향 — 알림을 만들 후보는 이 그룹뿐이다
  #############################################################################

  widget {
    group_definition {
      title       = "1. 사용자 영향"
      layout_type = "ordered"

      # 원인 후보(CPU·메모리)가 아니라 사용자가 겪는 것을 기준으로 둔다.
      # 아래 넷은 인프라 지표가 전부 정상인 채로도 움직인다.

      widget {
        query_value_definition {
          title      = "주문·발급 실패율"
          title_size = "16"
          autoscale  = false
          precision  = 3

          request {
            q          = "sum:o2.app.failure{${local.scope}}.as_count() / sum:o2.app.business_event{${local.scope}}.as_count()"
            aggregator = "last"

            conditional_formats {
              comparator = "<"
              value      = var.failure_rate_warning
              palette    = "white_on_green"
            }
            conditional_formats {
              comparator = "<"
              value      = var.failure_rate_critical
              palette    = "white_on_yellow"
            }
            conditional_formats {
              comparator = ">="
              value      = var.failure_rate_critical
              palette    = "white_on_red"
            }
          }
        }
      }

      widget {
        query_value_definition {
          title      = "응답시간 p95 (ms)"
          title_size = "16"
          autoscale  = false
          precision  = 0

          request {
            # APM 원시 단위(second)를 기존 화면 계약(ms)으로 변환한다.
            q          = "p95:trace.fastapi.request{${local.scope}} * 1000"
            aggregator = "last"

            conditional_formats {
              comparator = "<"
              value      = var.latency_p95_warning
              palette    = "white_on_green"
            }
            conditional_formats {
              comparator = "<"
              value      = var.latency_p95_critical
              palette    = "white_on_yellow"
            }
            conditional_formats {
              comparator = ">="
              value      = var.latency_p95_critical
              palette    = "white_on_red"
            }
          }
        }
      }

      widget {
        query_value_definition {
          # 서버는 매번 성공했을 수 있다. 사용자가 같은 동작을 반복했다는
          # 것 자체가 체감 저하의 증거다.
          title      = "재시도율"
          title_size = "16"
          autoscale  = false
          precision  = 3

          request {
            q          = "sum:o2.app.retry{${local.scope}}.as_count() / sum:o2.app.retry_eligible{${local.scope}}.as_count()"
            aggregator = "last"

            conditional_formats {
              comparator = "<"
              value      = var.retry_rate_warning
              palette    = "white_on_green"
            }
            conditional_formats {
              comparator = "<"
              value      = var.retry_rate_critical
              palette    = "white_on_yellow"
            }
            conditional_formats {
              comparator = ">="
              value      = var.retry_rate_critical
              palette    = "white_on_red"
            }
          }
        }
      }

      widget {
        query_value_definition {
          # 취소는 사후·비동기라 요청 시점에는 아무 신호가 없다.
          title      = "주문 취소율"
          title_size = "16"
          autoscale  = false
          precision  = 3

          request {
            q          = "sum:o2.app.cancel{${local.scope}}.as_count() / sum:o2.app.order_create{${local.scope}}.as_count()"
            aggregator = "last"

            conditional_formats {
              comparator = "<"
              value      = var.cancel_rate_warning
              palette    = "white_on_green"
            }
            conditional_formats {
              comparator = "<"
              value      = var.cancel_rate_critical
              palette    = "white_on_yellow"
            }
            conditional_formats {
              comparator = ">="
              value      = var.cancel_rate_critical
              palette    = "white_on_red"
            }
          }
        }
      }

      # 순간값 넷만 보면 스파이크와 지속을 구분할 수 없다. 알림의 `for` 에
      # 해당하는 판단을 사람이 하려면 추세가 같은 화면에 있어야 한다.
      widget {
        timeseries_definition {
          title         = "사용자 영향 추세 — 스파이크인가 지속인가"
          title_size    = "16"
          show_legend   = true
          legend_layout = "horizontal"

          request {
            q            = "sum:o2.app.failure{${local.scope}}.as_count() / sum:o2.app.business_event{${local.scope}}.as_count()"
            display_type = "line"
            style {
              palette    = "warm"
              line_type  = "solid"
              line_width = "normal"
            }
          }

          request {
            q            = "sum:o2.app.retry{${local.scope}}.as_count() / sum:o2.app.retry_eligible{${local.scope}}.as_count()"
            display_type = "line"
            style {
              palette    = "purple"
              line_type  = "solid"
              line_width = "thin"
            }
          }

          request {
            q            = "sum:o2.app.cancel{${local.scope}}.as_count() / sum:o2.app.order_create{${local.scope}}.as_count()"
            display_type = "line"
            style {
              palette    = "orange"
              line_type  = "dotted"
              line_width = "thin"
            }
          }

          marker {
            display_type = "error dashed"
            value        = "y = ${var.failure_rate_critical}"
            label        = "실패율 위험"
          }

          yaxis {
            min          = "0"
            include_zero = true
          }
        }
      }
    }
  }

  #############################################################################
  # 2. 부하 — 절대값이 아니라 평시 대비로 본다
  #############################################################################

  widget {
    group_definition {
      title       = "2. 부하"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # rps 만 보면 "이 값이 높은가"에 답할 수 없다. 특가 이벤트가 있는
          # 서비스라 평시 자체가 시간대마다 다르다.
          title       = "평시 대비 배수 (rps_ratio)"
          title_size  = "16"
          show_legend = true

          request {
            q            = "anomalies(sum:trace.fastapi.request.hits{${local.scope}}.as_rate(), 'agile', 3, direction='above', interval=60, alert_window='last_5m', seasonality='hourly')"
            display_type = "area"
            style {
              palette   = "cool"
              line_type = "solid"
            }
          }

          # EWMA 표본이 30개(약 5분) 쌓이기 전에는 이 값이 비어 있다.
          # 비어 있는 것이 오류가 아니라는 뜻을 마커로 남긴다.
          marker {
            display_type = "ok dashed"
            value        = "y = 1"
            label        = "평시"
          }

          yaxis {
            min          = "0"
            include_zero = true
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "초당 요청 수 (rps)"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:trace.fastapi.request.hits{${local.scope}}.as_rate()"
            display_type = "bars"
            style {
              palette = "dog_classic"
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
          # 트래픽 증가와 매크로를 가르는 첫 갈림길이다. 사용자 수가 함께
          # 늘었으면 트래픽 증가, rps 만 늘었으면 소수가 때리는 것이다.
          title       = "순 사용자 수"
          title_size  = "16"
          show_legend = true

          request {
            q            = "avg:${local.p}distinct_users{${local.scope}}"
            display_type = "line"
            style {
              palette = "green"
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

  #############################################################################
  # 3. 실패의 내부 구조 — 평균이 가리는 것을 드러낸다
  #############################################################################

  widget {
    group_definition {
      title       = "3. 실패의 구조"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # PG 장애와 DB 장애는 전체 실패율이 같다. 어느 이벤트가 실패하는지가
          # 갈라낸다. event 는 값의 종류가 6개로 고정이라 태그로 안전하다.
          title         = "이벤트별 실패율"
          title_size    = "16"
          show_legend   = true
          legend_layout = "auto"

          request {
            q            = "sum:o2.app.failure{${local.scope}} by {event}.as_count() / sum:o2.app.business_event{${local.scope}} by {event}.as_count()"
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
          title       = "응답시간 p50 · p95"
          title_size  = "16"
          show_legend = true

          # 두 선이 함께 오르면 전반적 지연, p95만 오르면 꼬리만 나빠진 것이다.
          # 후자는 평균으로는 보이지 않는다.
          request {
            q            = "p50:trace.fastapi.request{${local.scope}} * 1000"
            display_type = "line"
            style {
              palette   = "cool"
              line_type = "solid"
            }
          }

          request {
            q            = "p95:trace.fastapi.request{${local.scope}} * 1000"
            display_type = "line"
            style {
              palette    = "warm"
              line_type  = "solid"
              line_width = "thick"
            }
          }

          marker {
            display_type = "warning dashed"
            value        = "y = ${var.latency_p95_warning}"
            label        = "p95 경고"
          }

          yaxis {
            min          = "0"
            include_zero = true
          }
        }
      }

      widget {
        timeseries_definition {
          # 폴백 성공은 '성공'으로 기록되어 실패율에 잡히지 않는다.
          # 캐시가 죽어 원본을 때리고 있는 상황이 여기서만 보인다.
          title       = "캐시 적중률 · 폴백 사용률"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:o2.app.cache_access{${local.scope},result:hit}.as_count() / sum:o2.app.cache_access{${local.scope}}.as_count()"
            display_type = "line"
            style {
              palette = "green"
            }
          }

          request {
            q            = "sum:o2.app.fallback{${local.scope}}.as_count() / sum:o2.app.fallback_attempt{${local.scope}}.as_count()"
            display_type = "line"
            style {
              palette    = "orange"
              line_type  = "dashed"
              line_width = "normal"
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
          # 외부 PG 가 느려지는 것은 우리 코드가 정상인 채로 일어난다.
          title       = "PG 지연 비율"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p95:o2.apm.db.duration{${local.scope}} / p95:o2.apm.request.duration{${local.scope}}"
            display_type = "line"
            style {
              palette = "purple"
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

  #############################################################################
  # 4. 감별 — 원인을 좁히는 축. **알림을 걸지 않는다.**
  #############################################################################

  widget {
    group_definition {
      title       = "4. 감별 (알림 대상 아님)"
      layout_type = "ordered"

      widget {
        note_definition {
          background_color = "gray"
          font_size        = "12"
          text_align       = "left"
          vertical_align   = "top"
          show_tick        = false

          content = <<-EOT
            **어느 지표도 단독으로 시나리오를 특정하지 못한다.** 조합으로
            판단하고, 조합 판단은 사람 또는 에이전트가 한다. 그래서 여기에는
            알림을 걸지 않는다 — 받아도 할 행동이 정해지지 않는다.

            매크로는 인프라 지표가 전부 정상인 채로 진행된다. CPU 로는 안 보인다.
          EOT
        }
      }

      widget {
        timeseries_definition {
          # 트래픽 폭증은 사용자 수가 늘어난 것이고, 매크로는 소수가 많이
          # 때린 것이다. 총 rps 는 둘 다 오르므로 이 축이 갈라낸다.
          title       = "요청 집중도 — 상위 5계정 · 상위 1%"
          title_size  = "16"
          show_legend = true

          request {
            q            = "avg:${local.p}top5_share{${local.scope}}"
            display_type = "line"
            style {
              palette    = "warm"
              line_width = "thick"
            }
          }

          request {
            q            = "avg:${local.p}top1pct_share{${local.scope}}"
            display_type = "line"
            style {
              palette   = "cool"
              line_type = "dashed"
            }
          }

          yaxis {
            min          = "0"
            max          = "1"
            include_zero = true
          }
        }
      }

      widget {
        timeseries_definition {
          # 사람은 요청 간격이 불규칙하고 기계는 일정하다. 낮을수록 기계에 가깝다.
          # interval_cv_top(상위 계정만)이 감별에 쓰는 값이다.
          title       = "요청 간격 변동계수 — 낮으면 기계"
          title_size  = "16"
          show_legend = true

          request {
            q            = "avg:${local.p}interval_cv_top{${local.scope}}"
            display_type = "line"
            style {
              palette    = "warm"
              line_width = "thick"
            }
          }

          request {
            q            = "avg:${local.p}interval_cv{${local.scope}}"
            display_type = "line"
            style {
              palette   = "cool"
              line_type = "dashed"
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
          # 정상 사용자는 버튼을 누르고 요청이 간다. 매크로는 버튼 없이 API를
          # 직접 부른다. **두 스트림이 같은 10초 창에 모여야만 나오는 값이다** —
          # 비어 있으면 stream-client 가 안 흐르는 것일 수 있다.
          title       = "클릭 대비 요청 (click_ratio)"
          title_size  = "16"
          show_legend = true

          request {
            q            = "avg:${local.p}click_ratio{${local.scope}}"
            display_type = "line"
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
        timeseries_definition {
          title       = "User-Agent · IP 다양성"
          title_size  = "16"
          show_legend = true

          request {
            q            = "avg:${local.p}ua_diversity{${local.scope}}"
            display_type = "line"
            style {
              palette = "purple"
            }
          }

          request {
            q            = "avg:${local.p}ip_diversity{${local.scope}}"
            display_type = "line"
            style {
              palette   = "cool"
              line_type = "dashed"
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
          # 배포 장애만 이 값이 벌어진다. 인프라 지표로는 절대 보이지 않는다.
          # 최신 버전이 직전 버전보다 얼마나 더 실패하는가.
          title       = "버전 간 실패율 차이 (version_fail_delta)"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:o2.app.failure{${local.scope}} by {version}.as_count() / sum:o2.app.business_event{${local.scope}} by {version}.as_count()"
            display_type = "bars"
            style {
              palette = "warm"
            }
          }

          marker {
            display_type = "ok dashed"
            value        = "y = 0"
            label        = "차이 없음"
          }
        }
      }
    }
  }

  #############################################################################
  # 5. 이 화면을 믿을 수 있는가 — 없음도 신호다
  #############################################################################

  widget {
    group_definition {
      title       = "5. 파이프라인 자체"
      layout_type = "ordered"

      widget {
        note_definition {
          background_color = "blue"
          font_size        = "12"
          text_align       = "left"
          vertical_align   = "top"
          show_tick        = false

          content = <<-EOT
            **푸시 기반이라 "조용함"과 "정상"이 구분되지 않는다.** 스크레이프
            방식이면 대상이 죽으면 `up=0` 으로 잡히지만, 아무도 안 보내면
            그냥 아무 일도 없는 것처럼 보인다.

            위 두 값이 0이거나 비면 지표를 믿지 말고 이것부터 확인한다.

                aws logs tail /aws/lambda/o2-agg --since 10m --profile o2-data `
                  --filter-pattern "datadog_series"

            `datadog_series` 가 전송에 성공한 시계열 수다. 0 이면 같은 로그의
            `[o2warm]` 줄에 사유가 있다.
          EOT
        }
      }

      widget {
        timeseries_definition {
          # 이벤트가 들어오고는 있는가. 이것이 0이면 위의 모든 위젯이
          # 비는 것이 정상이고, 0이 아닌데 비면 계산이나 전송 문제다.
          title       = "윈도우당 이벤트 수 (event_count)"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:o2.app.business_event{${local.scope}}.as_count()"
            display_type = "bars"
            style {
              palette = "grey"
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
          # 표본이 적어서 계산을 못 한 것과 실제로 0인 것을 구분하는 값이다.
          # 낮으면 위 지표들을 액면가로 믿지 않는다.
          title       = "지표 신뢰도 (confidence)"
          title_size  = "16"
          show_legend = true

          request {
            q            = "avg:${local.p}confidence{${local.scope}}"
            display_type = "line"
            style {
              palette = "green"
            }
          }

          marker {
            display_type = "warning dashed"
            value        = "y = 0.5"
            label        = "해석 주의"
          }

          yaxis {
            min          = "0"
            max          = "1"
            include_zero = true
          }
        }
      }
    }
  }

  ###########################################################################
  # 6. 파드별 비교 — 재분석용 (알림 대상 아님)
  #
  # 위의 모든 위젯은 **service 단위**다. 그래서 파드 하나만 아픈 장애가
  # 통째로 안 보인다 — 파드 4개 중 1개가 죽어도 평균은 75%고, 그건 임계
  # 안이다. 이 그룹만이 그 하나를 집어낸다.
  #
  # **알림에서 여기로 온다.** `order_latency_p95`(service 단위)가 울리고
  # 1차 조치가 듣지 않았을 때, 명세의 자기 교정 루프가 "전부 느린 건가
  # 파드 하나인가" 를 묻는다. 그 질문에 답하는 자리가 여기다.
  # `latency_p95_pod_outlier` · `cache_hit_rate_pod_outlier` 가 지목한
  # 파드를 눈으로 확인하는 곳이기도 하다.
  #
  # **`pod_name:N/A` 선이 하나 섞여 나온다.** service 단위로 보낸 값이
  # 태그가 없어 그렇게 잡히는 것이다(D-057). 지우지 않고 둔다 — 파드
  # 선들과 겹쳐 보면 그게 곧 "전체 평균" 기준선 역할을 한다.
  ###########################################################################
  widget {
    group_definition {
      title       = "6. 파드별 비교 (재분석)"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # 파드 하나만 위로 떨어지면 그 파드가 범인이다. 전부 같이 오르면
          # 파드 문제가 아니라 상류(캐시·DB·PG) 문제다.
          #
          # 표본 5건 미만인 파드는 애초에 이 축에 안 실린다
          # (`LATENCY_POD_MIN_SAMPLES`) — 방금 뜬 파드의 콜드 스타트가
          # 이상치로 보이는 것을 막기 위해서다. 그래서 스케일아웃 직후
          # 선이 몇 개 비어 있는 것은 정상이다.
          title       = "파드별 응답시간 p95 — 하나만 느린가"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p95:o2.apm.request.duration{${local.scope}} by {pod_name} / 1000000"
            display_type = "line"
            style {
              palette   = "warm"
              line_type = "solid"
            }
          }

          marker {
            display_type = "warning dashed"
            value        = "y = ${var.latency_p95_warning}"
            label        = "p95 경고"
          }

          yaxis {
            min          = "0"
            include_zero = true
          }
        }
      }

      widget {
        timeseries_definition {
          # Valkey Pub/Sub 은 at-most-once 라 구독이 순간 끊긴 파드는 무효화를
          # 놓치고 옛 값을 계속 준다. 응답은 200 이라 실패율에 안 잡히고,
          # service 평균에도 묻힌다.
          #
          # 위 지연 위젯과 **같은 파드**가 떨어져 있으면 원인이 캐시 쪽이다.
          title       = "파드별 캐시 적중률 — 하나만 식었나"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:o2.app.cache_access{${local.scope},result:hit} by {pod_name}.as_count() / sum:o2.app.cache_access{${local.scope}} by {pod_name}.as_count()"
            display_type = "line"
            style {
              palette   = "cool"
              line_type = "solid"
            }
          }

          marker {
            display_type = "warning dashed"
            value        = "y = ${var.cache_hit_rate_critical}"
            label        = "적중률 위험"
          }

          yaxis {
            min          = "0"
            max          = "1"
            include_zero = true
          }
        }
      }
    }
  }
}

output "dashboard_url" {
  description = "대시보드 주소"
  value       = "${local.dd_app_url}/dashboard/${datadog_dashboard.business.id}"
}
