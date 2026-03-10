# BojkoIDX — Complete Technical Documentation

> **Audience**: Engineers and AI systems modifying or extending this codebase.
> **Date**: 2026-03-08

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Directory Structure](#3-directory-structure)
4. [Key Classes and Components](#4-key-classes-and-components)
5. [Strategy Logic](#5-strategy-logic)
6. [Data Flow](#6-data-flow)
7. [Backtesting Engine](#7-backtesting-engine)
8. [Configuration System](#8-configuration-system)
9. [Testing Strategy](#9-testing-strategy)
10. [Potential Risks and Weak Points](#10-potential-risks-and-weak-points)
11. [Suggestions for Improvement](#11-suggestions-for-improvement)
12. [Example End-to-End Flow](#12-example-end-to-end-flow)
13. [File-Level Mapping](#13-file-level-mapping)

---

## 1. Project Overview

### Purpose

BojkoIDX is an **algorithmic trading system** that implements a trend-following, two-timeframe **Break of Structure (BOS) + Pullback** strategy. It has two independently operating modes:

| Mode | Purpose |
|------|---------|
| **Live Paper Trading** | Connects to Interactive Brokers Gateway, receives real-time FX price data, and places bracket orders on a paper account. |
| **Historical Backtesting** | Replays historical bar data through the same strategy logic to evaluate performance, output trade records, and produce research reports. |

### Problem It Solves

The system enables a trader to:
1. Research whether a structural breakout + pullback entry pattern is statistically profitable across different FX pairs and index instruments.
2. Run automated paper trades against a live broker feed with the exact same logic, ensuring continuity between research and live execution.
3. Compare across multiple timeframes, instruments, and parameter sets via grid backtests.

### System Type

- **Backtesting engine** (primary research tool)
- **Live paper trading bot** (secondary, production-grade)
- **Research tool** (regime classifier, grid search, OOS validation)

### Supported Markets and Instruments

| Category | Instruments |
|----------|------------|
| FX (live + backtest) | EURUSD, GBPUSD, USDJPY, USDCHF, AUDJPY, CADJPY, EURJPY, GBPJPY |
| Indices (backtest only) | US100 (USATECHIDXUSD) via Dukascopy 1M data |

Live trading is FX-only (IBKR `Forex` contract type). Index instruments are used only in offline backtesting.

### Supported Data Sources

| Source | How Used |
|--------|---------|
| **Dukascopy** (via `dukascopy-node` npm package) | Historical 1M BID bars, downloaded locally as CSV |
| **IBKR Gateway / TWS** | Live tick streaming + H1 historical bars (via `ib_insync`) |

---

## 2. High-Level Architecture

### Two Operating Modes

```
┌─────────────────────────────────────────────┐
│              BACKTEST MODE                  │
│                                             │
│  data/1M/ CSVs                              │
│       ↓                                     │
│  scripts/build_h1_idx.py                    │
│       ↓ resample to LTF/HTF                 │
│  data/bars_idx/ CSVs                        │
│       ↓                                     │
│  scripts/run_backtest_idx.py                │
│       ↓ loads bars, runs                    │
│  src/strategies/trend_following_v1.py       │
│       ↓ produces trades                     │
│  reports/ (CSV + MD files)                  │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│             LIVE PAPER TRADING              │
│                                             │
│  IBKR Gateway (port 4002)                  │
│       ↓                                     │
│  src/data/ibkr_marketdata.py               │
│  (bootstrap H1 history + live tick stream)  │
│       ↓                                     │
│  src/runners/run_paper_ibkr_gateway.py      │
│  (main loop, 30s poll)                      │
│       ↓                                     │
│  src/core/strategy.py                       │
│  (TrendFollowingStrategy.process_bar)       │
│       ↓ OrderIntent                         │
│  src/execution/ibkr_exec.py                 │
│  (IBKRExecutionEngine — bracket orders)     │
│       ↓                                     │
│  src/core/state_store.py (SQLite)           │
│  src/reporting/logger.py (CSV)              │
└─────────────────────────────────────────────┘
```

### Module Dependency Graph

```
src/core/
  config.py         ← loaded by almost all modules
  models.py         ← Bar, Signal, OrderIntent, Fill dataclasses
  strategy.py       → uses: core/config, core/models, core/state_store
  state_store.py    ← SQLite persistence layer

src/structure/
  pivots.py         ← used by: strategies/trend_following_v1.py
  bias.py           ← uses: pivots.py; used by: strategies/trend_following_v1.py

src/strategies/
  trend_following_v1.py  → uses: structure/pivots, structure/bias, backtest/setup_tracker
                            ← called by: scripts/run_backtest_idx.py

src/backtest/
  setup_tracker.py  ← used by: strategies/trend_following_v1.py
  execution.py      ← used by: backtest/engine.py, backtest/engine_enhanced.py
  execution_partial_tp.py ← used by: backtest/engine_enhanced.py
  engine.py         → uses: zones/detect_zones, backtest/execution, indicators/atr
  engine_enhanced.py → uses: all of engine.py + indicators/ema, pivots, htf_location, session_filter
  metrics.py        ← used by: reporting modules

src/indicators/
  atr.py            ← standard Wilder ATR
  ema.py            ← EMA
  pivots.py         ← older pivot detection (no anti-lookahead; used by zones engine)
  htf_location.py   ← HTF context filter
  session_filter.py ← London/NY session classifier

src/zones/
  detect_zones.py   ← Supply/Demand zone detection (older engine path)

src/execution/
  ibkr_exec.py      → uses: core/models, core/config; called by: runners

src/data/
  ibkr_marketdata.py → uses: ib_insync; called by: runners
  download_dukascopy_m1_years.py ← standalone data downloading script

src/runners/
  run_paper_ibkr_gateway.py → orchestrates all live modules
  run_paper_ibkr.py         → legacy wrapper

src/reporting/
  logger.py   → writes logs/paper_trading_ibkr.csv, logs/paper_trading.csv
  report.py   → writes reports/ (backtest summary CSVs + .md files)

src/research/
  regime_classifier/ ← standalone research tool, no production dependency

src/utils/
  config.py   ← YAML config loader (legacy dict format)
```

### Control Flow: Backtest Mode

```
scripts/run_backtest_idx.py
  1. parse --ltf, --htf, --start, --end, --rr args
  2. load_ltf()          → read data/bars_idx/{symbol}_{tf}_bars.csv
  3. build_htf_from_ltf() → resample LTF to HTF via pandas
  4. filter_by_date()    → clip to date range
  5. run_trend_backtest() [strategies/trend_following_v1.py]
     a. calculate ATR-14 on LTF
     b. detect_pivots_confirmed() on LTF and HTF
     c. for each LTF bar:
        i.   check open position SL/TP
        ii.  check setup fill
        iii. get HTF bias
        iv.  detect BOS
        v.   create setup
  6. write trades CSV + report MD to reports/
```

### Control Flow: Live Mode

```
src/runners/run_paper_ibkr_gateway.py
  1. parse args (--symbol, --config, --allow_live_orders)
  2. Config.from_yaml()
  3. connect IB()  [ib_insync]
  4. IBKRMarketData.subscribe_symbol()  → bootstrap 60 days history
  5. every 30 seconds:
     a. IBKRMarketData.update_bars()    → close sealed H1 bars
     b. if new H1 bar:
        TrendFollowingStrategy.process_bar()  → List[OrderIntent]
     c. for each OrderIntent:
        IBKRExecutionEngine.submit_bracket()  → IBKR order IDs
     d. IBKRExecutionEngine.check_fills()     → log results
```

---

## 3. Directory Structure

```
BojkoIDX/
├── config/
│   └── config.yaml              ← YAML config file for live trading
│
├── data/
│   ├── 1M/                      ← Raw Dukascopy 1-minute BID CSVs
│   │   └── usatechidxusd-m1-bid-*.csv
│   └── bars_idx/                ← Pre-built resampled bars for index backtests
│       ├── usatechidxusd_1h_bars.csv
│       ├── usatechidxusd_30m_bars.csv
│       ├── usatechidxusd_15m_bars.csv
│       └── usatechidxusd_5m_bars.csv
│
├── docs/                        ← Documentation
│   ├── TECHNICAL_DOCUMENTATION.md  ← This file
│   ├── AI_CONTEXT.md            ← Quick reference for AI agents
│   ├── ARCHITECTURE.md          ← Original FX architecture overview
│   ├── TRADING_HOURS.md         ← Session analysis notes
│   └── guides/                  ← Implementation guides
│
├── logs/
│   ├── paper_trading_ibkr.csv   ← Detailed IBKR paper trade log
│   └── paper_trading.csv        ← Legacy simple log
│
├── reports/
│   ├── IDX_USATECHIDXUSD_SUMMARY.md   ← Multi-TF index backtest results
│   ├── IDX_USATECHIDXUSD_*_BACKTEST_REPORT.md
│   └── *.csv / *.md             ← Various FX backtest reports
│
├── scripts/
│   ├── build_h1_idx.py          ← 1M → any TF bar builder (index)
│   ├── run_backtest_idx.py      ← Single LTF/HTF backtest runner (index)
│   └── run_idx_summary.py       ← Multi-TF multi-year summary generator
│
├── src/
│   ├── backtest/                ← Backtesting engines and execution simulation
│   ├── core/                    ← Shared config, models, strategy, state persistence
│   ├── data/                    ← Data acquisition (Dukascopy download, IBKR market data)
│   ├── data_processing/         ← Tick → bar conversion
│   ├── data_sources/            ← (reserved / empty)
│   ├── execution/               ← Live IBKR order execution
│   ├── indicators/              ← ATR, EMA, pivot detection, session filter, HTF location
│   ├── live/                    ← (reserved)
│   ├── reporting/               ← Trade logging and report generation
│   ├── research/                ← Research tools (regime classifier, grid search)
│   ├── runners/                 ← Live trading entry points
│   ├── sim/                     ← (reserved)
│   ├── strategies/              ← Primary strategy: BOS + Pullback
│   ├── structure/               ← Market structure: pivot detection and HTF bias
│   ├── utils/                   ← Legacy YAML config loader
│   └── zones/                   ← Supply/Demand zone detection (older engine path)
│
├── tests/                       ← Unit tests (pytest)
├── tests_backtests/             ← Backtest-specific engine tests
└── package.json                 ← npm (for dukascopy-node downloader)
```

### Module Role Summary

| Directory | Role | Key Files |
|-----------|------|-----------|
| `src/core/` | Central hub: typed configuration, data models, strategy interface, SQLite state | `config.py`, `models.py`, `strategy.py`, `state_store.py` |
| `src/structure/` | Anti-lookahead pivot detection and HTF trend bias | `pivots.py`, `bias.py` |
| `src/strategies/` | BOS+Pullback main backtest loop (the "truth" strategy) | `trend_following_v1.py` |
| `src/backtest/` | Simulated execution engines (zones-based and BOS-based), metrics | `setup_tracker.py`, `execution.py`, `engine.py`, `engine_enhanced.py`, `metrics.py` |
| `src/indicators/` | Technical indicator calculations | `atr.py`, `ema.py`, `pivots.py`, `session_filter.py`, `htf_location.py` |
| `src/zones/` | Supply/Demand zone detection used by older `engine.py` path | `detect_zones.py` |
| `src/execution/` | IBKR live order submission, bracket order lifecycle | `ibkr_exec.py` |
| `src/data/` | Data download (Dukascopy) and IBKR market data streaming | `download_dukascopy_m1_years.py`, `ibkr_marketdata.py` |
| `src/data_processing/` | Tick-to-bar conversion | `tick_to_bars.py` |
| `src/runners/` | Live trading orchestration entry points | `run_paper_ibkr_gateway.py`, `run_paper_ibkr.py` |
| `src/reporting/` | CSV trade log, equity report, markdown summaries | `logger.py`, `report.py` |
| `src/research/` | Experimental market regime classifier | `regime_classifier/classifier.py` |
| `src/utils/` | Legacy YAML loader (`load_config`) | `config.py` |
| `scripts/` | Index data pipeline: build bars, run backtests, generate summaries | `build_h1_idx.py`, `run_backtest_idx.py`, `run_idx_summary.py` |

---

## 4. Key Classes and Components

### 4.1 `Config` — `src/core/config.py`

**What it does**: Typed dataclass hierarchy loaded from `config/config.yaml`. Holds all runtime parameters.

**Sub-dataclasses**:

| Class | Purpose |
|-------|---------|
| `StrategyConfig` | Pivot lookbacks, ATR multipliers, RR, SL anchor |
| `SymbolConfig` | Per-symbol: LTF/HTF timeframes, session filter hours, ADX gate, trailing stop |
| `RiskConfig` | Risk fraction, max positions, daily/monthly loss limits, kill switch |
| `IBKRConfig` | Connection details (host, port, clientId, readonly flag) |

**Key method**: `Config.from_yaml(path)` — loads YAML, falls back to defaults if file missing.

**Default symbols in `DEFAULT_SYMBOLS`**:
- EURUSD: H1/D1, session 08-21 UTC, ADX gate 16.0
- USDJPY: H1/D1, no session filter, RR=2.5, trailing stop (ts_r=2.0, lock_r=0.5)
- CADJPY: H1/D1, ATR filter 10-80%, RR=3.0, trailing stop

---

### 4.2 `TrendFollowingStrategy` — `src/core/strategy.py`

**What it does**: Stateless-ish strategy class for the live trading path. Processes a new bar and generates `OrderIntent` objects.

**Inputs**: `ltf_bars` (H1 DataFrame), `htf_bars` (H4 DataFrame), `current_bar_idx` (int)
**Outputs**: `List[OrderIntent]`
**Responsibilities**:
- Calculates ATR over a rolling 200-bar window
- Detects pivot highs and lows
- Detects BOS (close above last pivot high = LONG; below last pivot low = SHORT)
- Calculates entry, SL, TP from BOS level and ATR
- Optionally persists state to `SQLiteStateStore` (idempotency on restart)
- Cleans expired setups from `active_setups` dict

**Note**: This is a *simplified* strategy class. The authoritative backtest strategy is `trend_following_v1.py` which includes anti-lookahead pivot confirmation and the full HTF bias filter.

---

### 4.3 `run_trend_backtest` — `src/strategies/trend_following_v1.py`

**What it does**: The authoritative BOS+Pullback backtest engine. This is the "frozen" strategy used for all historical testing.

**Signature**:
```python
run_trend_backtest(symbol, ltf_df, htf_df, params_dict, initial_balance=10000)
    → (trades_df, metrics_dict)
```

**Inputs**:
- `ltf_df` — LTF bars with `open/high/low/close_bid/ask` columns, `DatetimeIndex`
- `htf_df` — HTF bars (same structure)
- `params_dict` — strategy parameter overrides (see Section 8)

**Outputs**:
- `trades_df` — one row per closed trade (entry/exit prices, R, feasibility flags, etc.)
- `metrics_dict` — aggregated stats (win rate, expectancy R, profit factor, max DD, etc.)

**Processing sequence** (per bar):

```
for each LTF bar i:
  1. if open position:         → check SL/TP → close if triggered
  2. if active setup:          → check fill → open position if filled; expire if TTL exceeded
  3. elif no position AND no setup AND not NEUTRAL HTF:
       a. check BOS
       b. if BOS aligns with HTF bias → create PullbackSetup
```

---

### 4.4 `detect_pivots_confirmed` — `src/structure/pivots.py`

**What it does**: Detects swing highs/lows with anti-lookahead delay.

**Inputs**: `df` (bar DataFrame), `lookback` (int), `confirmation_bars` (int)
**Outputs**: Four `pd.Series` aligned to `df.index`:
- `pivot_highs` (bool) — True at confirmation bar
- `pivot_lows` (bool) — True at confirmation bar
- `ph_levels` (float) — price at confirmed pivot high
- `pl_levels` (float) — price at confirmed pivot low

**Mechanism**:

```
Raw pivot at bar i:
  is_pivot_high[i] = (high[i] == max(high[i-k : i+k+1]))
  
Confirmed at bar i + confirmation_bars:
  if raw_pivot_high[i - conf_bars]:
      confirmed_high[i] = True
      confirmed_high_level[i] = high_level[i - conf_bars]
```

This ensures the strategy cannot see a pivot until `confirmation_bars` after the qualifying bar, eliminating lookahead bias.

---

### 4.5 `get_htf_bias_at_bar` / `determine_htf_bias` — `src/structure/bias.py`

**What it does**: Determines the higher-timeframe trend direction at a given bar timestamp.

**Anti-lookahead**: Uses only HTF bars with `index ≤ current_bar_time`.

**Bias rules** (from the last `pivot_count=4` confirmed pivots):

```
BULL if:
  (highs[0] > highs[1]  AND  lows[0] > lows[1])   # HH + HL
  OR  close > most_recent_pivot_high                # Above-structure breakout

BEAR if:
  (lows[0] < lows[1]  AND  highs[0] < highs[1])   # LL + LH
  OR  close < most_recent_pivot_low

Else: NEUTRAL (no trade)
```

Note: the arrays are ordered most-recent-first (index 0 = latest pivot).

---

### 4.6 `SetupTracker` — `src/backtest/setup_tracker.py`

**What it does**: Manages the lifecycle of one pending limit-order setup (BOS → fill or expire).

**State**: One active `PullbackSetup` at a time (creating a new one discards any unfilled prior).

**`PullbackSetup` fields**: `direction`, `bos_level`, `bos_time`, `entry_price`, `expiry_time`, `htf_bias`, `is_filled`, `is_expired`, `bars_to_fill`

**Key methods**:

| Method | Logic |
|--------|-------|
| `create_setup(...)` | Expires current active setup (if any), creates new one |
| `check_fill(bar, current_time)` | LONG: `low_ask ≤ entry ≤ high_ask`; SHORT: `low_bid ≤ entry ≤ high_bid`. Returns `True` if filled. Expires if `current_time ≥ expiry_time`. |
| `get_stats()` | Returns `{total_setups, filled, missed, missed_rate, avg_bars_to_fill}` |

---

### 4.7 `ExecutionEngine` — `src/backtest/execution.py`

**What it does**: Simulates order execution for the Supply/Demand zone backtest path (legacy).

**State**: `positions` (open trades), `pending_orders` (limit orders awaiting fill), `closed_trades`

**Bid/Ask model**:
- LONG buy: triggered when `low_ask ≤ order_price`; feasibility check: `low_ask ≤ price ≤ high_ask`
- SHORT sell: triggered when `high_bid ≥ order_price`; feasibility check: `low_bid ≤ price ≤ high_bid`
- LONG exit: on BID side (`low_bid ≤ sl` or `high_bid ≥ tp`)
- SHORT exit: on ASK side (`high_ask ≥ sl` or `low_ask ≤ tp`)

**Conflict resolution**: If both SL and TP hit intrabar → SL always wins (conservative/worst-case).

---

### 4.8 `IBKRExecutionEngine` — `src/execution/ibkr_exec.py`

**What it does**: Submits bracket orders (entry + TP + SL) to IBKR via `ib_insync`.

**Safety gates** (all three must pass):
1. `readonly = False`
2. `allow_live_orders = True`
3. `kill_switch_active = False`

If any gate is active → logs intent as `DRY`, returns sentinel order-id `-1`.

**Bracket model**: LIMIT parent → attached LMT (TP) + STP (SL) child orders, with GTD time-in-force equal to `pullback_max_bars` × 1 hour.

**Price rounding**: `_round_price()` rounds to IBKR minimum tick size per symbol (JPY pairs: 0.005, others: 0.00005) to avoid "Warning 110 — Price does not conform to the minimum price variation."

---

### 4.9 `SQLiteStateStore` — `src/core/state_store.py`

**What it does**: SQLite-backed crash-safe state persistence for live trading.

**Database tables**:

| Table | Purpose |
|-------|---------|
| `strategy_state` | Last processed bar, last pivot high/low, last BOS per symbol |
| `orders` | Full OrderIntent lifecycle: CREATED → SUBMITTED → FILLED → CLOSED |
| `risk_state` | Key-value store for peak equity, kill-switch flag, daily loss |
| `events` | Append-only audit log (INTENT_CREATED, FILL, EXIT, etc.) |

**Idempotency**: `make_intent_id(symbol, side, bos_level, bos_bar_ts)` computes a SHA-1 hash. If that `intent_id` already exists in `orders`, the strategy skips re-generating the same signal after a restart.

**Journal mode**: WAL (`synchronous=NORMAL`) — crash-safe without a full RDBMS.

---

### 4.10 `RegimeClassifier` — `src/research/regime_classifier/classifier.py`

**What it does**: Research-only tool. Classifies each H1 bar as `TREND_UP`, `TREND_DOWN`, `RANGE`, `HIGH_VOL_CHOP`, or `HIGH_VOL_TREND`.

**Features used**: ADX(14), EMA(200) slope (tanh-normalized), distance from EMA in ATR units, EMA crossings in last 50 bars, net/total move ratio, ATR percentile (252-bar lookback).

**Not used in production** — no live or backtest code depends on it.

---

### 4.11 `PartialTPEngine` — `src/backtest/execution_partial_tp.py`

**What it does**: Extends `ExecutionEngine` to support split-close: 50% at +1R, SL moves to breakeven, 50% at final target.

Used in the enhanced backtest path (`engine_enhanced.py` with `use_partial_tp=True`).

---

## 5. Strategy Logic

### Overview

The strategy is a **two-timeframe trend-following** system:
1. A higher timeframe (HTF, typically H4 or D1) defines the trend direction.
2. The lower timeframe (LTF, typically H1 or 30M) detects breakouts.
3. An entry is placed on a **pullback** after the breakout, not at the breakout itself.

### Step-by-Step: Per-Bar Logic

#### Step 1 — Open Position Management

If a position is open, every bar checks for exit:

```python
# LONG position
sl_hit = low_bid <= position['sl']
tp_hit = high_bid >= position['tp']

if sl_hit and tp_hit:     exit at sl  # worst-case
elif sl_hit:              exit at sl
elif tp_hit:              exit at tp
```

- **LONG exits on BID** (selling out)
- **SHORT exits on ASK** (buying back)
- **Price clamping**: exit price clamped to bar's feasible range; raises `ValueError` if still infeasible after clamp
- **R calculation**: `R = (exit_price - entry) / risk_distance` (LONG); negative for losses

#### Step 2 — Setup Fill Check

If a `PullbackSetup` is active:
- Check expiry: if `current_time ≥ expiry_time` → mark expired, add to `missed_setups`
- LONG fill: `low_ask ≤ entry_price ≤ high_ask`
- SHORT fill: `low_bid ≤ entry_price ≤ high_bid`

On fill:
```python
# Calculate SL
sl_time, sl_level = get_last_confirmed_pivot(df, pivot_lows, ...)
sl = sl_level - sl_buffer_atr × ATR           # LONG
sl = sl_level + sl_buffer_atr × ATR           # SHORT

# Calculate TP
risk = |entry - sl|
tp = entry + risk × risk_reward               # LONG
tp = entry - risk × risk_reward               # SHORT
```

#### Step 3 — HTF Bias Calculation

Only runs if no position and no active setup:

```python
htf_bias = get_htf_bias_at_bar(htf_df, current_time, ...)
if htf_bias == 'NEUTRAL':
    continue  # skip bar
```

The HTF check uses only bars `≤ current_time` (anti-lookahead).

#### Step 4 — BOS Detection

```python
bos, direction, bos_level = check_bos(ltf_df, i, pivot_highs, pivot_lows, ...)

# LONG BOS: close > last confirmed pivot high
# SHORT BOS: close < last confirmed pivot low
# require_close_break=True: wick alone insufficient
```

Direction filter:
```python
if LONG BOS but HTF != BULL: skip
if SHORT BOS but HTF != BEAR: skip
```

#### Step 5 — Setup Creation

```python
atr = current_bar['atr']

entry_price = bos_level + entry_offset_atr × ATR  # LONG: above BOS
entry_price = bos_level - entry_offset_atr × ATR  # SHORT: below BOS

expiry_time = current_time + pullback_max_bars bars
tracker.create_setup(direction, bos_level, bos_time, entry_price, expiry_time, ...)
```

Entry is placed **above the BOS level for LONG** — the expectation is that price will pull back to this level rather than immediately continue, providing a better entry risk/reward. The entry offset ensures the order doesn't fill on the same bar as the BOS.

### Complete Trade Lifecycle

```
[BAR N]   HTF = BULL
           close > last pivot high  →  LONG BOS detected  →  setup created
           entry_price = bos_level + 0.3×ATR
           expiry = bar N + 20

[BAR N+k] (k ≤ 20)
           low_ask ≤ entry_price ≤ high_ask  →  FILL
           SL = last_confirmed_pivot_low - 0.5×ATR
           TP = entry + (entry - SL) × 2.0
           Position opened with {entry, sl, tp}

[BAR N+j] (j > k)
           high_bid ≥ tp  →  TP hit
           exit at tp (clamped to [low_bid, high_bid])
           R = (tp - entry) / (entry - sl) ≈ +2.0
           Trade appended to trades list, position cleared
```

### ATR Calculation

Uses Wilder's 14-period ATR, calculated on **BID prices** (`high_bid`, `low_bid`, `close_bid`):

```
TR[i] = max(high[i] - low[i], |high[i] - close[i-1]|, |low[i] - close[i-1]|)
ATR[i] = EMA(TR, α=1/14)   (simple rolling mean in trend_following_v1.py)
```

Note: `indicators/atr.py` uses Wilder's EWM (`ewm(alpha=1/14)`), while `trend_following_v1.py` uses `rolling(14).mean()`. These differ slightly in warm-up behavior but converge.

---

## 6. Data Flow

### 6.1 Index Backtest Data Pipeline

```
data/1M/usatechidxusd-m1-bid-{year}.csv
    │
    │  scripts/build_h1_idx.py
    │  load_and_concat_m1():
    │    - glob all files matching symbol prefix
    │    - parse timestamp_ms as UTC datetime
    │    - deduplicate + sort by timestamp
    ↓
  1M DataFrame
  columns: open, high, low, close, volume
  index:   DatetimeIndex (UTC)
    │
    │  resample_m1(df, timeframe):
    │    - pandas resample(timeframe, closed='left', label='left')
    │    - agg: open=first, high=max, low=min, close=last
    │    - drop all-NaN rows
    ↓
  Resampled DataFrame (any TF: 5min, 15min, 30min, 1h, 4h, …)
    │
    │  add_bid_ask_columns(df, spread):
    │    - rename open/high/low/close → open_bid/high_bid/low_bid/close_bid
    │    - ASK = BID + spread  (constant, default spread=1.0 pt for US100)
    ↓
  data/bars_idx/{symbol}_{tf}_bars.csv
  columns: open_bid, high_bid, low_bid, close_bid,
           open_ask, high_ask, low_ask, close_ask
  index:   DatetimeIndex (UTC, column name "timestamp")
```

### 6.2 Raw Data Format

Dukascopy 1M CSV (`-m1-bid-` variant):

```
timestamp,open,high,low,close,volume
1609459200000,12868.0,12913.0,12868.0,12913.0,143
1609459260000,12913.0,12913.0,12869.0,12869.0,107
...
```

- `timestamp`: milliseconds since Unix epoch (UTC)
- `open, high, low, close`: BID OHLC prices (raw points, e.g. 12868.0 = 12868 pts for US100)
- `volume`: tick volume

### 6.3 Bar DataFrame Format (standard throughout system)

```
                        open_bid  high_bid   low_bid close_bid  open_ask  high_ask   low_ask close_ask
timestamp
2021-01-04 00:00:00+00:00  12868.0  13054.2  12860.1   12976.4  12869.0  13055.2  12861.1   12977.4
2021-01-04 01:00:00+00:00  12976.4  13010.5  12945.6   12990.1  12977.4  13011.5  12946.6   12991.1
```

### 6.4 FX Live Data Pipeline (IBKR)

```
IBKR Gateway (port 4002)
    │
    │  IBKRMarketData.subscribe_symbol():
    │    - request historical data (reqHistoricalData, last 60 days, 1H bars)
    │    - parse midpoint bars
    │    - apply half-spread (per-symbol constant) to get bid/ask columns
    ↓
Bootstrap H1 DataFrame (in-memory)
    │
    │  IBKRMarketData.update_bars() [called every 30s]:
    │    - receive live ticks (reqMktData)
    │    - accumulate in current-bar bucket
    │    - when hour boundary passes → seal completed bar → append to DataFrame
    ↓
Live H1 + H4 DataFrames
    │
    │  strategy.process_bar(ltf_bars, htf_bars, current_bar_idx)
    ↓
OrderIntent → IBKRExecutionEngine.submit_bracket()
```

### 6.5 Indicators Applied

| Indicator | Where | Column(s) Used |
|-----------|-------|----------------|
| ATR-14 | LTF bars | `high_bid`, `low_bid`, `close_bid` |
| Pivot High/Low | LTF + HTF bars | `high_bid`, `low_bid` |
| HTF Bias | HTF bars | Pivot sequence derived from `high_bid`/`low_bid` |
| EMA-200 | Optional filter (enhanced engine) | `close_bid` |
| ADX-14 | Optional gate (per-symbol SymbolConfig) | `high_bid`, `low_bid`, `close_bid` |
| Session Filter | Optional per-symbol gate | `timestamp` hour (UTC) |
| ATR Percentile | Optional CADJPY filter | ATR rolling percentile over 252 bars |

---

## 7. Backtesting Engine

### 7.1 Backtest Loop Overview

The main loop in `trend_following_v1.py::run_trend_backtest()` iterates bar-by-bar through `ltf_df` using a pure Python `for i in range(len(ltf_df))` loop — no vectorization. This is intentional: it prevents any form of future data leakage and mirrors the tick-by-tick evaluation of a live system.

### 7.2 Bar Processing Order Within Each Bar

The order within a single bar iteration is critical for anti-lookahead correctness:

```
1. EXIT check (position management)       ← uses current bar's price
2. FILL check (pending setup)             ← uses current bar's price
3. HTF BIAS update                        ← uses HTF data up to current_time
4. BOS detection                          ← uses confirmed pivots up to current bar
5. SETUP creation                         ← uses ATR from current bar
```

**Key rule**: Position/setup events are checked before new signals are generated. A BOS and its resulting setup can only be created when there is no open position and no pending setup.

### 7.3 Order Execution Model

**Entry model** (limit order simulation):
- A `PullbackSetup` acts as a pending limit order
- LONG: filled when ASK range covers `entry_price`
- SHORT: filled when BID range covers `entry_price`
- No partial fills; fills at exactly `entry_price`
- No slippage beyond the spread model

**Exit model** (stop-loss / take-profit):
- SL and TP are bracket orders checked each bar
- Triggered when bar's range touches the level on the correct price side
- Intrabar priority: SL wins over TP (conservative)
- Price clamping: if SL/TP is outside bar range (possible when pivot is far), clamped to bar's boundary

### 7.4 Spread Model

```
ASK = BID + fixed_spread
```

- Spread is constant (no intraday variation, no news spikes)
- Default for US100: 1.0 point
- FX instruments used with typical broker spreads

**Implication**: Real execution costs during high-volatility periods (economic releases, overnight gaps) are understated.

### 7.5 PnL Calculation

```python
# LONG trade
exit_pnl = (exit_price - entry_price) * 100000   # FX lot multiplier

# LONG R-value
risk_distance = entry_price - sl_price
realized_distance = exit_price - entry_price
R = realized_distance / risk_distance
```

**CRITICAL NOTE**: The `× 100000` multiplier is correct for 1-lot FX (pip value in USD for xxx/USD pairs). It is **meaningless for index instruments** (US100 points ≠ FX pips). For index backtests, always use the `R` column, never `pnl`.

### 7.6 Metrics Computed

After all trades:

| Metric | Calculation |
|--------|------------|
| `win_rate` | `(wins / total) × 100` (stored as %, e.g. 48.5) |
| `expectancy_R` | `mean(R)` across all trades |
| `profit_factor` | `sum(positive_pnl) / abs(sum(negative_pnl))` |
| `max_dd_pct` | Peak-to-trough drawdown on cumulative PnL equity curve |
| `max_losing_streak` | Longest consecutive losing streak |
| `missed_rate` | `missed_setups / total_setups` |
| `avg_bars_to_fill` | Mean bars elapsed from BOS to entry fill |

### 7.7 Partial TP Engine (optional)

When `use_partial_tp=True` in the enhanced backtest:
1. Entry: full position
2. First TP at +1R: close 50% of position, move SL to breakeven
3. Final TP (default +1.5R): close remaining 50%
4. If price reverses after first TP: exit at breakeven (0R on second half)

---

## 8. Configuration System

### 8.1 Two Config Systems (Historical Divergence)

There are **two independent config systems** in the codebase:

| System | Format | Used By |
|--------|--------|---------|
| `src/utils/config.py` + `config/config.yaml` | YAML dict (legacy) | `engine.py`, `engine_enhanced.py`, older backtest scripts |
| `src/core/config.py` + `Config` dataclasses | Typed Python dataclasses | `run_paper_ibkr_gateway.py`, `run_trend_backtest()`, strategy code |

New code should use `src/core/config.py`. The legacy system uses `load_config()` which returns a raw dict.

### 8.2 Strategy Parameters (typed system)

All parameters are in `StrategyConfig`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `pivot_lookback_ltf` | `3` | Pivot detection window half-size on LTF |
| `pivot_lookback_htf` | `5` | Pivot detection window half-size on HTF |
| `confirmation_bars` | `1` | Bars after raw pivot before it's confirmed |
| `require_close_break` | `True` | BOS needs a bar close through the level |
| `entry_offset_atr_mult` | `0.3` | Entry placed `0.3 × ATR` beyond BOS level |
| `pullback_max_bars` | `40` | Setup expires after this many bars |
| `sl_anchor` | `'last_pivot'` | SL placed at last confirmed opposite pivot |
| `sl_buffer_atr_mult` | `0.5` | SL buffer beyond pivot: `0.5 × ATR` |
| `risk_reward` | `1.5` | TP = entry ± risk × 1.5 |

**Note**: The index backtest scripts use `risk_reward=2.0` by default (passed as `--rr` arg), overriding the `StrategyConfig` default of `1.5`.

### 8.3 Per-Symbol Parameters (`SymbolConfig`)

Set in `DEFAULT_SYMBOLS` dict or overridden in `config.yaml`:

| Parameter | Description |
|-----------|-------------|
| `ltf` | LTF timeframe string: `"H1"` or `"30m"` |
| `htf` | HTF timeframe string: `"D1"`, `"H4"`, or `"H8"` |
| `session_filter` | Enable/disable session window restriction |
| `session_start_h` / `session_end_h` | UTC hour range for entries |
| `adx_h4_gate` | Minimum H4 ADX for entry (None = disabled) |
| `atr_pct_filter_min/max` | ATR percentile band filter (CADJPY: 10-80%) |
| `risk_reward` | Per-symbol RR override (None = use global) |
| `trailing_stop` | Dict: `{enabled, ts_r, lock_r}` — trailing stop activation |

### 8.4 Risk Parameters (`RiskConfig`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `risk_fraction_start` | `0.005` | 0.5% of equity per trade |
| `sizing_mode` | `'risk_first'` | Size by risk fraction (vs fixed units) |
| `max_open_positions_total` | `5` | Max concurrent positions across all symbols |
| `max_open_positions_per_symbol` | `1` | One position per symbol |
| `daily_loss_limit_pct` | `2.0` | Halt trading if daily loss exceeds 2% |
| `monthly_dd_stop_pct` | `15.0` | Halt if monthly DD exceeds 15% |
| `kill_switch_dd_pct` | `10.0` | Emergency kill switch at 10% DD |

---

## 9. Testing Strategy

### 9.1 Framework

**pytest** (both `tests/` and `tests_backtests/`). Tests can be run as standalone scripts with `if __name__ == "__main__"` or via pytest.

### 9.2 Test Structure

#### `tests/` — Unit Tests for Core Components

| File | What It Tests |
|------|--------------|
| `test_pivots_no_lookahead.py` | Anti-lookahead delay: pivot at bar 2 confirmed only at bar 3 |
| `test_bos_pullback_setup.py` | Setup creation and fill logic via `SetupTracker` |
| `test_missed_setup_expiry.py` | Setup expiry after `expiry_time` |
| `test_execution_logic.py` | `ExecutionEngine`: LONG limit fill, SL hit confirmation |
| `test_no_same_bar_entry.py` | Zone creation time tracking; conceptual same-bar entry prevention |
| `test_state_store.py` | SQLite tables, save/load `StrategyState`, idempotent migration |
| `test_full_run_metrics_yearly.py` | End-to-end backtest metrics computation (yearly breakdown) |
| `test_metrics_segments.py` | `metrics.py` segmented calculations |
| `test_tick_to_bars.py` | Tick-to-bar resampling |
| `test_trend_params_runtime.py` | *(empty — placeholder)* |
| `smoke_test_ibkr.py` | IBKR connection smoke test (requires live Gateway) |

#### `tests_backtests/` — Backtest Engine-Specific Tests

| File | What It Tests |
|------|--------------|
| `test_engine_fill_logic.py` | `try_fill()` edge cases (exact boundary, within range, out of range), `try_exit()` with conservative SL-wins-on-conflict |
| `test_indicators_adx_atr.py` | ADX and ATR indicator calculations |

### 9.3 Key Test Scenarios Covered

**Pivot detection anti-lookahead**:
```python
# High at bar 2 with lookback=2, confirmation_bars=1
# Expected: confirmed at bar 3, NOT bar 2
assert ph.iloc[2] == False
assert ph.iloc[3] == True
```

**Setup fill — LONG**:
```python
bar = {'low_ask': 1.1025, 'high_ask': 1.1050, ...}
entry_price = 1.1030
# low_ask (1.1025) ≤ entry (1.1030) ≤ high_ask (1.1050) → filled
```

**Setup expiry**:
```python
filled = tracker.check_fill(bar, timestamp_after_expiry)
assert filled == False
assert len(tracker.missed_setups) == 1
```

**Execution — conflict resolution**:
```python
# Both SL and TP hit in same bar → SL wins
result = try_exit(setup, open, high=1.1200(>tp), low=1.0940(<sl), ...)
assert result[0] == "SL"
```

**State store idempotency**:
```python
store.save_strategy_state(state)
loaded = store.load_strategy_state("EURUSD")
assert loaded.last_pivot_high.price == pytest.approx(1.1620)
```

### 9.4 Coverage Gaps

| Area | Gap |
|------|-----|
| `trend_following_v1.py` main loop | No dedicated integration test — relies on manual script runs |
| `bias.py` | No unit tests for `determine_htf_bias()` |
| `ibkr_exec.py` | No mock-based unit tests (requires live IB connection) |
| `run_paper_ibkr_gateway.py` | No integration tests |
| Trailing stop logic | No unit test (implemented in `ibkr_exec.py`) |
| `engine_enhanced.py` filters | Tested via backtest scripts, not pytest |
| `test_trend_params_runtime.py` | File exists but is empty |

---

## 10. Potential Risks and Weak Points

### 10.1 Lookahead Bias — Medium Risk

**Risk**: `src/indicators/pivots.py::detect_pivots()` (used by the older `engine.py`/zone path) does NOT apply a confirmation delay. It uses the full `[i-lookback, i+lookback]` window at detection time — this is a lookahead of `lookback` bars.

**Affected code**: `backtest/engine.py`, `backtest/engine_enhanced.py`, `zones/detect_zones.py`

**Safe code**: `src/structure/pivots.py::detect_pivots_confirmed()` — correctly delayed by `confirmation_bars`

**Recommendation**: The zone-based engine results should be treated with caution. The BOS+Pullback results (trend_following_v1) are free of this issue.

### 10.2 Intrabar Resolution — Medium Risk

**Risk**: All entries and exits are checked once per bar close. The actual sequence of prices within a bar is unknown. The system assumes:
1. SL and TP cannot both be "the first hit" — conflict is broken by assuming SL wins
2. Entry fills at exactly the limit price (no partial fills, no slippage within the bar)

**Real impact**: In trending markets, the actual sequence matters — a TP might actually be hit before an SL that the bar's low touches. The worst-case assumption makes the system conservative (understates gains, overstates losses) but introduces a systematic bias.

### 10.3 Constant Spread — Medium Risk

**Risk**: Real broker spreads are variable — wider during news events, overnight, and session transitions. Using a fixed spread understates trading costs in high-volatility periods.

**For FX**: Typical spread for EURUSD = 0.5-2 pips (varies by broker and time)
**For US100**: Typical spread = 0.5-2 points in normal conditions, 3-5+ during news

### 10.4 FX PnL Multiplier for Index Instruments — High Risk (Known)

**Risk**: `pnl = price_move × 100000` (FX lot multiplier) is used in `trend_following_v1.py`. This number is meaningless for US100.

**Mitigation already applied**: `run_backtest_idx.py` ignores `pnl` and computes an R-based drawdown metric separately. But if anyone calls `run_trend_backtest()` for index instruments and uses `pnl` directly, results will be wrong.

**Recommendation**: The `pnl` formula should be parameterized per instrument.

### 10.5 Single Position Per Symbol — Low Risk / Design Choice

**Risk**: The strategy holds at most one position and one pending setup simultaneously per run. This means:
- A BOS in the opposite direction while in a trade is ignored
- Setup cancellation on new opposing BOS means the system may miss a reversal entry

This is an intentional conservative design, not a bug.

### 10.6 HTF Resampled from LTF — Low Risk

**Risk**: The 4H HTF bars are built by resampling LTF bars. In live trading, IBKR provides H4 independently. In backtests, the H4 bar close time is exactly aligned with the LTF bar grid. Real H4 bars close at fixed UTC times (00:00, 04:00, 08:00, etc.) regardless of LTF.

**Impact**: Negligible for H1→H4 resampling if the H1 grid is correctly aligned. Could be a rounding issue for 30M or 5M LTF.

### 10.7 No Trade Costs / Commissions in Index Backtest — Low Risk

**Risk**: `run_trend_backtest()` does not deduct commissions. The `× 100000` PnL calculation is not used for index analysis (see above), but commissions are entirely ignored even in R-based analysis.

**Impact**: Small. For indices, a $5-10 round-trip commission on a $20,000 notional trade is ~0.05%, which is unlikely to materially change R-multiples. But for high-frequency 5M testing with 1,735 trades, cumulative cost matters.

### 10.8 Pivot Tie-Breaking

**Risk**: If two bars share the same `high` value in a pivot window, NumPy's `max()` will return the first occurrence. The bar with the earliest timestamp becomes the pivot. This edge case should be rare but is untested.

### 10.9 SQLiteStateStore — Single-Connection Assumption

The state store keeps one persistent `sqlite3.Connection` open. If the process is force-killed (`kill -9`), the WAL journal ensures crash safety. However, there is no explicit handling for disk-full conditions or permission errors beyond Python exceptions.

---

## 11. Suggestions for Improvement

### 11.1 Architecture

| Issue | Suggestion |
|-------|-----------|
| Two pivot detection implementations with different semantics | Consolidate: replace `src/indicators/pivots.py` with `src/structure/pivots.py` everywhere |
| Two config systems | Migrate all remaining code that uses `load_config()` (dict-based) to `Config` dataclasses |
| `pnl × 100000` hardcoded | Accept a `point_value` parameter in `run_trend_backtest()` (1 for FX, instrument-specific for indices) |
| `src/core/strategy.py` is a simplified duplicate | Either fully align with `trend_following_v1.py` (add HTF bias, confirmation delay) or document clearly what diverges |

### 11.2 Performance

| Issue | Suggestion |
|-------|-----------|
| O(n²) pivot scan in main loop | Pre-compute all confirmed pivots once before the loop (already done in `trend_following_v1.py`) using vectorized numpy — but `get_last_confirmed_pivot()` still scans backward each bar |
| `get_last_confirmed_pivot()` linear scan | Build a list of confirmed pivot indices once and binary-search by time |
| Full backtest in pure Python loop | For large datasets (5M × 4 years = 525K bars), consider Numba JIT or Cython for the inner loop |

### 11.3 Testing

| Gap | Suggestion |
|-----|-----------|
| No unit test for `bias.py` | Add tests for all three bias states (BULL, BEAR, NEUTRAL) with minimal pivot sequences |
| No integration test for `trend_following_v1.py` | Add a deterministic test: feed a synthetic known-bull dataset, assert exact trade count and R |
| `ibkr_exec.py` untestable without live connection | Add a mock `IB` object using `unittest.mock` to test order submission logic |
| Empty `test_trend_params_runtime.py` | Implement tests for runtime parameter overrides |

### 11.4 Maintainability

| Issue | Suggestion |
|-------|-----------|
| Backtest results stored as markdown files only | Add a structured results database (SQLite) for programmatic comparison |
| `run_idx_summary.py` hardcodes timeframes | Accept timeframe list as CLI argument |
| `DEFAULT_SYMBOLS` dict is the only place symbol config lives | Consider moving to `config/config.yaml` to allow runtime changes without code modification |
| Strategy "frozen" comment but code evolves | Add a changelog section to `trend_following_v1.py` documenting parameter changes over time |

---

## 12. Example End-to-End Flow

### Scenario: LONG trade on USATECHIDXUSD H1, 2023-02-15

**Setup:**
- LTF = H1, HTF = H4
- params: `pivot_lookback_ltf=3`, `pivot_lookback_htf=5`, `confirmation_bars=1`
- `entry_offset_atr_mult=0.3`, `pullback_max_bars=20`, `sl_buffer_atr_mult=0.5`, `RR=2.0`

---

**Bar 2023-02-15 09:00 — HTF bias check**

1. `get_htf_bias_at_bar()` filters H4 bars with index ≤ 09:00
2. Gets last H4 bar: `2023-02-15 08:00`
3. Retrieves last 4 confirmed H4 pivot highs and lows
4. Sequence: `highs = [(12200, 12300, 12150, 12050)]` — ascending
5. `lows` — also ascending
6. `determine_htf_bias()` returns `BULL`

**Bar 2023-02-15 09:00 — BOS detection**

1. `check_bos()` gets last confirmed LTF pivot high before 09:00
2. Last pivot high at 12250 (confirmed 1 bar ago)
3. Current `close_bid = 12268 > 12250` → **LONG BOS detected** at level `12250`
4. `ATR = 45.2` (14-bar average)

**Bar 2023-02-15 09:00 — Setup creation**

1. `entry_price = 12250 + 0.3 × 45.2 = 12263.6`
2. `expiry_time = bar 09:00 + 20 bars = 2023-02-16 05:00`
3. `tracker.create_setup(direction='LONG', bos_level=12250, entry_price=12263.6, expiry=...)`

**Bar 2023-02-15 11:00 — Price pulls back, fill check**

1. Bar: `{low_ask=12258, high_ask=12290, ...}`
2. `low_ask (12258) ≤ entry (12263.6) ≤ high_ask (12290)` → **FILL**
3. Fill at `12263.6` (limit price)

**SL/TP calculation on fill**:

1. `get_last_confirmed_pivot(pivot_lows)` → last pivot low = `12195.0` (confirmed)
2. `sl = 12195.0 - 0.5 × 45.2 = 12172.4`
3. `risk = 12263.6 - 12172.4 = 91.2`
4. `tp = 12263.6 + 91.2 × 2.0 = 12446.0`
5. Position opened: `{entry=12263.6, sl=12172.4, tp=12446.0}`

**Bar 2023-02-16 14:00 — TP hit**

1. Bar: `{low_bid=12390, high_bid=12450, ...}`
2. `high_bid (12450) ≥ tp (12446.0)` → TP hit
3. Exit at `12446.0` (within bar range, no clamping needed)
4. `realized_dist = 12446.0 - 12263.6 = 182.4`
5. `R = 182.4 / 91.2 = +2.0`
6. Trade appended to `trades` list, position cleared

**Result logged**:
```
entry_time: 2023-02-15T11:00:00
exit_time:  2023-02-16T14:00:00
direction:  LONG
entry_price: 12263.6
exit_price:  12446.0
pnl:         18240000.0   ← FX formula, IGNORE for indices
R:           2.0
exit_reason: TP
```

---

## 13. File-Level Mapping

### Core Strategy

| File | Responsibility |
|------|----------------|
| `src/strategies/trend_following_v1.py` | **Primary strategy engine**: BOS+Pullback backtest loop; `run_trend_backtest()` is the main entry point for all backtests |
| `src/structure/pivots.py` | Anti-lookahead pivot detection; `detect_pivots_confirmed()`, `get_last_confirmed_pivot()`, `get_pivot_sequence()` |
| `src/structure/bias.py` | HTF bias determination; `get_htf_bias_at_bar()`, `determine_htf_bias()` |
| `src/backtest/setup_tracker.py` | Setup lifecycle (BOS → limit order expiry/fill); `SetupTracker`, `PullbackSetup` |

### Configuration & Models

| File | Responsibility |
|------|----------------|
| `src/core/config.py` | Typed config: `Config`, `StrategyConfig`, `SymbolConfig`, `RiskConfig`, `IBKRConfig`; `DEFAULT_SYMBOLS` |
| `src/core/models.py` | Data model dataclasses: `Bar`, `Signal`, `OrderIntent`, `Fill`, `Side`, `ExitReason` |
| `src/core/strategy.py` | Strategy class for live trading: `TrendFollowingStrategy.process_bar()` |
| `src/core/state_store.py` | SQLite persistence: `SQLiteStateStore`, `StrategyState`, `DBOrderRecord`, `OrderStatus` |

### Backtest Infrastructure

| File | Responsibility |
|------|----------------|
| `src/backtest/engine.py` | Zone-based backtest loop (older/legacy path); calls `detect_zones` + `ExecutionEngine` |
| `src/backtest/engine_enhanced.py` | Zone-based backtest with optional EMA/BOS/HTF-location/session filters |
| `src/backtest/execution.py` | Simulated execution: `ExecutionEngine` (limit fills, SL/TP management) |
| `src/backtest/execution_partial_tp.py` | Partial TP variant: 50% @ +1R, move BE, 50% @ final target |
| `src/backtest/metrics.py` | Post-trade metrics: `compute_yearly_metrics()`, `compute_profit_factor()`, `compute_max_drawdown()` |

### Index Pipeline Scripts

| File | Responsibility |
|------|----------------|
| `scripts/build_h1_idx.py` | 1M CSV → any TF bars; `build_bars()`, `resample_m1()`, `add_bid_ask_columns()` |
| `scripts/run_backtest_idx.py` | Single LTF/HTF backtest runner; `run_backtest()`, `_calc_r_drawdown()`, generates report |
| `scripts/run_idx_summary.py` | 20-run (4 TF × 5 periods) combined summary; generates `IDX_USATECHIDXUSD_SUMMARY.md` |

### Indicators

| File | Responsibility |
|------|----------------|
| `src/indicators/atr.py` | Wilder ATR (EWM): `calculate_atr()` |
| `src/indicators/ema.py` | EMA calculation: `calculate_ema()`, `calculate_ema_from_df()` |
| `src/indicators/pivots.py` | Lookahead pivot detection (no confirmation delay!) — used by zone engine only |
| `src/indicators/session_filter.py` | London/NY session classification: `is_in_session()`, `get_session_name()` |
| `src/indicators/htf_location.py` | HTF range context: `build_htf_from_bars()`, `calculate_zone_position_in_htf_range()` |

### Live Trading

| File | Responsibility |
|------|----------------|
| `src/runners/run_paper_ibkr_gateway.py` | **Primary live entry point**: IB connect → event loop → strategy → execution |
| `src/runners/run_paper_ibkr.py` | Legacy wrapper (deprecated, prefer gateway runner) |
| `src/data/ibkr_marketdata.py` | IBKR market data: historical bootstrap + live tick streaming, sealed H1 bar production |
| `src/execution/ibkr_exec.py` | IBKR bracket order submission, fill monitoring, safety gates |

### Data Acquisition

| File | Responsibility |
|------|----------------|
| `src/data/download_dukascopy_m1_years.py` | Download Dukascopy 1M data year-by-year via `dukascopy-node` npm |
| `src/data/download_dukascopy_m1_sample.py` | Single-sample downloader |
| `src/data/merge_csv_without_duplicate_header.py` | Utility: merge multiple CSVs removing duplicate headers |
| `src/data_processing/tick_to_bars.py` | Convert raw tick CSV to OHLCV bars (for FX legacy pipeline) |

### Reporting & Logging

| File | Responsibility |
|------|----------------|
| `src/reporting/logger.py` | `TradingLogger`: writes `logs/paper_trading_ibkr.csv` (extended) + `paper_trading.csv` (legacy) |
| `src/reporting/report.py` | `generate_report()`: trades CSV, markdown summary, equity curve plot |

### Research

| File | Responsibility |
|------|----------------|
| `src/research/regime_classifier/classifier.py` | Market regime classification (TREND/RANGE/CHOP) using ADX + EMA features — research only |
| `src/research/regime_classifier/backtest_with_regime.py` | Strategy backtest conditioned on regime labels |
| `src/research/regime_classifier/grid_search.py` | Grid search over regime classifier thresholds |

### Tests

| File | Responsibility |
|------|----------------|
| `tests/test_pivots_no_lookahead.py` | Confirms anti-lookahead delay in `detect_pivots_confirmed()` |
| `tests/test_bos_pullback_setup.py` | Setup creation + fill logic |
| `tests/test_missed_setup_expiry.py` | Setup expiry after TTL |
| `tests/test_execution_logic.py` | `ExecutionEngine` fill + exit |
| `tests/test_no_same_bar_entry.py` | Anti-same-bar entry conceptual test |
| `tests/test_state_store.py` | SQLite state persistence |
| `tests/test_full_run_metrics_yearly.py` | End-to-end yearly metrics calculation |
| `tests/test_metrics_segments.py` | `metrics.py` isolated tests |
| `tests_backtests/test_engine_fill_logic.py` | Fill edge cases + conflict resolution |
| `tests_backtests/test_indicators_adx_atr.py` | ADX/ATR indicators |

---

*Generated: 2026-03-08 | Strategy: BOS+Pullback v1 (frozen) | Instruments: FX (live) + US100 (backtest)*
