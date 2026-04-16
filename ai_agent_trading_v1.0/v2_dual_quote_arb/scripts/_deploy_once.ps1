# Full code deploy without uploading .env (same intent as deploy_ec2_windows.ps1).
# Uses separate one-line SSH commands so Windows CRLF does not break remote bash.
$ErrorActionPreference = 'Stop'
$SourceRoot = 'C:\Users\user\trading\arb'
$PublicIp = '52.78.108.174'
$Key = 'c:\trading\arb\arb_key.pem'
$User = 'ubuntu'

$stage = Join-Path $env:TEMP ('arb-ec2-stage-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    robocopy $SourceRoot $stage /E /NFL /NDL /NJH /NJS /NC /NS `
        /XF arb_key.pem *.pem *.ppk .env `
        /XD .git venv .venv .pytest_cache logs .cursor __pycache__ data node_modules .qmd | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed exit $LASTEXITCODE" }

    $stageUnix = ($stage -replace '\\', '/').TrimEnd('/')
    $sshBase = @('-i', $Key, '-o', 'StrictHostKeyChecking=accept-new', '-o', 'BatchMode=yes')

    Write-Host '=== SSH: mkdir ~/arb ===' -ForegroundColor Cyan
    & ssh.exe @sshBase "${User}@${PublicIp}" 'mkdir -p ~/arb'

    Write-Host '=== SCP: code ===' -ForegroundColor Cyan
    & scp.exe @sshBase -r "${stageUnix}/*" "${User}@${PublicIp}:arb/"

    Write-Host '=== SSH: strip CRLF *.sh ===' -ForegroundColor Cyan
    & ssh.exe @sshBase "${User}@${PublicIp}" 'find ~/arb -name "*.sh" -type f -exec sed -i "s/\r$//" {} + 2>/dev/null; true'

    Write-Host '=== SSH: chmod ===' -ForegroundColor Cyan
    & ssh.exe @sshBase "${User}@${PublicIp}" 'chmod -R u+w ~/arb 2>/dev/null; chmod +x ~/arb/scripts/*.sh 2>/dev/null; true'

    Write-Host '=== SSH: setup_server.sh ===' -ForegroundColor Cyan
    & ssh.exe @sshBase "${User}@${PublicIp}" 'cd ~/arb && bash scripts/setup_server.sh'

    Write-Host '=== SSH: stop legacy + restart arb ===' -ForegroundColor Cyan
    & ssh.exe @sshBase "${User}@${PublicIp}" 'bash ~/arb/scripts/stop_legacy_trading.sh || true'
    & ssh.exe @sshBase "${User}@${PublicIp}" 'sudo systemctl daemon-reload && sudo systemctl restart arb && sudo systemctl status arb --no-pager'

    Write-Host '=== done ===' -ForegroundColor Green
}
finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
