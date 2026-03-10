# FINAL MULTI-SYMBOL OOS TEST REPORT

**Date:** 2026-02-19 11:49:02

---

## Configuration

**Frozen Parameters (FIX2 Engine):**

- entry_offset_atr_mult: `0.3`
- pullback_max_bars: `40`
- risk_reward: `1.5`
- sl_anchor: `last_pivot`
- sl_buffer_atr_mult: `0.5`
- pivot_lookback_ltf: `3`
- pivot_lookback_htf: `5`
- confirmation_bars: `1`
- require_close_break: `True`

## Test Setup

- **Train Context:** 2021-2022
- **OOS Test:** 2023-2024
- **Timeframe:** H1 / H4
- **Symbols:** EURUSD, GBPUSD, USDJPY, XAUUSD
- **Initial Balance:** $10,000

---

## Results Summary

| Symbol | Trades | WR (%) | Expectancy (R) | PF | MaxDD (%) | Return (%) |
|--------|--------|--------|----------------|----|-----------|-----------|
| GBPUSD | 199 | 48.7 | 0.580 | 1.71 | 17.0 | 173.4 |
| USDJPY | 226 | 50.0 | 0.300 | 1.14 | 1104.1 | 7510.2 |
| XAUUSD | 219 | 47.9 | 0.170 | 1.22 | 9475.1 | 253015.7 |

---

## Year-by-Year Breakdown

### GBPUSD

| Year | Trades | Expectancy (R) | WR (%) | PF | Long Exp | Short Exp |
|------|--------|----------------|--------|----|-----------|-----------|
| 2023 | 100 | 0.039 | 52.0 | 2.45 | -0.004 | 0.071 |
| 2024 | 99 | 1.126 | 45.5 | 1.09 | 0.266 | 2.118 |

### USDJPY

| Year | Trades | Expectancy (R) | WR (%) | PF | Long Exp | Short Exp |
|------|--------|----------------|--------|----|-----------|-----------|
| 2023 | 108 | 0.280 | 46.3 | 1.01 | 0.715 | -0.188 |
| 2024 | 118 | 0.318 | 53.4 | 1.30 | 0.489 | 0.069 |

### XAUUSD

| Year | Trades | Expectancy (R) | WR (%) | PF | Long Exp | Short Exp |
|------|--------|----------------|--------|----|-----------|-----------|
| 2023 | 108 | 0.141 | 50.9 | 1.32 | -0.195 | 0.391 |
| 2024 | 111 | 0.198 | 45.0 | 1.15 | 0.436 | -0.103 |

---

## Sanity Checks

- **Intrabar TP-in-conflict:** 0 (must be 0) [PASS]
- **Impossible exits:** 0 (must be 0) [PASS]

---

## Interpretation

**Symbols with positive expectancy:** 3/3

[ROBUST] **Edge appears robust** - works across multiple instruments

**Expectancy stability:**
- Mean: 0.350R
- Std Dev: 0.171R

---

**Report generated:** 2026-02-19 11:49:02
