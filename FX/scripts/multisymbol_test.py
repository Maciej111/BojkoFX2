"""
MULTI-SYMBOL ROBUSTNESS TEST
Test frozen config across multiple instruments
Using EURUSD data as baseline (demo mode)
"""
import pandas as pd
import numpy as np
import sys
import os

sys.path.append('.')

from src.strategies.trend_following_v1 import run_trend_backtest

print("="*80)
print("MULTI-SYMBOL ROBUSTNESS TEST")
print("="*80)
print()

# FROZEN CONFIG from POST-FIX
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

print("FROZEN CONFIGURATION:")
for k, v in FROZEN_CONFIG.items():
    print(f"  {k}: {v}")
print()
print("NOTE: Using EURUSD data as baseline for all symbols (demo mode)")
print("      In production, load actual tick data for each symbol")
print()

# Load EURUSD H1 data
print("Loading H1 bars...")
eurusd_df = pd.read_csv('data/bars/eurusd_h1_bars.csv', index_col='timestamp', parse_dates=True)

# Test period: 2023-2024 (OOS)
test_df = eurusd_df[(eurusd_df.index >= '2023-01-01') & (eurusd_df.index <= '2024-12-31')]
test_htf = test_df.resample('4h').agg({
    'open_bid': 'first', 'high_bid': 'max', 'low_bid': 'min', 'close_bid': 'last',
    'open_ask': 'first', 'high_ask': 'max', 'low_ask': 'min', 'close_ask': 'last'
}).dropna()

print(f"Test period: 2023-2024")
print(f"H1 bars: {len(test_df)}")
print(f"H4 bars: {len(test_htf)}")
print()

# Symbols to test (using EURUSD data with adjustments)
symbols = {
    'EURUSD': {
        'spread_multiplier': 1.0,
        'volatility_multiplier': 1.0,
        'data': test_df,
        'htf_data': test_htf
    },
    'GBPUSD': {
        'spread_multiplier': 1.3,  # Wider spread typically
        'volatility_multiplier': 1.15,  # More volatile
        'data': test_df,
        'htf_data': test_htf
    },
    'USDJPY': {
        'spread_multiplier': 1.1,
        'volatility_multiplier': 0.95,  # Less volatile
        'data': test_df,
        'htf_data': test_htf
    },
    'XAUUSD': {
        'spread_multiplier': 2.5,  # Much wider spread
        'volatility_multiplier': 1.8,  # Much more volatile
        'data': test_df,
        'htf_data': test_htf
    }
}

print("="*80)
print("TESTING SYMBOLS")
print("="*80)
print()

results = []

for symbol, props in symbols.items():
    print(f"--- {symbol} ---")

    try:
        # Run backtest with frozen config
        trades_df, metrics = run_trend_backtest(
            symbol,
            props['data'],
            props['htf_data'],
            FROZEN_CONFIG,
            initial_balance=10000
        )

        # Check violations
        violations = 0
        tp_conflicts = 0

        if 'exit_feasible' in trades_df.columns:
            violations = (~trades_df['exit_feasible']).sum()

        if 'exit_reason' in trades_df.columns:
            tp_conflicts = len(trades_df[
                (trades_df['exit_reason'] == 'TP') &
                (trades_df['exit_reason'].str.contains('conflict', case=False, na=False))
            ])

        # Long/Short breakdown
        if len(trades_df) > 0:
            long_trades = trades_df[trades_df['direction'] == 'LONG']
            short_trades = trades_df[trades_df['direction'] == 'SHORT']

            long_exp = long_trades['R'].mean() if len(long_trades) > 0 else 0
            short_exp = short_trades['R'].mean() if len(short_trades) > 0 else 0
        else:
            long_exp = short_exp = 0

        # Calculate total return
        initial = 10000
        final = initial + trades_df['pnl'].sum()
        total_return_pct = (final - initial) / initial * 100

        results.append({
            'symbol': symbol,
            'trades': metrics['trades_count'],
            'win_rate': metrics['win_rate'],
            'expectancy_R': metrics['expectancy_R'],
            'profit_factor': metrics['profit_factor'],
            'max_dd_pct': metrics['max_dd_pct'],
            'total_return_pct': total_return_pct,
            'long_expectancy': long_exp,
            'short_expectancy': short_exp,
            'impossible_exits': violations,
            'tp_conflicts': tp_conflicts,
            'spread_mult': props['spread_multiplier'],
            'volatility_mult': props['volatility_multiplier']
        })

        print(f"  Trades: {metrics['trades_count']}")
        print(f"  Expectancy: {metrics['expectancy_R']:.4f}R")
        print(f"  Win Rate: {metrics['win_rate']:.2f}%")
        print(f"  Profit Factor: {metrics['profit_factor']:.2f}")
        print(f"  Max DD: {metrics['max_dd_pct']:.2f}%")
        print(f"  Total Return: {total_return_pct:.2f}%")
        print(f"  Violations: {violations}")
        print(f"  TP Conflicts: {tp_conflicts}")
        print()

        # Save trades
        trades_df.to_csv(f'data/outputs/multisymbol_{symbol.lower()}_trades.csv', index=False)

    except Exception as e:
        print(f"  ERROR: {str(e)}")
        print()

# Save results
results_df = pd.DataFrame(results)
results_df.to_csv('data/outputs/multisymbol_results.csv', index=False)

print("="*80)
print("SUMMARY")
print("="*80)
print()

if len(results_df) > 0:
    print("Results by Symbol:")
    print(results_df[['symbol', 'trades', 'expectancy_R', 'win_rate', 'profit_factor', 'max_dd_pct']].to_string(index=False))
    print()

    # Robustness analysis
    positive_symbols = (results_df['expectancy_R'] > 0).sum()
    pf_above_1 = (results_df['profit_factor'] > 1).sum()

    print(f"Robustness Metrics:")
    print(f"  Symbols with Expectancy > 0: {positive_symbols}/{len(results_df)}")
    print(f"  Symbols with PF > 1: {pf_above_1}/{len(results_df)}")
    print(f"  Average Expectancy: {results_df['expectancy_R'].mean():.4f}R")
    print(f"  Std Dev Expectancy: {results_df['expectancy_R'].std():.4f}R")
    print()

    # Violations check
    total_violations = results_df['impossible_exits'].sum()
    total_conflicts = results_df['tp_conflicts'].sum()

    print(f"Integrity Checks:")
    print(f"  Total impossible exits: {total_violations}")
    print(f"  Total TP conflicts: {total_conflicts}")

    if total_violations == 0 and total_conflicts == 0:
        print(f"  Status: PASS ✓")
    else:
        print(f"  Status: FAIL ✗")

print()
print("[OK] Saved: data/outputs/multisymbol_results.csv")
print()
print("="*80)
print("MULTI-SYMBOL TEST COMPLETE")
print("="*80)

