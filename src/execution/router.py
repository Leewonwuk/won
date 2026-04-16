from __future__ import annotations

from dataclasses import dataclass

from src.execution.live_engine import LiveExecutionEngine
from src.execution.paper_engine import PaperExecutionEngine
from src.models import EdgeResult, SignalDecision


@dataclass(slots=True)
class ExecutionRouter:
    mode: str
    enable_live_orders: bool
    paper_engine: PaperExecutionEngine
    live_engine: LiveExecutionEngine | None = None

    def execute(self, decision: SignalDecision, edge: EdgeResult, size_base: float) -> dict:
        if self.mode == "paper":
            return self.paper_engine.execute(decision, edge, size_base)

        if self.mode == "live":
            if not self.enable_live_orders:
                raise RuntimeError("live mode disabled: set enable_live_orders=true")
            if self.live_engine is None:
                raise RuntimeError("live_engine is required in live mode")
            # Keep a shadow portfolio/PnL state in live mode.
            if decision.action == "CLOSE":
                live_result = self.live_engine.execute_close_by_position(self.paper_engine.portfolio, edge)
            else:
                live_result = self.live_engine.execute(decision, edge, size_base)

            paper_result = self.paper_engine.execute(decision, edge, size_base)
            return {"live_result": live_result, "paper_result": paper_result}

        raise ValueError(f"unsupported mode: {self.mode}")

