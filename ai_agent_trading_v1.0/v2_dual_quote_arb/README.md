# Strategy 2 — Dual-Quote Spread Arbitrage (v1.28)

> **Status: Live** — Running on AWS EC2 (Tokyo) since September 2025. Currently operating 6 coins with ~1,975 USDT pool.

Exploits temporary price differences between **COINUSDT** and **COINUSDC** markets within Binance — both sides are on the same exchange, eliminating transfer delays and FX risk.

---

## Core Idea

USDT and USDC are both USD-pegged stablecoins, so `DOGEUSDT` and `DOGEUSDC` should trade at nearly identical prices.  
When a temporary spread exceeds the fee threshold, the bot buys on the cheaper side and sells on the more expensive side simultaneously.

```
DOGEUSDT ask < DOGEUSDC bid − fee_threshold
  → Buy DOGEUSDT (pay USDT), Sell DOGEUSDC (receive USDC)

Reverse:
  → Buy DOGEUSDC (pay USDC), Sell DOGEUSDT (receive USDT)
```

**Break-even analysis:**
```
fee_stack = taker(0.10%) + maker(0.05%) = 0.15%
IOC overpay buffer  = ~0.005–0.010%
Real break-even     = ~0.155–0.160%
Entry threshold     = 0.17%  → ~0.015% net margin per trade
```

---

## State Machine

Every coin runs an independent async engine with a strict 3-state machine:

```
IDLE
  │  spread > threshold AND balances OK
  ▼
LEG_A_PENDING  ── IOC market order fills immediately
  │  Leg A filled
  ▼
LEG_B_PENDING  ── GTC limit order, reprice loop
  │  Leg B filled OR timeout
  ▼
IDLE
```

**GlobalTradeLock**: Only one coin may be in `LEG_A_PENDING` or `LEG_B_PENDING` at any time.  
This prevents capital from being double-committed across simultaneous entries.

---

## Late Reprice Algorithm (v1.28 Core Innovation)

The key insight: after Leg A fills, aggressive market orders for Leg B cost ~0.175 USDT in taker fees.  
By chasing the market with GTC limit orders, most fills happen at maker rates.

```
T = 0–30s:    GTC limit at min_profitable_price
              Follow market only if spread remains profitable

T = 30–120s:  [Late Reprice Mode]
              Remove price floor — chase market every 1 second
              Goal: induce maker fill before timeout

T = 120s:     Emergency market order (last resort)
              Absolute timeout anchored to Leg A fill time (never resets)
```

**Timeout anchor:** `time.time() - leg_a_fill_time` (not `order_time`).  
Repricing does not extend the clock — the 120s window is absolute.

**stop_loss backstop:** If price drops beyond the coin's stop-loss threshold (0.3–0.5%), an immediate market order fires regardless of timeout.

---

## Architecture

```
src/
├── live_engine_v2.py      # Core state machine engine (IDLE/LEG_A/LEG_B)
├── live_v2_main.py        # Multi-coin asyncio entry point
├── config_v2.py           # Per-coin YAML config loader
├── portfolio_v2.py        # Dual-quote balance tracker (USDT + USDC slots)
├── allocator_v2.py        # Capital allocation & rebalance logic
├── price_feed.py          # Binance WebSocket orderbook feed
├── ws_order_client.py     # WebSocket order status client
├── global_lock.py         # GlobalTradeLock implementation
├── price_util.py          # IOC price / spread calculation
├── entry_grid.py          # Threshold grid for parameter search
│
├── backtest/
│   ├── backtest_v12.py        # Tick-level backtest engine
│   ├── historical_data_v12.py # Binance kline data downloader
│   ├── v12_config.py          # Backtest config model
│   └── v12_price_util.py      # Price utilities for backtest
│
└── (tools)
    ├── v12_entry_threshold_grid.py   # Grid search: threshold vs PnL
    ├── rebalance_coin_slots_to_yaml.py
    └── verify_arb_allocation.py
```

---

## Live Configuration (April 2026)

| Coin | Threshold | stop_loss | IOC Buffer | Notes |
|---|---|---|---|---|
| TRX | 0.17% | 0.3% | 0.02% | High liquidity, tight spread |
| DOGE | 0.17% | 0.5% | 0.02% | |
| XRP | 0.17% | 0.3% | 0.02% | |
| SOL | 0.17% | 0.5% | 0.02% | |
| BNB | 0.17% | 0.4% | 0.03% | Low BNBUSDC liquidity; BNB fee reserve enforced |
| ADA | 0.17% | 0.3% | 0.02% | |

**Paused coins:**

| Coin | Reason | Resume condition |
|---|---|---|
| LINK | ~$9 price → 1 tick = 0.11% > threshold | Price ≥ $17 |
| AVAX | ~$9 price → 1 tick = 0.11% > threshold | Price ≥ $17 |

**Pool:** ~1,975 USDT-equivalent | **Per-trade notional:** ~494 USDT (25% of pool)

---

## Notable Bug Fixes (Production)

| Bug | Symptom | Fix |
|---|---|---|
| BUG-27 | Duplicate trade sequence numbers on emergency exit | Added `_log_seq` counter — increments on every `_log_trade` call |
| BUG-28 | Cumulative PnL column resets when coin order changes in merged CSV | Re-calculate cumulative sum from unified sorted timeline in `_send_merged_csv` |
| BUG-29 | `engine_state.json` overwritten by multiple coins in parallel | Split into per-coin `engine_state_{sym}.json` |

> Full bug history: see Notion portfolio link in root README.

---

## Deploy

```bash
# Upload engine to EC2
scp -i ~/.ssh/arb_key_tokyo.pem \
  src/live_engine_v2.py \
  src/live_v2_main.py \
  ubuntu@<EC2_IP>:/home/ubuntu/arb/src/v12/

# Restart service
ssh -i ~/.ssh/arb_key_tokyo.pem ubuntu@<EC2_IP> \
  "sudo systemctl restart arb && sleep 6 && \
   ls -t /home/ubuntu/arb/logs/v12/live_v2_*.log | head -1 | xargs tail -15"
```

See `scripts/cloud.env.v1.2.example` for required environment variables.

---

## Backtest

```bash
pip install -r ../../requirements.txt

# Single coin, 30 days
python -m cli_backtest_v2 --config configs/v12_doge_v2.yaml --days 30

# Threshold grid sweep
python v12_entry_threshold_grid.py --coin DOGE --days 30

# Tests
pytest tests/ -q
```

---

## Infra

- **EC2:** t3.micro (Tokyo, unlimited CPU credit mode), Elastic IP `52.193.135.160`
- **Service:** `sudo systemctl status arb`
- **Logs:** `/home/ubuntu/arb/logs/v12/live_v2_*.log`
- **Alerts:** Telegram Bot — hourly summary + per-trade notification
- **Log rotation:** `scripts/logrotate.conf`

---

**Successor:** [`../v3_funding_rate/`](../v3_funding_rate/) — funding rate arb, higher capital capacity, lower per-trade execution risk.
