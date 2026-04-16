from src.strategy.capital_allocator import Action, decide


def test_trade_kimchi_when_profitable_and_balances_ready() -> None:
    decision = decide(
        symbol="SOL",
        upbit_price_krw=220_000,
        binance_price_usdt=160,
        fx=1350,
        upbit_krw=0.0,
        upbit_coin=1.0,
        binance_usdt=200.0,
        binance_coin=0.0,
        entry_threshold_rate=0.003,
        fee_upbit_rate=0.0005,
        fee_binance_rate=0.0004,
        slippage_upbit_rate=0.0008,
        slippage_binance_rate=0.0008,
        transfer_fee_coin_base=0.01,
        fx_conversion_fee_rate=0.001,
        rebalance_profit_multiplier=2.0,
        rebalance_imbalance_threshold=0.15,
        daily_rebalances=0,
        max_daily_rebalances=3,
    )
    assert decision.action == Action.TRADE_KIMCHI


def test_rebalance_when_signal_exists_but_cannot_trade() -> None:
    decision = decide(
        symbol="TRX",
        upbit_price_krw=200,
        binance_price_usdt=0.14,
        fx=1350,
        upbit_krw=100_000.0,
        upbit_coin=0.0,  # cannot sell on upbit in kimchi direction
        binance_usdt=0.0,  # cannot buy on binance in kimchi direction
        binance_coin=5_000.0,
        entry_threshold_rate=0.003,
        fee_upbit_rate=0.0005,
        fee_binance_rate=0.0004,
        slippage_upbit_rate=0.0008,
        slippage_binance_rate=0.0008,
        transfer_fee_coin_base=1.0,
        fx_conversion_fee_rate=0.001,
        rebalance_profit_multiplier=1.2,
        rebalance_imbalance_threshold=0.15,
        daily_rebalances=0,
        max_daily_rebalances=3,
    )
    assert decision.action in (Action.REBALANCE_B_TO_U, Action.REBALANCE_U_TO_B)


def test_daily_rebalance_limit_blocks_rebalance() -> None:
    decision = decide(
        symbol="SOL",
        upbit_price_krw=220_000,
        binance_price_usdt=150,
        fx=1350,
        upbit_krw=100_000.0,
        upbit_coin=0.0,
        binance_usdt=0.0,
        binance_coin=0.0,
        entry_threshold_rate=0.003,
        fee_upbit_rate=0.0005,
        fee_binance_rate=0.0004,
        slippage_upbit_rate=0.0008,
        slippage_binance_rate=0.0008,
        transfer_fee_coin_base=0.01,
        fx_conversion_fee_rate=0.001,
        rebalance_profit_multiplier=1.0,
        rebalance_imbalance_threshold=0.15,
        daily_rebalances=3,
        max_daily_rebalances=3,
    )
    assert decision.action == Action.HOLD
    assert decision.reason == "rebalance_daily_limit_reached"
