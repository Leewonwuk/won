# Crypto Arbitrage Trading Bot (v1.1 / v1.28)

> Automated cryptocurrency arbitrage system built and operated with **Claude Code AI agent** — from strategy design and backtesting to live deployment on AWS EC2.

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![AWS EC2](https://img.shields.io/badge/AWS-EC2_t3.micro-orange)](https://aws.amazon.com/ec2/)
[![Binance API](https://img.shields.io/badge/Binance-REST%20%2F%20WebSocket-yellow)](https://binance-docs.github.io/apidocs/)

---

## Portfolio Document

Full strategy breakdown, implementation details, backtest results, and bug resolution history:

**[→ View Notion Portfolio](https://www.notion.so/3449fc6966538181bcb7ce45a254af3b)**

---

## Project Overview

| Item | Detail |
|---|---|
| Period | March 2025 – April 2026 (~13 months) |
| Role | Solo — design, development, and live operation |
| Stack | Python 3.11, asyncio, WebSocket, Binance/Upbit REST & WS API |
| Infra | AWS EC2 t3.micro (Tokyo), systemd, Telegram Bot |
| AI Tool | **Claude Code + Cursor** — used across the full development lifecycle |

---

## Strategy 1 — v1.1: Upbit ↔ Binance Kimchi Premium Arbitrage

Exploits temporary price gaps between the Korean exchange (Upbit, KRW) and the global exchange (Binance, USDT) on the same coin — known as the **Kimchi Premium**.

**How it works:**
- Premium exceeds threshold → sell on Upbit, buy on Binance (simultaneously)
- Reverse premium → buy on Upbit, sell on Binance
- Only executes when net profit > total fees (trading + slippage + transfer)

**4-Balance Portfolio Model** — each coin maintains 4 independent balances:

| Balance | Role |
|---|---|
| `upbit_krw` | KRW cash on Upbit |
| `upbit_coin` | Coin on Upbit |
| `binance_usdt` | USDT on Binance |
| `binance_coin` | Coin on Binance |

**Backtest Results (1 year, 1-minute candles):**

| Coin | Threshold | Annual Trades | Annual Return |
|---|---|---|---|
| DOGE | 0.60% | 76 | **+29.3%** |
| XRP | 0.70% | 23 | +13.5% |
| TRX | 0.60% | 10 | +6.1% |

---

## Strategy 2 — v1.28: Binance USDT/USDC Spread Arbitrage (Live)

Exploits temporary price differences between **COINUSDT** and **COINUSDC** markets within Binance — no cross-exchange transfers needed.

**State Machine:**
```
IDLE → LEG_A_PENDING → LEG_B_PENDING → IDLE
```

**Entry threshold:** 0.17% | **Fee stack (taker+maker):** ~0.15% | **Net margin:** ~0.015%

**Late Reprice Algorithm (v1.28 core innovation):**
```
T = 0–30s:    GTC limit at min_profitable_price
T = 30–120s:  Remove price floor, chase market every 1s → induce maker fill
T = 120s:     Emergency market order (last resort)
```

**Live operation (April 2026):** 6 coins (TRX, DOGE, XRP, SOL, BNB, ADA), ~1,975 USDT pool

---

## Architecture

```
src/
├── multi_main.py              # v1.1 multi-coin asyncio main loop
├── strategy/
│   ├── spread_calc.py         # Premium & net profit calculation
│   ├── signal.py              # Trade signal logic
│   └── capital_allocator.py  # Rebalancing decision engine
├── state/
│   └── multi_portfolio.py    # 4-balance portfolio model
├── exchanges/
│   ├── upbit_ws.py            # Upbit WebSocket
│   └── binance_ws.py          # Binance WebSocket
├── execution/
│   ├── live_engine.py         # Live order execution
│   └── paper_engine.py        # Paper trading
├── v12/
│   ├── live_engine_v2.py      # v1.28 state machine engine
│   └── live_v2_main.py        # v1.28 multi-coin main
└── v20/
    └── funding_engine.py      # v2.0 funding rate arb (on standby)
```

---

## AI Agent Usage

This project was developed with **Claude Code (Anthropic)** and **Cursor** AI agents throughout:

- **Design** — strategy logic, state machine architecture, fee models
- **Implementation** — core algorithm coding and code review
- **Debugging** — race conditions, cumulative stat errors, production bugs
- **Operations** — EC2 deployment automation, parameter tuning

> `Co-Authored-By: Claude` tags in commit history mark AI-assisted commits.

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env  # Add your API keys
```

```bash
python -m src.v12.cli_backtest_v2 --config configs/v12/v12_doge_v2.yaml --days 30  # backtest
python -m src.multi_main --config configs/multi.yaml  # paper trading
pytest -q  # tests
```

---

## Safety

- Default mode: `paper` (no real orders)
- Live orders require: `ARB_ENABLE_LIVE_ORDERS=true` + `ARB_LIVE_DRY_RUN=false`
- API keys in `.env` only — never committed (see `.env.example`)
