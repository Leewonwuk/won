from src.execution.live_engine import LiveExecutionEngine
from src.execution.paper_engine import PaperExecutionEngine
from src.execution.router import ExecutionRouter
from src.models import EdgeResult, SignalDecision
from src.state.portfolio import PortfolioState


class DummyUpbit:
    def place_market_sell(self, market: str, size_base: float) -> dict:
        return {"exchange": "upbit", "market": market, "qty": size_base}

    def place_market_buy(self, market: str, quote_amount_krw: float) -> dict:
        return {"exchange": "upbit", "market": market, "quote": quote_amount_krw}


class DummyBinance:
    def place_market_order(self, symbol: str, side: str, quantity: float) -> dict:
        return {"exchange": "binance", "symbol": symbol, "side": side, "qty": quantity}


def _edge() -> EdgeResult:
    return EdgeResult(
        symbol="BTC",
        upbit_to_binance_edge_rate=0.005,
        binance_to_upbit_edge_rate=-0.001,
        upbit_to_binance_transfer_fee_rate=0.0,
        binance_to_upbit_transfer_fee_rate=0.0,
        upbit_mid_krw=140_000_000,
        binance_mid_krw=139_000_000,
        fx_krw_per_usdt=1350.0,
    )


def test_live_router_dry_run() -> None:
    portfolio = PortfolioState()
    live = LiveExecutionEngine(
        upbit=DummyUpbit(),
        binance=DummyBinance(),
        upbit_market="KRW-BTC",
        binance_symbol="BTCUSDT",
        dry_run=True,
    )
    router = ExecutionRouter(
        mode="live",
        enable_live_orders=True,
        paper_engine=PaperExecutionEngine(portfolio=portfolio),
        live_engine=live,
    )
    result = router.execute(
        SignalDecision(action="OPEN_UPBIT_SHORT_BINANCE_LONG", reason="test", edge_rate=0.01),
        _edge(),
        0.001,
    )
    assert result["live_result"]["status"] == "LIVE_DRY_RUN"
    assert len(result["live_result"]["details"]) == 2
    assert result["paper_result"]["status"] == "OPENED"
    assert portfolio.is_open is True


def test_live_router_close_uses_position_direction() -> None:
    portfolio = PortfolioState()
    portfolio.open_position(
        direction="UPBIT_SHORT_BINANCE_LONG",
        size_base=0.001,
        upbit_price_krw=140_000_000,
        binance_price_krw=139_000_000,
    )
    live = LiveExecutionEngine(
        upbit=DummyUpbit(),
        binance=DummyBinance(),
        upbit_market="KRW-BTC",
        binance_symbol="BTCUSDT",
        dry_run=True,
    )
    router = ExecutionRouter(
        mode="live",
        enable_live_orders=True,
        paper_engine=PaperExecutionEngine(portfolio=portfolio),
        live_engine=live,
    )
    result = router.execute(SignalDecision(action="CLOSE", reason="test"), _edge(), 0.001)
    assert result["live_result"]["status"] == "LIVE_DRY_RUN"
    assert result["paper_result"]["status"] == "CLOSED"
    assert portfolio.is_open is False

