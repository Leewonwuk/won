# Strategy 3 — Funding Rate Arbitrage (v2.0)

> **Status: Standby** — Code complete as of March 2026. Waiting for sustained positive funding rate environment (bull market) before live deployment.

Delta-neutral arbitrage that captures **funding rate payments** on Binance perpetual futures — hold a spot long position and a matching perp short position to collect funding fees while remaining price-neutral.

---

## Core Idea

Binance perpetual futures pay a funding rate every 8 hours.  
When the market is bullish, long perpetual holders pay short holders — typically 0.01–0.10% per cycle (0.03–0.30% per day).

```
Position:
  Spot:  Buy COIN (long)
  Perp:  Short COIN-PERP (equal notional)

Net delta = 0  →  price-neutral, no directional risk

Cash flow:
  Every 8h: receive funding_rate × notional  (when rate > 0)
  Costs:    position open/close fees + borrow interest
```

**Entry condition:**
```
funding_rate_annualized > fee_breakeven_annualized
Typical target: annualized rate > 20% (= ~0.083% per 8h cycle)
```

---

## Architecture

```
src/
├── funding_engine.py      # Main engine — position open/monitor/close
├── funding_strategy.py    # Entry/exit signal: funding rate threshold check
├── config_v20.py          # Per-coin YAML config loader
├── position_state.py      # Spot + perp position state tracker
├── main.py                # Entry point
├── backtest_v2.py         # Funding rate backtest engine
├── backtest_v2_main.py    # Backtest CLI
└── sweep_v2_threshold.py  # Threshold sweep tool
```

---

## Config

```yaml
# configs/v20_doge.yaml (example — keys redacted)
symbol: DOGE
spot_notional_usdt: 500
min_funding_rate: 0.0003    # 0.03% per 8h = ~13% annualized
max_position_hold_hours: 72
leverage: 1                  # no leverage on perp side
```

---

## Key Differences from v1 / v2

| Aspect | v1 (Kimchi) | v2 (Dual-Quote) | v3 (Funding Rate) |
|---|---|---|---|
| Edge source | Exchange price gap | Stablecoin price gap | Funding rate payments |
| Holding period | Seconds | Seconds | Hours to days |
| Delta exposure | Hedged | Hedged | Fully hedged |
| Execution risk | High (two exchanges) | Medium (Leg B delay) | Low (open once, hold) |
| Capital capacity | Limited by transfer | ~$5K practical limit | Scales with funding rate |

---

## Why Standby?

Funding rate arb is most profitable during bull markets when retail traders pay high premiums to hold long perp positions.  
As of April 2026, funding rates have compressed to near-zero on most coins, making deployment unprofitable after fees.

**Deployment trigger:** Average 8h funding rate > 0.03% sustained for 3+ days across ≥ 3 coins in the portfolio.

---

## Running

```bash
pip install -r ../../requirements.txt

# Backtest funding rate history
python src/backtest_v2_main.py --config configs/v20_doge.yaml --days 90

# Threshold sweep
python src/sweep_v2_threshold.py --coin DOGE --days 90
```
