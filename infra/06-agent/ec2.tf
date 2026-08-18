resource "aws_instance" "dify" {
  ami           = data.aws_ssm_parameter.al2023.value
  instance_type = var.instance_type

  subnet_id                   = local.subnet_id
  vpc_security_group_ids      = [aws_security_group.dify.id]
  associate_public_ip_address = false
  iam_instance_profile        = aws_iam_instance_profile.dify.name

  user_data = templatefile("${path.module}/user_data.sh.tpl", {
    dify_ref = var.dify_ref
  })

  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_size
    encrypted   = true

    # 인스턴스를 지워도 볼륨이 남으면 요금만 남는다. 데이터 보존이
    # 필요해지면 별도 EBS 를 붙이는 쪽이 맞다 (README).
    delete_on_termination = true
  }

  metadata_options {
    http_tokens   = "required" # IMDSv2 강제
    http_endpoint = "enabled"

    # ★ 2 여야 한다. Dify 는 docker 브리지 네트워크 안에서 돌고, 컨테이너에서
    #   169.254.169.254 로 가는 패킷은 홉을 하나 더 쓴다. 1 이면 컨테이너가
    #   인스턴스 역할을 못 받아 Bedrock 호출이 자격증명 없음으로 실패한다.
    #   호스트에서 aws CLI 는 되는데 Dify 안에서만 안 되는 형태라 원인이 잘 안 보인다.
    http_put_response_hop_limit = 2
  }

  lifecycle {
    # ★ AMI 파라미터는 AWS 가 수시로 갱신한다. ignore 하지 않으면
    # 다음 apply 가 인스턴스를 교체하고, 루트 볼륨에 있던 Dify 워크플로가
    # 통째로 사라진다. AMI 를 올릴 때는 의도적으로 taint 한다.
    ignore_changes = [ami, user_data]
  }

  tags = {
    Name = local.name
  }
}
