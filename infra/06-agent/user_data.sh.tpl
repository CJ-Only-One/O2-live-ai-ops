#!/bin/bash
set -euxo pipefail

# 부팅에서 하는 일은 '띄울 수 있는 상태'까지다.
# docker compose up 은 사람이 한다 — .env 를 확인하고 모델 공급자를
# 정한 뒤에 올리는 편이 낫고, 부팅 실패를 로그로 쫓는 것보다 싸다.

dnf install -y docker git

# AL2023 리포에는 compose 플러그인이 없다. 바이너리를 직접 넣는다.
install -d /usr/libexec/docker/cli-plugins
curl -fsSL \
  https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o /usr/libexec/docker/cli-plugins/docker-compose
chmod +x /usr/libexec/docker/cli-plugins/docker-compose

systemctl enable --now docker
usermod -aG docker ec2-user

# ssm-user 는 여기서 docker 그룹에 못 넣는다 — 그 계정은 첫 SSM 세션에서
# 만들어지고 부팅 시점에는 아직 없다. SSM 에이전트가 ssm-user 에게
# NOPASSWD sudo 를 이미 주므로 세션에서는 `sudo docker compose ...` 로 쓴다.

if [ ! -d /opt/dify ]; then
  git clone --depth 1 --branch '${dify_ref}' \
    https://github.com/langgenius/dify.git /opt/dify
fi

cd /opt/dify/docker
if [ ! -f .env ]; then
  cp .env.example .env

  # ★ set -x 를 끄고 생성한다. 켜둔 채로 하면 SECRET_KEY 가
  #   /var/log/cloud-init-output.log 에 평문으로 남는다.
  #   SSM 접근 권한이 있어야 읽히지만, 로그에 남을 이유가 없는 값이다.
  set +x
  # SECRET_KEY 는 세션 쿠키 서명에 쓴다. 예제 값 그대로 두면 안 된다.
  SECRET=$(openssl rand -base64 42)
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET|" .env
  unset SECRET
  set -x
fi

chown -R ec2-user:ec2-user /opt/dify
