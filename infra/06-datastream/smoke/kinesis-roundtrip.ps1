[CmdletBinding()]
param(
    [string]$StreamName = "stream-business",
    [string]$Profile = "o2-data",
    [string]$Region = "ap-northeast-2"
)

$ErrorActionPreference = "Stop"
$env:AWS_PAGER = ""

function Invoke-AwsJson {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $output = & aws @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($output -join [Environment]::NewLine)
    }

    $text = $output -join [Environment]::NewLine
    if ([string]::IsNullOrWhiteSpace($text)) {
        return $null
    }

    return $text | ConvertFrom-Json
}

Write-Host "[1/5] Checking AWS credentials"
$identity = Invoke-AwsJson -Arguments @(
    "sts", "get-caller-identity",
    "--profile", $Profile,
    "--region", $Region,
    "--no-cli-pager",
    "--output", "json"
)
Write-Host "Account: $($identity.Account)"
Write-Host "ARN:     $($identity.Arn)"

Write-Host "[2/5] Checking stream and shard: $StreamName"
$stream = Invoke-AwsJson -Arguments @(
    "kinesis", "describe-stream-summary",
    "--stream-name", $StreamName,
    "--profile", $Profile,
    "--region", $Region,
    "--no-cli-pager",
    "--output", "json"
)
if ($stream.StreamDescriptionSummary.StreamStatus -ne "ACTIVE") {
    throw "Stream status is not ACTIVE: $($stream.StreamDescriptionSummary.StreamStatus)"
}

$shards = Invoke-AwsJson -Arguments @(
    "kinesis", "list-shards",
    "--stream-name", $StreamName,
    "--profile", $Profile,
    "--region", $Region,
    "--no-cli-pager",
    "--output", "json"
)
$shardId = $shards.Shards[0].ShardId
if ([string]::IsNullOrWhiteSpace($shardId)) {
    throw "No available shard found."
}
Write-Host "Shard:   $shardId"

Write-Host "[3/5] Writing JSON record"
$testId = [Guid]::NewGuid().ToString("N")
$payloadObject = [ordered]@{
    hello   = "world"
    test_id = $testId
}
$payloadJson = $payloadObject | ConvertTo-Json -Compress
$payloadBase64 = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes($payloadJson)
)

$putResult = Invoke-AwsJson -Arguments @(
    "kinesis", "put-record",
    "--stream-name", $StreamName,
    "--partition-key", "test-$testId",
    "--data", $payloadBase64,
    "--profile", $Profile,
    "--region", $Region,
    "--no-cli-pager",
    "--output", "json"
)
Write-Host "Sequence: $($putResult.SequenceNumber)"

Write-Host "[4/5] Reading the record"
$iteratorResult = Invoke-AwsJson -Arguments @(
    "kinesis", "get-shard-iterator",
    "--stream-name", $StreamName,
    "--shard-id", $putResult.ShardId,
    "--shard-iterator-type", "AT_SEQUENCE_NUMBER",
    "--starting-sequence-number", $putResult.SequenceNumber,
    "--profile", $Profile,
    "--region", $Region,
    "--no-cli-pager",
    "--output", "json"
)

$records = $null
$iterator = $iteratorResult.ShardIterator
for ($attempt = 1; $attempt -le 10; $attempt++) {
    $getResult = Invoke-AwsJson -Arguments @(
        "kinesis", "get-records",
        "--shard-iterator", $iterator,
        "--limit", "10",
        "--profile", $Profile,
        "--region", $Region,
        "--no-cli-pager",
        "--output", "json"
    )

    $records = @($getResult.Records)
    if ($records.Count -gt 0) {
        break
    }

    $iterator = $getResult.NextShardIterator
    Start-Sleep -Seconds 1
}

if ($records.Count -eq 0) {
    throw "Record was not returned within 10 seconds."
}

$decodedJson = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String($records[0].Data)
)
$decodedObject = $decodedJson | ConvertFrom-Json

if ($decodedObject.test_id -ne $testId -or $decodedObject.hello -ne "world") {
    throw "Returned payload does not match the input: $decodedJson"
}

Write-Host "[5/5] Round-trip validation succeeded" -ForegroundColor Green
Write-Host "Payload: $decodedJson"
