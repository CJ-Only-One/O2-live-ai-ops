data "aws_iam_policy_document" "node_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "node" {
  name               = "${var.cluster_name}-node-role"
  assume_role_policy = data.aws_iam_policy_document.node_assume.json
}

resource "aws_iam_role_policy_attachment" "node" {
  for_each = toset([
    "AmazonEKSWorkerNodePolicy",
    "AmazonEKS_CNI_Policy",               # Phase 2에서 IRSA로 분리 권장 (노드 전체 권한 축소)
    "AmazonEC2ContainerRegistryPullOnly", # ReadOnly보다 좁다. 노드는 pull만 하면 된다
    "AmazonSSMManagedInstanceCore",       # SSH 키/Bastion 없이 Session Manager로 노드 진입
  ])

  role       = aws_iam_role.node.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/${each.key}"
}

resource "aws_eks_node_group" "default" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "default"
  node_role_arn   = aws_iam_role.node.arn
  subnet_ids      = local.private_subnet_ids

  instance_types = var.node_instance_types
  capacity_type  = var.node_capacity_type
  disk_size      = var.node_disk_size

  # AL2는 1.32가 마지막이다. 1.33+ 는 AL2023 또는 Bottlerocket만 제공된다.
  ami_type = "AL2023_x86_64_STANDARD"

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }

  update_config {
    max_unavailable = 1
  }

  labels = {
    role = "general"
  }

  lifecycle {
    # Cluster Autoscaler / Karpenter가 desired_size를 바꾼 뒤
    # terraform apply가 다시 되돌리는 충돌을 막는다.
    ignore_changes = [scaling_config[0].desired_size]
  }

  depends_on = [aws_iam_role_policy_attachment.node]

  tags = {
    Name = "${var.cluster_name}-ng-default"
  }
}
