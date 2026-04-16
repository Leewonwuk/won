"""Compatibility entry — v1.2 백테스트 CLI는 ``src.v12.cli_backtest``.

권장: ``python -m src.v12 --config configs/v12/v12_btc_dual.yaml ...``
"""
from src.v12.cli_backtest import main

if __name__ == "__main__":
    main()
