# EC2 배포: scripts/start.sh 가 ARB_SERVICE_LINE 에 따라 분기.
#   v1.1 (기본): multi_main TRX+SOL — cloud.env.v1.1.example, configs/multi.yaml
#   v1.2: 바이낸스 듀얼쿼트 live_v2 — cloud.env.v1.2.example, ARB_SERVICE_LINE=v1.2
# 레거시 v1(src.main)는 stop_legacy_trading.sh 로 중지.
#
# 퍼블릭 IP (우선순위): -PublicIp → $env:ARB_EC2_PUBLIC_IP → $EnvFile(.env) 의
#   ARB_EC2_PUBLIC_IP / ARB_DEPLOY_EC2_IP / ARB_DEPLOY_SERVER=ubuntu@x.x.x.x
# SSH 키: -Key 미지정 시 .env 의 ARB_EC2_SSH_KEY → 기본 c:\trading\arb\arb_key.pem
# 업로드할 시크릿: -UploadLocalEnv 시 $UploadEnvFrom (기본 = $EnvFile = 루트 .env)
#
# .env.local 은 읽지 않음 (로컬 전용; 배포 스크립트가 건드리지 않음).
#
# 사용 예 (루트 .env에 IP·키가 있으면):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy_ec2_windows.ps1 -UploadLocalEnv

[CmdletBinding()]
param(
    [string] $PublicIp,
    [string] $Key,
    [string] $User = 'ubuntu',
    # 비워두면 scripts/ 상위(프로젝트 루트). 일부 호스트에서 $PSScriptRoot 가 비므로 MyInvocation 폴백.
    [string] $SourceRoot = '',
    # IP/키 파싱에만 사용. 기본: SourceRoot\.env (.env.local 사용 안 함)
    [string] $EnvFile = '',
    [string] $UploadEnvFrom = '',
    [switch] $UploadLocalEnv
)

$ErrorActionPreference = 'Stop'

if (-not $SourceRoot) {
    $scriptDir = $null
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        $scriptDir = $PSScriptRoot
    } elseif ($MyInvocation.MyCommand.Path) {
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    if ($scriptDir) {
        $SourceRoot = (Resolve-Path (Join-Path $scriptDir '..')).Path
    } else {
        $SourceRoot = (Get-Location).Path
    }
}

function Get-ArbEnvFileValue {
    param([string]$Path, [string]$Name)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding utf8) {
        $t = $line.TrimEnd()
        if ($t.StartsWith('#') -or [string]::IsNullOrWhiteSpace($t)) { continue }
        if (-not $t.Contains('=')) { continue }
        $parts = $t.Split('=', 2)
        $k = $parts[0].Trim()
        if ($k -ne $Name) { continue }
        $v = if ($parts.Count -gt 1) { $parts[1].Trim() } else { '' }
        if ($v.Length -ge 2 -and (($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'")))) {
            $v = $v.Substring(1, $v.Length - 2)
        }
        return $v
    }
    return $null
}

$DefaultKey = 'c:\trading\arb\arb_key.pem'
if (-not $EnvFile) { $EnvFile = Join-Path $SourceRoot '.env' }
if (-not $UploadEnvFrom) { $UploadEnvFrom = $EnvFile }

$resolvedIp = $PublicIp
if (-not $resolvedIp) { $resolvedIp = $env:ARB_EC2_PUBLIC_IP }
if (-not $resolvedIp) { $resolvedIp = Get-ArbEnvFileValue -Path $EnvFile -Name 'ARB_EC2_PUBLIC_IP' }
if (-not $resolvedIp) { $resolvedIp = Get-ArbEnvFileValue -Path $EnvFile -Name 'ARB_DEPLOY_EC2_IP' }
if (-not $resolvedIp) {
    $deploySrv = Get-ArbEnvFileValue -Path $EnvFile -Name 'ARB_DEPLOY_SERVER'
    if ($deploySrv -match '@([0-9]{1,3}(?:\.[0-9]{1,3}){3})(?:\s|$)') {
        $resolvedIp = $Matches[1]
    }
}
$PublicIp = $resolvedIp

if (-not $Key) {
    $Key = Get-ArbEnvFileValue -Path $EnvFile -Name 'ARB_EC2_SSH_KEY'
}
if (-not $Key) { $Key = $DefaultKey }

if (-not $PublicIp) {
    Write-Error (
        "EC2 public IP missing. Set `$env:ARB_EC2_PUBLIC_IP, use -PublicIp, or put ARB_EC2_PUBLIC_IP in $EnvFile " +
        "(or ARB_DEPLOY_EC2_IP / ARB_DEPLOY_SERVER=ubuntu@x.x.x.x). .env.local is not read."
    )
    exit 1
}

if (-not (Test-Path -LiteralPath $Key)) {
    Write-Error "SSH key not found: $Key (set ARB_EC2_SSH_KEY in .env)"
    exit 1
}
if (-not (Test-Path -LiteralPath $SourceRoot)) {
    Write-Error "SourceRoot not found: $SourceRoot"
    exit 1
}

if (Test-Path -LiteralPath $EnvFile) {
    Write-Host "Deploy target EC2: $PublicIp (env: $EnvFile)" -ForegroundColor DarkGray
}

$stage = Join-Path $env:TEMP ("arb-ec2-stage-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    robocopy $SourceRoot $stage /E /NFL /NDL /NJH /NJS /NC /NS `
        /XF arb_key.pem *.pem *.ppk .env `
        /XD .git venv .venv .pytest_cache logs .cursor __pycache__ data node_modules .qmd | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed (exit $LASTEXITCODE)" }

    $ssh = @('-i', $Key, '-o', 'StrictHostKeyChecking=accept-new', "${User}@${PublicIp}")
    $scp = @('-i', $Key, '-o', 'StrictHostKeyChecking=accept-new')

    Write-Host "=== SSH: mkdir ~/arb ===" -ForegroundColor Cyan
    & ssh.exe @ssh 'mkdir -p ~/arb'

    # Windows OpenSSH: 대상은 ~/arb/ 가 아니라 arb/ (홈 상대). 로컬 경로는 / 슬래시 권장.
    $stageUnix = ($stage -replace '\\', '/').TrimEnd('/')
    Write-Host "=== SCP: code upload (no .env) ===" -ForegroundColor Cyan
    & scp.exe @scp -r "${stageUnix}/*" "${User}@${PublicIp}:arb/"

    Write-Host "=== SSH: chmod u+w tree ===" -ForegroundColor Cyan
    & ssh.exe @ssh 'chmod -R u+w ~/arb 2>/dev/null; true'
    Write-Host "=== SSH: strip CRLF from *.sh ===" -ForegroundColor Cyan
    & ssh.exe @ssh 'find ~/arb -name "*.sh" -type f -exec sed -i "s/\r$//" {} + 2>/dev/null; true'

    if ($UploadLocalEnv) {
        if (-not (Test-Path -LiteralPath $UploadEnvFrom)) {
            throw "UploadLocalEnv: file not found: $UploadEnvFrom"
        }
        Write-Host "=== SCP: .env upload to server ~/arb/.env ===" -ForegroundColor Cyan
        $envUnix = ($UploadEnvFrom -replace '\\', '/')
        & scp.exe @scp -p $envUnix "${User}@${PublicIp}:arb/.env"
    } else {
        Write-Warning "If ~/arb/.env is missing on server, use -UploadLocalEnv or edit .env over SSH."
    }

    Write-Host "=== SSH: setup_server.sh ===" -ForegroundColor Cyan
    & ssh.exe @ssh 'chmod +x ~/arb/scripts/*.sh && cd ~/arb && bash scripts/setup_server.sh'

    Write-Host "=== SSH: stop legacy + restart arb ===" -ForegroundColor Cyan
    & ssh.exe @ssh 'bash ~/arb/scripts/stop_legacy_trading.sh || true; sudo systemctl stop arb-v12 2>/dev/null || true; pkill -f "src\.v12\.live_v2" 2>/dev/null || true; pkill -f "src\.multi_main" 2>/dev/null || true; sleep 2; sudo systemctl daemon-reload; sudo systemctl restart arb; sleep 3; echo "=== 프로세스 확인 (1개여야 정상) ==="; ps aux | grep -E "live_v2|multi_main" | grep -v grep || echo "(없음)"; sudo systemctl status arb --no-pager'

    Write-Host "=== done ===" -ForegroundColor Green
    Write-Host "Logs: ssh ... tail -f ~/arb/logs/system.log"
}
finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
