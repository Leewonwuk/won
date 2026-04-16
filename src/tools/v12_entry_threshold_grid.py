"""Compatibility entry — v1.2 임계값 그리드는 ``src.v12.entry_grid``.

권장: ``python -m src.v12.entry_grid --config configs/v12/v12_btc_dual.yaml ...``
"""
from src.v12.entry_grid import (
    DEFAULT_CANDIDATES,
    diagnose_premium_range,
    main,
    run_grid,
    select_best,
    select_best_any_trades,
    select_best_relaxed,
)

__all__ = [
    "DEFAULT_CANDIDATES",
    "diagnose_premium_range",
    "main",
    "run_grid",
    "select_best",
    "select_best_any_trades",
    "select_best_relaxed",
]

if __name__ == "__main__":
    main()
