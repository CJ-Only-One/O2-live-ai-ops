# ★ 이 문서는 계정 전역이다. Dify 호스트뿐 아니라 EKS 노드 접속을 포함한
#   모든 Session Manager 세션에 적용된다.
#
#   지금 이것을 소유할 더 나은 스택이 없어서 여기 둔다. 세션 설정을 다른
#   스택도 필요로 하게 되면 00-cicd 나 계정 베이스라인 스택으로 옮긴다.
#   옮기기 전까지는 `terraform destroy` 가 계정 기본값을 되돌린다는 것을
#   알고 있어야 한다.
#
#   ★ 콘솔에서 Session Manager Preferences 를 한 번이라도 저장했으면
#   이 문서가 이미 계정에 있다. 그 상태로 apply 하면 이렇게 실패한다:
#
#     DocumentAlreadyExists: Document with same name SSM-SessionManagerRunShell already exists
#
#   그때는 만들지 말고 가져온다:
#     terraform import 'aws_ssm_document.session_preferences[0]' SSM-SessionManagerRunShell

resource "aws_ssm_document" "session_preferences" {
  count = var.manage_session_preferences ? 1 : 0

  # 이름을 바꾸면 안 된다. Session Manager 는 이 이름 하나만 읽는다.
  name            = "SSM-SessionManagerRunShell"
  document_type   = "Session"
  document_format = "JSON"

  content = jsonencode({
    schemaVersion = "1.0"
    description   = "Session Manager preferences. Managed by infra/06-agent"
    sessionType   = "Standard_Stream"

    inputs = {
      # 숫자가 아니라 문자열이다. 숫자로 주면 스키마 검증에서 실패한다.
      idleSessionTimeout = tostring(var.session_idle_timeout_minutes)
      maxSessionDuration = tostring(var.session_max_duration_minutes)

      runAsEnabled     = false
      runAsDefaultUser = ""

      # 세션 로깅은 켜지 않는다. 켜려면 버킷/로그그룹을 먼저 만들어야 하고,
      # 빈 문자열로 두면 로깅 없이 동작한다.
      s3BucketName                = ""
      s3KeyPrefix                 = ""
      s3EncryptionEnabled         = false
      cloudWatchLogGroupName      = ""
      cloudWatchEncryptionEnabled = false
      cloudWatchStreamingEnabled  = false
      kmsKeyId                    = ""

      shellProfile = {
        linux   = ""
        windows = ""
      }
    }
  })

  tags = {
    Name = "${local.name}-session-preferences"
  }
}
