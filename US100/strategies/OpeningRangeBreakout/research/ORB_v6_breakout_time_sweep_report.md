# ORB v6 Breakout Time Sweep – Research Report

**Strategy:** Opening Range Breakout v5 + breakout time cutoff filter  
**Symbol:** USATECHIDXUSD (US100)  
**Period:** 2021-01-01 → 2025-12-31  
**Generated:** 2026-03-12 20:17 UTC

## Strategy Description

| Parameter | Value |
|-----------|-------|
| OR window | 14:30–15:00 UTC |
| Direction | LONG only |
| Entry | Next bar open after breakout close ≤ cutoff hour |
| Stop loss | OR_low |
| Take profit | 1.6R |
| EOD close | 21:00 UTC |
| Trend filter | close_bid > EMA50 (1h bars) |
| OR bias filter | OR_close > OR_open (bullish OR) |
| **Breakout cutoff** | **varied — see below** |

## Tested Cutoffs

`['16:00 UTC', '17:00 UTC', '18:00 UTC', '19:00 UTC', '21:00 UTC']`

Breakout signal bar (the 5-min bar whose close exceeds OR_high) must have a
timestamp **≤ cutoff hour**.  21:00 = ORB v5 baseline (no effective restriction).

## Results Table

| Cutoff | Trades | T/yr | WR% | E(R) | PF | MaxDD | TP% | EOD% | MCL |
|--------|--------|------|-----|------|----|-------|-----|------|-----|
| 16:00 | 381 | 76.2 | 54.3% | +0.090 | 1.23 | 8.4R | 15.5% | 49.3% | 6 |
| 17:00 | 399 | 79.8 | 54.6% | +0.095 | 1.25 | 9.0R | 15.5% | 50.4% | 6 |
| 18:00 ← best | 412 | 82.4 | 54.9% | +0.099 | 1.26 | 9.0R | 15.3% | 51.0% | 6 |
| 19:00 | 421 | 84.2 | 54.6% | +0.097 | 1.26 | 9.5R | 15.2% | 51.3% | 6 |
| 21:00 (v5 base) | 426 | 85.2 | 54.5% | +0.093 | 1.25 | 9.5R | 15.0% | 51.9% | 6 |

## Best Cutoff

**Recommended: 18:00 UTC** — **Not yet convincing**

Success criteria: E(R) > +0.10R, PF ≥ 1.30, T/yr ≥ 60

| Metric | Value |
|--------|-------|
| Trades | 412 |
| T/yr | 82.4 |
| Win rate | 54.9% |
| Expectancy | +0.099 R |
| Profit factor | 1.26 |
| Max DD | 9.0 R |
| MCL | 6 |

### Yearly breakdown (best cutoff)

| Year | Trades | WR% | E(R) | PF |
|------|--------|-----|------|----|  
| 2021 | 82 | 61.0% | +0.144 | 1.43 |
| 2022 | 65 | 49.2% | -0.003 | 0.99 |
| 2023 | 98 | 53.1% | +0.055 | 1.14 |
| 2024 | 81 | 63.0% | +0.264 | 1.86 |
| 2025 | 86 | 47.7% | +0.026 | 1.07 |


## Equity Curve Summary

Plots saved to `research/plots/`:

| File | Description |
|------|-------------|
| `orb_v6_equity_curves.png` | All cutoffs overlaid |
| `orb_v6_drawdown_curves.png` | All cutoffs overlaid |
| `orb_v6_best_equity_curve.png` | Best cutoff only (equity + DD) |

## Comparison vs ORB v5

| Metric | ORB v5 | ORB v6 best | Delta |
|--------|--------|-------------|-------|
| Trades | 426 | 412 | -14 |
| Win rate | 54.5% | 54.9% | +0.4pp |
| Expectancy R | +0.093 | +0.099 | +0.006 |
| Profit factor | 1.25 | 1.26 | +0.01 |
| Max DD (R) | 9.5R | 9.0R | -0.5R |
| TP hit rate | 15.0% | 15.3% | +0.3pp |
| EOD exits | 51.9% | 51.0% | -0.9pp |


## Stability Observations

- Expectancy improves with a 18:00 cutoff vs ORB v5 baseline
- Max drawdown improves with the restriction in place
- Earlier cutoffs capture higher-conviction early breakouts
  (they trade only days where price moves away from OR quickly)
- EOD exit rate falls with tighter cutoffs,
  indicating shorter hold times when breakouts are early

## Conclusion

**Should ORB v6 replace ORB v5 as new baseline?**  
Not conclusively — further investigation or a different cutoff range may be needed.

| Criterion | Pass? |
|-----------|-------|
| E(R) > +0.10R | FAIL (+0.099) |
| PF ≥ 1.30 | FAIL (1.26) |
| T/yr ≥ 60 | PASS (82.4) |
| Lower DD than v5 | PASS (9.0R vs 9.5R) |

## Script

`strategies/OpeningRangeBreakout/research/orb_v6_breakout_time_sweep.py`
