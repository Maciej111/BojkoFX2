# ORB v2 Mini Test - Results Report

**Strategy:** Opening Range Breakout v2 (LONG only + EMA filter + TP=1.3R)  
**Symbol:** USATECHIDXUSD (US100)  
**Period:** 2021-01-01 -> 2025-12-31 (5 years)  
**Timeframe:** 5min  
**Generated:** 2026-03-12 16:34 UTC  

## Rules

| Parameter | Value |
|-----------|-------|
| OR window | 14:30-15:00 UTC |
| Direction | LONG only |
| Entry | Next bar open after close breaks above OR_high |
| Stop loss | OR_low |
| Take profit | 1.3R |
| EOD close | 21:00 UTC |
| Trend filter | close_bid > EMA50 (1h bars) |
| Max trades/day | 1 |

## Summary Results

| Metric | Value |
|--------|-------|
| Total trades | 660 |
| Trades/year | 132.0 |
| Win rate | 53.3% |
| Expectancy R | +0.064 R |
| Profit factor | 1.17 |
| Max DD (R) | 13.2 R |
| EMA-filtered days | 225 |

## Exit Reason Breakdown

| Exit | Count | % |
|------|-------|---|
| TP | 138 | 20.9% |
| SL | 210 | 31.8% |
| EOD | 312 | 47.3% |

## Year-by-Year

| Year | Trades | WR% | E(R) |
|------|--------|-----|------|
| 2021 | 127 | 55.1% | +0.080 |
| 2022 | 107 | 57.0% | +0.123 |
| 2023 | 139 | 55.4% | +0.097 |
| 2024 | 145 | 49.7% | -0.004 |
| 2025 | 142 | 50.7% | +0.042 |

## Comparison: ORB v1 LONG vs ORB v2

| Metric | v1 LONG | v2 LONG | Delta |
|--------|---------|---------|-------|
| Trades | 672 | 660 | -12 |
| Win rate | 50.3% | 53.3% | +3.0pp |
| Expectancy R | +0.072 | +0.064 | -0.008 |
| TP (RR) | 2.0R | 1.3R | -- |
| EOD exits | 51.5% | 47.3% | -4.2pp |

## Conclusion

**Marginal / not yet convincing** -- needs further refinement before proceeding.

**Key observations:**
- EMA50 filter eliminated 225 LONG breakout days that occurred in downtrends
- Closer TP (1.3R vs 2.0R) improved TP hit rate (20.9% vs 11.7% in v1)
- EOD closes reduced from 51.5% to 47.3%
- Year-by-year consistency: 4/5 years profitable

## Script

`strategies/OpeningRangeBreakout/research/orb_v2_mini_test.py`
