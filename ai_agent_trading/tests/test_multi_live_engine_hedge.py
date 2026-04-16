"""Hedge-failure paths in MultiLiveExecutionEngine (mocked exchanges)."""
from __future__ import annotations

from unittest.mock import MagicMock

from src.config import CoinConfig
from src.execution.multi_live_engine import MultiLiveExecutionEngine
from src.state.multi_portfolio import CoinBalance


def _coin() -> CoinConfig:
    return CoinConfig(symbol="TRX", upbit_market="KRW-TRX", binance_symbol="TRXUSDT")


def _balance_kimchi() -> CoinBalance:
    return CoinBalance(symbol="TRX", upbit_krw=0.0, upbit_coin=100.0, binance_usdt=50.0, binance_coin=0.0)


def _balance_reverse() -> CoinBalance:
    return CoinBalance(symbol="TRX", upbit_krw=150_000.0, upbit_coin=0.0, binance_usdt=0.0, binance_coin=80.0)


def test_kimchi_binance_fails_recovery_succeeds() -> None:
    up = MagicMock()
    bn = MagicMock()
    bn.normalize_market_quantity.side_effect = lambda _sym, qty: float(qty)
    up.place_market_sell.return_value = {
        "uuid": "sell-1",
        "executed_volume": "100",
        "avg_price": "400",
    }
    up.get_order.return_value = {
        "uuid": "sell-1",
        "executed_volume": "100",
        "avg_price": "400",
    }
    bn.place_market_order.side_effect = RuntimeError("binance down")
    up.place_market_buy.return_value = {"uuid": "buy-back-1"}

    eng = MultiLiveExecutionEngine(upbit=up, binance=bn, dry_run=False)
    res = eng.execute_kimchi(_coin(), _balance_kimchi(), expected_upbit_price_krw=400.0, expected_binance_price_usdt=0.3)

    assert res["status"] == "LIVE_ERROR_HEDGE_RECOVERED"
    assert res["recovered"] is True
    assert res["hedge_incomplete"] is True
    up.place_market_sell.assert_called_once()
    bn.place_market_order.assert_called_once()
    up.place_market_buy.assert_called_once()


def test_kimchi_binance_fails_recovery_fails_halt() -> None:
    up = MagicMock()
    bn = MagicMock()
    bn.normalize_market_quantity.side_effect = lambda _sym, qty: float(qty)
    up.place_market_sell.return_value = {
        "uuid": "sell-2",
        "executed_volume": "100",
        "avg_price": "400",
    }
    up.get_order.return_value = {
        "executed_volume": "100",
        "avg_price": "400",
    }
    bn.place_market_order.side_effect = RuntimeError("binance down")
    up.place_market_buy.side_effect = RuntimeError("recovery failed")

    eng = MultiLiveExecutionEngine(upbit=up, binance=bn, dry_run=False)
    res = eng.execute_kimchi(_coin(), _balance_kimchi())

    assert res["status"] == "LIVE_HALT"
    assert res["recovered"] is False
    assert res["hedge_incomplete"] is True


def test_reverse_binance_fails_recovery_succeeds() -> None:
    up = MagicMock()
    bn = MagicMock()
    bn.normalize_market_quantity.side_effect = lambda _sym, qty: float(qty)
    up.place_market_buy.return_value = {
        "uuid": "buy-1",
        "executed_volume": "50",
        "avg_price": "3000",
    }
    up.get_order.return_value = {
        "executed_volume": "50",
        "avg_price": "3000",
    }
    bn.place_market_order.side_effect = RuntimeError("binance reject")
    up.place_market_sell.return_value = {"uuid": "sell-back-1"}

    eng = MultiLiveExecutionEngine(upbit=up, binance=bn, dry_run=False)
    res = eng.execute_reverse(_coin(), _balance_reverse())

    assert res["status"] == "LIVE_ERROR_HEDGE_RECOVERED"
    assert res["recovered"] is True
    bn.place_market_order.assert_called_once()
    up.place_market_sell.assert_called_once()


def test_reverse_binance_fails_recovery_fails_halt() -> None:
    up = MagicMock()
    bn = MagicMock()
    bn.normalize_market_quantity.side_effect = lambda _sym, qty: float(qty)
    up.place_market_buy.return_value = {
        "uuid": "buy-2",
        "executed_volume": "50",
        "avg_price": "3000",
    }
    up.get_order.return_value = {
        "executed_volume": "50",
        "avg_price": "3000",
    }
    bn.place_market_order.side_effect = RuntimeError("binance reject")
    up.place_market_sell.side_effect = RuntimeError("cannot sell back")

    eng = MultiLiveExecutionEngine(upbit=up, binance=bn, dry_run=False)
    res = eng.execute_reverse(_coin(), _balance_reverse())

    assert res["status"] == "LIVE_HALT"
    assert res["recovered"] is False
