[CmdletBinding()]
param(
    [string]$TableName = "o2-agent-context",
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

$testId = [Guid]::NewGuid().ToString("N")
$pk = "METRIC#smoke-$testId"
$sk = "TS#1"
$tempDirectory = Join-Path $env:TEMP "o2-dynamodb-smoke-$testId"
$itemFile = Join-Path $tempDirectory "item.json"
$keyFile = Join-Path $tempDirectory "key.json"

New-Item -ItemType Directory -Path $tempDirectory | Out-Null

try {
    $item = @{
        pk         = @{ S = $pk }
        sk         = @{ S = $sk }
        v          = @{ N = "1" }
        expires_at = @{ N = ([DateTimeOffset]::UtcNow.AddHours(1).ToUnixTimeSeconds().ToString()) }
    }
    $key = @{
        pk = @{ S = $pk }
        sk = @{ S = $sk }
    }

    $item | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $itemFile -Encoding ascii
    $key | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $keyFile -Encoding ascii

    Write-Host "[1/4] Checking table: $TableName"
    $table = Invoke-AwsJson -Arguments @(
        "dynamodb", "describe-table",
        "--table-name", $TableName,
        "--profile", $Profile,
        "--region", $Region,
        "--no-cli-pager",
        "--output", "json"
    )
    if ($table.Table.TableStatus -ne "ACTIVE") {
        throw "Table status is not ACTIVE: $($table.Table.TableStatus)"
    }

    Write-Host "[2/4] Writing test item"
    Invoke-AwsJson -Arguments @(
        "dynamodb", "put-item",
        "--table-name", $TableName,
        "--item", "file://$itemFile",
        "--profile", $Profile,
        "--region", $Region,
        "--no-cli-pager",
        "--output", "json"
    ) | Out-Null

    Write-Host "[3/4] Reading test item"
    $result = Invoke-AwsJson -Arguments @(
        "dynamodb", "get-item",
        "--table-name", $TableName,
        "--key", "file://$keyFile",
        "--consistent-read",
        "--profile", $Profile,
        "--region", $Region,
        "--no-cli-pager",
        "--output", "json"
    )
    if ($result.Item.pk.S -ne $pk -or $result.Item.v.N -ne "1") {
        throw "Returned item does not match the input."
    }

    Write-Host "[4/4] Deleting test item"
    Invoke-AwsJson -Arguments @(
        "dynamodb", "delete-item",
        "--table-name", $TableName,
        "--key", "file://$keyFile",
        "--profile", $Profile,
        "--region", $Region,
        "--no-cli-pager",
        "--output", "json"
    ) | Out-Null

    Write-Host "DynamoDB round-trip validation succeeded" -ForegroundColor Green
    Write-Host "PK: $pk"
    Write-Host "SK: $sk"
}
finally {
    Remove-Item -LiteralPath $tempDirectory -Recurse -Force -ErrorAction SilentlyContinue
}
