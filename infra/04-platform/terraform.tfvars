enable_datadog = true

# chat-gateway 이미지가 Kinesis 전송 코드를 포함해 배포된 뒤에 켠다.
# 먼저 켜도 에러는 안 나지만(구버전은 그냥 stdout으로 감), 배포 순서를
# 맞추는 편이 chat_ingest_surge Monitor의 No Data 구간을 줄인다.
enable_chat_events = true
