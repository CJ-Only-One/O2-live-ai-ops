output "vpc_id" {
  description = "EKS 모듈의 vpc_id 입력값"
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "SG 규칙 작성 시 VPC 내부 대역 지정용"
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "인터넷 페이싱 ALB/NLB 배치 대상"
  value       = [for s in aws_subnet.public : s.id]
}

output "private_app_subnet_ids" {
  description = "EKS 워커 노드 그룹 및 Pod ENI 배치 대상"
  value       = [for s in aws_subnet.private_app : s.id]
}

output "private_data_subnet_ids" {
  description = "RDS/ElastiCache 배치 대상"
  value       = [for s in aws_subnet.private_data : s.id]
}

output "db_subnet_group_name" {
  value = try(aws_db_subnet_group.data[0].name, null)
}

output "elasticache_subnet_group_name" {
  value = try(aws_elasticache_subnet_group.data[0].name, null)
}

output "nat_gateway_public_ips" {
  description = "외부 PG 모킹 서버 등에서 IP 허용목록을 걸어야 할 때 사용"
  value       = [for e in aws_eip.nat : e.public_ip]
}

output "flow_logs_bucket" {
  description = "Athena 테이블 생성 대상 버킷"
  value       = try(aws_s3_bucket.flow_logs[0].bucket, null)
}

output "azs" {
  value = local.azs
}

output "subnet_cidr_plan" {
  description = "설계 검토/문서화용 CIDR 요약"
  value = {
    public       = { for az, v in local.public_subnets : az => v.cidr }
    private_app  = { for az, v in local.private_app_subnets : az => v.cidr }
    private_data = { for az, v in local.private_data_subnets : az => v.cidr }
  }
}
