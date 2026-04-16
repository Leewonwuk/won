@echo off
setlocal
cd /d "C:\Users\user\trading\arb"

echo [AUTO-RESTART] TRX tick live runner
:loop
python -m src.main --config configs/trx_tiny_live.yaml
set EXITCODE=%ERRORLEVEL%
echo [RESTART] exit code=%EXITCODE%, restart in 5 sec...
timeout /t 5 /nobreak > nul
goto loop

endlocal
