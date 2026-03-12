# VWAP Pullback v2 -- Mini-Test Report

**Strategy:** VWAP Pullback v2 (LONG only)
**Symbol:** USATECHIDXUSD (US100 CFD)
**Period:** 2021-01-01 to 2025-12-31
**Generated:** 2026-03-12 23:13 UTC

---

## Key Changes vs v1

| Change | v1 | v2 |
|--------|----|----|
| VWAP anchor | Midnight UTC | **14:30 UTC (session open)** |
| Pullback condition | low <= VWAP + 0.5*ATR | **low <= VWAP (strict touch)** |
| Body ratio filter | >= 0.10 | Removed (close > open sufficient) |
| Max trades/day | 1 | **2** |
| Prior regime bars | 3 | 0 (disabled) |

---

## Strategy Rules

| Parameter | Value |
|-----------|-------|
| Direction | LONG only |
| Trend filter | close_bid > EMA50 on 1h bars |
| VWAP anchor | 14:30 UTC (session open, daily reset) |
| Pullback | low_bid <= VWAP (strict touch) |
| Confirmation | close_bid > open_bid AND close_bid > VWAP |
| Entry | Next bar open |
| Stop loss | Pullback low - 0.3 * ATR |
| Take profit | 1.5R |
| EOD close | 21:00 UTC |
| Max trades/day | 2 |
| ATR period | 14 |

---

## Results Summary

| Metric | v2 Value | v1 Value | Change |
|--------|----------|----------|--------|
| Total trades | 1647 | 433 | +1214 |
| Trades/year | 329.4 | 86.6 | +242.8 |
| Win rate | 41.3% | 43.0% | -1.7pp |
| **Expectancy (R)** | **+0.024** | **+0.047** | **-0.023** |
| **Profit factor** | **1.04** | **1.08** | **-0.04** |
| Max drawdown | 48.8 R | 20.8 R | +28.0 R |
| Max consec. losses | 21 | 8 | +13 |
| TP exits | 39.4% | 39.7% | -0.3pp |
| SL exits | 57.6% | 55.9% | +1.7pp |
| EOD exits | 3.0% | 4.4% | -1.4pp |

Days with a trade setup: 1647 out of 1821 total trading days
Days with no setup found: 962

---

## Yearly Breakdown

| Year | Trades | WR% | E(R) | PF |
|------|--------|-----|------|----|
| 2021 | 347 | 38.9% | -0.037 | 0.94 |
| 2022 | 269 | 41.3% | +0.038 | 1.07 |
| 2023 | 331 | 48.0% | +0.181 | 1.35 |
| 2024 | 350 | 39.1% | -0.030 | 0.95 |
| 2025 | 350 | 39.7% | -0.021 | 0.97 |


---

## Equity Curve

`plots/vwap_pullback_v2_equity.png`

---

## Observations

### Session VWAP
The VWAP now resets at 14:30 UTC (US session open). This makes the VWAP a
true intraday equilibrium reference for the current session rather than a
14.5h-old cumulative average. Pullbacks to this level are more meaningful.

### Strict VWAP touch
Requiring `low_bid <= VWAP` (vs `<= VWAP + 0.5*ATR`) filters out signals
where price merely approached but never reached the VWAP level. This reduces
trade count but (ideally) improves signal quality.

---

## Conclusion

**Not convincing -- session VWAP alone insufficient; further experimentation needed.**

### Next steps if promising
1. Add prior regime filter (e.g., 2 bars closing above VWAP before pullback)
2. Grid search: TP_rr in [1.5, 2.0, 2.5], stop_buffer in [0.2, 0.3, 0.5]
3. Walk-forward validation (2024, 2025 OOS windows)
4. Consider volatility filter (ATR > 20-day median)

---

*Script: `strategies/VWAPPullback/research/vwap_pullback_v2_mini_test.py`*
