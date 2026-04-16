from __future__ import annotations

from dataclasses import dataclass

from src.models import EdgeResult, SignalDecision
from src.state.portfolio import PortfolioState


@dataclass(slots=True)
class PaperExecutionEngine:
    portfolio: PortfolioState

    def execute(self, decision: SignalDecision, edge: EdgeResult, size_base: float) -> dict:
        if decision.action == "OPEN_UPBIT_SHORT_BINANCE_LONG" and not self.portfolio.is_open:
            self.portfolio.open_position(
                direction="UPBIT_SHORT_BINANCE_LONG",
                size_base=size_base,
                upbit_price_krw=edge.upbit_mid_krw,
                binance_price_krw=edge.binance_mid_krw,
            )
            return {"status": "OPENED", "direction": self.portfolio.direction, "pnl_delta_krw": 0.0}

        if decision.action == "OPEN_UPBIT_LONG_BINANCE_SHORT" and not self.portfolio.is_open:
            self.portfolio.open_position(
                direction="UPBIT_LONG_BINANCE_SHORT",
                size_base=size_base,
                upbit_price_krw=edge.upbit_mid_krw,
                binance_price_krw=edge.binance_mid_krw,
            )
            return {"status": "OPENED", "direction": self.portfolio.direction, "pnl_delta_krw": 0.0}

        if decision.action == "CLOSE" and self.portfolio.is_open:
            pnl = self.portfolio.close_position(
                upbit_price_krw=edge.upbit_mid_krw,
                binance_price_krw=edge.binance_mid_krw,
            )
            return {"status": "CLOSED", "direction": "NONE", "pnl_delta_krw": pnl}

        return {"status": "NOOP", "direction": self.portfolio.direction, "pnl_delta_krw": 0.0}

