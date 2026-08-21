"""o2hot — Hot Path 역쿼리 게이트웨이.

Hot(이 패키지) / Warm(o2warm) / Cold(S3+Athena) 중 첫 번째를 담당합니다.

    Dify (@webhook-dify 알림 수신) ─▶ Lambda o2-hot-api ─▶ Datadog v1 /query

Warm 은 Kinesis 이벤트를 사전 집계해 1~2ms 로 응답하지만 인프라/APM
시계열은 갖고 있지 않습니다. Agent 가 "지금 CPU/latency 가 얼마인가"를
물으면 이 패키지가 Datadog REST API 를 직접 역쿼리합니다.

docs/DatadogMcpQueryInstruction.md 의 구현안 A(HTTP REST API Gateway)를
따릅니다 — 구현안 B(EC2 상시 MCP 데몬)는 그 문서가 이미 "로컬 개발용"으로
분류했으므로 채택하지 않았습니다.
"""
