from __future__ import annotations

from dataclasses import dataclass

from src.config import RiskConfig
from src.models import EdgeResult, SignalDecision
from src.state.portfolio import PortfolioState


@dataclass(slots=True)
class RiskGuard:
    config: RiskConfig

    def check(
        self,
        decision: SignalDecision,
        edge: EdgeResult,
        portfolio: PortfolioState,
        size_base: float,
    ) -> tuple[bool, str]:
        if decision.action.startswith("OPEN") and portfolio.is_open:
            return False, "already_open"

        if decision.action.startswith("OPEN"):
            notional = edge.upbit_mid_krw * size_base
            if notional > self.config.max_notional_krw:
                return False, "max_notional_exceeded"

        if portfolio.realized_pnl_krw <= -self.config.max_daily_loss_krw:
            return False, "max_daily_loss_reached"

        return True, "ok"

