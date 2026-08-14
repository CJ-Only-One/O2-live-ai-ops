[CmdletBinding()]
param(
    [string]$Profile = "o2-producer",
    [string]$StreamName = "stream-business",
    [string]$Region = "ap-northeast-2"
)

$ErrorActionPreference = "Stop"
$env:AWS_PAGER = ""

$identityOutput = & aws sts get-caller-identity --profile $Profile --region $Region --no-cli-pager --output json 2>&1
if ($LASTEXITCODE -ne 0) {
    throw ($identityOutput -join [Environment]::NewLine)
}

$identity = ($identityOutput -join [Environment]::NewLine) | ConvertFrom-Json
if ($identity.Arn -notlike "*:user/o2-dev-producer") {
    throw "Unexpected IAM principal: $($identity.Arn)"
}

$testId = [Guid]::NewGuid().ToString("N")
$payload = [ordered]@{
    test_id = $testId
    source  = "o2-producer-profile-smoke"
} | ConvertTo-Json -Compress
$data = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload))

$putOutput = & aws kinesis put-record --stream-name $StreamName --partition-key "producer-$testId" --data $data --profile $Profile --region $Region --no-cli-pager --output json 2>&1
if ($LASTEXITCODE -ne 0) {
    throw ($putOutput -join [Environment]::NewLine)
}

$putResult = ($putOutput -join [Environment]::NewLine) | ConvertFrom-Json
Write-Host "Producer profile validation succeeded" -ForegroundColor Green
Write-Host "Principal: $($identity.Arn)"
Write-Host "Stream:    $StreamName"
Write-Host "Sequence:  $($putResult.SequenceNumber)"
