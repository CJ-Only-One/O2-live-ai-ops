[CmdletBinding()]
param(
    [string]$StreamName = "stream-business",
    [string]$FunctionName = "o2-agg",
    [string]$Profile = "o2-data",
    [string]$Region = "ap-northeast-2",
    [int]$TimeoutSeconds = 60
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

$testId = [Guid]::NewGuid().ToString("N")
$startTimeMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$payload = [ordered]@{
    test_id = $testId
    source  = "lambda-smoke"
} | ConvertTo-Json -Compress
$data = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload))

Write-Host "[1/4] Checking Lambda function: $FunctionName"
$function = Invoke-AwsJson -Arguments @(
    "lambda", "get-function-configuration",
    "--function-name", $FunctionName,
    "--profile", $Profile,
    "--region", $Region,
    "--no-cli-pager",
    "--output", "json"
)
if ($function.State -ne "Active" -or $function.LastUpdateStatus -ne "Successful") {
    throw "Lambda function is not ready. State=$($function.State), Update=$($function.LastUpdateStatus)"
}

Write-Host "[2/4] Checking event source mapping"
$mappings = Invoke-AwsJson -Arguments @(
    "lambda", "list-event-source-mappings",
    "--function-name", $FunctionName,
    "--event-source-arn", "arn:aws:kinesis:${Region}:066107819912:stream/$StreamName",
    "--profile", $Profile,
    "--region", $Region,
    "--no-cli-pager",
    "--output", "json"
)
if (@($mappings.EventSourceMappings).Count -eq 0 -or $mappings.EventSourceMappings[0].State -ne "Enabled") {
    throw "Enabled event source mapping was not found."
}

Write-Host "[3/4] Writing Kinesis test record"
Invoke-AwsJson -Arguments @(
    "kinesis", "put-record",
    "--stream-name", $StreamName,
    "--partition-key", "lambda-$testId",
    "--data", $data,
    "--profile", $Profile,
    "--region", $Region,
    "--no-cli-pager",
    "--output", "json"
) | Out-Null

Write-Host "[4/4] Waiting for Lambda log (up to $TimeoutSeconds seconds)"
$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$matchedEvent = $null
do {
    Start-Sleep -Seconds 5
    $events = Invoke-AwsJson -Arguments @(
        "logs", "filter-log-events",
        "--log-group-name", "/aws/lambda/$FunctionName",
        "--start-time", $startTimeMs.ToString(),
        "--filter-pattern", '"received"',
        "--profile", $Profile,
        "--region", $Region,
        "--no-cli-pager",
        "--output", "json"
    )
    $matchedEvent = @($events.events)[0]
} while ($null -eq $matchedEvent -and [DateTime]::UtcNow -lt $deadline)

if ($null -eq $matchedEvent) {
    throw "Lambda invocation log was not found within the timeout."
}

Write-Host "Lambda Kinesis validation succeeded" -ForegroundColor Green
Write-Host "Log: $($matchedEvent.message.Trim())"
