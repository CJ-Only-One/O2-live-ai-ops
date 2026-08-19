# 이벤트 발행 배선 — 파드가 Kinesis 로 이벤트를 낼 수 있게 한다.
#
# 이벤트 SDK(o2events)는 O2_EVENTS_SINK 하나로 목적지를 고른다. 기본값이 stdout
# 이라 배선이 없으면 이벤트가 파드 로그로 나갔다가 로테이션과 함께 사라진다.
# Datadog 로그 수집도 꺼져 있으므로(datadog.tf) 어디에도 남지 않는다.
#
# 스트림 자체는 여기서 만들지 않는다. stream-business / stream-client 는 백데이터
# 파트가 소유하고, 우리는 생산자로서 쓰기 권한만 받는다. 이름은 SDK 기본값과
# 이미 같아서 O2_STREAM_* 을 주입할 필요가 없다.

# ── 쓰기 권한 ─────────────────────────────────────────────────
# 이름으로 조회한다. ARN 을 박으면 계정이 바뀔 때 조용히 틀린 곳을 가리킨다.
data "aws_kinesis_stream" "business" {
  count = var.enable_app_events ? 1 : 0
  name  = var.events_stream_business
}

data "aws_kinesis_stream" "client" {
  count = var.enable_app_events ? 1 : 0
  name  = var.events_stream_client
}

data "aws_iam_policy_document" "app_kinesis" {
  count = var.enable_app_events ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["kinesis:PutRecord", "kinesis:PutRecords"]

    # 지금 우리가 내는 이벤트(coupon.issue·order.create·inventory.check·
    # order.cancel)는 전부 business 로 간다. client 까지 함께 주는 이유는
    # SDK 의 _stream_for() 가 client.* / live.* 를 client 스트림으로 보내는데,
    # sink 가 전송 예외를 삼키도록 되어 있기 때문이다 — 권한이 없으면 이벤트가
    # 사라진 줄도 모른 채 사라진다. 두 스트림 모두 우리는 생산자일 뿐이다.
    resources = [
      data.aws_kinesis_stream.business[0].arn,
      data.aws_kinesis_stream.client[0].arn,
    ]
  }
}

resource "aws_iam_role_policy" "app_kinesis" {
  count = var.enable_app_events ? 1 : 0

  name   = "event-streams"
  role   = aws_iam_role.app[0].id
  policy = data.aws_iam_policy_document.app_kinesis[0].json

  # 역할 자체는 app_data_access.tf 가 만든다. 그쪽이 꺼져 있으면 붙일 대상이
  # 없다. 여기서 막지 않으면 인덱스 오류로 깨지고 원인이 안 보인다.
  lifecycle {
    precondition {
      condition     = var.enable_app_data_wiring
      error_message = "enable_app_events = true 이면 enable_app_data_wiring 도 true 여야 한다. 파드 역할(aws_iam_role.app)이 그쪽에서 만들어진다."
    }
  }
}

# ── 해싱 salt ─────────────────────────────────────────────────
# SDK 는 user_key 를 그대로 싣지 않고 HMAC 으로 바꿔 담는다. 그 salt 다.
#
# 원본을 Secrets Manager 에만 두는 이유는 Datadog 키와 같다 — 이 data source 는
# SecretString 을 읽지 않으므로 Terraform state 에 값이 남지 않는다.
#
# 값이 바뀌면 같은 사용자가 다른 user_key 로 보이고 과거 이벤트와의 조인이
# 끊긴다. 한 번 정하면 바꾸지 않는다. 세 서비스가 같은 값을 봐야 하므로
# ConfigMap 이 아니라 Secret 으로 세 파드에 모두 넣는다.
data "aws_secretsmanager_secret" "events_salt" {
  count = var.enable_app_events ? 1 : 0
  name  = var.events_salt_secret_name
}

data "aws_iam_policy_document" "external_secrets_read_events_salt" {
  count = var.enable_app_events && var.enable_external_secrets ? 1 : 0

  statement {
    effect = "Allow"
    actions = [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetResourcePolicy",
      "secretsmanager:GetSecretValue",
      "secretsmanager:ListSecretVersionIds",
    ]
    resources = [data.aws_secretsmanager_secret.events_salt[0].arn]
  }
}

# ESO 역할은 시크릿 ARN 단위로 좁혀져 있다. 시크릿을 늘릴 때 이 정책을 같이
# 늘리지 않으면 ExternalSecret 이 SecretSyncedError 로 멈추고, Secret 이 없는
# 채로 파드가 envFrom 하여 CreateContainerConfigError 로 기동조차 못 한다.
resource "aws_iam_role_policy" "external_secrets_read_events_salt" {
  count = var.enable_app_events && var.enable_external_secrets ? 1 : 0

  name   = "read-events-salt"
  role   = aws_iam_role.external_secrets[0].id
  policy = data.aws_iam_policy_document.external_secrets_read_events_salt[0].json
}

resource "kubectl_manifest" "app_events_secret" {
  count = var.enable_app_events && var.enable_external_secrets ? 1 : 0

  yaml_body = yamlencode({
    apiVersion = "external-secrets.io/v1"
    kind       = "ExternalSecret"
    metadata = {
      name      = "o2-events"
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
        name           = "o2-events"
        creationPolicy = "Owner"
      }
      data = [
        {
          # 시크릿 본문이 평문 문자열이므로 property 를 쓰지 않는다.
          secretKey = "O2_EVENTS_SALT"
          remoteRef = {
            key = data.aws_secretsmanager_secret.events_salt[0].name
          }
        },
      ]
    }
  })

  depends_on = [
    kubectl_manifest.aws_secret_store,
    aws_iam_role_policy.external_secrets_read_events_salt,
  ]
}

# ── 영상 송출 비밀번호 ────────────────────────────────────────
# MediaMTX 의 publish 사용자 비밀번호. RTMP 인제스트가 인터넷에 열려 있어
# 이것이 유일한 방어선이다 — 없으면 NLB 주소를 아는 누구나 우리 방송으로
# 송출할 수 있다.
#
# 경로는 salt 와 같다. 원본은 Secrets Manager 에만 있고 Terraform 은 ARN 만
# 안다. 파드는 환경변수 하나로 받는다 (MTX_AUTHINTERNALUSERS_1_PASS).
data "aws_secretsmanager_secret" "media_publish" {
  count = var.enable_media ? 1 : 0
  name  = var.media_publish_secret_name
}

# CDN 비밀값. CloudFront 가 오리진 요청에 Authorization: Bearer 로 붙이고,
# MediaMTX 는 그 헤더를 보고 CDN 요청으로 판정해 시청자별 세션 ID 를 빼준다.
# 어긋나면 재생은 되는데 캐시만 조용히 안 먹는다 (D-038).
#
# 07-media 가 같은 시크릿을 읽는다. 값이 한 곳에만 있어야 두 쪽이 갈리지 않는다.
data "aws_secretsmanager_secret" "media_cdn" {
  count = var.enable_media ? 1 : 0
  name  = var.media_cdn_secret_name
}

data "aws_iam_policy_document" "external_secrets_read_media" {
  count = var.enable_media && var.enable_external_secrets ? 1 : 0

  statement {
    effect = "Allow"
    actions = [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetResourcePolicy",
      "secretsmanager:GetSecretValue",
      "secretsmanager:ListSecretVersionIds",
    ]
    resources = [
      data.aws_secretsmanager_secret.media_publish[0].arn,
      data.aws_secretsmanager_secret.media_cdn[0].arn,
    ]
  }
}

resource "aws_iam_role_policy" "external_secrets_read_media" {
  count = var.enable_media && var.enable_external_secrets ? 1 : 0

  name   = "read-media-publish"
  role   = aws_iam_role.external_secrets[0].id
  policy = data.aws_iam_policy_document.external_secrets_read_media[0].json
}

resource "kubectl_manifest" "app_media_secret" {
  count = var.enable_media && var.enable_external_secrets ? 1 : 0

  yaml_body = yamlencode({
    apiVersion = "external-secrets.io/v1"
    kind       = "ExternalSecret"
    metadata = {
      name      = "o2-media"
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
        name           = "o2-media"
        creationPolicy = "Owner"
      }
      data = [
        {
          # 시크릿 본문이 평문 문자열이라 property 를 쓰지 않는다.
          secretKey = "MTX_PUBLISH_PASS"
          remoteRef = {
            key = data.aws_secretsmanager_secret.media_publish[0].name
          }
        },
        {
          secretKey = "MTX_HLSCDNSECRET"
          remoteRef = {
            key = data.aws_secretsmanager_secret.media_cdn[0].name
          }
        },
      ]
    }
  })

  depends_on = [
    kubectl_manifest.aws_secret_store,
    aws_iam_role_policy.external_secrets_read_media,
  ]
}
