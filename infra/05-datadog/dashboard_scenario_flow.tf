###############################################################################
# 시나리오별 진행 화면 — 발생부터 해결까지 하나씩
#
# S1·S2·S3 각각에 대시보드 하나. 위젯이 위에서 아래로 **시간 순서**다.
#
#   ① 발생 → ② 감지 → ③ 진단 → ④ 조치 → ⑤ 검증
#
# `dashboard_scenarios.tf` 와 뭐가 다른가: 그쪽은 세 시나리오를 한 화면에 모아
# 놓은 **실험 진행자용 점검표**다. 이쪽은 시나리오 하나를 골라 **그 하나가
# 어떻게 풀려 가는지**를 따라가는 화면이다. 실행 중에 위에서 아래로 채워진다.
#
# ★ 검증 그룹(⑤)은 시나리오마다 조건이 다르고, 그 조건이 이 파일의 요점이다.
#   `docs/scenario-experiment.md` 1.2 를 그대로 옮겼다.
#
#     S1  전파 p95 복귀 **AND** 정상 사용자 차단률 상한 이내
#     S2  격리 후 p95 복귀, **증설분을 원복한 뒤에도** 유지
#     S3  1차는 조치 없이 ESCALATED 가 정상, 2차에서 전환 효과 확인
#
#   지연만 보면 "정상 사용자 절반을 차단해서 빨라진 것" 이 성공이 된다. 그래서
#   S1 의 ⑤ 는 위젯 두 개를 나란히 두고 **둘 다** 봐야 판정이 선다.
#
###############################################################################
# ★★ 쿼리 규칙 — 조용히 비는 사고를 막는 네 가지
#
# 전부 2026-08-27 에 `/api/v1/query` 로 실측해서 정했다. 어기면 **오류가 아니라
# 빈 화면**이 나오고, 빈 화면은 "정상" 과 구분되지 않는다.
#
# 1. **템플릿 변수(`$env` 등)를 쓰지 않는다.**
#    이 파일의 모든 범위는 Terraform 이 apply 시점에 값으로 박는다. 화면을
#    열 때 치환되는 것이 없으므로, 여기 적힌 쿼리와 실제로 나가는 쿼리가 같다.
#    확인한 쿼리가 곧 배포된 쿼리다.
#
# 2. **`key:value` 와 `key IN (...)` 를 한 중괄호에 같이 쓰지 않는다.**
#    섞으면 0 series 다. 실측:
#
#      {operation IN (chat.fanout,chat.message)}            -> 2 series
#      {env:dev,operation IN (chat.fanout,chat.message)}    -> **0 series**
#      {kube_deployment IN (api,api-canary)}                -> 2 series
#      {kube_namespace:o2-dev,kube_deployment IN (...)}     -> **0 series**
#
#    그래서 여러 값을 고를 때는 **와일드카드**(`operation:chat*`,
#    `kube_deployment:api*`)를 쓰거나 필터 없이 `by {...}` 로 펼친다.
#    `IN (...)` 은 그것만 단독으로 있을 때만 쓴다(아래 Lambda 위젯들).
#
# 3. **`aws.sqs.*` · `aws.kinesis.*` · `aws.firehose.*` 에 env 를 붙이지 않는다.**
#    이 셋은 `env` 태그가 아예 없다. 붙이면 전부 0 series 다.
#
# 4. **`aws.lambda.*` 에도 env 를 붙이지 않는다.**
#    실측: `aws.lambda.invocations{*} by {env}` 는 `env:dev` 와 `env:N/A` 로
#    갈리는데, **`env:dev` 에 들어오는 함수는 `o2-agg` 하나뿐이고 나머지 17개가
#    전부 `env:N/A`** 다. 즉 `{env:dev}` 로 묶으면 에이전트 대응 경로
#    (`o2-dify-ingress`·`o2-warm-api`·`o2-dev-dify-scale-executor` …)가 통째로
#    사라진다. 함수는 `functionname` 으로만 고른다.
#
# ★ 실험 전에는 대부분의 위젯이 비어 있는 것이 **정상**이다. 이 화면들은 부하와
#   장애 주입이 돌 때 채워진다. 다만 "실험을 안 해서 빈 것" 과 "계측이 없어서
#   영영 안 채워지는 것" 은 다른 사실이므로, 7일 창으로 전부 한 번씩 데이터가
#   들어온 것을 확인하고 넣었다. 확인 못 한 지표는 위젯을 만들지 않았다.
###############################################################################

locals {
  # 템플릿 변수를 안 쓰므로 여기서 한 번만 만들어 재사용한다.
  flow_env  = "env:${var.environment}"
  flow_api  = "env:${var.environment},service:${var.default_service}"
  flow_chat = "env:${var.environment},service:chat-gateway"
  flow_kube = "kube_namespace:${var.kube_namespace}"

  # 사람 승인(L3) 경로. `IN (...)` 단독이라 규칙 2 에 걸리지 않는다.
  flow_fn_approval = "o2-dev-dify-slack-approval-request,o2-dev-dify-slack-interactivity"
}

###############################################################################
# S1 — 채팅 총량 초과 → 채널 총량 제한 (승인 → 해결)
###############################################################################

resource "datadog_dashboard" "flow_s1" {
  title       = "[O2][S1] 채팅 총량 초과 — 발생부터 해결까지"
  layout_type = "ordered"
  reflow_type = "auto"

  description = join(" ", [
    "채팅 총량이 채널 감당 선을 넘어 전파가 늦어지고,",
    "사람 승인을 거쳐 채널 총량 제한을 건 뒤 회복되는 과정을 시간 순서로 본다.",
    "성공 판정은 전파 p95 복귀와 정상 사용자 차단률을 함께 본다.",
  ])

  widget {
    note_definition {
      background_color = "blue"
      font_size        = "14"
      text_align       = "left"
      vertical_align   = "top"
      show_tick        = false

      content = <<-EOT
        **위에서 아래가 시간 순서다.** ① 발생 → ② 감지 → ③ 진단 → ④ 조치 → ⑤ 검증.

        **성공은 두 조건이 동시에 서야 한다** (`scenario-experiment.md` 1.2).
        전파 p95 가 붕괴 전 구간으로 돌아오고, **정상 사용자 차단률이 상한 이내**여야
        한다. 지연만 보면 *정상 사용자를 절반 차단해서 빨라진 것*이 성공이 된다 —
        그래서 ⑤ 의 위젯 두 개를 반드시 같이 읽는다.

        **효과는 조치 적용 시각 이후만 센다.** 첫 파동은 이미 지나가 있다.

        실험 전에는 대부분 비어 있는 것이 정상이다. 부하가 돌면 위에서부터 채워진다.
      EOT
    }
  }

  widget {
    group_definition {
      title       = "① 발생 — 채널 감당 선을 넘긴다"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # 이 값이 `발화 수 × 접속자 수` 그 자체다. M-010 의 아이템/s 열과 같은
          # 값이고, 진입 Monitor 의 임계 근거도 이 표다.
          #   20,000  2파드 기준 안전선
          #   40,000  무너지는 지점
          title       = "팬아웃 아이템/s — 채널이 감당하는 총량"
          title_size  = "16"
          show_legend = true

          request {
            q            = "max:o2.app.fanout.items{${local.flow_env}}"
            display_type = "area"
          }
          marker {
            display_type = "warning dashed"
            label        = "안전선 (M-010 실측)"
            value        = "y = ${var.s1_fanout_items_warning}"
          }
          marker {
            display_type = "error dashed"
            label        = "감지 임계"
            value        = "y = ${var.s1_fanout_items_critical}"
          }
        }
      }

      widget {
        timeseries_definition {
          # 총량은 두 축의 곱이라, 어느 쪽이 올라서 넘겼는지를 여기서 가른다.
          # 접속자가 는 것과 발화가 는 것은 조치가 다르다.
          title       = "총량의 두 축 — 접속자 수와 발화율"
          title_size  = "16"
          show_legend = true

          request {
            q            = "max:o2.app.websocket.connections{${local.flow_env}}"
            display_type = "line"
          }
          request {
            q            = "sum:o2.app.business_event{${local.flow_chat},event:chat.send}.as_rate()"
            display_type = "line"
            style {
              palette = "cool"
            }
          }
        }
      }
    }
  }

  widget {
    group_definition {
      title       = "② 감지 — 알림이 울린 근거"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # 진입 Monitor 와 **같은 축**이다. 채널 총량은 방송마다 별개이므로
          # 인시던트 단위도 `service + broadcast_id` 다. 여기서 갈려 보이지
          # 않으면 조치를 어느 방송에 걸어야 할지 알 수 없다.
          title       = "전파 p95 — 방송별 (진입 Monitor 와 같은 축)"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p95:o2.chat.propagation{${local.flow_chat}} by {broadcast_id}"
            display_type = "line"
          }
          marker {
            display_type = "error dashed"
            label        = "진입 임계"
            value        = "y = ${var.chat_propagation_p95_critical_ms}"
          }
          marker {
            display_type = "warning dashed"
            label        = "경고"
            value        = "y = ${var.chat_propagation_p95_warning_ms}"
          }
        }
      }

      widget {
        timeseries_definition {
          # p50 이 같이 오르면 전 사용자가 겪는 지연이고, p95 만 오르면 일부
          # 파드·일부 방송이다. 조치 범위가 갈린다.
          title       = "몸통과 꼬리 — p50 · p95 · p99"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p50:o2.chat.propagation{${local.flow_chat}}"
            display_type = "line"
            style {
              palette = "grey"
            }
          }
          request {
            q            = "p95:o2.chat.propagation{${local.flow_chat}}"
            display_type = "line"
          }
          request {
            q            = "p99:o2.chat.propagation{${local.flow_chat}}"
            display_type = "line"
            style {
              palette = "warm"
            }
          }
        }
      }
    }
  }

  widget {
    group_definition {
      title       = "③ 진단 — 어디가 막혔나"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # 파드가 고르게 나쁘면 총량 문제이고, 한 파드만 나쁘면 그건 S1 이
          # 아니라 S2 다. 진단이 갈리는 자리라 조치 전에 반드시 본다.
          title       = "파드별 전파 p95 — 고른가, 한 파드인가"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p95:o2.chat.propagation{${local.flow_chat}} by {pod_name}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          # 규칙 2 — `operation IN (...)` 에 env 를 같이 쓰면 0 series 다.
          # 와일드카드로 고른다. chat.* 만 잡으므로 20초짜리 order.batch 가
          # 축을 눌러버리지 않는다.
          title       = "채팅 단계별 처리 지연 p95"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p95:o2.app.operation.duration{${local.flow_env},operation:chat*} by {operation}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          # 전파가 늦은 것이 CPU 때문인지 확인한다. CPU 가 멀쩡한데 전파만
          # 늦으면 원인은 자원이 아니라 총량이고, 그것이 S1 의 전제다.
          title       = "Gateway 파드 CPU"
          title_size  = "16"
          show_legend = true

          request {
            q            = "avg:kubernetes.cpu.usage.total{${local.flow_kube},kube_deployment:chat-gateway} by {pod_name}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          # 배치가 커지는 것은 팬아웃이 밀리기 시작했다는 선행 신호다.
          # 전파 p95 가 오르기 전에 여기가 먼저 움직인다.
          title       = "배치 크기와 메시지 크기"
          title_size  = "16"
          show_legend = true

          request {
            q            = "avg:o2.app.batch.size{${local.flow_env}}"
            display_type = "line"
          }
          request {
            q            = "avg:o2.app.message.size{${local.flow_env}}"
            display_type = "line"
            style {
              palette = "cool"
            }
          }
        }
      }
    }
  }

  widget {
    group_definition {
      title       = "④ 조치 — 사람 승인(L3) 뒤 채널 총량 제한"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # S1 의 조치는 L3 라 사람이 승인해야 실행된다. 승인 요청만 있고
          # 응답(interactivity)이 없으면 **사람 대기 중**이지 실패가 아니다.
          # 규칙 4 — env 를 붙이면 이 함수들이 전부 사라진다.
          title       = "승인 요청과 사람의 응답"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:aws.lambda.invocations{functionname IN (${local.flow_fn_approval})} by {functionname}.as_count()"
            display_type = "bars"
          }
        }
      }

      widget {
        timeseries_definition {
          # 조치가 실제로 걸렸다는 유일한 직접 증거다. 이 막대가 서기 시작한
          # 시각이 곧 "조치 적용 시각" 이고, 효과는 그 이후만 센다.
          title       = "채널 제한이 걸린 발화 수 — 조치 적용 시각"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:o2.app.failure{${local.flow_chat},event:chat.send,failure_code:channel_limited}.as_count()"
            display_type = "bars"
            style {
              palette = "warm"
            }
          }
        }
      }
    }
  }

  widget {
    group_definition {
      title       = "⑤ 검증 — 빨라졌나 + 안 망가뜨렸나 (둘 다 봐야 한다)"
      layout_type = "ordered"

      widget {
        note_definition {
          background_color = "yellow"
          font_size        = "13"
          text_align       = "left"
          vertical_align   = "center"
          show_tick        = false

          content = join(" ", [
            "**아래 두 위젯은 하나의 판정이다.**",
            "왼쪽만 좋아지면 정상 사용자를 차단해서 빨라진 것이고, 그것은 실패다.",
            "검증 대기는 60초 이상 — warm 집계 창이 10초라 그보다 짧으면 창 하나가",
            "튄 것으로 판정이 뒤집힌다.",
          ])
        }
      }

      widget {
        timeseries_definition {
          title       = "빨라졌나 — 전파 p95 복귀"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p95:o2.chat.propagation{${local.flow_chat}} by {broadcast_id}"
            display_type = "line"
          }
          marker {
            display_type = "error dashed"
            label        = "이 아래로 내려와야 한다"
            value        = "y = ${var.chat_propagation_p95_critical_ms}"
          }
        }
      }

      widget {
        timeseries_definition {
          # `chat_block_rate` Monitor 와 **같은 식**이다(chat_incident_monitors.tf).
          # 차단된 발화 ÷ 전체 발화. 여기가 상한을 넘으면 조치가 장애를 다른
          # 형태로 바꾼 것뿐이다.
          title       = "안 망가뜨렸나 — 정상 사용자 차단률"
          title_size  = "16"
          show_legend = true

          request {
            formula {
              formula_expression = "blocked / sent * 100"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "blocked"
                query       = "sum:o2.app.failure{${local.flow_chat},event:chat.send,failure_code:channel_limited}.as_count()"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "sent"
                query       = "sum:o2.app.business_event{${local.flow_chat},event:chat.send}.as_count()"
              }
            }
            display_type = "line"
          }
          marker {
            display_type = "error dashed"
            label        = "차단률 상한"
            value        = "y = ${var.chat_block_rate_critical * 100}"
          }
          marker {
            display_type = "warning dashed"
            label        = "경고"
            value        = "y = ${var.chat_block_rate_warning * 100}"
          }
        }
      }
    }
  }
}

###############################################################################
# S2 — 파드 자원 고갈 → 부하 쏠림 (증설 실패 → 격리, 사람 없음)
###############################################################################

resource "datadog_dashboard" "flow_s2" {
  title       = "[O2][S2] 파드 부하 쏠림 — 증설 실패에서 격리까지"
  layout_type = "ordered"
  reflow_type = "auto"

  description = join(" ", [
    "Service 에 붙은 파드 하나만 CPU 가 조여 서비스 꼬리 지연이 생기고,",
    "1차 증설이 미달한 뒤 재진단해서 격리로 푸는 과정을 시간 순서로 본다.",
    "1차 증설은 실패해야 정상이다.",
  ])

  widget {
    note_definition {
      background_color = "blue"
      font_size        = "14"
      text_align       = "left"
      vertical_align   = "top"
      show_tick        = false

      content = <<-EOT
        **위에서 아래가 시간 순서다.** ① 발생 → ② 감지 → ③ 진단 → ④ 조치 → ⑤ 검증.

        **1차 증설은 실패해야 정상이다.** 파드 하나만 느린 것이므로 대수를 늘리면
        p50 만 좋아지고 **p95·p99 는 그대로**다. ③ 의 파드별 위젯에서 그 차이를
        읽어 재진단이 서고, 그때 조치가 증설에서 격리로 바뀐다.

        **증설분을 원복한 뒤에도 유지되어야 끝이다.** 남긴 채 회복하면 "결국 파드를
        늘려서 나은 것" 을 배제할 수 없다 — ⑤ 에서 파드 수와 지연을 같이 본다.

        사람 승인이 없는 경로다(L1/L2). ④ 에 승인 위젯이 없는 것이 정상이다.
      EOT
    }
  }

  widget {
    group_definition {
      title       = "① 발생 — 파드 하나만 CPU 를 조인다"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # 스로틀은 절대 횟수가 아니라 **비율**로 봐야 한다. 트래픽이 늘면
          # periods 자체가 늘어서 횟수는 항상 오르기 때문이다.
          title       = "파드별 CPU 스로틀 비율"
          title_size  = "16"
          show_legend = true

          request {
            formula {
              formula_expression = "throttled / periods * 100"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "throttled"
                query       = "avg:kubernetes.cpu.cfs.throttled.periods{${local.flow_kube}} by {pod_name}"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "periods"
                query       = "avg:kubernetes.cpu.cfs.periods{${local.flow_kube}} by {pod_name}"
              }
            }
            display_type = "line"
          }
          marker {
            display_type = "warning dashed"
            label        = "스로틀 경고선"
            value        = "y = ${var.cpu_throttling_warning}"
          }
        }
      }

      widget {
        timeseries_definition {
          # 규칙 2 — `kube_deployment IN (...)` 에 namespace 를 같이 쓰면
          # 0 series 다. 와일드카드로 api 와 api-canary 를 같이 잡는다.
          title       = "api 계열 파드 수 — canary 가 붙는 시점"
          title_size  = "16"
          show_legend = true

          request {
            q            = "max:kubernetes_state.deployment.replicas_ready{${local.flow_kube},kube_deployment:api*} by {kube_deployment}"
            display_type = "line"
          }
        }
      }
    }
  }

  widget {
    group_definition {
      title       = "② 감지 — 서비스 전체의 꼬리가 늘어진다"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # 진입 Monitor 와 같은 축(p99). `trace.fastapi.request` 는 **초**라
          # ms 임계와 맞추려면 1000 을 곱해야 한다.
          title       = "API 응답 지연 — p50 · p95 · p99 (ms)"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p50:trace.fastapi.request{${local.flow_api}} * 1000"
            display_type = "line"
            style {
              palette = "grey"
            }
          }
          request {
            q            = "p95:trace.fastapi.request{${local.flow_api}} * 1000"
            display_type = "line"
          }
          request {
            q            = "p99:trace.fastapi.request{${local.flow_api}} * 1000"
            display_type = "line"
            style {
              palette = "warm"
            }
          }
          marker {
            display_type = "error dashed"
            label        = "진입 임계 p99"
            value        = "y = ${var.s2_tail_latency_p99_critical_ms}"
          }
          marker {
            display_type = "warning dashed"
            label        = "경고"
            value        = "y = ${var.s2_tail_latency_p99_warning_ms}"
          }
        }
      }

      widget {
        timeseries_definition {
          # 요청량이 그대로인데 꼬리만 늘어졌다는 것이 S2 의 전제다. 요청량이
          # 같이 뛰었으면 그건 부하 증가이지 쏠림이 아니다.
          title       = "요청량 — 부하가 는 것인가 아닌가"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:trace.fastapi.request.hits.by_http_status{${local.flow_api}} by {http.status_class}.as_rate()"
            display_type = "bars"
          }
        }
      }
    }
  }

  widget {
    group_definition {
      title       = "③ 진단 — 전체 포화인가, 한 파드인가 (재진단의 근거)"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # **이 화면의 핵심 위젯이다.** 선 하나만 위로 떨어져 나오면 쏠림이고,
          # 그러면 증설이 아니라 격리가 답이다. 선이 고르게 오르면 진짜 포화라
          # 증설이 맞다. 1차 조치가 미달한 이유가 여기서 읽힌다.
          title       = "파드별 처리 지연 p95 — 한 파드만 떨어져 나오는가"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p95:o2.app.operation.duration{${local.flow_api}} by {pod_name}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          # 집계 경로로 본 같은 사실. 위 위젯(Datadog 직접 계측)과 어긋나면
          # 둘 중 하나가 틀린 것이므로 판정을 미룬다.
          title       = "파드별 지연 p95 — 집계 경로 대조"
          title_size  = "16"
          show_legend = true

          request {
            q            = "avg:o2.warm.latency_p95{${local.flow_env}} by {pod_name}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          # readiness 만 넓히고 liveness 를 그대로 두면 CPU 스로틀 아래서
          # liveness 가 먼저 타임아웃돼 kubelet 이 파드를 통째로 재시작시킨다.
          # "Unready" 가 아니라 "죽었다 살아난다" — 그때마다 지연이 요동친다.
          title       = "파드 재시작 — 지연이 요동치면 여기부터 본다"
          title_size  = "16"
          show_legend = true

          request {
            q            = "max:kubernetes.containers.restarts{${local.flow_kube}} by {pod_name}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          # 하위 저장소의 누명을 벗기는 위젯이다. 여기가 조용한데 응답만
          # 늘어졌으면 원인은 애플리케이션 파드 쪽으로 좁혀진다.
          title       = "의존 계층 지연 p95 — DB · 캐시 (ms)"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p95:trace.pymysql.query{${local.flow_env}} * 1000"
            display_type = "line"
          }
          request {
            q            = "p95:trace.redis.command{${local.flow_env}} * 1000"
            display_type = "line"
            style {
              palette = "cool"
            }
          }
        }
      }
    }
  }

  widget {
    group_definition {
      title       = "④ 조치 — 1차 증설(미달) → 재진단 → 2차 격리"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # 실행기 호출 자체. 막대가 두 번 서는 것이 정상 경로다 —
          # 1차 증설, 2차 격리.
          title       = "조치 실행기 호출"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:aws.lambda.invocations{functionname:o2-dev-dify-scale-executor}.as_count()"
            display_type = "bars"
          }
        }
      }

      widget {
        timeseries_definition {
          # desired 가 먼저 오르고 ready 가 따라 오른다. 그 간격이 조치가
          # 실제로 걸리는 데 걸린 시간이고, 검증 창을 그 뒤에 잡아야 한다.
          title       = "파드 수 — 목표(desired)와 준비 완료(ready)"
          title_size  = "16"
          show_legend = true

          request {
            q            = "max:kubernetes_state.deployment.replicas_desired{${local.flow_kube},kube_deployment:api*} by {kube_deployment}"
            display_type = "line"
            style {
              line_type = "dashed"
            }
          }
          request {
            q            = "max:kubernetes_state.deployment.replicas_ready{${local.flow_kube},kube_deployment:api*} by {kube_deployment}"
            display_type = "line"
          }
        }
      }
    }
  }

  widget {
    group_definition {
      title       = "⑤ 검증 — 증설분을 원복한 뒤에도 유지되는가"
      layout_type = "ordered"

      widget {
        note_definition {
          background_color = "yellow"
          font_size        = "13"
          text_align       = "left"
          vertical_align   = "center"
          show_tick        = false

          content = join(" ", [
            "**아래 두 위젯을 겹쳐 읽는다.**",
            "파드 수가 원래대로 돌아온 구간에서도 p95·p99 가 canary 붙이기 전 값을",
            "유지해야 끝이다. 늘린 채로 회복한 것은 격리가 들은 것인지 대수로 덮은",
            "것인지 구분되지 않는다.",
          ])
        }
      }

      widget {
        timeseries_definition {
          title       = "지연 복귀 — canary 붙이기 전 값으로 (ms)"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p95:trace.fastapi.request{${local.flow_api}} * 1000"
            display_type = "line"
          }
          request {
            q            = "p99:trace.fastapi.request{${local.flow_api}} * 1000"
            display_type = "line"
            style {
              palette = "warm"
            }
          }
          marker {
            display_type = "error dashed"
            label        = "이 아래로 내려와야 한다"
            value        = "y = ${var.s2_tail_latency_p99_critical_ms}"
          }
        }
      }

      widget {
        timeseries_definition {
          title       = "증설분이 원복됐는가 — 파드 수"
          title_size  = "16"
          show_legend = true

          request {
            q            = "max:kubernetes_state.deployment.replicas_ready{${local.flow_kube},kube_deployment:api*} by {kube_deployment}"
            display_type = "line"
          }
        }
      }
    }
  }
}

###############################################################################
# S3 — 외부 결제 PG 지연 (1차 실패 → 지식화 → 2차 해결, 채팅 진입)
###############################################################################

resource "datadog_dashboard" "flow_s3" {
  title       = "[O2][S3] 외부 결제 지연 — 에스컬레이션에서 2차 해결까지"
  layout_type = "ordered"
  reflow_type = "auto"

  description = join(" ", [
    "외부 PG 지연으로 주문이 타임아웃되고, 1차는 적용할 Runbook 이 없어",
    "임의 조치 없이 사람에게 넘긴 뒤, 지식화된 2차에서 전환으로 푸는 과정을 본다.",
    "진입이 Datadog 이 아니라 채팅인 유일한 시나리오다.",
  ])

  widget {
    note_definition {
      background_color = "blue"
      font_size        = "14"
      text_align       = "left"
      vertical_align   = "top"
      show_tick        = false

      content = <<-EOT
        **위에서 아래가 시간 순서다.** ① 발생 → ② 감지 → ③ 진단 → ④ 조치 → ⑤ 검증.

        **1차는 조치를 안 하는 것이 성공이다.** 원인을 맞게 진단하고, active Runbook 이
        없으므로 임의 조치 없이 `ESCALATED` 로 사람에게 넘긴다. ④ 에서 **조회는 있는데
        실행이 없는** 모양이 정상이다. 1차가 임의 Failover 로 해결되면 실패다.

        **진입이 채팅이다.** 채팅 경로 8.0~8.7초 대 Datadog 트리거 63.6~68.4초 —
        ② 의 두 위젯을 나란히 두는 이유가 그 시차를 보이기 위해서다.

        **PG 장애는 2차에서도 유지한다.** 자연 회복이 아니라 우회 효과임을 증명해야
        하기 때문이다.

        인시던트 단위에서 `broadcast_id` 를 뺀다 — 외부 의존이라 모든 방송에 동시에
        영향하고, 방송별로 쪼개면 같은 사건이 방송 수만큼 늘어난다.
      EOT
    }
  }

  widget {
    group_definition {
      title       = "① 발생 — 외부 PG 가 느려진다"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # `apps/api/app/services/payment.py` 가 `pg_latency_ms` 를 이 지표로
          # 보낸다. 평시 PG 스텁 지연은 0ms 라 평소엔 바닥에 붙어 있다.
          # 단위는 ms — DogStatsD 로 ms 를 그대로 보내므로 환산하지 않는다.
          title       = "결제 처리 지연 p95 — PG 왕복 (ms)"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p95:o2.app.operation.duration{${local.flow_env},operation:payment.process}"
            display_type = "line"
          }
          marker {
            display_type = "error dashed"
            label        = "감지 임계"
            value        = "y = ${var.s3_pg_latency_p95_critical_ms}"
          }
          marker {
            display_type = "warning dashed"
            label        = "경고"
            value        = "y = ${var.s3_pg_latency_p95_warning_ms}"
          }
        }
      }

      widget {
        timeseries_definition {
          # 지연이 실패로 바뀌는 지점. `pg_timeout` 이 서기 시작하면 사용자는
          # 이미 주문에 실패하고 있다.
          title       = "결제 실패 사유 — pg_timeout 이 서는가"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:o2.app.failure{${local.flow_env},event:payment.process} by {failure_code}.as_count()"
            display_type = "bars"
            style {
              palette = "warm"
            }
          }
        }
      }
    }
  }

  widget {
    group_definition {
      title       = "② 감지 — 채팅이 먼저 운다 (Datadog 보다 빠르다)"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # 사용자 불만이 채팅에 쌓이는 것이 1차 진입이다. 규칙 3·4 —
          # SQS 와 Lambda 에 env 를 붙이면 둘 다 통째로 사라진다.
          title       = "채팅 진입 경로 — 신호 적체와 처리"
          title_size  = "16"
          show_legend = true

          request {
            q            = "max:aws.sqs.approximate_number_of_messages_visible{queuename:o2-dev-chat-signal}"
            display_type = "line"
          }
          request {
            q            = "sum:aws.lambda.invocations{functionname:o2-dev-chat-signal-worker}.as_count()"
            display_type = "bars"
          }
        }
      }

      widget {
        timeseries_definition {
          # 같은 사건을 Datadog 이 언제 알아채는지. 위 위젯과 시차를 비교하는
          # 것이 목적이라 임계선을 같이 그린다. 이쪽은 대조군이지 1차 진입이
          # 아니다.
          title       = "Datadog 보강 경로 — 같은 사건을 언제 아는가"
          title_size  = "16"
          show_legend = true

          request {
            q            = "p95:o2.app.operation.duration{${local.flow_env},operation:payment.process}"
            display_type = "line"
            style {
              palette = "cool"
            }
          }
          marker {
            display_type = "error dashed"
            label        = "Monitor 가 우는 선"
            value        = "y = ${var.s3_pg_latency_p95_critical_ms}"
          }
        }
      }
    }
  }

  widget {
    group_definition {
      title       = "③ 진단 — 우리가 느린가, 외부가 느린가"
      layout_type = "ordered"

      widget {
        timeseries_definition {
          # **이벤트별로 갈라야 원인이 나온다.** PG 장애와 DB 장애는 전체
          # 실패율이 같다. `payment.process` 만 오르고 나머지가 조용하면
          # 외부 의존이다.
          title       = "이벤트별 실패율 — payment 만 오르는가"
          title_size  = "16"
          show_legend = true

          request {
            q            = "avg:o2.warm.failure_rate{${local.flow_env}} by {event}"
            display_type = "line"
          }
        }
      }

      widget {
        timeseries_definition {
          # 실패 사유 코드 전체. `pg_timeout` 한 곳으로 몰려 있다는 것이
          # 외부 PG 원인의 근거다. 다만 이 화면은 "몰려 있다" 까지만 말한다 —
          # 원시 이벤트의 사유 분포는 에이전트가 Athena 로 판다.
          title       = "실패 사유 코드 — 한 곳으로 몰리는가"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:o2.app.failure{${local.flow_env}} by {failure_code}.as_count()"
            display_type = "bars"
          }
        }
      }

      widget {
        timeseries_definition {
          # 결제가 막히면 주문 큐가 밀린다. 사용자 영향의 크기를 보는 축이고,
          # 회복 판정에서도 같이 본다.
          title       = "주문 큐 적체와 대기 시간"
          title_size  = "16"
          show_legend = true

          request {
            q            = "max:aws.sqs.approximate_number_of_messages_visible{queuename:${var.order_confirm_queue_name}}"
            display_type = "line"
          }
          request {
            q            = "max:aws.sqs.approximate_age_of_oldest_message{queuename:${var.order_confirm_queue_name}}"
            display_type = "line"
            style {
              palette = "warm"
            }
          }
          marker {
            display_type = "error dashed"
            label        = "대기 시간 임계(초)"
            value        = "y = ${var.queue_backlog_age_critical_seconds}"
          }
        }
      }

      widget {
        timeseries_definition {
          # 폴백 성공은 '성공' 으로 기록되어 실패율에 안 잡힌다. 이 값만 오르는
          # 구간은 겉으로 멀쩡한데 실제로는 버티고 있는 상태다.
          title       = "폴백 사용률 — 실패율에 안 잡히는 저하"
          title_size  = "16"
          show_legend = true

          request {
            q            = "avg:o2.warm.fallback_rate{${local.flow_env}} by {service}"
            display_type = "line"
          }
        }
      }
    }
  }

  widget {
    group_definition {
      title       = "④ 조치 — 1차는 조회만(ESCALATED), 2차에 실행"
      layout_type = "ordered"

      widget {
        note_definition {
          background_color = "gray"
          font_size        = "13"
          text_align       = "left"
          vertical_align   = "center"
          show_tick        = false

          content = join(" ", [
            "**1차 실행에서는 아래 위젯이 '조회만 있고 실행이 없는' 모양이어야 한다.**",
            "적용할 active Runbook 이 없으므로 임의 조치 없이 사람에게 넘기는 것이",
            "정답이다. 실행 막대가 1차에 서면 그것이 실패다.",
          ])
        }
      }

      widget {
        timeseries_definition {
          # 조회(runbook-lookup)와 실행(scale-executor)과 승인 요청을 한 위젯에
          # 둔다. 셋의 조합으로 어느 단계에서 멈췄는지가 읽힌다.
          title       = "Runbook 조회 · 실행 · 승인 요청"
          title_size  = "16"
          show_legend = true

          request {
            q            = "sum:aws.lambda.invocations{functionname:o2-dev-dify-runbook-lookup}.as_count()"
            display_type = "bars"
          }
          request {
            q            = "sum:aws.lambda.invocations{functionname:o2-dev-dify-scale-executor}.as_count()"
            display_type = "bars"
            style {
              palette = "warm"
            }
          }
          request {
            q            = "sum:aws.lambda.invocations{functionname IN (${local.flow_fn_approval})} by {functionname}.as_count()"
            display_type = "bars"
            style {
              palette = "cool"
            }
          }
        }
      }
    }
  }

  widget {
    group_definition {
      title       = "⑤ 검증 — 우회가 들었는가 (장애는 유지한 채로)"
      layout_type = "ordered"

      widget {
        note_definition {
          background_color = "yellow"
          font_size        = "13"
          text_align       = "left"
          vertical_align   = "center"
          show_tick        = false

          content = join(" ", [
            "**PG 장애를 끄지 않은 상태에서 회복되어야 한다.**",
            "장애를 걷어내고 좋아진 것은 자연 회복이지 우회 효과가 아니다.",
            "① 의 지연 위젯이 여전히 높은 채로 아래 실패율이 내려오는 모양이 성공이다.",
          ])
        }
      }

      widget {
        timeseries_definition {
          # 우회가 들었다면 지연은 남아 있어도 실패는 사라진다. 그 분리가
          # 이 시나리오의 성공 서명이다.
          title       = "결제 실패율 복귀"
          title_size  = "16"
          show_legend = true

          request {
            formula {
              formula_expression = "failed / attempted * 100"
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "failed"
                query       = "sum:o2.app.failure{${local.flow_env},event:payment.process}.as_count()"
              }
            }
            query {
              metric_query {
                data_source = "metrics"
                name        = "attempted"
                query       = "sum:o2.app.business_event{${local.flow_env},event:payment.process}.as_count()"
              }
            }
            display_type = "line"
          }
          marker {
            display_type = "error dashed"
            label        = "실패율 상한"
            value        = "y = ${var.s3_payment_failure_rate_critical * 100}"
          }
        }
      }

      widget {
        timeseries_definition {
          # 사용자 쪽 회복. 큐가 빠지지 않으면 결제가 성공해도 주문은 아직
          # 밀려 있는 것이다.
          title       = "주문 큐 대기 시간 복귀"
          title_size  = "16"
          show_legend = true

          request {
            q            = "max:aws.sqs.approximate_age_of_oldest_message{queuename:${var.order_confirm_queue_name}}"
            display_type = "line"
          }
          marker {
            display_type = "warning dashed"
            label        = "이 아래로 내려와야 한다"
            value        = "y = ${var.queue_backlog_age_warning_seconds}"
          }
        }
      }
    }
  }
}

output "flow_s1_dashboard_url" {
  description = "S1 진행 화면 주소."
  value       = "${local.dd_app_url}/dashboard/${datadog_dashboard.flow_s1.id}"
}

output "flow_s2_dashboard_url" {
  description = "S2 진행 화면 주소."
  value       = "${local.dd_app_url}/dashboard/${datadog_dashboard.flow_s2.id}"
}

output "flow_s3_dashboard_url" {
  description = "S3 진행 화면 주소."
  value       = "${local.dd_app_url}/dashboard/${datadog_dashboard.flow_s3.id}"
}
