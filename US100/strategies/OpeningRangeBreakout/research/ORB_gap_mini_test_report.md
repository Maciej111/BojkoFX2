# ORB GAP Mini Test - Results Report

**Strategy:** Opening Range Breakout + GAP filter (LONG only + EMA50 + GAP >= 10.0x ATR + TP=1.6R)  
**Symbol:** USATECHIDXUSD (US100)  
**Period:** 2021-01-01 -> 2025-12-31 (5 years)  
**Timeframe:** 5min  
**Generated:** 2026-03-12 17:24 UTC  

## Rules

| Parameter | Value |
|-----------|-------|
| OR window | 14:30-15:00 UTC |
| Direction | LONG only |
| Entry | Next bar open after close breaks above OR_high |
| Stop loss | OR_low |
| Take profit | 1.6R |
| EOD close | 21:00 UTC |
| Trend filter | close_bid > EMA50 (1h bars) |
| GAP filter | abs(14:30 open - prev 21:00 close) / ATR(14) >= 10.0 |
| Max trades/day | 1 |

## Summary Results

| Metric | Value |
|--------|-------|
| Total trades | 321 |
| Trades/year | 64.2 |
| Win rate | 51.1% |
| Expectancy R | +0.056 R |
| Profit factor | 1.14 |
| Max DD (R) | 15.4 R |
| Avg gap/ATR ratio (traded days) | 21.141 |
| Days skipped — GAP filter | 1120 |
| Days skipped — EMA filter | 146 |

## Exit Reason Breakdown

| Exit | Count | % |
|------|-------|---|
| TP | 54 | 16.8% |
| SL | 115 | 35.8% |
| EOD | 152 | 47.4% |

## Year-by-Year

| Year | Trades | WR% | E(R) |
|------|--------|-----|------|
| 2021 | 63 | 52.4% | +0.065 |
| 2022 | 51 | 60.8% | +0.162 |
| 2023 | 74 | 55.4% | +0.159 |
| 2024 | 67 | 41.8% | -0.101 |
| 2025 | 66 | 47.0% | +0.011 |

## Comparison: ORB v3 vs ORB GAP

| Metric | v3 (no GAP filter) | ORB GAP | Delta |
|--------|-------------------|---------|-------|
| Trades | 660 | 321 | -339 |
| Win rate | 52.3% | 51.1% | -1.2pp |
| Expectancy R | +0.065 | +0.056 | -0.009 |
| Profit factor | 1.17 | 1.14 | -0.03 |
| TP hit rate | 14.2% | 16.8% | +2.6pp |
| EOD exits | 52.9% | 47.4% | -5.5pp |

## Conclusion

**Not yet convincing** -- needs further refinement.

**Key observations:**
- GAP filter (>= 10.0x ATR) removed 1120 days
  - Gap defined as: abs(14:30 UTC open - prev 21:00 UTC close) / ATR(14) on 5m bars
  - P50 of overnight session gap on this dataset: ~6.5x ATR; P62: ~10.0x ATR
- 4/5 years profitable
- Average gap/ATR on traded days: 21.141
- Trades/year: 64.2 (success criterion: >= 40)

## Script

`strategies/OpeningRangeBreakout/research/orb_gap_mini_test.py`
