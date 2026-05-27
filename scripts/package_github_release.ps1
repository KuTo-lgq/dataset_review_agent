param(
  [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

$suiteRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) {
  $OutputDir = Join-Path $suiteRoot "dist\dataset-review-agent"
}

if (Test-Path $OutputDir) {
  Remove-Item -LiteralPath $OutputDir -Recurse -Force
}
New-Item -ItemType Directory -Path $OutputDir | Out-Null

$copyDirs = @(
  "dataset_audit_pipeline",
  "dataset_review_platform_backend",
  "deploy",
  "scripts"
)

$copyFiles = @(
  ".env.example",
  ".gitignore",
  "LICENSE",
  "README.md",
  "requirements.txt",
  "requirements.platform.txt",
  "start_review_platform.ps1",
  "start_review_platform.sh",
  "askpass.example.cmd"
)

foreach ($relative in $copyDirs) {
  Copy-Item -LiteralPath (Join-Path $suiteRoot $relative) -Destination (Join-Path $OutputDir $relative) -Recurse -Force
}

foreach ($relative in $copyFiles) {
  $source = Join-Path $suiteRoot $relative
  if (Test-Path $source) {
    Copy-Item -LiteralPath $source -Destination (Join-Path $OutputDir $relative) -Force
  }
}

$removePaths = @(
  "dataset_review_platform_backend\data",
  "dataset_review_platform_backend\exports",
  "dataset_review_platform_backend\generated_configs",
  "dataset_review_platform_backend\imported_runs",
  "dataset_review_platform_backend\task_logs",
  "dataset_audit_pipeline\runs",
  "dataset_audit_pipeline\configs",
  "dataset_audit_pipeline\FULL_GUIDE.md",
  "dataset_audit_pipeline\OPERATION_GUIDE.md",
  "deploy\server\.env.runtime"
)

foreach ($relative in $removePaths) {
  $target = Join-Path $OutputDir $relative
  if (Test-Path $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
  }
}

Get-ChildItem -Path $OutputDir -Recurse -Force -Directory |
  Where-Object { $_.Name -in @("__pycache__", ".pytest_cache") } |
  Remove-Item -Recurse -Force

Get-ChildItem -Path $OutputDir -Recurse -Force -File -Include "*.pyc", "*.pyo", "*.log", "*.tmp" |
  Remove-Item -Force

$releaseReadme = @(
  "GitHub release folder is ready.",
  "",
  "Suggested next steps:",
  "1. Initialize a new Git repository in this folder.",
  "2. Review .env.example and deploy/server/platform.env.example.",
  "3. Update the README title or badges for your public repo name."
) -join [Environment]::NewLine

Set-Content -LiteralPath (Join-Path $OutputDir "PUBLISHING.md") -Value $releaseReadme -Encoding UTF8

Write-Host "Release folder ready: $OutputDir"
