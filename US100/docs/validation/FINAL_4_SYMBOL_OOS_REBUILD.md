# FINAL 4-SYMBOL OOS TEST - REALISTIC POSITION SIZING

**Date:** 2026-02-19 12:37:55

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

## Position Sizing

- **Initial Balance:** $10,000
- **Risk Per Trade:** 1.0%
- **Model:** Fixed Fractional
- **Formula:** equity *= (1 + R * risk_fraction)

## Test Setup

- **Train Context:** 2021-2022
- **OOS Test:** 2023-2024
- **Timeframe:** H1 / H4
- **Symbols Tested:** EURUSD, GBPUSD, USDJPY, XAUUSD

---

## Results Summary (with 1% Risk)

| Symbol | Trades | WR (%) | Expectancy (R) | PF | MaxDD (%) | Return (%) |
|--------|--------|--------|----------------|----|-----------|------------|
| EURUSD | 120 | 48.3 | 0.175 | 1.09 | 10.0 | 19.1 |
| GBPUSD | 199 | 48.7 | 0.580 | 1.71 | 26.1 | 149.6 |
| USDJPY | 226 | 50.0 | 0.300 | 1.14 | 16.2 | 84.3 |
| XAUUSD | 219 | 47.9 | 0.170 | 1.22 | 19.1 | 38.8 |

---

## Year-by-Year Breakdown

### EURUSD

| Year | Trades | Expectancy (R) | WR (%) | PF | Long Exp | Short Exp |
|------|--------|----------------|--------|----|-----------|-----------|
| 2023 | 120 | 0.175 | 48.3 | 1.09 | 0.134 | 0.250 |
| 2024 | 0 | 0.000 | 0.0 | 0.00 | 0.000 | 0.000 |

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

## Execution Sanity Checks

- **Intrabar TP-in-conflict:** 0 (must be 0) [PASS]
- **Impossible exits:** 0 (must be 0) [PASS]
- **Trades outside OOS window:** 0 [PASS]

---

## Interpretation

**Symbols with positive expectancy:** 4/4

[ROBUST] **Edge appears robust** - works across multiple instruments

**Expectancy statistics:**
- Mean: 0.306R
- Std Dev: 0.166R
- Min: 0.170R
- Max: 0.580R

**Return statistics (1% risk):**
- Mean: 73.0%
- Median: 61.5%
- Min: 19.1%
- Max: 149.6%

---

## Notes

- **Realistic returns:** Based on 1% risk per trade, compounded
- **Engine:** FIX2 (validated, 0 execution errors)

---

**Report generated:** 2026-02-19 12:37:55
