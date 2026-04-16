from src.state.multi_portfolio import RebalancePortfolio


def _init_portfolio() -> RebalancePortfolio:
    p = RebalancePortfolio()
    p.init_coin(
        symbol="SOL",
        upbit_krw=150_000,
        upbit_coin=1.0,
        binance_usdt=100.0,
        binance_coin=0.5,
    )
    return p


def test_execute_kimchi_trade_mutates_balances() -> None:
    p = _init_portfolio()
    event = p.execute_kimchi_trade(
        symbol="SOL",
        upbit_price_krw=220_000,
        binance_price_usdt=160,
        fx=1350,
        fee_upbit_rate=0.0005,
        fee_binance_rate=0.0004,
        slippage_upbit_rate=0.0008,
        slippage_binance_rate=0.0008,
    )
    b = p.get("SOL")
    assert event.event == "TRADE_KIMCHI"
    assert b.upbit_coin == 0.0
    assert b.binance_usdt == 0.0
    assert b.total_trades == 1


def test_execute_reverse_trade_mutates_balances() -> None:
    p = _init_portfolio()
    event = p.execute_reverse_trade(
        symbol="SOL",
        upbit_price_krw=220_000,
        binance_price_usdt=160,
        fx=1350,
        fee_upbit_rate=0.0005,
        fee_binance_rate=0.0004,
        slippage_upbit_rate=0.0008,
        slippage_binance_rate=0.0008,
    )
    b = p.get("SOL")
    assert event.event == "TRADE_REVERSE"
    assert b.upbit_krw == 0.0
    assert b.binance_coin == 0.0
    assert b.total_trades == 1


def test_execute_rebalance_counts_and_fees() -> None:
    p = _init_portfolio()
    event = p.execute_rebalance(
        symbol="SOL",
        upbit_price_krw=220_000,
        binance_price_usdt=160,
        fx=1350,
        transfer_fee_coin_base=0.01,
        fx_conversion_fee_rate=0.001,
        direction="upbit_to_binance",
    )
    b = p.get("SOL")
    assert event.event == "REBALANCE"
    assert b.total_rebalances == 1
    assert b.daily_rebalances == 1
    assert b.realized_fee_krw > 0
