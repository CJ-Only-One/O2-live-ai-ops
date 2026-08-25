# Runbook 저장소. Node 11(진단 이후 조치 조회)이 읽는 원천이다.
#
# 스키마는 이미 확정되어 있다:
#
#   PK  rca_type              RCA 유형 하나
#   SK  DEF                    유형당 정확히 하나. runbook_id·status·success_criteria 보관
#       ACTION#{action_id}     유형당 여러 개. risk_level·expected_effect·blast_radius·
#                              parameters_schema 보관
#
# status 는 active·draft·retired 셋이다(D-077). Lookup Lambda 는 active DEF와
# active ACTION만 Agent에 반환한다. draft·retired 는 같은 테이블에 남아도 자동
# 실행 후보가 아니다. status 필드가 없던 기존 아이템은 재시드 전까지만 active
# 로 간주하는 하위 호환 폴백이 있다.
#
# ★ PK 값 하나가 RCA 유형이 아니다 — `rca_type="KNOB"` 는 노브 카탈로그
#   파티션이고 SK 는 `KNOB#{action_id}` 다(D-067). 게이트 진입을 LLM 서술이
#   아니라 조회로 판정하기 위한 표이고, 축이 원인이 아니라 노브라서 따로 둔다.
#   같은 노브가 여러 rca_type 의 조치로 쓰이고, S3 처럼 **런북이 없는
#   시나리오의 조치**도 집이 있어야 하기 때문이다.
#   테이블·IAM·조회 Lambda 를 새로 만들지 않는다 — PK 값만 다르다.
#   lambda/runbook_lookup.py 가 조치마다 노브를 붙여 돌려준다.
#
# ★ parameters_schema.source 는 두 갈래다 — observability.*(런타임 관측값, Node 7 이
#   observability 키 아래로 몰아넣은 것) vs static:xxx(고정 정책값). 이 구분은 테이블
#   스키마가 아니라 ACTION 아이템 안 값의 관례라 여기 코드엔 드러나지 않지만,
#   Node 19(파라미터 리졸버)가 이 관례를 그대로 믿고 파싱한다.
#
# related_docs·usage_stats·escalation_target 은 아직 스키마에 안 넣는다.
# 서비스 레벨 정보라 따로 관리하기로 한 항목들이다.
#
# ★ DEF 아이템의 success_criteria 에는 D-058 로 baseline_conditions 가
#   추가됐다 — conditions(절대 SLO)와 별도 목록이고, Baseline 상태에서
#   기록한 값(예: baseline_p95_ms)을 relative_to 로 가리킨다. 스키마리스라
#   테이블·이 파일은 안 바뀐다. 시딩값은 scripts/seed_runbook.py 참조.
#
# ★ labels.txt 의 runbooks/<label>.md(사람이 읽는 마크다운 대응 문서)와는
#   다른 것이다. 이 테이블은 에이전트가 자동으로 조회·실행하는 기계 판독용
#   카탈로그다 — 이름이 같아서 헷갈리기 쉽다.

resource "aws_dynamodb_table" "runbook" {
  name         = "${local.name}-runbook"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "rca_type"
  range_key = "sk"

  attribute {
    name = "rca_type"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # PITR 안 건다. 진짜 원본은 이 테이블이 아니라 시딩 스크립트다 — 테이블이
  # 날아가도 스크립트를 다시 돌리면 그대로 복구된다. history.tf 의 S3 버전관리와는
  # 반대 결론인데, 거기는 "산출물이라 원본이 코드 밖에만 있는" 경우고 여기는
  # "원본이 스크립트(=코드)로 남아있는" 경우라 그렇다.
  point_in_time_recovery {
    enabled = false
  }

  tags = {
    Name = "${local.name}-runbook"
  }
}

output "runbook_table_name" {
  description = "시딩 스크립트와 runbook_lookup Lambda 환경변수에 넣을 테이블 이름"
  value       = aws_dynamodb_table.runbook.name
}
