"""Run v2 multi backtests with short windows first (7d, 14d, 21d), then sanity (30d, optional 60d).

Usage:
    python -m src.tools.run_short_window_backtests --config configs/multi.yaml
    python -m src.tools.run_short_window_backtests --windows 7,14 --sanity 30 --also-60
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Short-window-first backtest batch (v2 multi)")
    p.add_argument("--config", default="configs/multi.yaml")
    p.add_argument(
        "--windows",
        default="7,14,21",
        help="Primary lookback days (comma-separated), e.g. 7,14,21",
    )
    p.add_argument(
        "--sanity",
        default="30",
        help="Sanity lookback days (comma-separated), e.g. 30 or 30,60",
    )
    p.add_argument("--resolution", type=int, default=1, help="Candle minutes (1 or 5)")
    p.add_argument(
        "--no-skip-collect",
        dest="skip_collect",
        action="store_false",
        help="Force fresh REST collection (default: reuse latest CSV per coin)",
    )
    p.set_defaults(skip_collect=True)
    p.add_argument("--also-60", action="store_true", help="Append 60d to sanity windows")
    return p.parse_args()


def _parse_ints(s: str) -> list[int]:
    out: list[int] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    return out


def _run_one(
    *,
    config: str,
    days: int,
    resolution: int,
    skip_collect: bool,
) -> int:
    root = Path(__file__).resolve().parents[2]
    cmd = [
        sys.executable,
        "-m",
        "src.backtest_v2_main",
        "--config",
        config,
        "--days",
        str(days),
        "--resolution",
        str(resolution),
    ]
    if skip_collect:
        cmd.append("--skip-collect")
    print(f"\n>>> {' '.join(cmd)}\n", flush=True)
    return subprocess.call(cmd, cwd=str(root))


def main() -> None:
    args = parse_args()
    skip = args.skip_collect
    primary = _parse_ints(args.windows)
    sanity = _parse_ints(args.sanity)
    if args.also_60 and 60 not in sanity:
        sanity.append(60)

    if not primary and not sanity:
        print("No windows to run.", file=sys.stderr)
        sys.exit(1)

    exit_code = 0
    for label, days_list in (("primary", primary), ("sanity", sanity)):
        if not days_list:
            continue
        print(f"\n{'='*60}\n [{label.upper()}] windows: {days_list}\n{'='*60}")
        for d in days_list:
            code = _run_one(
                config=args.config,
                days=d,
                resolution=args.resolution,
                skip_collect=skip,
            )
            if code != 0:
                exit_code = code
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
