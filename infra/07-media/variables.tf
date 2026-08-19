variable "region" {
  description = "CloudFront 배포 자체는 글로벌이지만 프로바이더는 리전이 필요하다"
  type        = string
  default     = "ap-northeast-2"
}

variable "project" {
  type    = string
  default = "o2"
}

variable "team" {
  type    = string
  default = "o2"
}

variable "environment" {
  description = "04-platform 의 environment 와 같아야 한다 (D-034)"
  type        = string
  default     = "dev"
}

variable "origin_domain" {
  description = <<-EOT
    HLS 를 내보내는 오리진. 지금은 프론트와 같은 ALB 다.

    **ALB 를 다시 만들면 이 값이 바뀐다.** `kubectl get ingress frontend -n o2-dev`
    의 hostname 이고, 비워 두면 apply 가 precondition 에서 멈춘다.

    remote state 로 읽지 않는 이유는 ALB 를 Terraform 이 만들지 않기 때문이다.
    AWS Load Balancer Controller 가 Ingress 를 보고 만든다.
  EOT
  type        = string
}

variable "cdn_secret_name" {
  description = <<-EOT
    MediaMTX 의 hlsCDNSecret 이 든 Secrets Manager 시크릿 이름.

    같은 값을 두 곳이 쓴다 — CloudFront 는 오리진 요청에 `Authorization:
    Bearer <값>` 으로 붙이고, MediaMTX 는 그 헤더를 보고 CDN 요청으로 판정한다.
    일치하지 않으면 **재생은 되는데 캐시만 안 먹는다** (D-038).
  EOT
  type        = string
  default     = "o2/dev/media-cdn-secret"
}

variable "price_class" {
  description = <<-EOT
    엣지 로케이션 범위. 시청자가 한국에만 있으므로 가장 좁은 것을 쓴다.

    PriceClass_All 로 넓히면 전 세계 엣지를 쓰는 대신 GB당 요금이 오른다.
    넓힌다고 국내 시청자가 빨라지지 않는다.
  EOT
  type        = string
  default     = "PriceClass_200"
}
