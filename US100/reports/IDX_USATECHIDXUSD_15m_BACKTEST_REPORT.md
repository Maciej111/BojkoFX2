# Index Backtest Report: USATECHIDXUSD

**Period:** 2024-01-01 → 2024-12-30
**LTF:** 15m  |  **HTF:** 4h
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
| Total trades | 105 |
| Win rate | 45.7% |
| Expectancy (R) | 0.353 |
| Profit factor | 1.75 |
| Max R-drawdown | 14.51R |
| Max losing streak | 6 |
| Total setups detected | 171 |
| Missed rate | 38.0% |
| TP exits | 47 |
| SL exits | 58 |

## Trade Direction Breakdown

| Direction | Trades | Win Rate | Avg R |
|-----------|--------|----------|-------|
| LONG | 70 | 47.1% | 0.394 |
| SHORT | 35 | 42.9% | 0.271 |

## R Distribution

| Bucket | Count |
|--------|-------|
| < -1R | 1 |
| -1R to 0 | 56 |
| 0 to 1R | 1 |
| 1R to 2R | 2 |
| 2R to 3R | 45 |
| >= 3R | 0 |