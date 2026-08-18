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
  description = "포트 포워딩을 건 뒤 로컬에서 여는 주소는 http://localhost:8080"
  value       = "http://${aws_instance.dify.private_ip}"
}

output "security_group_id" {
  value = aws_security_group.dify.id
}

output "ssm_session_command" {
  value = "aws ssm start-session --target ${aws_instance.dify.id} --region ${var.region}"
}

output "ssm_port_forward_command" {
  description = "콘솔을 로컬 8080 으로 당겨온다. ALB 도 퍼블릭 노출도 필요 없다"
  value = join(" ", [
    "aws ssm start-session --target ${aws_instance.dify.id}",
    "--document-name AWS-StartPortForwardingSession",
    "--parameters '{\"portNumber\":[\"80\"],\"localPortNumber\":[\"8080\"]}'",
    "--region ${var.region}",
  ])
}
