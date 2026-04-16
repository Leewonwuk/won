from __future__ import annotations

from dataclasses import dataclass
import time

from src.models import EdgeResult, SignalDecision


@dataclass(slots=True)
class SignalEngine:
    entry_threshold_rate: float
    exit_threshold_rate: float
    cooldown_sec: int
    max_position_hold_sec: float = 0.0

    _last_action_ts: float = 0.0

    def decide(
        self,
        edge: EdgeResult,
        has_open_position: bool,
        position_open_at: float | None = None,
    ) -> SignalDecision:
        now = time.time()
        best_open_edge = max(edge.upbit_to_binance_edge_rate, edge.binance_to_upbit_edge_rate)

        if has_open_position and self.max_position_hold_sec > 0 and position_open_at is not None:
            if now - position_open_at >= self.max_position_hold_sec:
                self._last_action_ts = now
                return SignalDecision(
                    action="CLOSE",
                    reason="max_hold_time_exceeded",
                    edge_rate=best_open_edge,
                )

        if (now - self._last_action_ts) < self.cooldown_sec:
            return SignalDecision(action="HOLD", reason="cooldown")

        if not has_open_position:
            if edge.upbit_to_binance_edge_rate >= self.entry_threshold_rate:
                self._last_action_ts = now
                return SignalDecision(
                    action="OPEN_UPBIT_SHORT_BINANCE_LONG",
                    reason="entry_threshold_hit",
                    edge_rate=edge.upbit_to_binance_edge_rate,
                )
            if edge.binance_to_upbit_edge_rate >= self.entry_threshold_rate:
                self._last_action_ts = now
                return SignalDecision(
                    action="OPEN_UPBIT_LONG_BINANCE_SHORT",
                    reason="entry_threshold_hit",
                    edge_rate=edge.binance_to_upbit_edge_rate,
                )
            return SignalDecision(action="HOLD", reason="entry_not_met", edge_rate=best_open_edge)

        # Position is open: close when edge mean-reverts.
        if best_open_edge <= self.exit_threshold_rate:
            self._last_action_ts = now
            return SignalDecision(action="CLOSE", reason="exit_threshold_hit", edge_rate=best_open_edge)
        return SignalDecision(action="HOLD", reason="hold_open_position", edge_rate=best_open_edge)

