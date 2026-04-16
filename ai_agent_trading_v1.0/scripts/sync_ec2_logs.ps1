# EC2 로그 동기화 스크립트
# Windows 작업 스케줄러에 등록해서 5분마다 자동 실행 권장
#
# 수동 실행: powershell -ExecutionPolicy Bypass -File scripts\sync_ec2_logs.ps1

param(
    [string]$Ip    = "52.78.108.174",
    [string]$Key   = "c:\Users\user\.ssh\arb_key_tokyo.pem",
    [string]$User  = "ubuntu",
    [string]$Local = "C:\Users\user\trading\arb\logs",
    [switch]$RegisterTask,
    [string]$TaskName = "ArbLogSync",
    [int]$IntervalMinutes = 5
)

$remote = "${User}@${Ip}:~/arb/logs/"

Write-Host "[$(Get-Date -Format 'HH:mm:ss')] EC2 로그 동기화 시작 ($Ip)" -ForegroundColor Cyan

try {
    if ($RegisterTask) {
        $arg = "-ExecutionPolicy Bypass -File `"$PSCommandPath`" -Ip `"$Ip`" -Key `"$Key`" -User `"$User`" -Local `"$Local`""
        $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arg
        $trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -Once -At (Get-Date)
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -RunLevel Highest -Force | Out-Null
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 작업 스케줄러 등록 완료: $TaskName (매 $IntervalMinutes분)" -ForegroundColor Green
        return
    }

    # logs 폴더가 없으면 생성
    if (-not (Test-Path $Local)) { New-Item -ItemType Directory -Path $Local | Out-Null }

    # scp로 EC2 logs 폴더 전체 내려받기
    & scp.exe -i $Key `
        -o StrictHostKeyChecking=no `
        -o ConnectTimeout=10 `
        "${remote}*" $Local 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 동기화 완료" -ForegroundColor Green
    } else {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 동기화 실패 (exit $LASTEXITCODE)" -ForegroundColor Red
    }
} catch {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 오류: $_" -ForegroundColor Red
}
