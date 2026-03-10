# Market Regime Classifier — Research Report

**Generated**: 2026-03-05 23:45 UTC
**Data source**: C:\dev\projects\BojkoFx\data\research\regime_grid_search.csv
**OOS period**: 2023-01-01 to 2024-12-31
**Symbols**: EURUSD, GBPUSD, USDJPY, XAUUSD
**Strategy**: BOS + Pullback (PROOF V2 params, frozen)
**Grid**: 18 configs × 1 symbols = 18 runs

---

## Section 1: Executive Summary

- **EURUSD** (HURTS): baseline ExpR=+0.212 → best ExpR=+0.176 (Δ=-0.036, filtered=33%) | config: `trend_enter=0.5 chop_enter=0.7 hvt=70`

  - Worst: ExpR=-0.818 | config: `trend_enter=0.5 chop_enter=0.5 hvt=70`

- **GBPUSD**: no data

- **USDJPY**: no data

- **XAUUSD**: no data


### Overall Verdict: **HURTS** — regime filter degrades performance

---

## Section 2: Baseline vs Best Config

### EURUSD

| Metric | Baseline | Best Config | Delta |
|--------|----------|-------------|-------|
| Trades | 234 | 134 | -43% |
| Win Rate | 46.6% | 29.4% | -0.172 |
| Exp(R) | +0.212 | +0.176 | -0.036 |
| Max DD | 17.0% | 1.8% | -15.200% |
| PF | 1.03 | 1.47 | +0.439 |

---

## Section 3: Grid Search Heatmap (ExpR)

### EURUSD

**high_vol_threshold = 70**

| trend_enter↓ / chop_enter→ | 0.5 | 0.6 | 0.7 |
|---|---|---|---|
| **0.5** | -0.818 | -0.378 | +0.176 |
| **0.6** | -0.818 | -0.317 | +0.000 |
| **0.7** | -0.818 | -0.333 | +0.000 |

**high_vol_threshold = 80**

| trend_enter↓ / chop_enter→ | 0.5 | 0.6 | 0.7 |
|---|---|---|---|
| **0.5** | -0.478 | -0.228 | -0.064 |
| **0.6** | -0.478 | -0.304 | -0.234 |
| **0.7** | -0.478 | -0.282 | -0.238 |

---

## Section 4: Regime Distribution

_Note: Regime distribution is derived from per-run regime series. Summary approximated from filter stats in grid results._

### EURUSD (best config)

- Config: trend_enter=0.5 chop_enter=0.7 hvt=70

- Trades baseline: 200 | Allowed by regime: 134 (67% of baseline) | Filtered: 66 (33%)


---

## Section 5: Trade Filter Analysis

### EURUSD

| Metric | Value |
|--------|-------|
| TP trades filtered (false negatives) | 5 |
| SL trades filtered (correct blocks) | 12 |
| Total filtered | 17 |
| Filter precision (SL_filtered / total) | 70.6% |

---

## Section 6: Recommendation

### Verdict: **REJECT**: No meaningful improvement or hurts performance


### Symbols analysis:

- EURUSD: ⚠️ PARTIAL | ExpR delta=-16.7% | filtered=33% | DD improved=True


### Overfit risk:

The grid search was performed on OOS 2023-2024 data only (no in-sample optimisation).
Risk: 18 configs × 4 symbols = 72 evaluations. With multiple comparisons, some positive results may be noise.
Recommendation: validate the top config on 2025 data (out-of-sample) before production use.
