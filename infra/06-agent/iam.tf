data "aws_iam_policy_document" "assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "dify" {
  name               = "${local.name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# SSH 키도 bastion 도 만들지 않는다. 노드그룹과 같은 방식으로
# Session Manager 로만 들어간다.
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.dify.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "bedrock" {
  count = var.enable_bedrock_access ? 1 : 0

  statement {
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
      "bedrock:ListFoundationModels",
    ]
    # 모델 ARN 은 어떤 모델을 쓸지 정한 뒤 좁힌다.
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "bedrock" {
  count = var.enable_bedrock_access ? 1 : 0

  name   = "${local.name}-bedrock"
  role   = aws_iam_role.dify.id
  policy = data.aws_iam_policy_document.bedrock[0].json
}

# Hot Path 역쿼리 게이트웨이(`o2-hot-api`, 06-datastream) 호출 권한.
#
# 그쪽 Function URL 은 `authorization_type = AWS_IAM` 이고(D-042), 이미
# 이 역할을 principal 로 하는 리소스 기반 정책을 갖고 있다. 그런데도
# **403 이었다** — 실제로 EC2 에서 호출해 확인했다. 같은 계정이면
# 리소스 정책만으로 충분하다고 읽기 쉬우나, 이 조합에서는 호출자
# 쪽 신원 기반 권한도 있어야 통과한다. 한쪽만 있으면 조용히 막히고,
# 함수 로그에는 아무것도 남지 않아 원인이 안 보인다.
#
# 대상 함수를 ARN 으로 못 박는다. 06-datastream 을 remote state 로
# 읽지 않는 것은 `irsa.tf` 가 클러스터를 이름으로 조회하는 것과 같은
# 이유다 — 스택 간 state 의존을 늘리지 않는다. 함수 이름이 바뀌면
# 여기도 함께 고쳐야 한다.
data "aws_iam_policy_document" "hot_api_invoke" {
  statement {
    sid    = "InvokeHotApiFunctionUrl"
    effect = "Allow"

    # **둘 다 있어야 한다.** 하나만 주면 403 이고, 함수 로그에는 아무것도
    # 남지 않아 원인이 안 보인다. 실측으로 확인했다(같은 엔드포인트,
    # 세션 정책만 바꿔 가며):
    #
    #   InvokeFunctionUrl 만  (Resource 를 * 로 넓혀도) → 403
    #   InvokeFunction 만                              → 403
    #   둘 다                                          → 200
    #
    # 문서만 보면 Function URL 은 `lambda:InvokeFunctionUrl` 하나로 되는
    # 것처럼 읽힌다. `o2-warm-api` 의 리소스 정책에 statement 가 두 개인
    # 것(`FunctionURLAllowPublicAccess` + `FunctionURLAllowInvokeAction`)이
    # 같은 이유다 — AWS 콘솔이 만들어 준 것이라 그때는 넘겼던 단서다.
    actions = [
      "lambda:InvokeFunctionUrl",
      "lambda:InvokeFunction",
    ]

    resources = ["arn:aws:lambda:${var.region}:${data.aws_caller_identity.current.account_id}:function:o2-hot-api"]

    # `lambda:FunctionUrlAuthType` 조건을 걸지 않는다. 리소스 기반 정책
    # (06-datastream 의 aws_lambda_permission)에는 AWS 가 그 키를 채워 주지만,
    # **신원 기반 정책 평가에는 그 키가 오지 않는다.** 조건을 걸면 문이
    # 안 열린다 — 이것도 실제로 걸어 보고 403 을 받았다.
    #
    #   simulate-principal-policy (키를 직접 주입) → allowed
    #   simulate-principal-policy (키 없이)        → implicitDeny,
    #                                                MissingContextValues=[lambda:FunctionUrlAuthType]
    #
    # 조건 없이도 위험이 늘지 않는다. 대상이 이 함수 ARN 하나로 좁혀져
    # 있고, 그 함수의 URL 은 AWS_IAM 이라 인증 없는 경로가 없다.
  }
}

resource "aws_iam_role_policy" "hot_api_invoke" {
  name   = "${local.name}-hot-api-invoke"
  role   = aws_iam_role.dify.id
  policy = data.aws_iam_policy_document.hot_api_invoke.json
}

resource "aws_iam_instance_profile" "dify" {
  name = "${local.name}-profile"
  role = aws_iam_role.dify.name
}
