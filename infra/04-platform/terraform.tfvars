enable_datadog = true

# chat-gateway 이미지가 Kinesis 전송 코드를 포함해 배포된 뒤에 켠다.
# 먼저 켜도 에러는 안 나지만(구버전은 그냥 stdout으로 감), 배포 순서를
# 맞추는 편이 chat_ingest_surge Monitor의 No Data 구간을 줄인다.
enable_chat_events = true
# 영상 재생 주소. 07-media 의 `terraform output hls_base_url` 값이다.
# CloudFront 를 통해야 캐시가 팬아웃을 흡수한다 (D-039).
hls_base_url = "https://dq8dzhb390eet.cloudfront.net/hls"
datadog_secrets_manager_secret_name = "o2/dev/datadog-new"
datadog_site = "us5.datadoghq.com"
