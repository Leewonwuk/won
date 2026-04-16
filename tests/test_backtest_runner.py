from pathlib import Path

from src.backtest.backtest_runner import run_backtest_from_csv


def test_backtest_runner_smoke(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "\n".join(
            [
                "ts,upbit_close_krw,binance_close_usdt,usdtkrw_close",
                "2026-01-01T00:00:00+00:00,220000,162.5,1350",
                "2026-01-01T00:05:00+00:00,221000,162.0,1350",
                "2026-01-01T00:10:00+00:00,220500,162.3,1350",
            ]
        ),
        encoding="utf-8",
    )
    result = run_backtest_from_csv(
        csv_path=str(csv_path),
        symbol="SOL",
        trade_size_base=20.0,
        entry_threshold_rate=0.0001,
        exit_threshold_rate=0.00005,
        fee_upbit_rate=0.0,
        fee_binance_rate=0.0,
        slippage_upbit_rate=0.0,
        slippage_binance_rate=0.0,
        transfer_fee_upbit_to_binance_base=0.0,
        transfer_fee_binance_to_upbit_base=0.0,
    )
    assert result.rows == 3
    assert result.start_equity_krw == 2_000_000

