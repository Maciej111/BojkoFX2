# Index Backtest Report: USATECHIDXUSD

**Period:** 2021-01-01 → 2024-12-30
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
| Total trades | 694 |
| Win rate | 46.0% |
| Expectancy (R) | 0.460 |
| Profit factor | 1.49 |
| Max R-drawdown | 34.54R |
| Max losing streak | 11 |
| Total setups detected | 1039 |
| Missed rate | 33.2% |
| TP exits | 306 |
| SL exits | 388 |

## Trade Direction Breakdown

| Direction | Trades | Win Rate | Avg R |
|-----------|--------|----------|-------|
| LONG | 386 | 46.9% | 0.637 |
| SHORT | 308 | 44.8% | 0.239 |

## R Distribution

| Bucket | Count |
|--------|-------|
| < -1R | 8 |
| -1R to 0 | 367 |
| 0 to 1R | 4 |
| 1R to 2R | 10 |
| 2R to 3R | 302 |
| >= 3R | 3 |