# DD_API_KEY / DD_APP_KEY 를 이 파일에도, 어떤 다른 커밋되는 파일에도 적지 않는다.
#
# - tfvars 변수로 받으면 값이 plan 파일에 평문으로 남는다.
# - Secrets Manager data source 로 읽어도 그 결과가 terraform.tfstate 에
#   평문으로 남는다(이 스택의 state 는 S3 에 있고 팀이 공유한다).
#
# 그래서 매번 Secrets Manager 에서 직접 읽어 "이 프로세스의 환경변수"로만
# 잠깐 쥐고 있다가 끝나면 지운다 — README.md 의 수동 절차를 그대로 스크립트로
# 옮긴 것뿐이다. 새 비밀 저장 방식이 아니다.
#
# 사용법 (이 디렉터리에서):
#   .\apply.ps1            # init + plan 까지. 승인은 사람이 tfplan 을 보고 따로
#   .\apply.ps1 -Apply     # plan 을 보여준 뒤 확인을 받고 그대로 적용까지
#   .\apply.ps1 -Apply -Yes  # 확인 없이 적용 (CI 등 무인 실행용. 대화형 세션에서는 쓰지 않는다)

param(
    [switch]$Apply,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"

try {
    $env:AWS_PROFILE = "o2-data"

    Write-Host "Secrets Manager(o2/dev/datadog)에서 Datadog 키를 읽는 중..."
    $raw = aws secretsmanager get-secret-value --secret-id o2/dev/datadog --query SecretString --output text
    if ($LASTEXITCODE -ne 0 -or -not $raw) {
        throw "Secrets Manager 조회 실패. AWS_PROFILE=o2-data 로그인 상태를 확인한다."
    }
    $j = $raw | ConvertFrom-Json
    $env:DD_API_KEY = $j.'api-key'
    $env:DD_APP_KEY = $j.'app-key'
    $raw = $null
    $j = $null

    if (-not $env:DD_API_KEY -or -not $env:DD_APP_KEY) {
        throw "시크릿에 api-key/app-key 필드가 없다. o2/dev/datadog 값을 확인한다."
    }

    terraform init -input=false
    if ($LASTEXITCODE -ne 0) { throw "terraform init 실패" }

    terraform plan -out=tfplan
    if ($LASTEXITCODE -ne 0) { throw "terraform plan 실패" }

    if ($Apply) {
        if (-not $Yes) {
            $confirm = Read-Host "`n위 plan 을 적용한다. 계속하려면 'yes' 입력"
            if ($confirm -ne "yes") {
                Write-Host "취소했다. tfplan 파일은 남아 있다 — 나중에 'terraform apply tfplan' 으로 직접 적용할 수 있다."
                return
            }
        }
        terraform apply tfplan
    } else {
        Write-Host "`nplan 만 실행했다. 적용하려면: terraform apply tfplan (또는 .\apply.ps1 -Apply)"
    }
}
finally {
    # 이 프로세스 안에서만 지운다. 셸이 이 스크립트를 dot-source(". .\apply.ps1")로
    # 부르지 않았다면 부모 세션의 환경에는 애초에 안 남는다.
    Remove-Item Env:\DD_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:\DD_APP_KEY -ErrorAction SilentlyContinue
}
