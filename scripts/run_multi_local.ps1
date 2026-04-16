# Windows 로컬에서 EC2 start.sh 와 동일한 기본값으로 multi_main 실행.
#   powershell -ExecutionPolicy Bypass -File scripts\run_multi_local.ps1
# 필요 시: $env:ARB_MULTI_CONFIG = "configs\multi.yaml"

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

if (-not $env:ARB_MULTI_CONFIG) {
    $env:ARB_MULTI_CONFIG = "configs/multi.yaml"
}

$config = $env:ARB_MULTI_CONFIG
Write-Host "multi_main  config=$config"
python -m src.multi_main --config $config
