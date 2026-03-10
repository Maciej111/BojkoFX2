# Index Backtest Report: USATECHIDXUSD

**Period:** 2024-01-01 → 2024-12-30
**LTF:** 30m  |  **HTF:** 4h
**Strategy:** BOS + Pullback (trend_following_v1)

## Strategy Parameters

| Parameter | Value |
|-----------|-------|
| pivot_lookback_ltf | 3 |
| pivot_lookback_htf | 5 |
| confirmation_bars | 1 |
| require_close_break | True |
| entry_offset_atr_mult | 0.3 |
| pullback_max_bars | 20 |
| sl_anchor | last_pivot |
| sl_buffer_atr_mult | 0.5 |
| risk_reward | 2.0 |
| use_session_filter | True |
| session_start_hour_utc | 13 |
| session_end_hour_utc | 20 |

## Results Summary

| Metric | Value |
|--------|-------|
| Total trades | 81 |
| Win rate | 39.5% |
| Expectancy (R) | 0.145 |
| Profit factor | 1.24 |
| Max R-drawdown | 14.50R |
| Max losing streak | 5 |
| Total setups detected | 138 |
| Missed rate | 40.6% |
| TP exits | 30 |
| SL exits | 51 |

## Trade Direction Breakdown

| Direction | Trades | Win Rate | Avg R |
|-----------|--------|----------|-------|
| LONG | 57 | 42.1% | 0.224 |
| SHORT | 24 | 33.3% | -0.042 |

## R Distribution

| Bucket | Count |
|--------|-------|
| < -1R | 1 |
| -1R to 0 | 48 |
| 0 to 1R | 1 |
| 1R to 2R | 1 |
| 2R to 3R | 30 |
| >= 3R | 0 |