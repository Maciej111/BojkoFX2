# Index Backtest Report: USATECHIDXUSD

**Period:** 2021-01-01 -> 2026-03-07
**LTF:** 5m  |  **HTF:** 4h
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
| use_bos_momentum_filter | True |
| bos_min_range_atr_mult | 1.2 |
| bos_min_body_to_range_ratio | 0.6 |
| use_flag_contraction_setup | False |
| flag_impulse_lookback_bars | 8 |
| flag_contraction_bars | 5 |
| flag_min_impulse_atr_mult | 2.5 |
| flag_max_contraction_atr_mult | 1.2 |
| flag_breakout_buffer_atr_mult | 0.1 |
| flag_sl_buffer_atr_mult | 0.3 |

## Results Summary

| Metric | Value |
|--------|-------|
| Total trades | 13 |
| Win rate | 46.2% |
| Expectancy (R) | 0.404 |
| Profit factor | 1.75 |
| Max R-drawdown | 2.00R |
| Max losing streak | 2 |
| Total setups detected | 20 |
| Missed rate | 35.0% |
| TP exits | 6 |
| SL exits | 7 |

## Trade Direction Breakdown

| Direction | Trades | Win Rate | Avg R |
|-----------|--------|----------|-------|
| LONG | 6 | 50.0% | 0.542 |
| SHORT | 7 | 42.9% | 0.286 |

## R Distribution

| Bucket | Count |
|--------|-------|
| < -1R | 0 |
| -1R to 0 | 7 |
| 0 to 1R | 0 |
| 1R to 2R | 0 |
| 2R to 3R | 6 |
| >= 3R | 0 |