"""
RE-RUN Config #2 with FIXED ENGINE
"""
import pandas as pd
import sys
import os

sys.path.append('.')

from src.strategies.trend_following_v1 import run_trend_backtest

print("="*80)
print("RE-RUN CONFIG #2 WITH FIXED ENGINE")
print("="*80)
print()

# Load H1 bars
print("Loading H1 bars...")
ltf_df = pd.read_csv('data/bars/eurusd_h1_bars.csv', index_col='timestamp', parse_dates=True)
ltf_df = ltf_df[(ltf_df.index >= '2021-01-01') & (ltf_df.index <= '2024-12-31')]
print(f"[OK] Loaded {len(ltf_df)} H1 bars")

# Build H4
print("Building H4 bars...")
htf_df = ltf_df.resample('4h').agg({
    'open_bid': 'first', 'high_bid': 'max', 'low_bid': 'min', 'close_bid': 'last',
    'open_ask': 'first', 'high_ask': 'max', 'low_ask': 'min', 'close_ask': 'last'
}).dropna()
print(f"[OK] Built {len(htf_df)} H4 bars")
print()

# Config #2 parameters (from audit)
params = {
    'entry_offset_atr_mult': 0.3,
    'pullback_max_bars': 40,
    'risk_reward': 1.8,
    'sl_anchor': 'last_pivot',
    'sl_buffer_atr_mult': 0.5,
    'pivot_lookback_ltf': 3,
    'pivot_lookback_htf': 5,
    'confirmation_bars': 1,
    'require_close_break': True
}

print("Config #2 parameters:")
for k, v in params.items():
    print(f"  {k}: {v}")
print()

# Run backtest
print("Running backtest with FIXED engine...")
print()

trades_df, metrics = run_trend_backtest('EURUSD', ltf_df, htf_df, params, initial_balance=10000)

print()
print(f"[OK] Backtest complete!")
print(f"  Trades: {len(trades_df)}")
print(f"  Expectancy: {metrics['expectancy_R']:.4f}R")
print(f"  Win Rate: {metrics['win_rate']:.2f}%")
print(f"  Profit Factor: {metrics['profit_factor']:.2f}")
print(f"  Max DD: {metrics['max_dd_pct']:.2f}%")
print()

# Save trades
trades_file = 'data/outputs/trades_full_2_FIXED.csv'
os.makedirs(os.path.dirname(trades_file), exist_ok=True)
trades_df.to_csv(trades_file, index=False)
print(f"[OK] Saved trades: {trades_file}")

# Generate summary
summary = f"""# Config #2 FIXED - Summary Report

**Date:** 2026-02-18
**Period:** 2021-2024
**Engine:** FIXED (worst-case, bid/ask, R-calc)

## Parameters

```yaml
entry_offset_atr_mult: {params['entry_offset_atr_mult']}
pullback_max_bars: {params['pullback_max_bars']}
risk_reward: {params['risk_reward']}
sl_anchor: {params['sl_anchor']}
sl_buffer_atr_mult: {params['sl_buffer_atr_mult']}
```

## Results

- **Trades:** {len(trades_df)}
- **Expectancy:** {metrics['expectancy_R']:.4f}R
- **Win Rate:** {metrics['win_rate']:.2f}%
- **Profit Factor:** {metrics['profit_factor']:.2f}
- **Max Drawdown:** {metrics['max_dd_pct']:.2f}%
- **Max Losing Streak:** {metrics['max_losing_streak']}

## Engine Fixes Applied

1. ✅ **Worst-case policy enforced** - SL always chosen in conflicts
2. ✅ **Bid/Ask sides correct** - LONG exits on BID, SHORT exits on ASK
3. ✅ **R-multiple calculated correctly** - realized_distance / risk_distance
4. ✅ **Extended columns added** - risk_distance, realized_distance, planned_sl, planned_tp

---

*Report generated: {pd.Timestamp.now()}*
"""

summary_file = 'reports/full_run_top3_summary_FIXED.md'
with open(summary_file, 'w') as f:
    f.write(summary)

print(f"[OK] Saved summary: {summary_file}")
print()
print("="*80)
print("RE-RUN COMPLETE")
print("="*80)

