# 애플리케이션이 데이터 계층에 닿기 위한 배선.
#
# 03-data 가 RDS·Valkey·SQS 를 만들었지만 그 주소는 terraform output 에만 있었다.
# 파드 입장에서는 존재하지 않는 것과 같아서, 배포된 API 는 config.py 의 기본값
# (localhost:3306)을 보고 있었다.
#
# 왜 여기(04-platform)인가:
#   - 03-data 에는 aws 프로바이더만 있다. 클러스터 안에 무언가 만들 수 없다.
#   - 매니페스트 저장소(O2-live-deploy)에 넣으면 엔드포인트를 손으로 적게 되고,
#     데이터 스택을 다시 만들면 조용히 어긋난다.
#   - 이 스택은 이미 "클러스터 안의 구성을 코드로" 를 맡고 있다 (D-008).
#
# 엔드포인트는 03-data 의 remote state 에서 읽으므로, 데이터 스택을 재생성하면
# 여기를 apply 하는 것만으로 따라간다.

data "terraform_remote_state" "datastore" {
  count = var.enable_app_data_wiring ? 1 : 0

  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = var.datastore_state_key
    region = var.region
  }
}

locals {
  datastore = try(data.terraform_remote_state.datastore[0].outputs, null)
}

# ── 접속 정보 (비밀 아님) ─────────────────────────────────────
# 파드는 envFrom 으로 통째로 받는다. 키 이름은 apps/api 의 config.py 가
# 기대하는 것과 맞춘다.
resource "kubectl_manifest" "app_data_config" {
  count = var.enable_app_data_wiring ? 1 : 0

  yaml_body = yamlencode({
    apiVersion = "v1"
    kind       = "ConfigMap"
    metadata = {
      name      = "o2-data"
      namespace = var.app_namespace
      labels = {
        "app.kubernetes.io/managed-by" = "terraform"
      }
    }
    data = {
      DB_HOST = local.datastore.db_writer_endpoint

      # 리플리카가 없으면 writer 와 같은 값이 온다.
      # 애플리케이션은 처음부터 두 값을 나눠 쓰고, 리플리카를 켜는 것만으로
      # 읽기가 분산되게 한다 (설계 문서 4.2).
      DB_READER_HOST = local.datastore.db_reader_endpoint

      DB_PORT = tostring(local.datastore.db_port)
      DB_NAME = local.datastore.db_name

      # 마스터 사용자 이름은 비밀이 아니다. 비밀번호만 ExternalSecret 으로 온다.
      DB_USER = "o2admin"

      VALKEY_HOST        = local.datastore.valkey_primary_endpoint
      VALKEY_READER_HOST = local.datastore.valkey_reader_endpoint
      VALKEY_PORT        = tostring(local.datastore.valkey_port)

      # ★ transit 암호화가 켜져 있어 클라이언트가 평문으로 붙으면 연결이 끊긴다.
      #   redis-py: Redis(..., ssl=True) / ioredis: new Redis({ tls: {} })
      VALKEY_TLS = tostring(local.datastore.valkey_tls_required)

      SQS_ORDER_QUEUE_URL = local.datastore.order_queue_url
    }
  })
}

# 잘못 조합하면 파드가 기동조차 못 한다. plan 단계에서 먼저 막는다.
#
# ESO 없이 배선만 켜면 Secret o2-db 가 만들어지지 않고, 파드는 그것을
# envFrom 으로 참조하므로 CreateContainerConfigError 로 죽는다.
# apply 가 성공한 뒤 파드에서만 드러나는 실패라 원인 추적이 오래 걸린다.
resource "terraform_data" "require_external_secrets" {
  count = var.enable_app_data_wiring ? 1 : 0

  lifecycle {
    precondition {
      condition     = var.enable_external_secrets
      error_message = "enable_app_data_wiring = true 이면 enable_external_secrets 도 true 여야 한다. ESO 가 없으면 Secret o2-db 가 생성되지 않아 파드가 기동하지 못한다."
    }
  }
}

# ── DB 비밀번호 ───────────────────────────────────────────────
# 원본은 RDS 가 만들어 Secrets Manager 에 넣은 시크릿이다
# (03-data 의 manage_master_user_password). Terraform state 에는 ARN 만 있다.
resource "kubectl_manifest" "app_db_secret" {
  count = var.enable_app_data_wiring ? 1 : 0

  yaml_body = yamlencode({
    apiVersion = "external-secrets.io/v1"
    kind       = "ExternalSecret"
    metadata = {
      name      = "o2-db"
      namespace = var.app_namespace
    }
    spec = {
      refreshPolicy   = "Periodic"
      refreshInterval = "1h"
      secretStoreRef = {
        name = "aws-secrets-manager"
        kind = "ClusterSecretStore"
      }
      target = {
        name           = "o2-db"
        creationPolicy = "Owner"
      }
      data = [
        {
          secretKey = "DB_PASSWORD"
          remoteRef = {
            # RDS 관리형 시크릿은 {"username":..., "password":...} JSON 이다.
            key      = local.datastore.db_master_secret_arn
            property = "password"
          }
        },
      ]
    }
  })

  depends_on = [
    kubectl_manifest.aws_secret_store,
    # 권한이 먼저 붙어야 첫 동기화가 성공한다. 없으면 SecretSyncedError 로 시작해
    # 다음 refresh(1시간)까지 Secret 이 없는 상태가 이어진다.
    aws_iam_role_policy.external_secrets_read_db,
  ]
}

# ESO 역할은 시크릿 ARN 단위로 좁혀져 있다 (external_secrets.tf).
# 리소스를 좁게 잡은 것 자체는 맞지만, 시크릿을 하나 늘릴 때마다 여기도 함께
# 늘려야 한다. 안 늘리면 ExternalSecret 이 SecretSyncedError 로 멈추고
# Secret 이 아예 생성되지 않는다 — 파드는 그것을 envFrom 으로 참조하므로
# CreateContainerConfigError 로 기동조차 못 한다.
#
# 정책을 별도 리소스로 두는 이유는 external_secrets.tf 를 건드리지 않기 위해서다.
# 한 역할에 인라인 정책 여러 개를 붙일 수 있다.
data "aws_iam_policy_document" "external_secrets_read_db" {
  count = var.enable_app_data_wiring && var.enable_external_secrets ? 1 : 0

  statement {
    effect = "Allow"
    actions = [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetResourcePolicy",
      "secretsmanager:GetSecretValue",
      "secretsmanager:ListSecretVersionIds",
    ]
    # RDS 가 만들어 관리하는 마스터 비밀번호 시크릿 (rds!db-... 형식).
    resources = [local.datastore.db_master_secret_arn]
  }
}

resource "aws_iam_role_policy" "external_secrets_read_db" {
  count = var.enable_app_data_wiring && var.enable_external_secrets ? 1 : 0

  name   = "read-db-master-secret"
  role   = aws_iam_role.external_secrets[0].id
  policy = data.aws_iam_policy_document.external_secrets_read_db[0].json
}

# ── SQS 접근 권한 ─────────────────────────────────────────────
# API 파드가 주문 메시지를 넣고, 워커가 꺼낸다.
# IRSA 가 아니라 Pod Identity 를 쓴다 — ESO 와 같은 방식이고,
# ServiceAccount 애노테이션이나 OIDC 결합이 없어 클러스터 재생성이 단순하다.

data "aws_iam_policy_document" "app_assume" {
  count = var.enable_app_data_wiring ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole", "sts:TagSession"]

    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app" {
  count = var.enable_app_data_wiring ? 1 : 0

  name               = "${var.project}-${var.environment}-app"
  assume_role_policy = data.aws_iam_policy_document.app_assume[0].json
}

data "aws_iam_policy_document" "app_sqs" {
  count = var.enable_app_data_wiring ? 1 : 0

  # 큐 하나로 리소스를 좁힌다. 계정의 모든 큐에 대한 권한을 주면
  # 백데이터 파트의 큐까지 닿는다.
  statement {
    effect = "Allow"
    actions = [
      "sqs:SendMessage",
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
    ]
    resources = [local.datastore.order_queue_arn]
  }
}

resource "aws_iam_role_policy" "app_sqs" {
  count = var.enable_app_data_wiring ? 1 : 0

  name   = "order-queue"
  role   = aws_iam_role.app[0].id
  policy = data.aws_iam_policy_document.app_sqs[0].json
}

# ServiceAccount 를 여기서 만드는 이유:
# Pod Identity association 은 namespace + serviceAccount 이름 문자열로 건다.
# 매니페스트 저장소에 두면 Argo 가 만들기 전까지 association 대상이 없는 상태가
# 되어, 첫 배포에서 파드가 자격증명 없이 뜬다.
resource "kubectl_manifest" "app_service_account" {
  for_each = var.enable_app_data_wiring ? toset(var.app_service_accounts) : toset([])

  yaml_body = yamlencode({
    apiVersion = "v1"
    kind       = "ServiceAccount"
    metadata = {
      name      = each.value
      namespace = var.app_namespace
      labels = {
        "app.kubernetes.io/managed-by" = "terraform"
      }
    }
  })
}

resource "aws_eks_pod_identity_association" "app" {
  for_each = var.enable_app_data_wiring ? toset(var.app_service_accounts) : toset([])

  cluster_name    = local.cluster_name
  namespace       = var.app_namespace
  service_account = each.value
  role_arn        = aws_iam_role.app[0].arn

  depends_on = [
    aws_iam_role_policy.app_sqs,
    kubectl_manifest.app_service_account,
  ]
}
