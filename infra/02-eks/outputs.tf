output "cluster_name" {
  value = aws_eks_cluster.this.name
}

output "cluster_endpoint" {
  value = aws_eks_cluster.this.endpoint
}

output "cluster_version" {
  value = aws_eks_cluster.this.version
}

output "oidc_provider_arn" {
  value = aws_iam_openid_connect_provider.eks.arn
}

output "lbc_role_arn" {
  description = "helm install 시 serviceAccount.annotations 에 넣을 값"
  value       = aws_iam_role.lbc.arn
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "github_actions_role_arn" {
  description = "GitHub Actions 워크플로의 role-to-assume 값. enable_github_oidc=false 이면 null"
  value       = try(aws_iam_role.github_actions[0].arn, null)
}

output "kubeconfig_command" {
  value = "aws eks update-kubeconfig --region ${var.region} --name ${aws_eks_cluster.this.name}"
}

output "lbc_helm_command" {
  description = "복사해서 바로 실행 가능한 LBC 설치 명령"
  value       = <<-EOT
    helm repo add eks https://aws.github.io/eks-charts && helm repo update
    helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller \
      -n kube-system \
      --set clusterName=${aws_eks_cluster.this.name} \
      --set serviceAccount.create=true \
      --set serviceAccount.name=aws-load-balancer-controller \
      --set "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn=${aws_iam_role.lbc.arn}" \
      --set region=${var.region} \
      --set vpcId=${local.vpc_id}
  EOT
}
