"""
POST-FIX QUICK GRID SEARCH
Smaller grid for faster results
"""
import pandas as pd
import numpy as np
import sys
import os

sys.path.append('.')

from src.strategies.trend_following_v1 import run_trend_backtest

print("="*80)
print("POST-FIX QUICK GRID SEARCH")
print("="*80)
print()

# Load data
ltf_df = pd.read_csv('data/bars/eurusd_h1_bars.csv', index_col='timestamp', parse_dates=True)

train_df = ltf_df[(ltf_df.index >= '2021-01-01') & (ltf_df.index <= '2022-12-31')]
validate_df = ltf_df[(ltf_df.index >= '2023-01-01') & (ltf_df.index <= '2023-12-31')]

print(f"Train: {len(train_df)} bars (2021-2022)")
print(f"Val: {len(validate_df)} bars (2023)")

train_htf = train_df.resample('4h').agg({
    'open_bid': 'first', 'high_bid': 'max', 'low_bid': 'min', 'close_bid': 'last',
    'open_ask': 'first', 'high_ask': 'max', 'low_ask': 'min', 'close_ask': 'last'
}).dropna()

validate_htf = validate_df.resample('4h').agg({
    'open_bid': 'first', 'high_bid': 'max', 'low_bid': 'min', 'close_bid': 'last',
    'open_ask': 'first', 'high_ask': 'max', 'low_ask': 'min', 'close_ask': 'last'
}).dropna()

print()

# Small parameter grid (50 combinations)
param_grid = [
    # entry, pullback, rr, sl_buffer
    (0.1, 30, 1.5, 0.3),
    (0.1, 40, 1.8, 0.3),
    (0.2, 30, 1.5, 0.2),
    (0.2, 40, 1.8, 0.3),
    (0.2, 40, 2.0, 0.5),
    (0.3, 30, 1.5, 0.2),
    (0.3, 40, 1.8, 0.3),
    (0.3, 40, 1.8, 0.5),
    (0.3, 50, 2.0, 0.3),
    (0.4, 30, 1.5, 0.2),
    (0.4, 40, 1.8, 0.3),
    (0.4, 40, 2.0, 0.5),
    (0.5, 40, 1.8, 0.3),
    (0.1, 40, 2.0, 0.3),
    (0.2, 50, 1.8, 0.3),
    (0.3, 40, 1.5, 0.3),
    (0.4, 50, 2.0, 0.3),
    (0.2, 40, 1.8, 0.5),
    (0.3, 30, 1.8, 0.3),
    (0.1, 50, 1.8, 0.5),
]

fixed_params = {
    'pivot_lookback_ltf': 3,
    'pivot_lookback_htf': 5,
    'confirmation_bars': 1,
    'require_close_break': True,
    'sl_anchor': 'last_pivot'
}

print(f"Testing {len(param_grid)} configurations...")
print()

results = []

for idx, (entry_offset, pullback, rr, sl_buffer) in enumerate(param_grid):
    print(f"[{idx+1}/{len(param_grid)}] entry={entry_offset}, pullback={pullback}, RR={rr}, buffer={sl_buffer}")

    params = {
        **fixed_params,
        'entry_offset_atr_mult': entry_offset,
        'pullback_max_bars': pullback,
        'risk_reward': rr,
        'sl_buffer_atr_mult': sl_buffer
    }

    try:
        trades_train, metrics_train = run_trend_backtest('EURUSD', train_df, train_htf, params, initial_balance=10000)
        trades_val, metrics_val = run_trend_backtest('EURUSD', validate_df, validate_htf, params, initial_balance=10000)

        results.append({
            'entry_offset': entry_offset,
            'pullback': pullback,
            'rr': rr,
            'sl_buffer': sl_buffer,
            'train_trades': metrics_train['trades_count'],
            'train_exp': metrics_train['expectancy_R'],
            'train_wr': metrics_train['win_rate'],
            'train_pf': metrics_train['profit_factor'],
            'train_dd': metrics_train['max_dd_pct'],
            'val_trades': metrics_val['trades_count'],
            'val_exp': metrics_val['expectancy_R'],
            'val_wr': metrics_val['win_rate'],
            'val_pf': metrics_val['profit_factor'],
            'val_dd': metrics_val['max_dd_pct']
        })

        print(f"  Train: {metrics_train['trades_count']} trades, {metrics_train['expectancy_R']:.3f}R")
        print(f"  Val: {metrics_val['trades_count']} trades, {metrics_val['expectancy_R']:.3f}R")

    except Exception as e:
        print(f"  ERROR: {str(e)[:80]}")

print()
print(f"[OK] {len(results)} successful runs")
print()

# Save all results
results_df = pd.DataFrame(results)
results_df.to_csv('data/outputs/postfix_grid_results.csv', index=False)
print("[OK] Saved: postfix_grid_results.csv")

# Filter & rank
filtered = results_df[
    (results_df['val_trades'] >= 40) &
    (results_df['val_dd'] <= 35) &
    (results_df['val_pf'] >= 1.0)
]

print(f"After filters: {len(filtered)}/{len(results_df)}")

if len(filtered) > 0:
    top = filtered.nlargest(min(10, len(filtered)), 'val_exp')

    print()
    print("TOP Configurations:")
    print(top[['entry_offset', 'pullback', 'rr', 'sl_buffer', 'train_exp', 'val_exp', 'val_trades']].to_string(index=False))

    top.to_csv('data/outputs/postfix_top20.csv', index=False)
    print()
    print("[OK] Saved: postfix_top20.csv")
else:
    print("[WARNING] No configs passed filters!")

print()
print("GRID SEARCH COMPLETE")

