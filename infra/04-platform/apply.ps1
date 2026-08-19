# Do NOT write DD_API_KEY / DD_APP_KEY in this file or any other committed files.
#
# - If passed as tfvars variables, values will remain in plaintext in the plan file.
# - Even if read from a Secrets Manager data source, the result will remain in plaintext
#   in terraform.tfstate (the state for this stack is in S3 and shared by the team).
#
# Therefore, we retrieve them directly from Secrets Manager and hold them only 
# temporarily as environment variables of this process, then clear them when done.
# This script simply automates the manual procedure described in README.md.
#
# Usage (in this directory):
#   .\apply.ps1            # Runs init + plan. Approval is done separately by inspecting tfplan.
#   .\apply.ps1 -Apply     # Shows the plan and applies it after confirmation.
#   .\apply.ps1 -Apply -Yes  # Applies without confirmation (for non-interactive runs like CI).
#

param(
    [switch]$Apply,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"

try {
    $env:AWS_PROFILE = "o2-data"

    Write-Host "Reading Datadog keys from Secrets Manager (o2/dev/datadog)..."
    $raw = aws secretsmanager get-secret-value --secret-id o2/dev/datadog --query SecretString --output text
    if ($LASTEXITCODE -ne 0 -or -not $raw) {
        throw "Failed to retrieve secret from Secrets Manager. Check AWS_PROFILE=o2-data login status."
    }
    $j = $raw | ConvertFrom-Json
    $env:DD_API_KEY = $j.'api-key'
    $env:DD_APP_KEY = $j.'app-key'
    $raw = $null
    $j = $null

    if (-not $env:DD_API_KEY -or -not $env:DD_APP_KEY) {
        throw "api-key/app-key fields not found in the secret. Check o2/dev/datadog value."
    }

    terraform init -input=false
    if ($LASTEXITCODE -ne 0) { throw "terraform init failed" }

    terraform plan -out=tfplan
    if ($LASTEXITCODE -ne 0) { throw "terraform plan failed" }

    if ($Apply) {
        if (-not $Yes) {
            $confirm = Read-Host "`nApply the plan above. To continue, type 'yes'"
            if ($confirm -ne "yes") {
                Write-Host "Cancelled. tfplan file is kept — you can apply it manually later with 'terraform apply tfplan'."
                return
            }
        }
        terraform apply tfplan
    } else {
        Write-Host "`nOnly planned. To apply: terraform apply tfplan (or .\apply.ps1 -Apply)"
    }
}
finally {
    # Clear from this process only. If not dot-sourced (". .\apply.ps1"),
    # these won't remain in the parent session's environment anyway.
    Remove-Item Env:\DD_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:\DD_APP_KEY -ErrorAction SilentlyContinue
}
