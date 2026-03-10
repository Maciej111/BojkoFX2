# Index Backtest Report: USATECHIDXUSD

**Period:** 2024-01-01 → 2024-12-30
**LTF:** 1h  |  **HTF:** 4h
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
| Total trades | 59 |
| Win rate | 35.6% |
| Expectancy (R) | 0.118 |
| Profit factor | 0.98 |
| Max R-drawdown | 18.18R |
| Max losing streak | 14 |
| Total setups detected | 111 |
| Missed rate | 45.9% |
| TP exits | 20 |
| SL exits | 39 |

## Trade Direction Breakdown

| Direction | Trades | Win Rate | Avg R |
|-----------|--------|----------|-------|
| LONG | 36 | 38.9% | 0.271 |
| SHORT | 23 | 30.4% | -0.120 |

## R Distribution

| Bucket | Count |
|--------|-------|
| < -1R | 2 |
| -1R to 0 | 36 |
| 0 to 1R | 0 |
| 1R to 2R | 1 |
| 2R to 3R | 19 |
| >= 3R | 1 |