@echo off
setlocal
cd /d "C:\Users\user\trading\arb"

echo [START] TRX tick live runner
python -m src.main --config configs/trx_tiny_live.yaml

endlocal
