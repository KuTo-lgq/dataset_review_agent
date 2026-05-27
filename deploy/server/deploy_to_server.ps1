param(
  [string]$ServerUser = 'reviewer',
  [string]$ServerHost = '10.0.0.10',
  [string]$RemoteRoot = '/home/reviewer/dataset-review-agent'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
$packagePath = Join-Path $env:TEMP 'dataset_review_suite_deploy.tar.gz'
if (Test-Path $packagePath) { Remove-Item $packagePath -Force }

tar -czf $packagePath -C $root .
if ($LASTEXITCODE -ne 0) { throw 'tar package failed' }

if (-not $env:SSH_ASKPASS) {
  Write-Warning 'SSH_ASKPASS is not set. If SSH requires a password, export it before running this script.'
}
if (-not $env:SSH_ASKPASS_REQUIRE) { $env:SSH_ASKPASS_REQUIRE = 'force' }
if (-not $env:DISPLAY) { $env:DISPLAY = 'codex' }

$target = "$ServerUser@$ServerHost"
ssh -o StrictHostKeyChecking=no $target "mkdir -p $RemoteRoot"
scp -o StrictHostKeyChecking=no $packagePath "${target}:$RemoteRoot/package.tar.gz"
ssh -o StrictHostKeyChecking=no $target "cd $RemoteRoot && tar -xzf package.tar.gz && rm -f package.tar.gz && bash deploy/server/install_user_service.sh"
