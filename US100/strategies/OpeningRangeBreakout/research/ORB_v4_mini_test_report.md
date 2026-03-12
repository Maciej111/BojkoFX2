# ORB v4 Mini Test - Results Report

**Strategy:** Opening Range Breakout v4 (LONG only + EMA50 + OR width filter + TP=1.6R)  
**Symbol:** USATECHIDXUSD (US100)  
**Period:** 2021-01-01 -> 2025-12-31 (5 years)  
**Timeframe:** 5min  
**Generated:** 2026-03-12 16:50 UTC  

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
| OR width filter | 0.7 <= OR_range/ATR(14) <= 2.0 |
| Max trades/day | 1 |

## Summary Results

| Metric | Value |
|--------|-------|
| Total trades | 119 |
| Trades/year | 23.8 |
| Win rate | 47.1% |
| Expectancy R | +0.099 R |
| Profit factor | 1.20 |
| Max DD (R) | 9.8 R |
| Avg OR/ATR ratio (traded days) | 1.720 |
| Days skipped — OR width filter | 1076 |
| Days skipped — EMA filter | 35 |

## Exit Reason Breakdown

| Exit | Count | % |
|------|-------|---|
| TP | 38 | 31.9% |
| SL | 59 | 49.6% |
| EOD | 22 | 18.5% |

## Year-by-Year

| Year | Trades | WR% | E(R) |
|------|--------|-----|------|
| 2021 | 31 | 54.8% | +0.219 |
| 2022 | 15 | 46.7% | +0.185 |
| 2023 | 20 | 45.0% | +0.011 |
| 2024 | 21 | 33.3% | -0.169 |
| 2025 | 32 | 50.0% | +0.174 |

## Comparison: ORB v3 vs ORB v4

| Metric | v3 (no width filter) | v4 (OR width filter) | Delta |
|--------|---------------------|---------------------|-------|
| Trades | 660 | 119 | -541 |
| Win rate | 52.3% | 47.1% | -5.2pp |
| Expectancy R | +0.065 | +0.099 | +0.034 |
| Profit factor | 1.17 | 1.20 | +0.03 |
| TP hit rate | 14.2% | 31.9% | +17.7pp |
| EOD exits | 52.9% | 18.5% | -34.4pp |

## Conclusion

**Marginal** -- improvement needed before building a full module.

**Key observations:**
- OR width filter (0.7–2.0x ATR) removed 1076 days with extreme OR ranges
- 4/5 years profitable
- Average OR/ATR ratio on traded days: 1.720

## Script

`strategies/OpeningRangeBreakout/research/orb_v4_mini_test.py`
