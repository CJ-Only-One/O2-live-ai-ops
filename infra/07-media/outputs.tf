output "distribution_domain" {
  description = "재생 주소의 호스트. HLS_BASE_URL 을 https://<이 값>/hls 로 바꾼다"
  value       = aws_cloudfront_distribution.media.domain_name
}

output "distribution_id" {
  description = "무효화(invalidation) 를 걸 때 쓴다"
  value       = aws_cloudfront_distribution.media.id
}

output "hls_base_url" {
  description = "04-platform 의 hls_base_url 에 그대로 넣을 값"
  value       = "https://${aws_cloudfront_distribution.media.domain_name}/hls"
}
