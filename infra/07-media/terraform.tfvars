# 이 파일은 커밋된다 (루트 .gitignore 의 `!infra/*/terraform.tfvars`).
# **비밀값이 아니라 비밀값이 있는 곳의 이름만 적는다.**

# HLS 오리진. 프론트와 같은 ALB 다.
# `kubectl get ingress frontend -n o2-dev` 의 hostname 이고,
# ALB 를 다시 만들면 바뀐다.
origin_domain = "k8s-o2dev-frontend-0af27d967f-1008618203.ap-northeast-2.elb.amazonaws.com"

# MediaMTX 의 hlsCDNSecret 이 든 시크릿 이름. 값이 아니라 이름이다.
cdn_secret_name = "o2/dev/media-cdn-secret"

# 지표·태그의 env. 04-platform 과 같아야 한다 (D-034).
environment = "dev"
