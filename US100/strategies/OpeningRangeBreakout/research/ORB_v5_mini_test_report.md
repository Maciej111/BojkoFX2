# ORB v5 Mini Test – Bullish OR Filter

**Strategy:** Opening Range Breakout + Bullish OR bias (LONG only + EMA50 + OR_close > OR_open + TP=1.6R)  
**Symbol:** USATECHIDXUSD (US100)  
**Period:** 2021-01-01 -> 2025-12-31 (5 years)  
**Timeframe:** 5min  
**Generated:** 2026-03-12 19:55 UTC

## Rules

| Parameter | Value |
|-----------|-------|
| OR window | 14:30–15:00 UTC |
| Direction | LONG only |
| Entry | Next bar open after close breaks above OR_high |
| Stop loss | OR_low |
| Take profit | 1.6R |
| EOD close | 21:00 UTC |
| Trend filter | close_bid > EMA50 (1h bars) |
| OR bias filter | OR_close > OR_open (first bar open vs last bar close of OR window) |
| Max trades/day | 1 |

## Summary Results

| Metric | Value |
|--------|-------|
| Total trades | 426 |
| Trades/year | 85.2 |
| Win rate | 54.5% |
| Expectancy R | +0.093 R |
| Profit factor | 1.25 |
| Max DD (R) | 9.5 R |
| Days skipped — bearish OR | 624 |
| Days skipped — EMA filter | 115 |

## Exit Reason Breakdown

| Exit | Count | % |
|------|-------|---|
| TP | 64 | 15.0% |
| SL | 141 | 33.1% |
| EOD | 221 | 51.9% |

## Year-by-Year

| Year | Trades | WR% | E(R) |
|------|--------|-----|------|
| 2021 | 84 | 59.5% | +0.126 |
| 2022 | 68 | 50.0% | +0.013 |
| 2023 | 103 | 53.4% | +0.050 |
| 2024 | 82 | 62.2% | +0.259 |
| 2025 | 89 | 47.2% | +0.022 |

## Comparison: ORB v3 vs ORB v5

| Metric | v3 (no OR filter) | v5 (bullish OR) | Delta |
|--------|-------------------|-----------------|-------|
| Trades | 660 | 426 | -234 |
| Win rate | 52.3% | 54.5% | +2.2pp |
| Expectancy R | +0.065 | +0.093 | +0.028 |
| Profit factor | 1.17 | 1.25 | +0.08 |
| TP hit rate | 14.2% | 15.0% | +0.8pp |
| EOD exits | 52.9% | 51.9% | -1.0pp |

## Conclusion

**Promising** — worth further investigation.

**Key observations:**
- Bullish OR filter removed 624 days
- 5/5 years profitable
- Success criteria: E(R) > +0.08R, PF >= 1.20, Trades/year >= 60

## Script

`strategies/OpeningRangeBreakout/research/orb_v5_mini_test.py`
