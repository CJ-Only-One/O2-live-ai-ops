variable "team" {
  description = "팀 식별자. 태그로만 사용"
  type        = string
  default     = "o2"
}

variable "project" {
  description = "리소스 prefix. 소문자/하이픈만"
  type        = string
  default     = "o2"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", var.project))
    error_message = "소문자, 숫자, 하이픈만 허용."
  }
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "cluster_name" {
  description = <<-EOT
    EKS 클러스터 이름. 노드 보안 그룹을 찾는 데만 쓴다.
    EKS 파드가 Dify 를 호출할 수 있게 인그레스를 그 SG 로 좁힌다.
    03-data 와 같은 패턴이다.
  EOT
  type        = string
  default     = "o2-eks"
}

variable "network_state_bucket" {
  description = "network 스택의 S3 backend 버킷"
  type        = string
}

variable "network_state_key" {
  type    = string
  default = "network/terraform.tfstate"
}

# ── 호스트 ────────────────────────────────────────────────────────

variable "instance_type" {
  description = <<-EOT
    Dify 셀프호스트는 컨테이너 9개를 띄운다 —
    api, worker, web, sandbox, ssrf_proxy, nginx, plugin_daemon,
    postgres, redis, 그리고 벡터 DB(weaviate).

    공식 최소 요구는 2 vCPU / 4 GiB 이고, 그 값은 "뜨기는 한다" 수준이다.
    워커가 문서 인덱싱을 돌면 4 GiB 에서 OOM 이 난다. t3.large(2 vCPU / 8 GiB)
    가 실사용 하한이다.

    t3.small(EKS 노드와 같은 등급)로 내리지 말 것. 2 GiB 로는 postgres 와
    weaviate 만으로도 부족하다.
  EOT
  type        = string
  default     = "t3.large"
}

variable "root_volume_size" {
  description = <<-EOT
    GiB. Dify 이미지 전체가 약 10 GiB, 여기에 postgres·weaviate 데이터와
    업로드 문서가 쌓인다. 60 이면 개발용으로 여유가 있다.

    ★ 데이터가 이 루트 볼륨에만 있다. 인스턴스를 교체하면 워크플로가
    전부 사라진다. 보존이 필요해지면 별도 EBS 를 붙이고 /opt/dify/volumes
    를 그쪽으로 옮긴다 (README 참조).
  EOT
  type        = number
  default     = 60
}

variable "dify_ref" {
  description = <<-EOT
    클론할 Dify git ref. main 은 언제든 깨질 수 있으므로 릴리스 태그로
    고정하는 편이 낫다.

    apply 전 확인:
      curl -s https://api.github.com/repos/langgenius/dify/releases/latest \
        | jq -r .tag_name
  EOT
  type        = string
  default     = "main"
}

variable "enable_bedrock_access" {
  description = <<-EOT
    Dify 가 모델 공급자로 Bedrock 을 쓸 때 필요한 권한을 인스턴스 역할에
    붙인다. 외부 LLM API(OpenAI 등)만 쓸 거면 false 로 두고 API 키는
    Dify UI 에서 넣는다.
  EOT
  type        = bool
  default     = true
}

# ── Session Manager ──────────────────────────────────────────────

variable "manage_session_preferences" {
  description = <<-EOT
    Session Manager 세션 설정(SSM-SessionManagerRunShell)을 이 스택이 소유한다.

    ★ 계정 전역이다. EKS 노드 접속을 포함한 모든 세션에 적용되고,
    destroy 하면 계정 기본값으로 돌아간다. 세션 설정을 다른 스택도
    필요로 하게 되면 false 로 두고 계정 베이스라인 쪽으로 옮긴다.
  EOT
  type        = bool
  default     = true
}

variable "session_idle_timeout_minutes" {
  description = <<-EOT
    무통신 상태가 이만큼 지속되면 세션을 끊는다.

    ★ AWS 상한이 60 이다. "6시간 유휴 허용" 은 불가능하다.
    긴 스튜디오 작업을 끊기지 않게 하는 것은 이 값이 아니라
    tunnel.sh 의 keepalive 다 — 주기적으로 트래픽을 흘려 유휴 자체를
    만들지 않는다. 그러면 실제 상한은 session_max_duration_minutes 가 된다.
  EOT
  type        = number
  default     = 60

  validation {
    condition     = var.session_idle_timeout_minutes >= 1 && var.session_idle_timeout_minutes <= 60
    error_message = "1 이상 60 이하. AWS 상한이 60분이다."
  }
}

variable "session_max_duration_minutes" {
  description = <<-EOT
    활동 여부와 무관하게 세션을 끊는 절대 상한. 360 = 6시간.

    무제한으로 두지 않는다. 터널을 켜둔 채 노트북을 덮으면 세션이
    영원히 남고, 그게 정상인지 아닌지 알 방법이 없다.
  EOT
  type        = number
  default     = 360

  validation {
    condition     = var.session_max_duration_minutes >= 1 && var.session_max_duration_minutes <= 1440
    error_message = "1 이상 1440 이하 (24시간)."
  }
}
