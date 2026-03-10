# BojkoIDX — AI Context Document

> **Purpose**: This document explains the algorithmic assumptions, data pipeline, and system architecture of the BojkoIDX trading bot for use by AI assistants working on this codebase. Read this before modifying any strategy logic, backtest infrastructure, or data handling code.

---

## 1. Project Overview

BojkoIDX is an algorithmic trading system in two operating modes:

| Mode | Target | Infrastructure |
|------|--------|---------------|
| **Live trading** | FX pairs (EURUSD, GBPUSD, etc.) via Interactive Brokers | GCP VM, systemd service, IBKR Gateway TCP:4002, Flask dashboard :8080 |
| **Backtesting** | FX pairs + indices (US100 / USATECHIDXUSD) | Local Python scripts, Dukascopy 1M data |

The core strategy is the same in both modes: **Break of Structure (BOS) + Pullback entry** with a two-timeframe (LTF/HTF) trend filter.

---

## 2. Core Algorithm — BOS + Pullback

The strategy identifies trend direction on the higher timeframe (HTF), then waits for a breakout (BOS) and a pullback entry on the lower timeframe (LTF).

### High-level sequence per LTF bar

```
For each LTF bar i:
  1. If open position → check SL/TP hit → record trade if closed
  2. If active setup (waiting for fill) → check if price touched entry level
     → if touched → enter position
     → if expired  → discard setup
  3. If no position AND no active setup:
     a. Get HTF bias at current time
     b. If NEUTRAL → skip
     c. Check for BOS on LTF
     d. If BOS aligns with HTF bias → create pullback setup (limit order)
```

**One position at a time. One pending setup at a time.** Creating a new setup immediately discards any unfilled prior setup.

---

## 3. Pivot Detection (`src/structure/pivots.py`)

### `detect_pivots_confirmed(df, lookback=3, confirmation_bars=1)`

Detects **swing highs and lows** with an **anti-lookahead delay**.

**Raw pivot** at bar `i`:
- Pivot High: `high[i]` is the maximum in window `[i - lookback, i + lookback]`
- Pivot Low: `low[i]` is the minimum in window `[i - lookback, i + lookback]`

**Confirmation** (anti-lookahead): The raw pivot at bar `i` is only *reported* at bar `i + confirmation_bars`. This means at simulation time the strategy never knows about a pivot until `confirmation_bars` have elapsed after it.

**Returns** four `pd.Series` aligned to `df.index`:
- `pivot_highs` — bool, True at confirmation bar for a pivot high
- `pivot_lows` — bool, True at confirmation bar for a pivot low
- `ph_levels` — float, the price level of the confirmed pivot high (NaN elsewhere)
- `pl_levels` — float, the price level of the confirmed pivot low (NaN elsewhere)

**Default parameters**: `lookback=3` (LTF), `lookback=5` (HTF), `confirmation_bars=1`

All pivot lookups scan backward from `current_time` — they are strictly non-lookahead.

---

## 4. HTF Bias (`src/structure/bias.py`)

### `get_htf_bias_at_bar(htf_df, current_bar_time, ...)`

Looks at the latest HTF bar whose timestamp is `≤ current_bar_time` (anti-lookahead), then calls `determine_htf_bias()`.

### `determine_htf_bias(pivot_sequence, last_close)`

Uses the last 4 confirmed pivot highs and lows (most recent first):

| Condition | Bias |
|-----------|------|
| Last 2 highs ascending AND last 2 lows ascending | `BULL` |
| Last close > most recent pivot high | `BULL` |
| Last 2 lows descending AND last 2 highs descending | `BEAR` |
| Last close < most recent pivot low | `BEAR` |
| None of the above | `NEUTRAL` |

**NEUTRAL trades are skipped.** The strategy only enters when HTF has a clear directional bias.

---

## 5. Break of Structure Detection (`check_bos` in strategy)

A BOS is detected on the LTF at bar `i`:

- **LONG BOS**: `close_bid[i] > last confirmed pivot high` (requires close break by default)
- **SHORT BOS**: `close_bid[i] < last confirmed pivot low`

`require_close_break=True` (default) means a wick alone is not enough — the candle body must close through the level.

BOS direction must match the HTF bias:
- LONG BOS is only valid when HTF = `BULL`
- SHORT BOS is only valid when HTF = `BEAR`

---

## 6. Setup Creation

When a valid (aligned) BOS is detected, a `PullbackSetup` is created:

```
entry_price (LONG)  = bos_level + entry_offset_atr_mult × ATR14
entry_price (SHORT) = bos_level - entry_offset_atr_mult × ATR14
```

This places the limit order **above the BOS level for longs** (confirmed breakout continuation entry) and **below** for shorts.

**expiry**: `pullback_max_bars=20` bars from BOS bar. If not filled by then, the setup is discarded and counted as a "missed setup".

---

## 7. Entry Fill Check (`SetupTracker.check_fill`)

Each bar (after BOS), the tracker checks whether price touched the limit order level:

| Direction | Fill condition |
|-----------|---------------|
| LONG | `low_ask ≤ entry_price ≤ high_ask` |
| SHORT | `low_bid ≤ entry_price ≤ high_bid` |

**LONG entries are on the ASK side** (buying at the ask). **SHORT entries are on the BID side** (selling at the bid).

---

## 8. Position Exit Logic

Once in a position, every bar is checked for SL/TP:

| Direction | SL trigger | TP trigger |
|-----------|-----------|-----------|
| LONG | `low_bid ≤ sl` | `high_bid ≥ tp` |
| SHORT | `high_ask ≥ sl` | `low_ask ≤ tp` |

**Bid/Ask asymmetry**: LONG exits on BID (selling out), SHORT exits on ASK (buying back).

**Worst-case intrabar conflict**: If both SL and TP would be hit in the same bar, SL wins (conservative assumption).

**Price clamping**: Exit prices are clamped to the feasible bar range. If the calculated SL/TP falls outside the bar (e.g., a very wide pivot-based SL), it is clamped to `low_bid/high_bid` (LONG) or `low_ask/high_ask` (SHORT). After clamping the exit must be feasible; if not, a `ValueError` is raised.

### Stop-Loss Anchor

SL is set at the last confirmed LTF pivot (opposite side) at the moment of fill, with an ATR buffer:

```
SL (LONG)  = last confirmed pivot low  - sl_buffer_atr_mult × ATR14
SL (SHORT) = last confirmed pivot high + sl_buffer_atr_mult × ATR14
```

Fallback (no pivot found): `entry ± 2 × ATR`.

### Take-Profit

```
risk = |entry - sl|
TP (LONG)  = entry + risk × risk_reward
TP (SHORT) = entry - risk × risk_reward
```

Default `risk_reward = 2.0`.

---

## 9. R-Value Calculation

Each trade records:

```
risk_distance = |entry - sl|
realized_distance = exit_price - entry  (LONG)
                  = entry - exit_price  (SHORT)
R = realized_distance / risk_distance
```

A full win = ≈ +2.0R (at RR=2.0). A full loss = ≈ −1.0R.

**Expectancy** = `mean(R across all trades)`.

### Important: PNL column is NOT reliable for indices

The `pnl` column in trade records uses `× 100000` (FX lot size multiplier). This produces nonsensical dollar values for index instruments (US100 quoted in points). For index backtests, **always use the R column** for analysis. The `run_backtest_idx.py` script suppresses PNL and uses R-based drawdown.

---

## 10. ATR Calculation

ATR is calculated on LTF bars using the standard 14-period Wilder ATR:

```
TR = max(high - low, |high - prev_close|, |low - prev_close|)
ATR = rolling_mean(TR, 14)
```

All prices use the **bid** series for ATR (`high_bid`, `low_bid`, `close_bid`).

---

## 11. Data Model

### Column names

All bar DataFrames must have these columns:

| Column | Description |
|--------|-------------|
| `open_bid`, `high_bid`, `low_bid`, `close_bid` | OHLC on bid side |
| `open_ask`, `high_ask`, `low_ask`, `close_ask` | OHLC on ask side |
| `volume` | Tick volume |

The index must be a `pd.DatetimeIndex` (UTC, timezone-naive).

### Spread model

ASK = BID + fixed spread (constant per instrument). For US100 (USATECHIDXUSD) the default spread is **1.0 point**. This is a simplification; real spread is variable.

```python
df['open_ask']  = df['open_bid']  + spread
df['high_ask']  = df['high_bid']  + spread
df['low_ask']   = df['low_bid']   + spread
df['close_ask'] = df['close_bid'] + spread
```

### Source data

Raw data is Dukascopy **1-minute BID bars** in CSV format with millisecond timestamps:
```
timestamp_ms, open, high, low, close, volume
```

Files are stored in `data/1M/{symbol}/YYYY/BidAskOHLCV/*.csv`.

---

## 12. Data Pipeline for Indices (`scripts/build_h1_idx.py`)

```
data/1M/usatechidxusd/**/*.csv
        ↓  load_and_concat_m1()
   1M DataFrame (BID OHLC)
        ↓  resample_m1(df, timeframe)
   Resampled DataFrame (any TF)
        ↓  add_bid_ask_columns(df, spread)
   DataFrame with bid+ask columns
        ↓  save to CSV
data/bars_idx/usatechidxusd_{tf}_bars.csv
```

**Resampling rules** (OHLCV from 1M):
- `open` = first, `high` = max, `low` = min, `close` = last, `volume` = sum

Supported timeframes: `5min`, `15min`, `30min`, `1h`, `4h` (any pandas offset string).

**Prebuilt bar files** (2021-01 → 2026-03):

| File | Bars | TF |
|------|------|----|
| `data/bars_idx/usatechidxusd_1h_bars.csv` | 43,776 | 1H |
| `data/bars_idx/usatechidxusd_30m_bars.csv` | 87,552 | 30M |
| `data/bars_idx/usatechidxusd_15m_bars.csv` | 175,104 | 15M |
| `data/bars_idx/usatechidxusd_5m_bars.csv` | 525,312 | 5M |

---

## 13. Backtest Infrastructure

### `scripts/run_backtest_idx.py`

Runs a single backtest for one LTF/HTF combination:

```bash
python scripts/run_backtest_idx.py --ltf 5min --htf 4h --start 2021-01-01 --end 2025-01-01 --rr 2.0
```

- HTF bars are **built on-the-fly** by resampling LTF bars (`build_htf_from_ltf`), not loaded from a file.
- Outputs: `reports/IDX_{SYM}_{ltf}_BACKTEST_TRADES.csv` + `reports/IDX_{SYM}_{ltf}_BACKTEST_REPORT.md`
- **R-based drawdown** is computed instead of dollar drawdown (see above).

### `scripts/run_idx_summary.py`

Runs all 20 combinations (4 LTF × 5 periods) and generates:

```
reports/IDX_USATECHIDXUSD_SUMMARY.md
```

**Combinations**: LTF in `{5min, 15min, 30min, 1h}` with HTF always `4h`. Periods: 2021, 2022, 2023, 2024, 2021–2024.

---

## 14. Default Strategy Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `pivot_lookback_ltf` | `3` | Pivot window half-size on LTF |
| `pivot_lookback_htf` | `5` | Pivot window half-size on HTF |
| `confirmation_bars` | `1` | Bars delay before pivot is "confirmed" |
| `require_close_break` | `True` | BOS requires a closing break (not just wick) |
| `entry_offset_atr_mult` | `0.3` | Entry placed 0.3×ATR above/below BOS level |
| `pullback_max_bars` | `20` | Setup expires after 20 bars without fill |
| `sl_anchor` | `'last_pivot'` | SL at last confirmed opposite pivot |
| `sl_buffer_atr_mult` | `0.5` | SL placed 0.5×ATR beyond the pivot |
| `risk_reward` | `2.0` | TP = entry ± risk × 2.0 |

---

## 15. Feasibility Checks Summary

| Direction | Entry fill | Entry feasibility check | Exit check | Exit feasibility check |
|-----------|-----------|------------------------|------------|----------------------|
| LONG | `low_ask ≤ entry ≤ high_ask` | `low_ask ≤ entry ≤ high_ask` | `low_bid ≤ sl` or `high_bid ≥ tp` | exit clamped to `[low_bid, high_bid]` |
| SHORT | `low_bid ≤ entry ≤ high_bid` | `low_bid ≤ entry ≤ high_bid` | `high_ask ≥ sl` or `low_ask ≤ tp` | exit clamped to `[low_ask, high_ask]` |

This models realistic execution: longs are bought at the offer (ASK) and closed at the bid; shorts are sold at the bid and closed at the offer (ASK).

---

## 16. Backtest Results Summary (US100, RR=2.0)

Results from `reports/IDX_USATECHIDXUSD_SUMMARY.md`:

| LTF | Period | Trades | WR% | Exp (R) | PF |
|-----|--------|--------|-----|---------|-----|
| 5M | 2021–2024 | 1,735 | ~46% | +0.300 | 1.39 |
| 30M | 2021–2024 | 573 | ~39% | +0.168 | 1.19 |
| 1H | 2021–2024 | 414 | ~34% | -0.044 | 0.84 |

5M with 4H HTF is the best-performing configuration — all 4 individual years (2021–2024) were profitable.

> **Caution**: These are in-sample results on Dukascopy historical data with a constant spread model. No walk-forward validation has been done for index instruments.

---

## 17. Repository Structure

```
src/
  strategies/
    trend_following_v1.py     # Core strategy + main backtest loop
  structure/
    pivots.py                 # Pivot detection (anti-lookahead)
    bias.py                   # HTF bias (HH/HL pattern detection)
  backtest/
    setup_tracker.py          # Setup lifecycle (BOS → limit order → fill/expire)

scripts/
  build_h1_idx.py             # 1M → any TF bar builder for index data
  run_backtest_idx.py         # Single LTF/HTF backtest runner (index)
  run_idx_summary.py          # Multi-TF multi-year summary report generator

data/
  1M/                         # Raw Dukascopy 1-minute CSV files
    usatechidxusd/
  bars_idx/                   # Prebuilt resampled bar files
    usatechidxusd_1h_bars.csv
    usatechidxusd_30m_bars.csv
    usatechidxusd_15m_bars.csv
    usatechidxusd_5m_bars.csv

reports/
  IDX_USATECHIDXUSD_SUMMARY.md    # Multi-TF combined backtest report

docs/
  ARCHITECTURE.md             # FX live-trading infrastructure details
  AI_CONTEXT.md               # This file
```

---

## 18. Known Limitations and Assumptions

1. **Constant spread**: ASK = BID + fixed spread. Real spreads are variable, especially during news events.
2. **FX multiplier in PNL**: `pnl = realized_price_move × 100000` is correct for 1 lot FX but meaningless for index instruments. Always use the `R` column for index analysis.
3. **Intrabar resolution**: The backtest uses OHLC bars — it cannot know the exact tick sequence within a bar. The worst-case tie-breaking rule (if both SL and TP would be hit intrabar, SL wins) makes the simulation conservative.
4. **No session filter**: Trades can open at any time, including low-liquidity overnight periods (relevant for indices).
5. **No slippage beyond spread**: Entry and exit are filled at exactly the limit/stop price as long as the bar's range covers it.
6. **No partial fills, no position sizing**: Each trade is treated as 1 unit of risk.
7. **One position at a time**: The system cannot hold multiple positions simultaneously.
8. **HTF resampled from LTF**: The 4H HTF bars are built by resampling LTF bars, so they are perfectly synchronised — no cross-feed latency.
9. **Pivot ties**: If multiple bars share the same high/low in the window, the leftmost one is treated as the pivot (NumPy `==` equality comparison).
