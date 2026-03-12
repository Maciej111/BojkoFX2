# Index Backtest Report: USATECHIDXUSD

**Period:** 2021-01-01 → 2026-03-07
**LTF:** 15m  |  **HTF:** 1h
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
| risk_reward | 2.5 |
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
| Total trades | 94 |
| Win rate | 22.3% |
| Expectancy (R) | -0.289 |
| Profit factor | 0.63 |
| Max R-drawdown | 34.13R |
| Max losing streak | 12 |
| Total setups detected | 134 |
| Missed rate | 29.9% |
| TP exits | 18 |
| SL exits | 76 |

## Trade Direction Breakdown

| Direction | Trades | Win Rate | Avg R |
|-----------|--------|----------|-------|
| LONG | 55 | 23.6% | -0.282 |
| SHORT | 39 | 20.5% | -0.297 |

## R Distribution

| Bucket | Count |
|--------|-------|
| < -1R | 2 |
| -1R to 0 | 71 |
| 0 to 1R | 2 |
| 1R to 2R | 1 |
| 2R to 3R | 18 |
| >= 3R | 0 |