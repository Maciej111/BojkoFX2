# Index Backtest Report: USATECHIDXUSD

**Period:** 2021-01-01 -> 2026-03-07
**LTF:** 30m  |  **HTF:** 1h
**Strategy:** BOS + Pullback (trend_following_v1)

## Strategy Parameters

| Parameter | Value |
|-----------|-------|
| pivot_lookback_ltf | 4 |
| pivot_lookback_htf | 7 |
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
| Total trades | 66 |
| Win rate | 25.8% |
| Expectancy (R) | -0.435 |
| Profit factor | 0.54 |
| Max R-drawdown | 30.71R |
| Max losing streak | 13 |
| Total setups detected | 100 |
| Missed rate | 34.0% |
| TP exits | 17 |
| SL exits | 49 |

## Trade Direction Breakdown

| Direction | Trades | Win Rate | Avg R |
|-----------|--------|----------|-------|
| LONG | 37 | 27.0% | -0.560 |
| SHORT | 29 | 24.1% | -0.276 |

## R Distribution

| Bucket | Count |
|--------|-------|
| < -1R | 1 |
| -1R to 0 | 48 |
| 0 to 1R | 0 |
| 1R to 2R | 0 |
| 2R to 3R | 17 |
| >= 3R | 0 |