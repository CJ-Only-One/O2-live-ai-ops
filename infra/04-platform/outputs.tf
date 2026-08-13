output "argocd_namespace" {
  value = helm_release.argocd.namespace
}

output "argocd_chart_version" {
  value = "${helm_release.argocd.chart} ${helm_release.argocd.version}"
}

# 사람이 클러스터를 들여다볼 때만 필요하다.
# 파이프라인(Terraform, Argo, GitHub Actions)은 kubeconfig를 쓰지 않는다.
output "kubeconfig_command" {
  value = "aws eks update-kubeconfig --region ${var.region} --name ${local.cluster_name}"
}

output "argocd_ui_command" {
  description = <<-EOT
    UI 접속. 외부 노출은 아직 하지 않았다.
    server.insecure 로 설치해 서버가 평문으로 서빙하므로 http 로 붙어야 한다.
    443 포트로 포워딩하고 https 로 접속하면 TLS 핸드셰이크가 깨져 연결이 끊긴다.
  EOT
  value       = "kubectl port-forward -n argocd svc/argocd-server 8080:80   # → http://localhost:8080"
}

output "argocd_initial_password_command" {
  description = <<-EOT
    Argo CD는 설치할 때마다 랜덤 비밀번호를 새로 만든다.
    클러스터를 자주 다시 만드는 지금 방식에서는 사실상 매번 로테이션되므로,
    사람이 정한 값으로 바꾸지 않고 그때그때 조회해서 쓴다.
    따라서 argocd-initial-admin-secret 은 삭제하지 않는다.
    5명이 admin 하나를 공유하는 구조이므로, 실사용자를 받기 전에는
    enable_dex 를 켜고 GitHub SSO로 옮길 것.
  EOT
  value       = "kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
}
