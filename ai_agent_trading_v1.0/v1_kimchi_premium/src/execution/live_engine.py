from __future__ import annotations

from dataclasses import dataclass

from src.exchanges.binance_trading_client import BinanceTradingClient
from src.exchanges.upbit_trading_client import UpbitTradingClient
from src.models import EdgeResult, SignalDecision
from src.state.portfolio import PortfolioState


@dataclass(slots=True)
class LiveExecutionEngine:
    upbit: UpbitTradingClient
    binance: BinanceTradingClient
    upbit_market: str
    binance_symbol: str
    dry_run: bool = True

    def _dry_order(self, exchange: str, side: str, symbol: str, qty_or_quote: float) -> dict:
        return {
            "exchange": exchange,
            "side": side,
            "symbol": symbol,
            "qty_or_quote": qty_or_quote,
            "mode": "dry_run",
        }

    def preflight_check(self) -> dict:
        if self.dry_run:
            return {"status": "LIVE_DRY_RUN_PREFLIGHT", "checks": ["credentials_loaded"]}
        upbit_accounts = self.upbit.get_accounts()
        binance_account = self.binance.get_account()
        return {
            "status": "LIVE_PREFLIGHT_OK",
            "upbit_accounts_count": len(upbit_accounts),
            "binance_permissions": binance_account.get("permissions", []),
        }

    def execute(self, decision: SignalDecision, edge: EdgeResult, size_base: float) -> dict:
        if decision.action == "HOLD":
            return {"status": "NOOP", "details": []}

        if decision.action == "OPEN_UPBIT_SHORT_BINANCE_LONG":
            if self.dry_run:
                return {
                    "status": "LIVE_DRY_RUN",
                    "details": [
                        self._dry_order("upbit", "sell", self.upbit_market, size_base),
                        self._dry_order("binance", "buy", self.binance_symbol, size_base),
                    ],
                }
            upbit_order = self.upbit.place_market_sell(self.upbit_market, size_base)
            binance_order = self.binance.place_market_order(self.binance_symbol, "BUY", size_base)
            return {"status": "LIVE_EXECUTED", "details": [upbit_order, binance_order]}

        if decision.action == "OPEN_UPBIT_LONG_BINANCE_SHORT":
            if self.dry_run:
                return {
                    "status": "LIVE_DRY_RUN",
                    "details": [
                        self._dry_order("upbit", "buy_quote", self.upbit_market, edge.upbit_mid_krw * size_base),
                        self._dry_order("binance", "sell", self.binance_symbol, size_base),
                    ],
                }
            upbit_order = self.upbit.place_market_buy(self.upbit_market, edge.upbit_mid_krw * size_base)
            binance_order = self.binance.place_market_order(self.binance_symbol, "SELL", size_base)
            return {"status": "LIVE_EXECUTED", "details": [upbit_order, binance_order]}

        if decision.action == "CLOSE":
            return {"status": "LIVE_CLOSE_PENDING", "details": []}

        return {"status": "UNSUPPORTED_ACTION", "details": []}

    def execute_close_by_position(self, portfolio: PortfolioState, edge: EdgeResult) -> dict:
        if not portfolio.is_open:
            return {"status": "NO_POSITION", "details": []}

        size_base = portfolio.size_base
        if portfolio.direction == "UPBIT_SHORT_BINANCE_LONG":
            if self.dry_run:
                return {
                    "status": "LIVE_DRY_RUN",
                    "details": [
                        self._dry_order("upbit", "buy_quote", self.upbit_market, edge.upbit_mid_krw * size_base),
                        self._dry_order("binance", "sell", self.binance_symbol, size_base),
                    ],
                }
            upbit_order = self.upbit.place_market_buy(self.upbit_market, edge.upbit_mid_krw * size_base)
            binance_order = self.binance.place_market_order(self.binance_symbol, "SELL", size_base)
            return {"status": "LIVE_EXECUTED", "details": [upbit_order, binance_order]}

        if portfolio.direction == "UPBIT_LONG_BINANCE_SHORT":
            if self.dry_run:
                return {
                    "status": "LIVE_DRY_RUN",
                    "details": [
                        self._dry_order("upbit", "sell", self.upbit_market, size_base),
                        self._dry_order("binance", "buy", self.binance_symbol, size_base),
                    ],
                }
            upbit_order = self.upbit.place_market_sell(self.upbit_market, size_base)
            binance_order = self.binance.place_market_order(self.binance_symbol, "BUY", size_base)
            return {"status": "LIVE_EXECUTED", "details": [upbit_order, binance_order]}

        return {"status": "UNKNOWN_POSITION_DIRECTION", "details": [portfolio.direction]}

