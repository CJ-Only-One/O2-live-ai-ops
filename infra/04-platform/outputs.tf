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
  description = "UI 접속. 외부 노출은 아직 하지 않았다"
  value       = "kubectl port-forward -n argocd svc/argocd-server 8080:443"
}

output "argocd_initial_password_command" {
  description = "첫 로그인 후 비밀번호를 바꾸고 이 시크릿을 삭제할 것"
  value       = "kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
}
