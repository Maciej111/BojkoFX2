# IBKR Gateway — Paper Trading Integration

> **Strategy:** Trend-Following v1 (BOS + Pullback) — parameters frozen from PROOF V2.  
> **Engine:** FIX2 backtest engine logic ported to live execution.  
> **Broker:** Interactive Brokers via IB Gateway (paper account).

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Gateway Setup](#2-gateway-setup)
3. [Environment Variables](#3-environment-variables)
4. [How to Run — Dry Run](#4-how-to-run--dry-run)
5. [How to Enable Real Paper Orders](#5-how-to-enable-real-paper-orders)
6. [Log Files](#6-log-files)
7. [Kill Switch](#7-kill-switch)
8. [Architecture Overview](#8-architecture-overview)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Prerequisites

| Item | Version |
|------|---------|
| Python | 3.10+ |
| ib_insync | ≥ 0.9.86 |
| IB Gateway | latest (paper account) |
| pandas | ≥ 2.0 |

Install Python dependencies:

```bash
pip install -r requirements.txt
```

---

## 2. Gateway Setup

1. **Download IB Gateway** from  
   https://www.interactivebrokers.com/en/trading/ibgateway.php  
   Choose *Stable* channel.

2. **Log in with your paper account** credentials  
   (Paper account username is different from your live account).

3. **Enable API access**  
   Inside Gateway: *Configure → Settings → API → Settings*

   | Setting | Value |
   |---------|-------|
   | Enable ActiveX and Socket Clients | ✅ checked |
   | Socket port | **4002** |
   | Allow connections from localhost only | ✅ checked |
   | Trusted IPs | `127.0.0.1` |
   | Read-Only API | leave **unchecked** if you want to place orders |

4. **Restart Gateway** after saving settings.

---

## 3. Environment Variables

Copy the template and edit it:

```bash
cp config/ibkr.env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `IBKR_HOST` | `127.0.0.1` | Gateway host |
| `IBKR_PORT` | `4002` | Gateway paper port (TWS paper = 7497) |
| `IBKR_CLIENT_ID` | `7` | Unique integer; must not clash with other connections |
| `IBKR_ACCOUNT` | *(blank)* | Your paper account string, e.g. `DU1234567` |
| `IBKR_READONLY` | `true` | **Gate 1**: `false` to allow orders |
| `ALLOW_LIVE_ORDERS` | `false` | **Gate 2**: `true` to allow orders |
| `KILL_SWITCH` | `false` | `true` = block all orders immediately |

> **All three gates must be clear before a single order is sent:**
> `IBKR_READONLY=false` AND `ALLOW_LIVE_ORDERS=true` AND `KILL_SWITCH=false`

Load the `.env` file before running (PowerShell):

```powershell
Get-Content .env | ForEach-Object {
    if ($_ -match "^([^#=]+)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2])
    }
}
```

Or use `python-dotenv` (already in requirements):

```python
from dotenv import load_dotenv
load_dotenv()
```

---

## 4. How to Run — Dry Run

Dry run **does not place any orders**. It connects to Gateway, bootstraps
60 days of H1 history, streams live bars, and logs all signals/intents.

```bash
# 5-minute dry run, single symbol
python -m src.runners.run_paper_ibkr_gateway --symbol EURUSD --minutes 5

# Run indefinitely until Ctrl+C
python -m src.runners.run_paper_ibkr_gateway --symbol EURUSD

# Multiple symbols
python -m src.runners.run_paper_ibkr_gateway --symbol EURUSD,GBPUSD,USDJPY

# Custom port (TWS paper)
python -m src.runners.run_paper_ibkr_gateway --symbol EURUSD --port 7497
```

Expected output:

```
========================================================================
  IBKR GATEWAY PAPER TRADING RUNNER
========================================================================
  Symbols          : EURUSD
  Gateway          : 127.0.0.1:4002  clientId=7
  IBKR_READONLY    : True
  ALLOW_LIVE_ORDERS: False
  ...
  ⚠  DRY-RUN MODE — no orders will be sent to IBKR.

[IBKR] Connected to 127.0.0.1:4002 | server time: 2026-02-20 14:00:01
[IBKR] Bootstrapping 60d H1 history for EURUSD...
[IBKR] Loaded 1043 H1 bars for EURUSD (2025-12-22 → 2026-02-20)
[IBKR] Subscribed to EURUSD
[READY] ...
```

---

## 5. How to Enable Real Paper Orders

> ⚠️ This will place **real orders on your IBKR paper demo account**.
> No real money is at risk, but positions will appear in TWS/Gateway.

**Step 1:** Set environment variables

```bash
IBKR_READONLY=false
ALLOW_LIVE_ORDERS=true
KILL_SWITCH=false
```

**Step 2:** Run with `--allow_live_orders` flag

```bash
python -m src.runners.run_paper_ibkr_gateway --symbol EURUSD --allow_live_orders
```

The runner will show a confirmation prompt:

```
  🔴 LIVE PAPER ORDERS ENABLED — trades will hit your demo account!
  Type 'YES' to confirm:
```

Type `YES` and press Enter.

**Order type:** LIMIT bracket (entry + TP + SL attached).  
**TTL:** `pullback_max_bars` hours (default 40 h), after which the entry is cancelled.

---

## 6. Log Files

All logs are written to `logs/` directory.

### `logs/paper_trading_ibkr.csv` (primary — full detail)

| Column | Description |
|--------|-------------|
| `timestamp` | UTC event time |
| `symbol` | e.g. EURUSD |
| `signal_id` | Unique UUID per signal |
| `event_type` | INTENT / ORDER_PLACED / FILL / TRADE_CLOSED / RISK_BLOCK / KILL_SWITCH |
| `side` | LONG / SHORT |
| `entry_type` | LIMIT / MARKET |
| `entry_price_intent` | Intended entry price |
| `sl_price` | Stop loss level |
| `tp_price` | Take profit level |
| `ttl_bars` | Order TTL in H1 bars |
| `parentOrderId` | IBKR parent order ID |
| `tpOrderId` | IBKR TP order ID |
| `slOrderId` | IBKR SL order ID |
| `order_create_time` | When order was submitted |
| `fill_time` | When entry was filled |
| `fill_price` | Actual entry fill price |
| `exit_time` | When trade was closed |
| `exit_price` | Actual exit fill price |
| `exit_reason` | TP / SL / CANCEL / EXPIRE |
| `latency_ms` | fill_time − order_create_time (ms) |
| `slippage_entry_pips` | fill_price vs intended entry (pips) |
| `slippage_exit_pips` | exit_price vs intended SL/TP (pips) |
| `realized_R` | R-multiple: (exit−entry) / risk_distance |
| `commissions` | IB commission (USD, if available) |
| `spread_at_entry` | ask−bid at fill time |
| `status_timeline` | e.g. `Submitted | Filled | Closed_TP` |

### `logs/paper_trading.csv` (legacy — compact)

Backward-compatible format for older scripts.

---

## 7. Kill Switch

### Manual (ENV)

```bash
# Immediately stop all new orders
KILL_SWITCH=true

# Restart cleanly:
KILL_SWITCH=false
```

### Automatic (rolling drawdown)

The engine auto-activates the kill switch when:

```
(peak_equity − current_equity) / peak_equity × 100 ≥ kill_switch_dd_pct
```

Default `kill_switch_dd_pct = 10.0` (10% drawdown from peak).

Configure in `config/config.yaml`:

```yaml
risk:
  kill_switch_dd_pct: 10.0
```

When auto-activated:
- All pending limit orders remain open (cancel manually in Gateway if needed).
- No new orders are placed.
- Event logged as `KILL_SWITCH` in `paper_trading_ibkr.csv`.

---

## 8. Architecture Overview

```
config/config.yaml
      │
      ▼
Config.from_env()  ←── ENV variables
      │
      ├── StrategyConfig  (frozen from PROOF V2)
      ├── RiskConfig
      └── IBKRConfig
            │
            ▼
  ┌─────────────────────────────────────┐
  │   run_paper_ibkr_gateway.py         │
  │   (main loop, 30 s poll)            │
  └────────┬──────────┬─────────────────┘
           │          │
           ▼          ▼
  IBKRMarketData  IBKRExecutionEngine
  (ib_insync)     (3-gate safety)
   │                │
   │  H1 bars       │  bracket orders
   ▼                ▼
TrendFollowingStrategy   TradingLogger
(BOS + Pullback)         paper_trading_ibkr.csv
```

**No strategy logic is changed.** The core (`src/core/strategy.py`) is identical
to the backtest. Only the data source and execution layer differ.

---

## 9. Troubleshooting

### `[ERROR] IBKR connect failed: TimeoutError`

- Is IB Gateway running and logged in?
- Check port: Gateway paper = **4002**, TWS paper = **7497**
- Check clientId is not already used by another API connection

### `[WARN] Historical data unavailable`

- Gateway may need a **market data subscription** for the symbol.
- During off-hours (weekend), some symbols return empty history.
- For FX, ensure you have "Forex" market data subscription active.

### `[ERROR] No bars after bootstrap`

- Verify the symbol is in the supported list: `EURUSD`, `GBPUSD`, `USDJPY`
- Check Gateway console for API permission errors.

### Orders not filling

- In dry-run mode, orders are never sent — see `[DRY_RUN]` in output.
- Confirm `IBKR_READONLY=false` AND `ALLOW_LIVE_ORDERS=true` AND `--allow_live_orders` flag.
- Check Gateway paper account has sufficient virtual funds.

### `pacing violation` in logs

- IBKR limits historical data requests. Wait ~30 seconds between reconnects.

---

*Last updated: 2026-02-20*

