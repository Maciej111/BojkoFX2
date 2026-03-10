"""
POST-FIX WALK-FORWARD
Rolling window optimization and testing
"""
import pandas as pd
import numpy as np
import sys
import os

sys.path.append('.')

from src.strategies.trend_following_v1 import run_trend_backtest

print("="*80)
print("POST-FIX WALK-FORWARD")
print("="*80)
print()

# Load data
print("Loading H1 bars...")
ltf_df = pd.read_csv('data/bars/eurusd_h1_bars.csv', index_col='timestamp', parse_dates=True)
print(f"[OK] Loaded {len(ltf_df)} H1 bars")
print()

# Define walk-forward windows
windows = [
    {'name': 'WF1', 'train_start': '2021-01-01', 'train_end': '2022-12-31', 'test_start': '2023-01-01', 'test_end': '2023-12-31'},
    {'name': 'WF2', 'train_start': '2022-01-01', 'train_end': '2023-12-31', 'test_start': '2024-01-01', 'test_end': '2024-12-31'}
]

print("Walk-Forward Windows:")
for w in windows:
    print(f"  {w['name']}: Train {w['train_start'][:4]}-{w['train_end'][:4]} -> Test {w['test_start'][:4]}")
print()

# Parameter grid (smaller for WF speed)
param_grid = {
    'entry_offset_atr_mult': [0.1, 0.2, 0.3, 0.4],
    'pullback_max_bars': [30, 40, 50],
    'risk_reward': [1.5, 1.8, 2.0],
    'sl_buffer_atr_mult': [0.2, 0.3, 0.5]
}

fixed_params = {
    'pivot_lookback_ltf': 3,
    'pivot_lookback_htf': 5,
    'confirmation_bars': 1,
    'require_close_break': True,
    'sl_anchor': 'last_pivot'
}

from itertools import product
all_combinations = list(product(
    param_grid['entry_offset_atr_mult'],
    param_grid['pullback_max_bars'],
    param_grid['risk_reward'],
    param_grid['sl_buffer_atr_mult']
))

print(f"Parameter combinations: {len(all_combinations)}")
print()

# Walk-forward loop
wf_results = []

for window in windows:
    print("="*80)
    print(f"{window['name']}: Train {window['train_start'][:4]}-{window['train_end'][:4]} -> Test {window['test_start'][:4]}")
    print("="*80)
    print()

    # Split data
    train_df = ltf_df[(ltf_df.index >= window['train_start']) & (ltf_df.index <= window['train_end'])]
    test_df = ltf_df[(ltf_df.index >= window['test_start']) & (ltf_df.index <= window['test_end'])]

    train_htf = train_df.resample('4h').agg({
        'open_bid': 'first', 'high_bid': 'max', 'low_bid': 'min', 'close_bid': 'last',
        'open_ask': 'first', 'high_ask': 'max', 'low_ask': 'min', 'close_ask': 'last'
    }).dropna()

    test_htf = test_df.resample('4h').agg({
        'open_bid': 'first', 'high_bid': 'max', 'low_bid': 'min', 'close_bid': 'last',
        'open_ask': 'first', 'high_ask': 'max', 'low_ask': 'min', 'close_ask': 'last'
    }).dropna()

    print(f"Train: {len(train_df)} H1 bars")
    print(f"Test: {len(test_df)} H1 bars")
    print()

    # Optimize on train
    print("Optimizing on train period...")
    train_results = []

    for idx, (entry_offset, pullback, rr, sl_buffer) in enumerate(all_combinations):
        if (idx + 1) % 10 == 0:
            print(f"  [{idx+1}/{len(all_combinations)}]", end='\r')

        params = {
            **fixed_params,
            'entry_offset_atr_mult': entry_offset,
            'pullback_max_bars': pullback,
            'risk_reward': rr,
            'sl_buffer_atr_mult': sl_buffer
        }

        try:
            trades_train, metrics_train = run_trend_backtest('EURUSD', train_df, train_htf, params, initial_balance=10000)

            if metrics_train['trades_count'] >= 40 and metrics_train['profit_factor'] >= 1.0:
                train_results.append({
                    'params': params,
                    'expectancy': metrics_train['expectancy_R'],
                    'trades': metrics_train['trades_count'],
                    'pf': metrics_train['profit_factor']
                })
        except:
            continue

    print(f"  [{len(all_combinations)}/{len(all_combinations)}] Done")
    print(f"[OK] {len(train_results)} viable configurations found")
    print()

    if len(train_results) == 0:
        print("[WARNING] No viable configurations on train. Skipping this window.")
        continue

    # Select best from train
    train_results_df = pd.DataFrame(train_results)
    best_config = train_results_df.nlargest(1, 'expectancy').iloc[0]

    print(f"Best configuration on train:")
    print(f"  Expectancy: {best_config['expectancy']:.4f}R")
    print(f"  Trades: {best_config['trades']}")
    print(f"  Parameters: {best_config['params']}")
    print()

    # Test on test period with FROZEN parameters
    print(f"Testing on {window['test_start'][:4]} with FROZEN parameters...")

    try:
        trades_test, metrics_test = run_trend_backtest('EURUSD', test_df, test_htf, best_config['params'], initial_balance=10000)

        wf_results.append({
            'window': window['name'],
            'train_period': f"{window['train_start'][:4]}-{window['train_end'][:4]}",
            'test_period': window['test_start'][:4],
            'entry_offset': best_config['params']['entry_offset_atr_mult'],
            'pullback': best_config['params']['pullback_max_bars'],
            'rr': best_config['params']['risk_reward'],
            'sl_buffer': best_config['params']['sl_buffer_atr_mult'],
            'train_expectancy': best_config['expectancy'],
            'train_trades': best_config['trades'],
            'test_expectancy': metrics_test['expectancy_R'],
            'test_trades': metrics_test['trades_count'],
            'test_wr': metrics_test['win_rate'],
            'test_pf': metrics_test['profit_factor'],
            'test_maxdd': metrics_test['max_dd_pct']
        })

        print(f"[OK] Test Results:")
        print(f"  Trades: {metrics_test['trades_count']}")
        print(f"  Expectancy: {metrics_test['expectancy_R']:.4f}R")
        print(f"  Win Rate: {metrics_test['win_rate']:.2f}%")
        print(f"  Profit Factor: {metrics_test['profit_factor']:.2f}")
        print()

    except Exception as e:
        print(f"[ERROR] Test failed: {str(e)}")
        print()

# Save results
wf_results_df = pd.DataFrame(wf_results)
wf_results_df.to_csv('data/outputs/postfix_walkforward_results.csv', index=False)
print("[OK] Saved: data/outputs/postfix_walkforward_results.csv")

print()
print("="*80)
print("WALK-FORWARD COMPLETE")
print("="*80)
print()

# Summary
if len(wf_results_df) > 0:
    print("Summary:")
    print(wf_results_df[['window', 'train_expectancy', 'test_expectancy', 'test_trades']].to_string(index=False))
    print()
    print(f"Average Test Expectancy: {wf_results_df['test_expectancy'].mean():.4f}R")
    print(f"Positive Test Periods: {(wf_results_df['test_expectancy'] > 0).sum()}/{len(wf_results_df)}")

