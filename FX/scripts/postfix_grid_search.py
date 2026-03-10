"""
POST-FIX GRID SEARCH
Clean train/validate split with FIX2 engine
"""
import pandas as pd
import numpy as np
import sys
import os

sys.path.append('.')

from src.strategies.trend_following_v1 import run_trend_backtest

print("="*80)
print("POST-FIX GRID SEARCH")
print("="*80)
print()

# Load H1 bars
print("Loading H1 bars...")
ltf_df = pd.read_csv('data/bars/eurusd_h1_bars.csv', index_col='timestamp', parse_dates=True)
print(f"[OK] Loaded {len(ltf_df)} H1 bars")

# Split data
train_df = ltf_df[(ltf_df.index >= '2021-01-01') & (ltf_df.index <= '2022-12-31')]
validate_df = ltf_df[(ltf_df.index >= '2023-01-01') & (ltf_df.index <= '2023-12-31')]

print(f"[OK] Train: {len(train_df)} bars (2021-2022)")
print(f"[OK] Validate: {len(validate_df)} bars (2023)")

# Build H4 for each period
print("Building H4 bars...")
train_htf = train_df.resample('4h').agg({
    'open_bid': 'first', 'high_bid': 'max', 'low_bid': 'min', 'close_bid': 'last',
    'open_ask': 'first', 'high_ask': 'max', 'low_ask': 'min', 'close_ask': 'last'
}).dropna()

validate_htf = validate_df.resample('4h').agg({
    'open_bid': 'first', 'high_bid': 'max', 'low_bid': 'min', 'close_bid': 'last',
    'open_ask': 'first', 'high_ask': 'max', 'low_ask': 'min', 'close_ask': 'last'
}).dropna()

print(f"[OK] Train H4: {len(train_htf)} bars")
print(f"[OK] Validate H4: {len(validate_htf)} bars")
print()

# Define parameter grid
param_grid = {
    'entry_offset_atr_mult': [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
    'pullback_max_bars': [20, 30, 40, 50],
    'risk_reward': [1.5, 1.8, 2.0, 2.5],
    'sl_anchor': ['last_pivot'],  # pre_bos_pivot removed for simplicity
    'sl_buffer_atr_mult': [0.1, 0.2, 0.3, 0.5]
}

# Fixed parameters
fixed_params = {
    'pivot_lookback_ltf': 3,
    'pivot_lookback_htf': 5,
    'confirmation_bars': 1,
    'require_close_break': True
}

# Generate all combinations (sample if too many)
from itertools import product

all_combinations = list(product(
    param_grid['entry_offset_atr_mult'],
    param_grid['pullback_max_bars'],
    param_grid['risk_reward'],
    param_grid['sl_anchor'],
    param_grid['sl_buffer_atr_mult']
))

print(f"Total combinations: {len(all_combinations)}")

# Sample if > 200
max_runs = 200
if len(all_combinations) > max_runs:
    np.random.seed(42)
    sampled_indices = np.random.choice(len(all_combinations), max_runs, replace=False)
    combinations = [all_combinations[i] for i in sampled_indices]
    print(f"[SAMPLING] Running {max_runs} random combinations")
else:
    combinations = all_combinations
    print(f"[FULL GRID] Running all {len(combinations)} combinations")

print()

# Run grid search
results = []

for idx, (entry_offset, pullback, rr, sl_anchor, sl_buffer) in enumerate(combinations):
    print(f"[{idx+1}/{len(combinations)}] Testing: entry={entry_offset}, pullback={pullback}, RR={rr}, buffer={sl_buffer}")

    params = {
        **fixed_params,
        'entry_offset_atr_mult': entry_offset,
        'pullback_max_bars': pullback,
        'risk_reward': rr,
        'sl_anchor': sl_anchor,
        'sl_buffer_atr_mult': sl_buffer
    }

    try:
        # Train
        trades_train, metrics_train = run_trend_backtest('EURUSD', train_df, train_htf, params, initial_balance=10000)

        # Validate
        trades_val, metrics_val = run_trend_backtest('EURUSD', validate_df, validate_htf, params, initial_balance=10000)

        # Check feasibility
        if 'exit_feasible' in trades_train.columns:
            train_violations = (~trades_train['exit_feasible']).sum()
        else:
            train_violations = 0

        if 'exit_feasible' in trades_val.columns:
            val_violations = (~trades_val['exit_feasible']).sum()
        else:
            val_violations = 0

        results.append({
            'entry_offset': entry_offset,
            'pullback': pullback,
            'rr': rr,
            'sl_anchor': sl_anchor,
            'sl_buffer': sl_buffer,
            # Train metrics
            'train_trades': metrics_train['trades_count'],
            'train_expectancy': metrics_train['expectancy_R'],
            'train_wr': metrics_train['win_rate'],
            'train_pf': metrics_train['profit_factor'],
            'train_maxdd': metrics_train['max_dd_pct'],
            'train_violations': train_violations,
            # Validate metrics
            'val_trades': metrics_val['trades_count'],
            'val_expectancy': metrics_val['expectancy_R'],
            'val_wr': metrics_val['win_rate'],
            'val_pf': metrics_val['profit_factor'],
            'val_maxdd': metrics_val['max_dd_pct'],
            'val_violations': val_violations
        })

        print(f"  Train: {metrics_train['trades_count']} trades, {metrics_train['expectancy_R']:.3f}R")
        print(f"  Val: {metrics_val['trades_count']} trades, {metrics_val['expectancy_R']:.3f}R")

    except Exception as e:
        print(f"  [ERROR] {str(e)[:100]}")
        continue

print()
print(f"[OK] Grid search complete. {len(results)} successful runs.")
print()

# Save results
results_df = pd.DataFrame(results)
results_df.to_csv('data/outputs/postfix_grid_results.csv', index=False)
print("[OK] Saved: data/outputs/postfix_grid_results.csv")

# Filter and rank
print()
print("="*80)
print("FILTERING & RANKING")
print("="*80)
print()

# Apply filters
filtered = results_df[
    (results_df['val_trades'] >= 60) &
    (results_df['val_maxdd'] <= 30) &
    (results_df['val_pf'] >= 1.05) &
    (results_df['val_violations'] == 0) &
    (results_df['train_violations'] == 0)
]

print(f"Configurations after filters: {len(filtered)}/{len(results_df)}")

if len(filtered) == 0:
    print("[WARNING] No configurations passed filters!")
    print("Relaxing filters...")
    filtered = results_df[
        (results_df['val_trades'] >= 40) &
        (results_df['val_maxdd'] <= 35) &
        (results_df['val_pf'] >= 1.0)
    ]
    print(f"After relaxed filters: {len(filtered)}")

# Sort by validate expectancy
top20 = filtered.nlargest(20, 'val_expectancy')

print()
print("TOP 20 Configurations (by Validate Expectancy):")
print()
print(top20[['entry_offset', 'pullback', 'rr', 'sl_buffer', 'train_expectancy', 'val_expectancy', 'val_trades', 'val_pf', 'val_maxdd']].to_string())
print()

# Save top 20
top20.to_csv('data/outputs/postfix_top20.csv', index=False)
print("[OK] Saved: data/outputs/postfix_top20.csv")

print()
print("="*80)
print("GRID SEARCH COMPLETE")
print("="*80)

