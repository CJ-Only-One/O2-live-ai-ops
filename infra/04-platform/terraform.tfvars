enable_datadog = true

# 영상 재생 주소. 07-media 의 `terraform output hls_base_url` 값이다.
# CloudFront 를 통해야 캐시가 팬아웃을 흡수한다 (D-039).
hls_base_url = "https://dq8dzhb390eet.cloudfront.net/hls"
