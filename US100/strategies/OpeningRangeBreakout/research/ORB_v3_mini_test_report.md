# ORB v3 Mini Test - Results Report

**Strategy:** Opening Range Breakout v3 (LONG only + EMA50 filter + TP=1.6R)  
**Symbol:** USATECHIDXUSD (US100)  
**Period:** 2021-01-01 -> 2025-12-31 (5 years)  
**Timeframe:** 5min  
**Generated:** 2026-03-12 16:42 UTC  

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
| Max trades/day | 1 |

## Summary Results

| Metric | Value |
|--------|-------|
| Total trades | 660 |
| Trades/year | 132.0 |
| Win rate | 52.3% |
| Expectancy R | +0.065 R |
| Profit factor | 1.17 |
| Max DD (R) | 14.9 R |
| EMA-filtered days | 225 |

## Exit Reason Breakdown

| Exit | Count | % |
|------|-------|---|
| TP | 94 | 14.2% |
| SL | 217 | 32.9% |
| EOD | 349 | 52.9% |

## Year-by-Year

| Year | Trades | WR% | E(R) |
|------|--------|-----|------|
| 2021 | 127 | 55.1% | +0.099 |
| 2022 | 107 | 57.0% | +0.163 |
| 2023 | 139 | 54.7% | +0.098 |
| 2024 | 145 | 47.6% | -0.018 |
| 2025 | 142 | 48.6% | +0.016 |

## Comparison: ORB v2 vs ORB v3

| Metric | v2 (TP=1.3R) | v3 (TP=1.6R) | Delta |
|--------|-------------|----------------|-------|
| Trades | 660 | 660 | +0 |
| Win rate | 53.3% | 52.3% | -1.0pp |
| Expectancy R | +0.064 | +0.065 | +0.001 |
| Profit factor | 1.17 | 1.17 | +0.00 |
| TP hit rate | - | 14.2% | -- |
| EOD exits | - | 52.9% | -- |

## Conclusion

**Marginal** -- improvement needed before building a full module.

**Key observations:**
- 4/5 years profitable
- TP hit rate at 1.6R: 14.2% (v2 at 1.3R was 20.9%)
- EOD closes: 52.9% of trades
- EMA50 filter: 225 breakout days skipped (same as v2)

## Script

`strategies/OpeningRangeBreakout/research/orb_v3_mini_test.py`
