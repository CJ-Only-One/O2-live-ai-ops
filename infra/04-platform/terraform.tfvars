enable_datadog = true

# chat-gateway 이미지가 Kinesis 전송 코드를 포함해 배포된 뒤에 켠다.
# 먼저 켜도 에러는 안 나지만(구버전은 그냥 stdout으로 감), 배포 순서를
# 맞추는 편이 chat_ingest_surge Monitor의 No Data 구간을 줄인다.
enable_chat_events = true
# 영상 재생 주소. 07-media 의 `terraform output hls_base_url` 값이다.
# CloudFront 를 통해야 캐시가 팬아웃을 흡수한다 (D-039).
hls_base_url                        = "https://dq8dzhb390eet.cloudfront.net/hls"
datadog_secrets_manager_secret_name = "o2/dev/datadog-new"
datadog_site                        = "us5.datadoghq.com"

# 스케일링 부품 (D-037: 필요해질 때 넣는다)
#
# 둘 다 "안전망" 이지 주력이 아니다. 주력은 큐시트 기반 사전 확장이다(D-041).
#   KEDA      2차 보정 — 예상보다 크거나 오래 지속되는 부하
#   Karpenter 4차 최후 — 예상 밖 Pending Pod, 노드 장애
enable_keda      = true
enable_karpenter = true
