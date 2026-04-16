from src.backtest.v12_config import V12Config
from src.backtest.v12_price_util import v12_leg_mids


def test_hl_mid_uses_range_average() -> None:
    row = {
        "btc_usdt_close": "100000",
        "btc_usdc_close": "100000",
        "btc_usdt_high": "102000",
        "btc_usdt_low": "98000",
        "btc_usdc_high": "100500",
        "btc_usdc_low": "99500",
    }
    cfg = V12Config(price_mode="hl_mid")
    ut, uc = v12_leg_mids(row, cfg)
    assert ut == 100000.0
    assert uc == 100000.0


def test_close_mode_ignores_high_low() -> None:
    row = {
        "btc_usdt_close": "99000",
        "btc_usdc_close": "100000",
        "btc_usdt_high": "200000",
        "btc_usdt_low": "1",
        "btc_usdc_high": "200000",
        "btc_usdc_low": "1",
    }
    cfg = V12Config(price_mode="close")
    ut, uc = v12_leg_mids(row, cfg)
    assert ut == 99000.0
    assert uc == 100000.0
