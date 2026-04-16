from src.models import OrderBookTop, SpreadInput
from src.strategy.signal import SignalEngine
from src.strategy.spread_calc import calc_edge


def test_calc_edge_applies_costs() -> None:
    snapshot = SpreadInput(
        upbit_krw=OrderBookTop(exchange="upbit", symbol="KRW-BTC", bid=141000000, ask=141020000, ts="t"),
        binance_usdt=OrderBookTop(exchange="binance", symbol="BTCUSDT", bid=104000, ask=104010, ts="t"),
        fx_krw_per_usdt=1350.0,
        fee_upbit_rate=0.0005,
        fee_binance_rate=0.0004,
        slippage_upbit_rate=0.0007,
        slippage_binance_rate=0.0007,
    )
    edge = calc_edge(
        snapshot,
        symbol="BTC",
        trade_size_base=0.001,
        transfer_fee_upbit_to_binance_base=0.0,
        transfer_fee_binance_to_upbit_base=0.0,
    )
    assert edge.upbit_to_binance_edge_rate < 0.01
    assert edge.binance_to_upbit_edge_rate < 0.01


def test_calc_edge_reduces_when_transfer_fee_applied() -> None:
    snapshot = SpreadInput(
        upbit_krw=OrderBookTop(exchange="upbit", symbol="KRW-SOL", bid=220000, ask=220500, ts="t"),
        binance_usdt=OrderBookTop(exchange="binance", symbol="SOLUSDT", bid=162.8, ask=163.0, ts="t"),
        fx_krw_per_usdt=1350.0,
        fee_upbit_rate=0.0005,
        fee_binance_rate=0.0004,
        slippage_upbit_rate=0.0007,
        slippage_binance_rate=0.0007,
    )
    edge_no_transfer = calc_edge(snapshot, symbol="SOL", trade_size_base=20.0)
    edge_with_transfer = calc_edge(
        snapshot,
        symbol="SOL",
        trade_size_base=20.0,
        transfer_fee_upbit_to_binance_base=0.01,
        transfer_fee_binance_to_upbit_base=0.01,
    )
    assert edge_with_transfer.upbit_to_binance_edge_rate < edge_no_transfer.upbit_to_binance_edge_rate
    assert edge_with_transfer.binance_to_upbit_edge_rate < edge_no_transfer.binance_to_upbit_edge_rate


def test_signal_entry_and_hold() -> None:
    engine = SignalEngine(entry_threshold_rate=0.003, exit_threshold_rate=0.0005, cooldown_sec=0)
    dummy_edge = type(
        "Edge",
        (),
        {"upbit_to_binance_edge_rate": 0.004, "binance_to_upbit_edge_rate": -0.001},
    )()
    decision = engine.decide(dummy_edge, has_open_position=False)
    assert decision.action == "OPEN_UPBIT_SHORT_BINANCE_LONG"

    hold_decision = engine.decide(dummy_edge, has_open_position=True)
    assert hold_decision.action == "HOLD"


def test_signal_max_hold_forces_close() -> None:
    from unittest.mock import patch

    engine = SignalEngine(
        entry_threshold_rate=0.003,
        exit_threshold_rate=0.0005,
        cooldown_sec=0,
        max_position_hold_sec=1.0,
    )
    # Large edge would normally hold_open_position
    dummy_edge = type(
        "Edge",
        (),
        {"upbit_to_binance_edge_rate": 0.05, "binance_to_upbit_edge_rate": -0.001},
    )()
    with patch("src.strategy.signal.time") as mock_time:
        mock_time.time.return_value = 1000.0
        d = engine.decide(dummy_edge, has_open_position=True, position_open_at=998.0)
    assert d.action == "CLOSE"
    assert d.reason == "max_hold_time_exceeded"

