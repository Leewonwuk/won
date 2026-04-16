# Crypto Arbitrage Trading System

Automated cryptocurrency arbitrage trading system built and operated with **Claude Code AI agent** — from strategy design and backtesting through live deployment on AWS EC2.

This project contains **three independent strategies**, each evolved from the previous based on real production learnings.

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![AWS EC2](https://img.shields.io/badge/AWS-EC2_t3.micro-orange)](https://aws.amazon.com/ec2/)
[![Binance API](https://img.shields.io/badge/Binance-REST%20%2F%20WebSocket-yellow)](https://binance-docs.github.io/apidocs/)

---

## Portfolio Document

Full strategy breakdown, implementation details, backtest results, and bug resolution history:

**[→ View Notion Portfolio](https://www.notion.so/3449fc6966538181bcb7ce45a254af3b)**

---

## Strategy Overview

| Directory | Strategy | Exchanges | Status |
|---|---|---|---|
| [`v1_kimchi_premium/`](./v1_kimchi_premium/) | Cross-exchange KRW arbitrage (Upbit ↔ Binance) | Upbit + Binance | Archived |
| [`v2_dual_quote_arb/`](./v2_dual_quote_arb/) | Dual-quote spread arb (COINUSDT ↔ COINUSDC) | Binance only | **Live** |
| [`v3_funding_rate/`](./v3_funding_rate/) | Funding rate arb (Spot long + Perp short) | Binance only | Standby |

> Each strategy is a fully self-contained codebase with its own `src/`, `configs/`, `scripts/`, and `tests/`.

---

## Why Three Separate Strategies?

| Transition | What drove the change |
|---|---|
| v1 → v2 | Kimchi premium dried up as Korean markets matured; pivoted to a market-neutral intra-exchange spread requiring no cross-border transfers |
| v2 → v3 | Dual-quote spread alpha compresses as more bots compete; funding rate arb offers larger capital capacity and lower execution risk |

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11, asyncio |
| Market data | Binance WebSocket (UDS subscribe) |
| Order execution | REST + WebSocket GTC/IOC order client |
| Infra | AWS EC2 t3.micro (Tokyo), systemd, Telegram Bot |
| Testing | pytest, 30-day Binance OHLC backtests |
| AI tooling | Claude Code (Cursor + Harness) |

---

## AI Agent Usage

All three strategies were built with **Claude Code** as an AI pair programmer across the full lifecycle:

- **Bug tracking** — 29 production bugs (BUG-01 ~ BUG-29) identified and fixed with AI-assisted root cause analysis
- **Backtest orchestration** — threshold grid sweeps, 30-day PnL simulations via AI-generated scripts
- **Config tuning** — break-even analysis, fee stack calculations, per-coin IOC buffer optimization
- **Live diagnostics** — log parsing, EC2 SSH commands, Telegram alert validation

See [`v2_dual_quote_arb/scripts/V12_LIVE_CLOUD_NOTES.md`](./v2_dual_quote_arb/scripts/V12_LIVE_CLOUD_NOTES.md) for a real-time ops log of AI-assisted production incident responses.

---

## Project Timeline

| Period | Milestone |
|---|---|
| March 2025 | v1.1 live — Kimchi premium arbitrage across Upbit + Binance |
| September 2025 | v1.2 — Pivot to Binance-only USDT/USDC dual-quote spread |
| January 2026 | v1.28 — Late Reprice algorithm, GlobalTradeLock, 6-coin portfolio |
| April 2026 | v3 code complete — Funding rate arb awaiting market conditions |

---

## Safety

- Default mode: `paper` (no real orders placed)
- Live orders require: `ARB_ENABLE_LIVE_ORDERS=true` + `ARB_LIVE_DRY_RUN=false`
- API keys in `.env` only — never committed (see `.env.example` in each strategy dir)
