# Strategy 1 — Kimchi Premium Arbitrage (v1.1)

> **Status: Archived** — Operated March–August 2025. Strategy retired as kimchi premium compressed below profitability threshold.

Cross-exchange arbitrage exploiting price gaps between the Korean exchange (Upbit, KRW) and the global exchange (Binance, USDT) on the same coin — commonly known as the **Kimchi Premium**.

---

## How It Works

When the same coin trades at a higher price on Upbit (KRW) vs Binance (USDT), a premium exists.  
The bot simultaneously sells on the expensive side and buys on the cheap side, capturing the spread minus fees.

```
Upbit KRW price > Binance USDT price × FX rate + fee_threshold
  → Sell on Upbit (KRW), Buy on Binance (USDT)

Reverse:
  → Buy on Upbit (KRW), Sell on Binance (USDT)
```

**Entry condition:**
```
net_profit = |upbit_price - binance_price × fx| - trading_fees - slippage
Execute only if net_profit > threshold
```

---

## 4-Balance Portfolio Model

Each coin maintains 4 independent balances. The engine checks feasibility against all 4 before placing any order.

| Balance | Exchange | Currency |
|---|---|---|
| `upbit_krw` | Upbit | KRW cash |
| `upbit_coin` | Upbit | Coin (e.g., DOGE) |
| `binance_usdt` | Binance | USDT |
| `binance_coin` | Binance | Coin (e.g., DOGE) |

The capital allocator monitors balance ratios and triggers rebalancing when any slot falls below minimum thresholds.

---

## Architecture

```
src/
├── multi_main.py              # asyncio main loop — concurrent multi-coin
├── main.py                    # single-coin entry point
├── config.py                  # YAML config loader
├── models.py                  # Trade/Order data models
├── marketdata.py              # Real-time price aggregation
│
├── exchanges/
│   ├── upbit_ws.py            # Upbit WebSocket (KRW orderbook)
│   ├── upbit_client.py        # Upbit REST API
│   ├── upbit_trading_client.py
│   ├── binance_ws.py          # Binance WebSocket (USDT orderbook)
│   ├── binance_client.py      # Binance REST API
│   └── fx_upbit.py            # KRW/USD exchange rate feed
│
├── strategy/
│   ├── spread_calc.py         # Premium & net profit calculation
│   ├── signal.py              # Entry/exit signal generation
│   └── capital_allocator.py  # 4-balance rebalancing logic
│
├── state/
│   ├── portfolio.py           # Single-coin portfolio state
│   └── multi_portfolio.py    # Multi-coin portfolio manager
│
├── execution/
│   ├── live_engine.py         # Live order execution
│   ├── multi_live_engine.py   # Multi-coin concurrent execution
│   ├── paper_engine.py        # Paper trading simulation
│   ├── risk_guard.py          # Pre-order risk checks
│   └── router.py              # Paper/live mode router
│
├── logging/
│   ├── event_logger.py        # Structured trade event logging
│   └── multi_run_csv.py       # CSV trade log aggregation
│
├── notifications/
│   └── telegram_notifier.py  # Telegram Bot trade alerts
│
└── backtest/
    ├── backtest_runner.py     # Backtest execution engine
    └── historical_data.py    # Binance OHLC data fetcher
```

---

## Backtest Results (1-year, 1-minute candles)

| Coin | Entry Threshold | Annual Trades | Gross Return | Net Return (after fees) |
|---|---|---|---|---|
| DOGE | 0.60% | 76 | ~32% | **+29.3%** |
| XRP | 0.70% | 23 | ~15% | +13.5% |
| TRX | 0.60% | 10 | ~7% | +6.1% |

> Fee model: Upbit taker 0.05% + Binance taker 0.10% + slippage ~0.03%

---

## Config

```yaml
# configs/multi.yaml (example — keys redacted)
coins:
  - symbol: DOGE
    threshold: 0.0060       # 0.60% entry threshold
    trade_notional_krw: 50000
    min_profit_krw: 200
upbit_api_key: "***"
binance_api_key: "***"
```

---

## Running

```bash
# Install dependencies
pip install -r ../../requirements.txt

# Paper trading (safe — no real orders)
python -m src.multi_main --config configs/multi.yaml

# Backtest
python -m src.backtest_main --config configs/multi.yaml --days 30

# Tests
pytest tests/ -q
```

---

## Why This Strategy Was Retired

By mid-2025, the average kimchi premium on major coins (DOGE, XRP, TRX) dropped from ~0.8% to ~0.3%, below the ~0.55% break-even threshold.  
The strategy requires simultaneous execution across two exchanges in different countries, creating operational complexity (FX risk, transfer delays, regulatory exposure) that the lower premium no longer justified.

**Successor:** [`../v2_dual_quote_arb/`](../v2_dual_quote_arb/) — same market-neutral philosophy, but intra-exchange with no transfer overhead.
