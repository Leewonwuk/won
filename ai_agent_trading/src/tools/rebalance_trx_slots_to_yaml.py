"""Backward-compatible entry: same as `rebalance_coin_slots_to_yaml --symbol TRX`."""
from __future__ import annotations

import sys

# Insert --symbol TRX after script name if not already present
if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--all" not in argv and not any(a == "--symbol" for a in argv):
        sys.argv = [sys.argv[0], "--symbol", "TRX", *argv]
    from src.tools.rebalance_coin_slots_to_yaml import main

    main()
