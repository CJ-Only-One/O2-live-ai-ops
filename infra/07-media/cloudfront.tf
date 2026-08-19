# 영상 배포용 CloudFront.
#
# **왜 필요한가.** MediaMTX 는 파드 1개다. 40,000 × 2 Mbps = 80 Gbps 는 파드
# 하나가 낼 수 있는 양이 아니다. 세그먼트는 파일이므로 엣지가 팬아웃을
# 흡수하고 오리진은 세그먼트당 1회만 맞는다 (architecture.md 2.2).
#
# **/hls 만 통과시킨다.** 프론트·API·WebSocket 은 지금처럼 ALB 로 직접 간다.
# 전부 CloudFront 뒤로 넣으면 캐시하면 안 되는 경로를 하나씩 예외 처리해야
# 하고, 그 목록이 틀리면 API 응답이 캐시되어 남의 주문이 보인다.

locals {
  origin_id = "alb-hls"
}

# CDN 비밀값. 원본은 Secrets Manager 에만 있고 여기서는 값을 읽어 쓴다.
#
# 이 스택은 값을 state 에 남긴다 — CloudFront 의 오리진 커스텀 헤더가
# 평문 문자열이라 다른 방법이 없다. 그래서 이 시크릿은 다른 용도와 공유하지
# 않고 CDN 전용으로 둔다.
data "aws_secretsmanager_secret_version" "cdn" {
  secret_id = var.cdn_secret_name
}

# ── 캐시 정책 ─────────────────────────────────────────────────
# 플레이리스트와 세그먼트는 수명이 정반대라 정책을 나눈다.

# .m3u8 — 2초마다 내용이 바뀐다. 세그먼트 길이보다 짧게 잡아야 재생이 끊기지
# 않는다. 그렇다고 캐시를 끄면 방송 시작 30초에 오리진이 그대로 맞는다.
resource "aws_cloudfront_cache_policy" "playlist" {
  name        = "${var.project}-${var.environment}-hls-playlist"
  comment     = "HLS 플레이리스트. 세그먼트 길이보다 짧은 TTL"
  min_ttl     = 0
  default_ttl = 1
  max_ttl     = 2

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_gzip = true

    # ★ 쿼리스트링을 캐시 키에서 뺀다. MediaMTX 가 시청자별 세션 ID 를 붙이면
    #   캐시가 시청자 수만큼 갈린다. hlsCDNSecret 이 그것을 막지만, 설정이
    #   빠졌을 때 조용히 비싸지는 것보다 여기서도 막아두는 편이 낫다 (D-038).
    query_strings_config {
      query_string_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    cookies_config {
      cookie_behavior = "none"
    }
  }
}

# .ts — 파일명이 콘텐츠 해시라 내용이 바뀌면 이름이 바뀐다. 무효화가 필요 없고
# 오래 잡을수록 오리진이 편하다.
resource "aws_cloudfront_cache_policy" "segment" {
  name        = "${var.project}-${var.environment}-hls-segment"
  comment     = "HLS 세그먼트. 파일명이 곧 콘텐츠 식별자라 길게 잡는다"
  min_ttl     = 86400
  default_ttl = 31536000
  max_ttl     = 31536000

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_gzip = false # 이미 압축된 미디어다

    query_strings_config {
      query_string_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    cookies_config {
      cookie_behavior = "none"
    }
  }
}

resource "aws_cloudfront_distribution" "media" {
  enabled = true
  comment = "${var.project}-${var.environment} HLS"

  # 한국 시청자만 본다. 넓혀도 빨라지지 않고 GB당 요금만 오른다.
  price_class = var.price_class

  origin {
    domain_name = var.origin_domain
    origin_id   = local.origin_id

    custom_origin_config {
      http_port  = 80
      https_port = 443
      # ALB 에 인증서가 없어 HTTP 로만 간다. 도메인과 ACM 인증서가 생기면
      # https-only 로 바꾼다.
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }

    # ★ 이 헤더가 캐싱의 전제다. MediaMTX 는 이것을 보고 CDN 요청으로 판정해
    #   시청자별 세션 ID 를 붙이지 않는다. 값이 어긋나면 재생은 되는데
    #   캐시만 안 먹어서, 조용히 비싸지고 조용히 느려진다 (D-038).
    custom_header {
      name  = "Authorization"
      value = "Bearer ${data.aws_secretsmanager_secret_version.cdn.secret_string}"
    }
  }

  # 기본 동작. 아래 ordered_cache_behavior 에 안 걸리는 것은 여기로 온다.
  # /hls 외에는 이 배포로 보내지 않을 것이므로 플레이리스트 정책을 쓴다.
  default_cache_behavior {
    target_origin_id       = local.origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = aws_cloudfront_cache_policy.playlist.id
    compress               = true
  }

  # 세그먼트만 길게 잡는다. 확장자로 가른다 — MediaMTX 의 mpegts 변형은
  # .ts 를 낸다 (mediamtx-config.yaml 의 hlsVariant).
  ordered_cache_behavior {
    path_pattern           = "*.ts"
    target_origin_id       = local.origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = aws_cloudfront_cache_policy.segment.id
    compress               = false
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    # 도메인이 없어 CloudFront 기본 인증서를 쓴다. *.cloudfront.net 으로 붙는다.
    cloudfront_default_certificate = true
  }

  lifecycle {
    precondition {
      condition     = var.origin_domain != ""
      error_message = "origin_domain 이 비어 있다. `kubectl get ingress frontend -n o2-dev` 의 hostname 을 terraform.tfvars 에 넣을 것."
    }
  }
}
