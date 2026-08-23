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

output "karpenter_role_arn" {
  description = "Karpenter 컨트롤러 IRSA 역할. 04-platform 이 ServiceAccount 에 붙인다."
  value       = try(aws_iam_role.karpenter[0].arn, null)
}

output "karpenter_node_role_name" {
  description = <<-EOT
    Karpenter 가 띄운 노드가 쓸 역할 이름. EC2NodeClass 의 `role` 에 넣는다.

    관리형 노드그룹과 같은 역할을 재사용한다 — 이미 EKS 접근 항목에 등록돼 있어
    새 노드가 바로 조인한다. 따로 만들면 access entry 등록을 잊고 노드가
    NotReady 로 남는다.
  EOT
  value       = aws_iam_role.node.name
}

output "karpenter_interruption_queue" {
  description = "중단 알림 큐 이름. Helm 값 settings.interruptionQueue 에 넣는다."
  value       = try(aws_sqs_queue.karpenter_interruption[0].name, null)
}
