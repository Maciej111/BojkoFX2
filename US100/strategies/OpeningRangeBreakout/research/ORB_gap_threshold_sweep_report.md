# ORB GAP Threshold Sweep – Research Report

**Strategy:** Opening Range Breakout + GAP filter  
**Symbol:** USATECHIDXUSD (US100) | **Period:** 2021-01-01 → 2025-12-31 | **Timeframe:** 5min  
**Generated:** 2026-03-12 19:50 UTC

## Strategy Rules

| Parameter | Value |
|-----------|-------|
| OR window | 14:30–15:00 UTC |
| Direction | LONG only |
| Entry | Next bar open after close breaks above OR high |
| Stop loss | OR low |
| Take profit | 1.6R |
| EOD close | 21:00 UTC |
| Trend filter | close > EMA50 (1h bars) |
| GAP definition | abs(14:30 open − prev 21:00 close) / ATR(14) |
| Max trades/day | 1 |

## Thresholds Tested

`[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]` (0.0 = no filter / v3 baseline)

## Results Table

| Threshold | Trades | T/yr | WR% | E(R) | PF | MaxDD | TP% | EOD% |
|-----------|--------|------|-----|------|----|-------|-----|------|
| 0.0 (v3 base) | 660 | 132.0 | 52.3% | +0.065 | 1.17 | 14.9R | 14.2% | 52.9% |
| 0.1 ATR | 654 | 130.8 | 52.4% | +0.069 | 1.19 | 15.2R | 14.2% | 53.2% |
| 0.2 ATR | 652 | 130.4 | 52.5% | +0.067 | 1.18 | 15.2R | 14.1% | 53.2% |
| 0.3 ATR | 649 | 129.8 | 52.5% | +0.069 | 1.18 | 15.2R | 14.2% | 53.2% |
| 0.4 ATR | 640 | 128.0 | 52.3% | +0.065 | 1.17 | 15.1R | 14.2% | 53.0% |
| 0.5 ATR | 637 | 127.4 | 52.1% | +0.060 | 1.16 | 15.1R | 14.0% | 53.1% |
| 0.6 ATR | 633 | 126.6 | 52.0% | +0.057 | 1.15 | 17.4R | 13.9% | 52.9% |


## Best Threshold

**Recommended: 0.1 ATR**  (FAIL – success criteria: E(R)>+0.08R, PF>=1.20, T/yr>=40)

| Metric | Value |
|--------|-------|
| Trades | 654 |
| T/yr | 130.8 |
| Win rate | 52.4% |
| Expectancy | +0.069 R |
| Profit factor | 1.19 |
| Max DD | 15.2 R |


## Interpretation

- **3/6** tested thresholds exceed v3 baseline expectancy (+0.065 R); best: E(R)=+0.069  
- Trades/year range: 127–132 across tested thresholds  
- Note: session-gap distribution on this dataset — P25≈0.07, P33≈2.0, P50≈6.5 ATR.  
  Thresholds 0.1–0.6 primarily filter out the ~25% of days with near-zero overnight gap.

### Does a moderate GAP filter improve ORB?

Based on the sweep, small thresholds (0.1–0.6 ATR multiples) filter only the
~25% of days with near-zero overnight session gaps.  Effectiveness depends on
whether those low-gap days are systematically worse for ORB setups.

### Should this filter be kept for the next ORB iteration?

Only if at least one tested threshold shows clear improvement over v3 on both
expectancy (+0.08R) and profit factor (1.20) while maintaining ≥40 trades/year.
See best-threshold section above for the verdict.

## Outputs

| File | Description |
|------|-------------|
| `research/output/orb_gap_threshold_sweep_results.csv` | Full numeric results |
| `research/plots/orb_gap_threshold_expectancy.png` | Expectancy bar chart |
| `research/plots/orb_gap_threshold_pf.png` | Profit factor bar chart |

## Script

`strategies/OpeningRangeBreakout/research/orb_gap_threshold_sweep.py`
