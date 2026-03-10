"""
FINAL PROOF MODE - Extract and save OOS trades from revalidation
"""

import pandas as pd
import sys
import os

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

INITIAL_BALANCE = 10000
SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']

print("Extracting OOS trades for FINAL_PROOF_MODE...")
print()

os.makedirs('data/outputs', exist_ok=True)

for symbol in SYMBOLS:
    print(f"Processing {symbol}...")

    ltf_file = f'data/bars_validated/{symbol.lower()}_1h_validated.csv'
    htf_file = f'data/bars_validated/{symbol.lower()}_4h_validated.csv'

    if not os.path.exists(ltf_file):
        print(f"  [SKIP] No validated bars")
        continue

    ltf_df = pd.read_csv(ltf_file, parse_dates=['timestamp'])
    htf_df = pd.read_csv(htf_file, parse_dates=['timestamp'])

    # Run backtest
    trades_full, _ = run_trend_backtest(symbol, ltf_df, htf_df, FROZEN_CONFIG, INITIAL_BALANCE)

    if len(trades_full) == 0:
        print(f"  [SKIP] No trades")
        continue

    # Parse timestamps and filter OOS
    trades_full['entry_time'] = pd.to_datetime(trades_full['entry_time'])
    trades_full['year'] = trades_full['entry_time'].dt.year

    trades_oos = trades_full[trades_full['year'].isin([2023, 2024])].copy()

    # Save
    output_file = f'data/outputs/trades_OOS_{symbol}_2023_2024.csv'
    trades_oos.to_csv(output_file, index=False)

    print(f"  Saved {len(trades_oos)} OOS trades to {output_file}")

print()
print("OOS trades extraction complete.")

