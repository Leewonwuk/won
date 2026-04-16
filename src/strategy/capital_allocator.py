"""Capital allocator: decides trade/rebalance actions per coin per tick.

Decision flow per coin:
  1. Compute premium
     - 김프 수익성: 바이낸스 ask 기준 (실제 매수 체결가)
     - 역프 수익성: 바이낸스 bid 기준 (실제 매도 체결가)
     - 임계값 비교: mid price 기준 (방향 중립)
  2. If premium > threshold AND can trade → TRADE
  3. If can't trade (no coin/cash) AND premium > threshold → evaluate REBALANCE
  4. Rebalance only if expected_profit > rebalance_cost × multiplier
     - 리밸런싱 수수료는 방향(U→B / B→U)에 맞는 값 사용
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Action(str, Enum):
    HOLD = "HOLD"
    TRADE_KIMCHI = "TRADE_KIMCHI"           # 김프: sell upbit, buy binance
    TRADE_REVERSE = "TRADE_REVERSE"         # 역프: buy upbit, sell binance
    REBALANCE_B_TO_U = "REBALANCE_B_TO_U"  # coin Binance→Upbit, cash Upbit→Binance
    REBALANCE_U_TO_B = "REBALANCE_U_TO_B"  # coin Upbit→Binance, cash Binance→Upbit


@dataclass
class Decision:
    action: Action
    symbol: str
    premium: float
    reason: str
    expected_profit_krw: float = 0.0
    rebalance_cost_krw: float = 0.0


def decide(
    symbol: str,
    upbit_price_krw: float,
    binance_bid_price_usdt: float,          # 바이낸스 매도호가 (역프 수익성 + 임계값 기준)
    fx: float,
    # balances
    upbit_krw: float,
    upbit_coin: float,
    binance_usdt: float,
    binance_coin: float,
    # params
    entry_threshold_rate: float,
    fee_upbit_rate: float,
    fee_binance_rate: float,
    slippage_upbit_rate: float,
    slippage_binance_rate: float,
    transfer_fee_coin_base_utob: float,     # U→B 코인 이체 수수료 (코인 단위)
    transfer_fee_coin_base_btou: float,     # B→U 코인 이체 수수료 (코인 단위)
    fx_conversion_fee_rate: float,
    rebalance_profit_multiplier: float,
    rebalance_imbalance_threshold: float,
    daily_rebalances: int,
    max_daily_rebalances: int,
    # 바이낸스 매수호가: 김프 수익성 계산 시 실제 체결가 (없으면 bid로 fallback)
    binance_ask_price_usdt: float = 0.0,
    # 긴급 리밸런싱 / 목표 비율 (config 주입, 기본값은 기존 동작 유지)
    emergency_cash_ratio: float = 0.08,
    emergency_coin_ratio: float = 0.30,
    target_portfolio_ratio: float = 0.25,
    wall_filter_enabled: bool = False,
    wall_min_liquidity_ratio: float = 0.6,
    wall_buy_binance_taker_buy_ratio_max: float = 0.7,
    wall_sell_binance_taker_buy_ratio_min: float = 0.3,
    taker_buy_ratio: float | None = None,
    liquidity_ratio: float | None = None,
) -> Decision:
    """Decide action for a single coin on a single tick."""

    # ---- 가격 준비 ----
    binance_bid_krw = binance_bid_price_usdt * fx
    if binance_bid_krw <= 0:
        return Decision(Action.HOLD, symbol, 0.0, "zero_binance_price")

    eff_ask_usdt = binance_ask_price_usdt if binance_ask_price_usdt > 0 else binance_bid_price_usdt
    binance_ask_krw = eff_ask_usdt * fx

    # 임계값 비교용 프리미엄: mid price 기준 (방향 중립)
    mid_price_krw = (binance_bid_krw + binance_ask_krw) / 2.0
    premium = (upbit_price_krw - mid_price_krw) / mid_price_krw

    total_trade_fee_rate = fee_upbit_rate + fee_binance_rate + slippage_upbit_rate + slippage_binance_rate

    def _wall_filter_block_reason() -> str | None:
        if not wall_filter_enabled:
            return None
        if liquidity_ratio is not None and liquidity_ratio < wall_min_liquidity_ratio:
            return "wall_filter_blocked_liquidity"
        if taker_buy_ratio is None:
            return None
        if premium > 0 and taker_buy_ratio > wall_buy_binance_taker_buy_ratio_max:
            return "wall_filter_blocked_buy_pressure"
        if premium < 0 and taker_buy_ratio < wall_sell_binance_taker_buy_ratio_min:
            return "wall_filter_blocked_sell_pressure"
        return None

    def _total_val() -> float:
        """포트폴리오 총가치 (KRW). bid 기준으로 계산."""
        return (upbit_krw
                + upbit_coin * upbit_price_krw
                + binance_usdt * fx
                + binance_coin * binance_bid_krw)

    def _pick_transfer_fee(action: Action) -> float:
        return transfer_fee_coin_base_utob if action == Action.REBALANCE_U_TO_B else transfer_fee_coin_base_btou

    # ---- Kimchi premium (업비트 비쌈) ----
    if premium > entry_threshold_rate:
        can_sell = upbit_coin > 1e-12
        can_buy = binance_usdt > 0.01

        if can_sell and can_buy:
            # 김프: 바이낸스에서 코인을 '사야' 하므로 ask 기준으로 수익성 계산
            kimchi_premium = (upbit_price_krw - binance_ask_krw) / binance_ask_krw
            notional_krw = min(upbit_coin * upbit_price_krw, binance_usdt * fx)
            expected_profit = notional_krw * (kimchi_premium - total_trade_fee_rate)
            if expected_profit > 0:
                wall_block = _wall_filter_block_reason()
                if wall_block:
                    return Decision(Action.HOLD, symbol, premium, wall_block)
                return Decision(Action.TRADE_KIMCHI, symbol, premium,
                                "kimchi_premium_profitable",
                                expected_profit_krw=expected_profit)
            return Decision(Action.HOLD, symbol, premium, "kimchi_premium_fee_exceeds_profit")

        # Can't trade → consider rebalancing
        if daily_rebalances >= max_daily_rebalances:
            return Decision(Action.HOLD, symbol, premium, "rebalance_daily_limit_reached")

        rebalance_action = _rebalance_direction_by_imbalance(
            upbit_krw=upbit_krw, upbit_coin=upbit_coin,
            binance_usdt=binance_usdt, binance_coin=binance_coin,
            upbit_price_krw=upbit_price_krw, binance_bid_krw=binance_bid_krw,
            fx=fx, imbalance_threshold=rebalance_imbalance_threshold,
            target_ratio=target_portfolio_ratio,
        )
        if rebalance_action is None:
            return Decision(Action.HOLD, symbol, premium, "rebalance_not_needed_by_imbalance")

        eff_fee = _pick_transfer_fee(rebalance_action)
        rebalance_cost = _estimate_rebalance_cost(
            upbit_krw=upbit_krw, binance_usdt=binance_usdt,
            upbit_price_krw=upbit_price_krw, binance_bid_krw=binance_bid_krw,
            fx=fx, transfer_fee_coin_base=eff_fee,
            fx_conversion_fee_rate=fx_conversion_fee_rate,
        )
        total_val = _total_val()
        next_trade_notional = total_val / 2
        expected_next_profit = next_trade_notional * (premium - total_trade_fee_rate)

        if expected_next_profit > rebalance_cost * rebalance_profit_multiplier:
            return Decision(rebalance_action, symbol, premium, "rebalance_profitable",
                            expected_profit_krw=expected_next_profit,
                            rebalance_cost_krw=rebalance_cost)

        # 수익성 기준 미달이어도 현금이 바닥나면 긴급 리밸런싱
        if total_val > 0 and (upbit_krw / total_val) < emergency_cash_ratio:
            return Decision(rebalance_action, symbol, premium,
                            "rebalance_emergency_cash_depleted_kimchi",
                            rebalance_cost_krw=rebalance_cost)

        return Decision(Action.HOLD, symbol, premium, "rebalance_not_profitable")

    # ---- Reverse premium (바이낸스 비쌈) ----
    if premium < -entry_threshold_rate:
        can_buy = upbit_krw > 1.0
        can_sell = binance_coin > 1e-12

        if can_buy and can_sell:
            # 역프: 바이낸스에서 코인을 '팔아야' 하므로 bid 기준으로 수익성 계산
            reverse_premium = (binance_bid_krw - upbit_price_krw) / upbit_price_krw
            notional_krw = min(upbit_krw, binance_coin * binance_bid_krw)
            expected_profit = notional_krw * (reverse_premium - total_trade_fee_rate)
            if expected_profit > 0:
                wall_block = _wall_filter_block_reason()
                if wall_block:
                    return Decision(Action.HOLD, symbol, premium, wall_block)
                return Decision(Action.TRADE_REVERSE, symbol, premium,
                                "reverse_premium_profitable",
                                expected_profit_krw=expected_profit)
            return Decision(Action.HOLD, symbol, premium, "reverse_premium_fee_exceeds_profit")

        # Can't trade → consider rebalancing
        if daily_rebalances >= max_daily_rebalances:
            return Decision(Action.HOLD, symbol, premium, "rebalance_daily_limit_reached")

        rebalance_action = _rebalance_direction_by_imbalance(
            upbit_krw=upbit_krw, upbit_coin=upbit_coin,
            binance_usdt=binance_usdt, binance_coin=binance_coin,
            upbit_price_krw=upbit_price_krw, binance_bid_krw=binance_bid_krw,
            fx=fx, imbalance_threshold=rebalance_imbalance_threshold,
            target_ratio=target_portfolio_ratio,
        )
        if rebalance_action is None:
            return Decision(Action.HOLD, symbol, premium, "rebalance_not_needed_by_imbalance")

        eff_fee = _pick_transfer_fee(rebalance_action)
        rebalance_cost = _estimate_rebalance_cost(
            upbit_krw=upbit_krw, binance_usdt=binance_usdt,
            upbit_price_krw=upbit_price_krw, binance_bid_krw=binance_bid_krw,
            fx=fx, transfer_fee_coin_base=eff_fee,
            fx_conversion_fee_rate=fx_conversion_fee_rate,
        )
        total_val = _total_val()
        next_trade_notional = total_val / 2
        expected_next_profit = next_trade_notional * (abs(premium) - total_trade_fee_rate)

        if expected_next_profit > rebalance_cost * rebalance_profit_multiplier:
            return Decision(rebalance_action, symbol, premium, "rebalance_profitable",
                            expected_profit_krw=expected_next_profit,
                            rebalance_cost_krw=rebalance_cost)

        # 수익성 기준 미달이어도 업비트 KRW가 바닥나면 긴급 리밸런싱
        if total_val > 0 and (upbit_krw / total_val) < emergency_cash_ratio and rebalance_action is not None:
            return Decision(rebalance_action, symbol, premium,
                            "rebalance_emergency_cash_depleted_reverse",
                            rebalance_cost_krw=rebalance_cost)

        return Decision(Action.HOLD, symbol, premium, "rebalance_not_profitable")

    # ---- No trade signal — 현금 고갈 긴급 리밸런싱 체크 ----
    if daily_rebalances < max_daily_rebalances:
        total_val_inner = _total_val()
        if total_val_inner > 0:
            upbit_krw_ratio = upbit_krw / total_val_inner
            binance_usdt_ratio = (binance_usdt * fx) / total_val_inner
            upbit_coin_ratio = (upbit_coin * upbit_price_krw) / total_val_inner
            binance_coin_ratio = (binance_coin * binance_bid_krw) / total_val_inner
            if upbit_krw_ratio < emergency_cash_ratio and upbit_coin_ratio > emergency_coin_ratio:
                return Decision(Action.REBALANCE_U_TO_B, symbol, premium, "cash_depleted_upbit_krw")
            if binance_usdt_ratio < emergency_cash_ratio and binance_coin_ratio > emergency_coin_ratio:
                return Decision(Action.REBALANCE_B_TO_U, symbol, premium, "cash_depleted_binance_usdt")

    return Decision(Action.HOLD, symbol, premium, "below_threshold")


def _estimate_rebalance_cost(
    upbit_krw: float,
    binance_usdt: float,
    upbit_price_krw: float,
    binance_bid_krw: float,
    fx: float,
    transfer_fee_coin_base: float,
    fx_conversion_fee_rate: float,
) -> float:
    """리밸런싱 총 비용 추정 (KRW).

    Cost = 코인 네트워크 이체 수수료 + 현금 환전 수수료.
    """
    coin_transfer_fee_krw = transfer_fee_coin_base * max(upbit_price_krw, binance_bid_krw)
    cash_to_convert = max(upbit_krw, binance_usdt * fx)
    fx_fee_krw = cash_to_convert * fx_conversion_fee_rate
    return coin_transfer_fee_krw + fx_fee_krw


def _rebalance_direction_by_imbalance(
    upbit_krw: float,
    upbit_coin: float,
    binance_usdt: float,
    binance_coin: float,
    upbit_price_krw: float,
    binance_bid_krw: float,
    fx: float,
    imbalance_threshold: float,
    target_ratio: float = 0.25,
) -> Action | None:
    """코인 비중 불균형이 임계값 초과 시 리밸런싱 방향 반환."""
    total_val = (
        upbit_krw
        + upbit_coin * upbit_price_krw
        + binance_usdt * fx
        + binance_coin * binance_bid_krw
    )
    if total_val <= 0:
        return None

    upper_bound = target_ratio * (1 + imbalance_threshold)
    upbit_coin_ratio = (upbit_coin * upbit_price_krw) / total_val
    binance_coin_ratio = (binance_coin * binance_bid_krw) / total_val

    if upbit_coin_ratio > upper_bound:
        return Action.REBALANCE_U_TO_B
    if binance_coin_ratio > upper_bound:
        return Action.REBALANCE_B_TO_U
    return None
