# Short-window-first v2 multi backtest (7d, 14d primary + 30d sanity; optional 60d).
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\run_backtest_short_windows.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\run_backtest_short_windows.ps1 -Also60

param(
    [string]$Config = "configs\multi.yaml",
    [switch]$Also60,
    [switch]$NoSkipCollect
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$extra = @()
if ($Also60) { $extra += "--also-60" }
if ($NoSkipCollect) { $extra += "--no-skip-collect" }  # forces REST re-download

& python -m src.tools.run_short_window_backtests --config $Config @extra
exit $LASTEXITCODE
