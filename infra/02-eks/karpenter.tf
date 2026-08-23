# Karpenter — 노드 자동 확장의 IAM·SQS 쪽.
#
# 역할 분담은 LBC(`lbc_irsa.tf`)와 같다. 여기서 IAM 만 만들고 Helm 설치는
# `04-platform` 이 한다. 클러스터를 만드는 apply 와 클러스터 안을 채우는 apply 를
# 한 스택에 둘 수 없기 때문이다(`04-platform/main.tf` 주석).
#
# **이것은 4차 안전망이지 주력이 아니다.** architecture.md 9.1 의 계산대로 노드
# 확보에 최소 26초(2026-08-21 실측) + 이미지 pull + 기동이 걸리는데, 방송 시작
# 스파이크는 30초 안에 끝난다. 주력은 큐시트 기반 사전 확장이고(D-041) Karpenter 는
# **예상 밖 Pending Pod 와 노드 장애**를 받는다.
#
# 관리형 노드그룹을 없애지 않는다. Karpenter 자신이 돌 자리가 필요하고, 자기가
# 만든 노드 위에서 돌면 그 노드를 정리하면서 자살한다.

###############################################################################
# 노드가 쓰는 보안그룹에 discovery 태그를 붙인다.
#
# 서브넷 태그는 `01-network/subnets.tf` 가 이미 붙여 두었다. 보안그룹은 EKS 가
# 자동 생성한 클러스터 SG 하나를 노드가 그대로 쓰고 있어서 여기서 태그한다.
# **콘솔에서 손으로 붙이지 않는다** — 다음 apply 에 사라진다.
###############################################################################

resource "aws_ec2_tag" "cluster_sg_karpenter" {
  count = var.enable_karpenter ? 1 : 0

  resource_id = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  key         = "karpenter.sh/discovery"
  value       = var.cluster_name
}

###############################################################################
# 컨트롤러 역할 (IRSA)
###############################################################################

data "aws_iam_policy_document" "karpenter_assume" {
  count = var.enable_karpenter ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.eks.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:sub"
      values   = ["system:serviceaccount:kube-system:karpenter"]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "karpenter" {
  count = var.enable_karpenter ? 1 : 0

  name               = "${var.cluster_name}-karpenter-role"
  assume_role_policy = data.aws_iam_policy_document.karpenter_assume[0].json
}

data "aws_iam_policy_document" "karpenter" {
  count = var.enable_karpenter ? 1 : 0

  # 인스턴스 타입·가격·AMI 조회. 읽기라 리소스를 좁힐 수 없다.
  statement {
    sid    = "Read"
    effect = "Allow"
    actions = [
      "ec2:DescribeInstances",
      "ec2:DescribeInstanceTypes",
      "ec2:DescribeInstanceTypeOfferings",
      "ec2:DescribeImages",
      "ec2:DescribeLaunchTemplates",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeSubnets",
      "ec2:DescribeSpotPriceHistory",
      "ec2:DescribeAvailabilityZones",
      "pricing:GetProducts",
      "ssm:GetParameter", # AMI ID 를 SSM 파라미터로 찾는다
    ]
    resources = ["*"]
  }

  # 노드 생성. 태그 조건으로 **이 클러스터 것만** 만들 수 있게 좁힌다.
  statement {
    sid    = "CreateNodes"
    effect = "Allow"
    actions = [
      "ec2:CreateFleet",
      "ec2:CreateLaunchTemplate",
      "ec2:RunInstances",
      "ec2:CreateTags",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/kubernetes.io/cluster/${var.cluster_name}"
      values   = ["owned"]
    }
  }

  # 서브넷·SG·AMI·런치템플릿은 만드는 게 아니라 참조만 하므로 위 태그 조건이
  # 걸리지 않는다. 별도 statement 로 둔다.
  statement {
    sid    = "RunInstancesResources"
    effect = "Allow"
    actions = [
      "ec2:RunInstances",
      "ec2:CreateFleet",
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:ec2:${data.aws_region.current.region}::image/*",
      "arn:${data.aws_partition.current.partition}:ec2:${data.aws_region.current.region}:*:snapshot/*",
      "arn:${data.aws_partition.current.partition}:ec2:${data.aws_region.current.region}:*:subnet/*",
      "arn:${data.aws_partition.current.partition}:ec2:${data.aws_region.current.region}:*:security-group/*",
      "arn:${data.aws_partition.current.partition}:ec2:${data.aws_region.current.region}:*:launch-template/*",
    ]
  }

  # 노드 종료·정리. 자기가 만든 것만 건드리도록 태그로 좁힌다.
  # 이 조건이 없으면 **관리형 노드그룹의 노드까지 종료할 수 있다.**
  statement {
    sid    = "TerminateNodes"
    effect = "Allow"
    actions = [
      "ec2:TerminateInstances",
      "ec2:DeleteLaunchTemplate",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "ec2:ResourceTag/kubernetes.io/cluster/${var.cluster_name}"
      values   = ["owned"]
    }
  }

  # 노드에 붙일 역할을 인스턴스 프로파일에 넘긴다. 넘길 수 있는 역할을
  # 노드 역할 하나로 못 박는다 — 넓히면 임의 역할을 단 노드를 띄울 수 있다.
  statement {
    sid       = "PassNodeRole"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.node.arn]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ec2.amazonaws.com"]
    }
  }

  # Karpenter 1.x 는 인스턴스 프로파일을 스스로 만들고 지운다.
  #
  # `ListInstanceProfiles` 는 고아 프로파일을 청소하는 컨트롤러
  # (`instanceprofile.garbagecollection`)가 쓴다. 빠뜨리면 노드 생성은 되는데
  # 그 컨트롤러가 초당 여러 번 403 을 내며 로그를 채운다.
  # 목록 조회라 리소스를 좁힐 수 없다.
  statement {
    sid    = "InstanceProfile"
    effect = "Allow"
    actions = [
      "iam:CreateInstanceProfile",
      "iam:DeleteInstanceProfile",
      "iam:GetInstanceProfile",
      "iam:ListInstanceProfiles",
      "iam:TagInstanceProfile",
      "iam:AddRoleToInstanceProfile",
      "iam:RemoveRoleFromInstanceProfile",
    ]
    resources = ["*"]
  }

  # 클러스터 정보 조회 (엔드포인트 등).
  statement {
    sid       = "DescribeCluster"
    effect    = "Allow"
    actions   = ["eks:DescribeCluster"]
    resources = [aws_eks_cluster.this.arn]
  }

  # 중단 알림 큐. 스팟 회수·인스턴스 상태 변경을 미리 받아 파드를 빼낸다.
  statement {
    sid    = "InterruptionQueue"
    effect = "Allow"
    actions = [
      "sqs:DeleteMessage",
      "sqs:GetQueueUrl",
      "sqs:ReceiveMessage",
    ]
    resources = [aws_sqs_queue.karpenter_interruption[0].arn]
  }
}

resource "aws_iam_policy" "karpenter" {
  count = var.enable_karpenter ? 1 : 0

  name        = "${var.cluster_name}-karpenter-policy"
  description = "Karpenter controller"
  policy      = data.aws_iam_policy_document.karpenter[0].json
}

resource "aws_iam_role_policy_attachment" "karpenter" {
  count = var.enable_karpenter ? 1 : 0

  role       = aws_iam_role.karpenter[0].name
  policy_arn = aws_iam_policy.karpenter[0].arn
}

###############################################################################
# 중단 알림 큐
#
# 없어도 Karpenter 는 돈다. 다만 스팟 회수 통보(2분)를 못 받아 파드가 갑자기
# 사라진다. 온디맨드만 쓰더라도 인스턴스 상태 변경·헬스 이벤트는 유용하므로
# 같이 만든다 — SQS 비용은 사실상 0 이다.
###############################################################################

resource "aws_sqs_queue" "karpenter_interruption" {
  count = var.enable_karpenter ? 1 : 0

  name = "${var.cluster_name}-karpenter-interruption"

  # 통보는 수명이 짧다. 오래 남겨도 쓸모가 없다.
  message_retention_seconds = 300
  sqs_managed_sse_enabled   = true
}

data "aws_iam_policy_document" "karpenter_queue" {
  count = var.enable_karpenter ? 1 : 0

  statement {
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.karpenter_interruption[0].arn]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com", "sqs.amazonaws.com"]
    }
  }
}

resource "aws_sqs_queue_policy" "karpenter_interruption" {
  count = var.enable_karpenter ? 1 : 0

  queue_url = aws_sqs_queue.karpenter_interruption[0].url
  policy    = data.aws_iam_policy_document.karpenter_queue[0].json
}

# EventBridge 규칙 넷. 각각이 다른 종류의 "이 노드가 곧 사라진다" 신호다.
locals {
  karpenter_events = {
    spot_interruption = {
      source      = "aws.ec2"
      detail_type = "EC2 Spot Instance Interruption Warning"
    }
    rebalance = {
      source      = "aws.ec2"
      detail_type = "EC2 Instance Rebalance Recommendation"
    }
    instance_state = {
      source      = "aws.ec2"
      detail_type = "EC2 Instance State-change Notification"
    }
    health = {
      source      = "aws.health"
      detail_type = "AWS Health Event"
    }
  }
}

resource "aws_cloudwatch_event_rule" "karpenter" {
  for_each = var.enable_karpenter ? local.karpenter_events : {}

  name        = "${var.cluster_name}-karpenter-${each.key}"
  description = "Karpenter interruption: ${each.value.detail_type}"

  event_pattern = jsonencode({
    source        = [each.value.source]
    "detail-type" = [each.value.detail_type]
  })
}

resource "aws_cloudwatch_event_target" "karpenter" {
  for_each = var.enable_karpenter ? local.karpenter_events : {}

  rule = aws_cloudwatch_event_rule.karpenter[each.key].name
  arn  = aws_sqs_queue.karpenter_interruption[0].arn
}
