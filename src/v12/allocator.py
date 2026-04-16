"""v1.2 dual-quote allocator: BTCUSDT leg vs BTCUSDC leg (USD numeraire).

Maps to v1 semantics: upbit_* → USDT leg, binance_* → USDC leg, fx = 1.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.strategy.capital_allocator import Action


@dataclass
class DecisionV12:
    action: Action
    symbol: str
    premium: float
    reason: str
    expected_profit_usd: float = 0.0
    rebalance_cost_usd: float = 0.0


def _estimate_rebalance_cost_usd(
    usdt: float,
    usdc: float,
    mid_usdt: float,
    mid_usdc: float,
    transfer_fee_btc: float,
    stable_move_fee_rate: float,
) -> float:
    ref_mid = 0.5 * (mid_usdt + mid_usdc)
    coin_fee_usd = transfer_fee_btc * ref_mid
    cash_convert = max(usdt, usdc)
    return coin_fee_usd + cash_convert * stable_move_fee_rate


def _rebalance_direction_by_imbalance(
    usdt: float,
    btc_ut: float,
    usdc: float,
    btc_uc: float,
    mid_usdt: float,
    mid_usdc: float,
    imbalance_threshold: float,
    target_ratio: float = 0.25,
) -> Action | None:
    total_val = usdt + usdc + btc_ut * mid_usdt + btc_uc * mid_usdc
    if total_val <= 0:
        return None
    upper = target_ratio * (1 + imbalance_threshold)
    ut_ratio = (btc_ut * mid_usdt) / total_val
    uc_ratio = (btc_uc * mid_usdc) / total_val
    if ut_ratio > upper:
        return Action.REBALANCE_U_TO_B
    if uc_ratio > upper:
        return Action.REBALANCE_B_TO_U
    return None


def decide_v12(
    symbol: str,
    mid_usdt: float,
    mid_usdc: float,
    usdt: float,
    btc_ut: float,
    usdc: float,
    btc_uc: float,
    entry_threshold_rate: float,
    fee_usdt_leg_rate: float,
    fee_usdc_leg_rate: float,
    slippage_usdt_leg_rate: float,
    slippage_usdc_leg_rate: float,
    transfer_fee_btc: float,
    stable_move_fee_rate: float,
    rebalance_profit_multiplier: float,
    rebalance_imbalance_threshold: float,
    target_portfolio_ratio: float,
    daily_rebalances: int,
    max_daily_rebalances: int,
    emergency_cash_ratio: float = 0.08,
    emergency_coin_ratio: float = 0.30,
    reverse_entry_threshold_rate: float = 0.0,
) -> DecisionV12:
    """Decide action for one bar. Premium vs USDC leg mid (reference)."""
    if mid_usdc <= 0 or mid_usdt <= 0:
        return DecisionV12(Action.HOLD, symbol, 0.0, "zero_price")

    premium = (mid_usdt - mid_usdc) / mid_usdc

    total_trade_fee_rate = (
        fee_usdt_leg_rate
        + fee_usdc_leg_rate
        + slippage_usdt_leg_rate
        + slippage_usdc_leg_rate
    )

    def _total_val() -> float:
        return usdt + usdc + btc_ut * mid_usdt + btc_uc * mid_usdc

    # ---- Positive premium: USDT leg expensive (kimchi) ----
    if premium > entry_threshold_rate:
        can_sell = btc_ut > 1e-12
        can_buy = usdc > 0.01

        if can_sell and can_buy:
            kimchi_premium = (mid_usdt - mid_usdc) / mid_usdc
            notional_usd = min(btc_ut * mid_usdt, usdc)
            expected_profit = notional_usd * (kimchi_premium - total_trade_fee_rate)
            if expected_profit > 0:
                return DecisionV12(
                    Action.TRADE_KIMCHI,
                    symbol,
                    premium,
                    "kimchi_premium_profitable",
                    expected_profit_usd=expected_profit,
                )
            return DecisionV12(Action.HOLD, symbol, premium, "kimchi_premium_fee_exceeds_profit")

        if daily_rebalances >= max_daily_rebalances:
            return DecisionV12(Action.HOLD, symbol, premium, "rebalance_daily_limit_reached")

        rebalance_action = _rebalance_direction_by_imbalance(
            usdt=usdt,
            btc_ut=btc_ut,
            usdc=usdc,
            btc_uc=btc_uc,
            mid_usdt=mid_usdt,
            mid_usdc=mid_usdc,
            imbalance_threshold=rebalance_imbalance_threshold,
            target_ratio=target_portfolio_ratio,
        )
        if rebalance_action is None:
            return DecisionV12(Action.HOLD, symbol, premium, "rebalance_not_needed_by_imbalance")

        rebalance_cost = _estimate_rebalance_cost_usd(
            usdt=usdt,
            usdc=usdc,
            mid_usdt=mid_usdt,
            mid_usdc=mid_usdc,
            transfer_fee_btc=transfer_fee_btc,
            stable_move_fee_rate=stable_move_fee_rate,
        )
        total_val = _total_val()
        next_trade_notional = total_val / 2
        expected_next_profit = next_trade_notional * (premium - total_trade_fee_rate)

        if expected_next_profit > rebalance_cost * rebalance_profit_multiplier:
            return DecisionV12(
                rebalance_action,
                symbol,
                premium,
                "rebalance_profitable",
                expected_profit_usd=expected_next_profit,
                rebalance_cost_usd=rebalance_cost,
            )

        if total_val > 0 and (usdt / total_val) < emergency_cash_ratio:
            return DecisionV12(
                rebalance_action,
                symbol,
                premium,
                "rebalance_emergency_cash_depleted_kimchi",
                rebalance_cost_usd=rebalance_cost,
            )

        return DecisionV12(Action.HOLD, symbol, premium, "rebalance_not_profitable")

    # ---- Negative premium: USDC leg expensive (reverse) ----
    _rev_threshold = reverse_entry_threshold_rate if reverse_entry_threshold_rate > 0.0 else entry_threshold_rate
    if premium < -_rev_threshold:
        can_buy = usdt > 0.01
        can_sell = btc_uc > 1e-12

        if can_buy and can_sell:
            reverse_premium = (mid_usdc - mid_usdt) / mid_usdt if mid_usdt > 0 else 0.0
            notional_usd = min(usdt, btc_uc * mid_usdc)
            expected_profit = notional_usd * (reverse_premium - total_trade_fee_rate)
            if expected_profit > 0:
                return DecisionV12(
                    Action.TRADE_REVERSE,
                    symbol,
                    premium,
                    "reverse_premium_profitable",
                    expected_profit_usd=expected_profit,
                )
            return DecisionV12(Action.HOLD, symbol, premium, "reverse_premium_fee_exceeds_profit")

        if daily_rebalances >= max_daily_rebalances:
            return DecisionV12(Action.HOLD, symbol, premium, "rebalance_daily_limit_reached")

        rebalance_action = _rebalance_direction_by_imbalance(
            usdt=usdt,
            btc_ut=btc_ut,
            usdc=usdc,
            btc_uc=btc_uc,
            mid_usdt=mid_usdt,
            mid_usdc=mid_usdc,
            imbalance_threshold=rebalance_imbalance_threshold,
            target_ratio=target_portfolio_ratio,
        )
        if rebalance_action is None:
            return DecisionV12(Action.HOLD, symbol, premium, "rebalance_not_needed_by_imbalance")

        rebalance_cost = _estimate_rebalance_cost_usd(
            usdt=usdt,
            usdc=usdc,
            mid_usdt=mid_usdt,
            mid_usdc=mid_usdc,
            transfer_fee_btc=transfer_fee_btc,
            stable_move_fee_rate=stable_move_fee_rate,
        )
        total_val = _total_val()
        next_trade_notional = total_val / 2
        expected_next_profit = next_trade_notional * (abs(premium) - total_trade_fee_rate)

        if expected_next_profit > rebalance_cost * rebalance_profit_multiplier:
            return DecisionV12(
                rebalance_action,
                symbol,
                premium,
                "rebalance_profitable",
                expected_profit_usd=expected_next_profit,
                rebalance_cost_usd=rebalance_cost,
            )

        if (
            total_val > 0
            and (usdt / total_val) < emergency_cash_ratio
            and rebalance_action is not None
        ):
            return DecisionV12(
                rebalance_action,
                symbol,
                premium,
                "rebalance_emergency_cash_depleted_reverse",
                rebalance_cost_usd=rebalance_cost,
            )

        return DecisionV12(Action.HOLD, symbol, premium, "rebalance_not_profitable")

    # ---- No signal: emergency cash (mirror v1) ----
    if daily_rebalances < max_daily_rebalances:
        total_val_inner = _total_val()
        if total_val_inner > 0:
            usdt_ratio = usdt / total_val_inner
            usdc_ratio = usdc / total_val_inner
            ut_coin_ratio = (btc_ut * mid_usdt) / total_val_inner
            uc_coin_ratio = (btc_uc * mid_usdc) / total_val_inner
            if usdt_ratio < emergency_cash_ratio and ut_coin_ratio > emergency_coin_ratio:
                return DecisionV12(Action.REBALANCE_U_TO_B, symbol, premium, "cash_depleted_usdt_leg")
            if usdc_ratio < emergency_cash_ratio and uc_coin_ratio > emergency_coin_ratio:
                return DecisionV12(Action.REBALANCE_B_TO_U, symbol, premium, "cash_depleted_usdc_leg")

    return DecisionV12(Action.HOLD, symbol, premium, "below_threshold")
