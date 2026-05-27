param(
  [string]$Host = '127.0.0.1',
  [int]$Port = 8017
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
python -m uvicorn dataset_review_platform_backend.app.main:app --host $Host --port $Port
