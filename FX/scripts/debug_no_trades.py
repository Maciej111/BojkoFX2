"""
Debug - check why no trades in OOS
"""
import pandas as pd
import sys
sys.path.append('.')

from src.strategies.trend_following_v1 import run_trend_backtest

FROZEN_CONFIG = {
    'entry_offset_atr_mult': 0.3,
    'pullback_max_bars': 40,
    'risk_reward': 1.5,
    'sl_anchor': 'last_pivot',
    'sl_buffer_atr_mult': 0.5,
    'pivot_lookback_ltf': 3,
    'pivot_lookback_htf': 5,
    'confirmation_bars': 1,
    'require_close_break': True
}

# Test GBPUSD (has full 2024 data)
ltf_df = pd.read_csv('data/bars/gbpusd_1h_bars.csv', parse_dates=['timestamp'])
htf_df = pd.read_csv('data/bars/gbpusd_4h_bars.csv', parse_dates=['timestamp'])

print(f"Loaded bars:")
print(f"  LTF: {len(ltf_df)} bars")
print(f"  LTF period: {ltf_df['timestamp'].min()} to {ltf_df['timestamp'].max()}")
print()

# Run backtest
trades, metrics = run_trend_backtest('GBPUSD', ltf_df, htf_df, FROZEN_CONFIG, 10000)

print(f"Total trades: {len(trades)}")

if len(trades) > 0:
    trades['entry_time'] = pd.to_datetime(trades['entry_time'])
    print(f"\nFirst trade: {trades['entry_time'].min()}")
    print(f"Last trade: {trades['entry_time'].max()}")

    # Check years
    trades['year'] = trades['entry_time'].dt.year
    print(f"\nTrades by year:")
    print(trades['year'].value_counts().sort_index())

    # Show first 5 trades
    print(f"\nFirst 5 trades:")
    print(trades[['entry_time', 'direction', 'R']].head())
else:
    print("NO TRADES GENERATED!")
    print("\nPossible reasons:")
    print("- No BOS detected")
    print("- HTF bias filtering out all setups")
    print("- No pivot confirmations")
    print("- Entry conditions never met")

