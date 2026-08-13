# Datadog 키의 원본은 AWS Secrets Manager에만 둔다. 이 data source는 SecretString을
# 읽지 않으므로 Terraform state에 API/App Key가 남지 않는다.
data "aws_secretsmanager_secret" "datadog" {
  count = var.enable_datadog ? 1 : 0
  name  = var.datadog_secrets_manager_secret_name
}

# ESO controller만 assume할 수 있는 EKS Pod Identity 역할이다. IRSA와 달리 OIDC
# provider 또는 ServiceAccount annotation에 결합되지 않아 클러스터 재생성이 단순하다.
data "aws_iam_policy_document" "external_secrets_assume" {
  count = var.enable_datadog ? 1 : 0

  statement {
    effect = "Allow"
    actions = [
      "sts:AssumeRole",
      "sts:TagSession",
    ]

    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "external_secrets" {
  count = var.enable_datadog ? 1 : 0

  name               = "${var.project}-${var.environment}-external-secrets"
  assume_role_policy = data.aws_iam_policy_document.external_secrets_assume[0].json
}

data "aws_iam_policy_document" "external_secrets_read_datadog" {
  count = var.enable_datadog ? 1 : 0

  # ESO가 Secrets Manager provider에서 실제 사용하는 읽기 API만 준다.
  statement {
    effect = "Allow"
    actions = [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetResourcePolicy",
      "secretsmanager:GetSecretValue",
      "secretsmanager:ListSecretVersionIds",
    ]
    resources = [data.aws_secretsmanager_secret.datadog[0].arn]
  }
}

resource "aws_iam_role_policy" "external_secrets_read_datadog" {
  count = var.enable_datadog ? 1 : 0

  name   = "read-datadog-secret"
  role   = aws_iam_role.external_secrets[0].id
  policy = data.aws_iam_policy_document.external_secrets_read_datadog[0].json
}

# Pod Identity association은 ServiceAccount/namespace 문자열을 기준으로 동작한다.
# Helm chart가 controller를 띄우기 전에 둘을 명시적으로 만들면, controller Pod가 첫
# 기동부터 임시 IAM 자격증명을 주입받는다.
resource "kubectl_manifest" "external_secrets_namespace" {
  count = var.enable_datadog ? 1 : 0

  yaml_body = yamlencode({
    apiVersion = "v1"
    kind       = "Namespace"
    metadata = {
      name = var.external_secrets_namespace
      labels = {
        "app.kubernetes.io/managed-by" = "terraform"
      }
    }
  })

  depends_on = [aws_eks_access_policy_association.admin]
}

resource "kubectl_manifest" "external_secrets_service_account" {
  count = var.enable_datadog ? 1 : 0

  yaml_body = yamlencode({
    apiVersion = "v1"
    kind       = "ServiceAccount"
    metadata = {
      name      = "external-secrets"
      namespace = var.external_secrets_namespace
    }
  })

  depends_on = [kubectl_manifest.external_secrets_namespace]
}

resource "aws_eks_pod_identity_association" "external_secrets" {
  count = var.enable_datadog ? 1 : 0

  cluster_name    = local.cluster_name
  namespace       = var.external_secrets_namespace
  service_account = "external-secrets"
  role_arn        = aws_iam_role.external_secrets[0].arn

  depends_on = [
    aws_iam_role_policy.external_secrets_read_datadog,
    kubectl_manifest.external_secrets_service_account,
  ]
}

# External Secrets Operator 자체는 일반 Helm release로 설치한다. ServiceAccount와
# Pod Identity association은 위에서 먼저 만들었으므로 controller가 재시작될 필요가 없다.
resource "helm_release" "external_secrets" {
  count = var.enable_datadog ? 1 : 0

  name             = "external-secrets"
  namespace        = var.external_secrets_namespace
  create_namespace = false

  repository = "https://charts.external-secrets.io"
  chart      = "external-secrets"
  version    = var.external_secrets_chart_version

  timeout = 900
  wait    = true

  values = [yamlencode({
    installCRDs = true
    serviceAccount = {
      create = false
      name   = "external-secrets"
    }
    resources = {
      requests = { cpu = "25m", memory = "64Mi" }
      limits   = { memory = "128Mi" }
    }
    webhook = {
      resources = {
        requests = { cpu = "10m", memory = "32Mi" }
        limits   = { memory = "64Mi" }
      }
    }
    certController = {
      resources = {
        requests = { cpu = "10m", memory = "32Mi" }
        limits   = { memory = "64Mi" }
      }
    }
  })]

  depends_on = [aws_eks_pod_identity_association.external_secrets]
}

# Datadog chart가 참조할 namespace는 ESO의 ExternalSecret보다 먼저 만든다.
resource "kubectl_manifest" "datadog_namespace" {
  count = var.enable_datadog ? 1 : 0

  yaml_body = yamlencode({
    apiVersion = "v1"
    kind       = "Namespace"
    metadata = {
      name = var.datadog_namespace
      labels = {
        "app.kubernetes.io/managed-by" = "terraform"
      }
    }
  })

  depends_on = [aws_eks_access_policy_association.admin]
}

# Pod Identity에서는 auth/serviceAccountRef를 적지 않는다. ESO controller 자신의
# Pod Identity credentials를 AWS SDK 기본 credential chain으로 사용한다.
resource "kubectl_manifest" "datadog_secret_store" {
  count = var.enable_datadog ? 1 : 0

  yaml_body = yamlencode({
    apiVersion = "external-secrets.io/v1"
    kind       = "ClusterSecretStore"
    metadata = {
      name = "aws-secrets-manager"
    }
    spec = {
      provider = {
        aws = {
          service = "SecretsManager"
          region  = var.region
        }
      }
    }
  })

  depends_on = [
    helm_release.external_secrets,
    aws_eks_pod_identity_association.external_secrets,
    aws_iam_role_policy.external_secrets_read_datadog,
  ]
}

# Secrets Manager JSON의 두 property만 Datadog이 기대하는 Secret key로 동기화한다.
resource "kubectl_manifest" "datadog_external_secret" {
  count = var.enable_datadog ? 1 : 0

  yaml_body = yamlencode({
    apiVersion = "external-secrets.io/v1"
    kind       = "ExternalSecret"
    metadata = {
      name      = "datadog"
      namespace = var.datadog_namespace
    }
    spec = {
      refreshPolicy   = "Periodic"
      refreshInterval = var.datadog_secret_refresh_interval
      secretStoreRef = {
        name = "aws-secrets-manager"
        kind = "ClusterSecretStore"
      }
      target = {
        name           = var.datadog_kubernetes_secret_name
        creationPolicy = "Owner"
      }
      data = [
        {
          secretKey = "api-key"
          remoteRef = {
            key      = data.aws_secretsmanager_secret.datadog[0].name
            property = "api-key"
          }
        },
        {
          secretKey = "app-key"
          remoteRef = {
            key      = data.aws_secretsmanager_secret.datadog[0].name
            property = "app-key"
          }
        },
      ]
    }
  })

  depends_on = [
    kubectl_manifest.datadog_namespace,
    kubectl_manifest.datadog_secret_store,
  ]
}
