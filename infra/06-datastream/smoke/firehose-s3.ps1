[CmdletBinding()]
param(
    [ValidateSet("business", "client")]
    [string]$Channel = "business",
    [string]$Profile = "o2-data",
    [string]$Region = "ap-northeast-2",
    [string]$BucketName = "o2-data-lake-066107819912",
    [int]$TimeoutSeconds = 420
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

$streamName = "stream-$Channel"
$deliveryStreamName = "o2-$Channel-to-s3"
$prefix = "raw/$Channel/"
$testId = [Guid]::NewGuid().ToString("N")

Write-Host "[1/4] Checking Firehose delivery stream: $deliveryStreamName"
$deliveryStream = Invoke-AwsJson -Arguments @(
    "firehose", "describe-delivery-stream",
    "--delivery-stream-name", $deliveryStreamName,
    "--profile", $Profile,
    "--region", $Region,
    "--no-cli-pager",
    "--output", "json"
)
if ($deliveryStream.DeliveryStreamDescription.DeliveryStreamStatus -ne "ACTIVE") {
    throw "Firehose status is not ACTIVE: $($deliveryStream.DeliveryStreamDescription.DeliveryStreamStatus)"
}

Write-Host "[2/4] Recording existing S3 objects"
$before = Invoke-AwsJson -Arguments @(
    "s3api", "list-objects-v2",
    "--bucket", $BucketName,
    "--prefix", $prefix,
    "--profile", $Profile,
    "--region", $Region,
    "--no-cli-pager",
    "--output", "json"
)
$existingKeys = @($before.Contents | ForEach-Object { $_.Key })

Write-Host "[3/4] Writing test records to $streamName"
1..20 | ForEach-Object {
    $payload = [ordered]@{
        test_id = $testId
        channel = $Channel
        n       = $_
    } | ConvertTo-Json -Compress
    $data = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload))

    Invoke-AwsJson -Arguments @(
        "kinesis", "put-record",
        "--stream-name", $streamName,
        "--partition-key", "firehose-$testId",
        "--data", $data,
        "--profile", $Profile,
        "--region", $Region,
        "--no-cli-pager",
        "--output", "json"
    ) | Out-Null
}

Write-Host "[4/4] Waiting for a new S3 object (up to $TimeoutSeconds seconds)"
$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$newKeys = @()
do {
    Start-Sleep -Seconds 15
    $after = Invoke-AwsJson -Arguments @(
        "s3api", "list-objects-v2",
        "--bucket", $BucketName,
        "--prefix", $prefix,
        "--profile", $Profile,
        "--region", $Region,
        "--no-cli-pager",
        "--output", "json"
    )
    $currentKeys = @($after.Contents | ForEach-Object { $_.Key })
    $newKeys = @($currentKeys | Where-Object { $_ -notin $existingKeys })
    Write-Host "Elapsed: $([int]($TimeoutSeconds - ($deadline - [DateTime]::UtcNow).TotalSeconds))s"
} while ($newKeys.Count -eq 0 -and [DateTime]::UtcNow -lt $deadline)

if ($newKeys.Count -eq 0) {
    throw "No new S3 object found under s3://$BucketName/$prefix within the timeout."
}

Write-Host "Firehose delivery validation succeeded" -ForegroundColor Green
$newKeys | ForEach-Object { Write-Host "S3 key: $_" }
