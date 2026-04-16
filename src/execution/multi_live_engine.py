"""v2 (multi_main) spot legs: Kimchi / Reverse as Upbit + Binance market orders.

TRADE_KIMCHI: market sell full Upbit coin + market buy with full Binance USDT.
TRADE_REVERSE: market buy with full Upbit KRW + market sell full Binance coin.

Rebalancing across venues still requires on-chain transfer; not executed here.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging

from src.config import CoinConfig
from src.exchanges.binance_trading_client import BinanceTradingClient
from src.exchanges.upbit_trading_client import UpbitTradingClient
from src.state.multi_portfolio import CoinBalance

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MultiLiveExecutionEngine:
    upbit: UpbitTradingClient
    binance: BinanceTradingClient
    dry_run: bool = True

    def _dry(self, exchange: str, kind: str, symbol: str, amount: float) -> dict:
        return {"exchange": exchange, "kind": kind, "symbol": symbol, "amount": amount, "mode": "dry_run"}

    @staticmethod
    def _f(value: object, default: float = 0.0) -> float:
        try:
            return float(value)  # type: ignore[arg-type]
        except Exception:
            return default

    def _fetch_upbit_fill(self, order_resp: dict) -> dict:
        """Best-effort fetch of filled qty/avg from Upbit order uuid."""
        raw = dict(order_resp or {})
        order_uuid = str(raw.get("uuid") or "").strip()
        detail = {}
        if order_uuid:
            try:
                detail = self.upbit.get_order(order_uuid)
            except Exception as exc:
                logger.warning("upbit get_order failed (uuid=%s): %s", order_uuid, exc)
        payload = detail or raw

        executed_qty = self._f(payload.get("executed_volume"), 0.0)
        avg_price = self._f(payload.get("avg_price"), 0.0)
        krw_notional = 0.0

        trades = payload.get("trades") if isinstance(payload, dict) else None
        if isinstance(trades, list) and trades:
            notional_sum = 0.0
            qty_sum = 0.0
            for t in trades:
                if not isinstance(t, dict):
                    continue
                funds = self._f(t.get("funds"), 0.0)
                vol = self._f(t.get("volume"), 0.0)
                px = self._f(t.get("price"), 0.0)
                if funds > 0:
                    notional_sum += funds
                elif vol > 0 and px > 0:
                    notional_sum += vol * px
                qty_sum += vol
            if qty_sum > 0:
                executed_qty = qty_sum
            if notional_sum > 0:
                krw_notional = notional_sum
                if executed_qty > 0:
                    avg_price = notional_sum / executed_qty

        if krw_notional <= 0 and executed_qty > 0 and avg_price > 0:
            krw_notional = executed_qty * avg_price

        return {
            "uuid": order_uuid,
            "executed_qty": executed_qty,
            "avg_price": avg_price,
            "krw_notional": krw_notional,
            "raw": payload,
        }

    def _fetch_binance_fill(self, order_resp: dict) -> dict:
        raw = dict(order_resp or {})
        executed_qty = self._f(raw.get("executedQty"), 0.0)
        quote_qty = self._f(raw.get("cummulativeQuoteQty"), 0.0)
        avg_price = quote_qty / executed_qty if executed_qty > 0 and quote_qty > 0 else 0.0
        if avg_price <= 0:
            fills = raw.get("fills")
            if isinstance(fills, list) and fills:
                quote_sum = 0.0
                qty_sum = 0.0
                for f in fills:
                    if not isinstance(f, dict):
                        continue
                    px = self._f(f.get("price"), 0.0)
                    qty = self._f(f.get("qty"), 0.0)
                    if px > 0 and qty > 0:
                        quote_sum += px * qty
                        qty_sum += qty
                if qty_sum > 0:
                    executed_qty = qty_sum
                    quote_qty = quote_sum
                    avg_price = quote_sum / qty_sum
        return {
            "executed_qty": executed_qty,
            "quote_qty": quote_qty,
            "avg_price": avg_price,
            "raw": raw,
        }

    def _emergency_reverse_upbit_after_sell(self, coin: CoinConfig, up_fill: dict) -> dict:
        krw = self._f(up_fill.get("krw_notional"), 0.0)
        if krw <= 1.0:
            return {"recovered": False, "reason": "unknown_sell_notional", "attempted_krw": krw}
        # leave a small cushion for fees.
        attempt_krw = max(krw * 0.999, 1.0)
        try:
            rev = self.upbit.place_market_buy(coin.upbit_market, attempt_krw)
            return {"recovered": True, "order": rev, "attempted_krw": attempt_krw}
        except Exception as exc:
            return {"recovered": False, "reason": str(exc), "attempted_krw": attempt_krw}

    def _emergency_reverse_upbit_after_buy(self, coin: CoinConfig, up_fill: dict) -> dict:
        qty = self._f(up_fill.get("executed_qty"), 0.0)
        if qty <= 1e-12:
            return {"recovered": False, "reason": "unknown_bought_qty", "attempted_qty": qty}
        attempt_qty = max(qty * 0.999, 0.0)
        if attempt_qty <= 1e-12:
            return {"recovered": False, "reason": "tiny_bought_qty", "attempted_qty": attempt_qty}
        try:
            rev = self.upbit.place_market_sell(coin.upbit_market, attempt_qty)
            return {"recovered": True, "order": rev, "attempted_qty": attempt_qty}
        except Exception as exc:
            return {"recovered": False, "reason": str(exc), "attempted_qty": attempt_qty}

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

    def execute_kimchi(
        self,
        coin: CoinConfig,
        balance: CoinBalance,
        *,
        trade_fraction: float = 1.0,
        expected_upbit_price_krw: float | None = None,
        expected_binance_price_usdt: float | None = None,
    ) -> dict:
        """Sell all Upbit base; buy base with all Binance USDT."""
        fraction = max(0.0, min(float(trade_fraction), 1.0))
        sell_vol_raw = balance.upbit_coin * fraction
        sell_vol = self.binance.normalize_market_quantity(coin.binance_symbol, sell_vol_raw)
        quote_usdt = balance.binance_usdt * fraction
        if sell_vol <= 1e-12:
            return {
                "status": "SKIP",
                "reason": "upbit_coin_below_binance_lot_step",
                "coin": coin.symbol,
                "raw_qty": sell_vol_raw,
            }
        if expected_upbit_price_krw and expected_upbit_price_krw > 0:
            upbit_sell_notional = sell_vol * expected_upbit_price_krw
            if upbit_sell_notional < 5000:
                return {
                    "status": "SKIP",
                    "reason": "upbit_sell_under_min_total",
                    "coin": coin.symbol,
                    "sell_qty": sell_vol,
                    "notional_krw": upbit_sell_notional,
                }
        if quote_usdt <= 0.01:
            return {"status": "SKIP", "reason": "no_binance_usdt", "coin": coin.symbol}
        if self.dry_run:
            return {
                "status": "LIVE_DRY_RUN",
                "details": [
                    self._dry("upbit", "market_sell_volume", coin.upbit_market, sell_vol),
                    self._dry("binance", "market_buy_qty", coin.binance_symbol, sell_vol),
                ],
            }
        try:
            up_order = self.upbit.place_market_sell(coin.upbit_market, sell_vol)
        except Exception as exc:
            return {"status": "LIVE_ERROR_UPBIT", "error": str(exc), "coin": coin.symbol}

        up_fill = self._fetch_upbit_fill(up_order)
        try:
            bn_order = self.binance.place_market_order(coin.binance_symbol, "BUY", sell_vol)
        except Exception as exc:
            recovery = self._emergency_reverse_upbit_after_sell(coin, up_fill)
            recovered = bool(recovery.get("recovered"))
            return {
                "status": "LIVE_ERROR_HEDGE_RECOVERED" if recovered else "LIVE_HALT",
                "coin": coin.symbol,
                "error": f"{exc} (raw_qty={sell_vol_raw:.12f}, normalized_qty={sell_vol:.12f})",
                "hedge_incomplete": True,
                "recovered": recovered,
                "recovery": recovery,
                "upbit_order": up_order,
            }

        bn_fill = self._fetch_binance_fill(bn_order)
        up_actual = self._f(up_fill.get("avg_price"), 0.0)
        bn_actual = self._f(bn_fill.get("avg_price"), 0.0)
        up_slip = None
        bn_slip = None
        if expected_upbit_price_krw and expected_upbit_price_krw > 0 and up_actual > 0:
            up_slip = abs(up_actual - expected_upbit_price_krw) / expected_upbit_price_krw
        if expected_binance_price_usdt and expected_binance_price_usdt > 0 and bn_actual > 0:
            bn_slip = abs(bn_actual - expected_binance_price_usdt) / expected_binance_price_usdt

        return {
            "status": "LIVE_EXECUTED",
            "details": [up_order, bn_order],
            "fills": {"upbit": up_fill, "binance": bn_fill},
            "slippage": {
                "upbit": up_slip,
                "binance": bn_slip,
                "expected_upbit_price_krw": expected_upbit_price_krw,
                "actual_upbit_price_krw": up_actual if up_actual > 0 else None,
                "expected_binance_price_usdt": expected_binance_price_usdt,
                "actual_binance_price_usdt": bn_actual if bn_actual > 0 else None,
            },
        }

    def execute_reverse(
        self,
        coin: CoinConfig,
        balance: CoinBalance,
        *,
        trade_fraction: float = 1.0,
        expected_upbit_price_krw: float | None = None,
        expected_binance_price_usdt: float | None = None,
    ) -> dict:
        """Spend all Upbit KRW on base; sell all Binance base for USDT."""
        fraction = max(0.0, min(float(trade_fraction), 1.0))
        krw = balance.upbit_krw * fraction
        sell_qty_raw = balance.binance_coin * fraction
        sell_qty = self.binance.normalize_market_quantity(coin.binance_symbol, sell_qty_raw)
        if krw <= 1.0:
            return {"status": "SKIP", "reason": "no_upbit_krw", "coin": coin.symbol}
        if sell_qty <= 1e-12:
            return {
                "status": "SKIP",
                "reason": "binance_coin_below_lot_step",
                "coin": coin.symbol,
                "raw_qty": sell_qty_raw,
            }
        if expected_upbit_price_krw and expected_upbit_price_krw > 0:
            spend_krw = min(krw * 0.999, sell_qty * expected_upbit_price_krw)
        else:
            spend_krw = krw * 0.999
        spend_krw = float(int(max(spend_krw, 0.0)))
        if spend_krw < 5000:
            return {
                "status": "SKIP",
                "reason": "upbit_buy_under_min_total",
                "coin": coin.symbol,
                "spend_krw": spend_krw,
            }
        if self.dry_run:
            return {
                "status": "LIVE_DRY_RUN",
                "details": [
                    self._dry("upbit", "market_buy_krw", coin.upbit_market, spend_krw),
                    self._dry("binance", "market_sell_qty", coin.binance_symbol, sell_qty),
                ],
            }
        try:
            up_order = self.upbit.place_market_buy(coin.upbit_market, spend_krw)
        except Exception as exc:
            return {"status": "LIVE_ERROR_UPBIT", "error": str(exc), "coin": coin.symbol}

        up_fill = self._fetch_upbit_fill(up_order)
        sell_qty_norm = self.binance.normalize_market_quantity(coin.binance_symbol, sell_qty)
        if sell_qty_norm <= 1e-12:
            recovery = self._emergency_reverse_upbit_after_buy(coin, up_fill)
            recovered = bool(recovery.get("recovered"))
            return {
                "status": "LIVE_ERROR_HEDGE_RECOVERED" if recovered else "LIVE_HALT",
                "coin": coin.symbol,
                "error": (
                    f"binance sell qty below LOT_SIZE after normalize: "
                    f"raw={sell_qty:.12f}, normalized={sell_qty_norm:.12f}"
                ),
                "hedge_incomplete": True,
                "recovered": recovered,
                "recovery": recovery,
                "upbit_order": up_order,
            }
        try:
            bn_order = self.binance.place_market_order(coin.binance_symbol, "SELL", sell_qty_norm)
        except Exception as exc:
            recovery = self._emergency_reverse_upbit_after_buy(coin, up_fill)
            recovered = bool(recovery.get("recovered"))
            return {
                "status": "LIVE_ERROR_HEDGE_RECOVERED" if recovered else "LIVE_HALT",
                "coin": coin.symbol,
                "error": (
                    f"{exc} "
                    f"(raw_qty={sell_qty_raw:.12f}, normalized_qty={sell_qty_norm:.12f})"
                ),
                "hedge_incomplete": True,
                "recovered": recovered,
                "recovery": recovery,
                "upbit_order": up_order,
            }

        bn_fill = self._fetch_binance_fill(bn_order)
        up_actual = self._f(up_fill.get("avg_price"), 0.0)
        bn_actual = self._f(bn_fill.get("avg_price"), 0.0)
        up_slip = None
        bn_slip = None
        if expected_upbit_price_krw and expected_upbit_price_krw > 0 and up_actual > 0:
            up_slip = abs(up_actual - expected_upbit_price_krw) / expected_upbit_price_krw
        if expected_binance_price_usdt and expected_binance_price_usdt > 0 and bn_actual > 0:
            bn_slip = abs(bn_actual - expected_binance_price_usdt) / expected_binance_price_usdt

        return {
            "status": "LIVE_EXECUTED",
            "details": [up_order, bn_order],
            "fills": {"upbit": up_fill, "binance": bn_fill},
            "slippage": {
                "upbit": up_slip,
                "binance": bn_slip,
                "expected_upbit_price_krw": expected_upbit_price_krw,
                "actual_upbit_price_krw": up_actual if up_actual > 0 else None,
                "expected_binance_price_usdt": expected_binance_price_usdt,
                "actual_binance_price_usdt": bn_actual if bn_actual > 0 else None,
            },
        }
