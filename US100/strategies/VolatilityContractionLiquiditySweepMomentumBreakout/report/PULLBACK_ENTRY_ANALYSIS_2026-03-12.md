# VCLSMB — BOS + Pullback Entry: Backtest Comparison Report

**Strategy:** VolatilityContraction → LiquiditySweep → MomentumBreakout  
**Symbol:** USATECHIDXUSD  
**Period:** 2021-01-01 → 2025-12-31 (5 years)  
**Timeframe:** 5min  
**Generated:** 2026-03-12  
**Config:** sweep_atr=0.75 | mom_atr=1.3 | body_ratio=0.75 | compression_lb=20 | RR=2.0

---

## 1. Head-to-Head Comparison

| Metric                | Baseline | + Pullback Entry | Delta |
|-----------------------|----------|-----------------|-------|
| Total Trades          | 117      | 157             | +40 (+34%) |
| Win Rate              | 33.3%    | 31.2%           | **-2.1pp** |
| Expectancy R          | +0.000 R | -0.064 R        | **-0.064 R** |
| Profit Factor         | 1.00     | 0.91            | **-0.09** |
| Max Drawdown (R)      | 11.0 R   | 27.0 R          | **+16.0 R (+145%)** |
| First Entries         | 117      | 117             | 0 |
| Pullback Entries      | —        | 40              | +40 |

---

## 2. Isolated Pullback Entry Performance

Derived from the difference between the two runs:

| Metric                | Value |
|-----------------------|-------|
| Pullback Trades       | 40 |
| Pullback TP (wins)    | 10  (49 total − 39 baseline) |
| Pullback SL (losses)  | 30  (108 total − 78 baseline) |
| **Pullback Win Rate** | **25.0%** |
| **Pullback E(R)**     | **-0.25 R**  (= 10×2.0 − 30×1.0) / 40 |

**Minimum WR required to break even at RR=2.0:** 33.3%  
**Actual pullback WR: 25.0%** → below breakeven by **8.3pp**

---

## 3. Direction Breakdown

### Baseline (no pullback)
| Direction | Trades | Win Rate | E(R) |
|-----------|--------|----------|------|
| LONG      | 52     | 35%      | +0.038 |
| SHORT     | 65     | 32%      | -0.031 |

### With Pullback Entry
| Direction | Trades | Win Rate | E(R) | +Δ Trades |
|-----------|--------|----------|------|-----------|
| LONG      | 71     | 35%      | +0.056 | +19 |
| SHORT     | 86     | 28%      | -0.163 | +21 |

**Observation:** LONG pullbacks kept WR stable (35%), but SHORT pullbacks dropped from 32% → 28%, suggesting that SHORT continuation entries enter against reversion bias after the initial short setup resolves.

---

## 4. Drawdown Analysis

The Max DD jump from 11.0R to 27.0R is the most critical warning signal. Adding losing trades at -0.25R expectancy extends losing streaks significantly and more than doubles the maximum drawdown.

At 40 pullback entries over 5 years (~8/year), the feature adds:
- ~8 additional trades/year, averaging **-2.0R/year net**, i.e. −2R drag on annual performance

---

## 5. Verdict

**Pullback continuation entries with current parameters (atr_mult=0.2, max_entries=2) are NOT beneficial with this setup:**

- Win rate (25%) is 8pp below the RR=2.0 breakeven threshold (33.3%)
- Negative expectancy: -0.25R per pullback trade
- Max DD increases by 145%
- Net annual drag: approx. -2R/year

**Recommended action:** Do NOT enable `--pullback-entry` in production or grid search until:

1. **Pullback filter is tuned** — e.g. only take pullback entries that return to breakout level within N bars, or only when the first trade was a winner
2. **Separate SHORT vs LONG pullbacks** — LONG pullbacks may warrant further research (only 35% WR maintained)
3. **Tighter pullback zone** — try `pullback_atr_mult=0.1` or add a close-above-breakout confirmation requirement
4. **Winner-only reentry** — only enter pullback if first trade closed at TP (not SL)

---

## 6. Files

| File | Description |
|------|-------------|
| `REPORT_BASELINE_2026-03-12.md` | Full baseline backtest report |
| `REPORT_PULLBACK_2026-03-12.md` | Full pullback backtest report |
| `PULLBACK_ENTRY_ANALYSIS_2026-03-12.md` | This comparison analysis |

---

## 7. Implementation Status

The BOS + Pullback feature is fully implemented and disabled by default (`enable_pullback_entry=False`).  
It can be activated with `--pullback-entry` for further research iterations.  
All 35 VCLSMB unit tests pass with the feature code in place.
