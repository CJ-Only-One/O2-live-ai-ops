output "instance_id" {
  value = aws_instance.dify.id
}

output "private_ip" {
  description = "EKS 파드가 붙는 주소. 퍼블릭 IP 는 없다"
  value       = aws_instance.dify.private_ip
}

output "dify_api_base" {
  description = <<-EOT
    앱에서 워크플로를 호출할 때 쓰는 베이스 URL.
    ConfigMap 에 넣을 값이다 — 앱 코드나 매니페스트에 IP 를 적지 않는다
    (docs/decisions.md D-018 과 같은 원칙).
  EOT
  value       = "http://${aws_instance.dify.private_ip}/v1"
}

output "console_url" {
  description = "포트 포워딩을 건 뒤 로컬에서 여는 주소는 http://localhost:17080"
  value       = "http://${aws_instance.dify.private_ip}"
}

output "security_group_id" {
  value = aws_security_group.dify.id
}

# ── 알림 중계 Lambda ─────────────────────────────────────────────

output "alert_relay_function_url" {
  description = <<-EOT
    Datadog webhook 에 등록하는 주소.

    ★ 인증이 x-dd-secret 헤더 하나뿐이라 **URL 자체를 비밀로 취급한다.**
      공유 문서에 적지 않는다. 필요하면 이 출력이나 콘솔에서 확인한다.
  EOT
  value       = aws_lambda_function_url.alert_relay.function_url
  sensitive   = true
}

output "alert_relay_security_group_id" {
  value = aws_security_group.alert_relay.id
}

output "alert_relay_log_command" {
  description = "알림이 안 올 때 제일 먼저 볼 곳"
  value       = "aws logs tail /aws/lambda/${local.alert_relay_name} --follow --region ${var.region}"
}

output "ssm_session_command" {
  value = "aws ssm start-session --target ${aws_instance.dify.id} --region ${var.region}"
}

output "ssm_port_forward_command" {
  description = <<-EOT
    콘솔을 로컬 17080 으로 당겨온다. ALB 도 퍼블릭 노출도 필요 없다.

    ★ 로컬 포트를 바꾸지 말 것. 서버의 NEXT_PUBLIC_SOCKET_URL 이
    ws://localhost:17080 으로 고정돼 있어, 다른 포트로 열면 화면은 뜨는데
    실시간 동기화(socket.io)만 조용히 죽는다.
  EOT
  value = join(" ", [
    "aws ssm start-session --target ${aws_instance.dify.id}",
    "--document-name AWS-StartPortForwardingSession",
    "--parameters portNumber=80,localPortNumber=17080",
    "--region ${var.region}",
  ])
}
