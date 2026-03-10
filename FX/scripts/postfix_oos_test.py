"""
POST-FIX OOS TEST 2024
Test TOP3 configurations on 2024 (out-of-sample)
"""
import pandas as pd
import sys
import os

sys.path.append('.')

from src.strategies.trend_following_v1 import run_trend_backtest

print("="*80)
print("POST-FIX OOS TEST 2024")
print("="*80)
print()

# Load TOP3 from grid search
print("Loading TOP3 configurations...")
try:
    top20 = pd.read_csv('data/outputs/postfix_top20.csv')
    top3 = top20.head(3)
    print(f"[OK] Loaded TOP3 from grid search")
except:
    print("[ERROR] postfix_top20.csv not found. Run postfix_grid_search.py first.")
    sys.exit(1)

print()
print("TOP3 Configurations:")
for idx, row in top3.iterrows():
    print(f"  #{idx+1}: entry={row['entry_offset']}, pullback={row['pullback']}, RR={row['rr']}, buffer={row['sl_buffer']}")
    print(f"       Val: {row['val_trades']} trades, {row['val_expectancy']:.3f}R")
print()

# Load 2024 data (OOS)
print("Loading 2024 data (OOS)...")
ltf_df = pd.read_csv('data/bars/eurusd_h1_bars.csv', index_col='timestamp', parse_dates=True)
test_df = ltf_df[(ltf_df.index >= '2024-01-01') & (ltf_df.index <= '2024-12-31')]
test_htf = test_df.resample('4h').agg({
    'open_bid': 'first', 'high_bid': 'max', 'low_bid': 'min', 'close_bid': 'last',
    'open_ask': 'first', 'high_ask': 'max', 'low_ask': 'min', 'close_ask': 'last'
}).dropna()

print(f"[OK] Test (2024): {len(test_df)} H1 bars, {len(test_htf)} H4 bars")
print()

# Run TOP3 on 2024
results = []

for rank, (idx, row) in enumerate(top3.iterrows(), 1):
    print(f"="*80)
    print(f"Testing Configuration #{rank}")
    print(f"="*80)

    params = {
        'entry_offset_atr_mult': row['entry_offset'],
        'pullback_max_bars': int(row['pullback']),
        'risk_reward': row['rr'],
        'sl_anchor': row['sl_anchor'],
        'sl_buffer_atr_mult': row['sl_buffer'],
        'pivot_lookback_ltf': 3,
        'pivot_lookback_htf': 5,
        'confirmation_bars': 1,
        'require_close_break': True
    }

    print("Parameters:")
    for k, v in params.items():
        print(f"  {k}: {v}")
    print()

    try:
        trades_test, metrics_test = run_trend_backtest('EURUSD', test_df, test_htf, params, initial_balance=10000)

        # Check feasibility
        if 'exit_feasible' in trades_test.columns:
            test_violations = (~trades_test['exit_feasible']).sum()
        else:
            test_violations = 0

        # Check intrabar conflicts
        tp_in_conflict = len(trades_test[trades_test['exit_reason'] == 'TP']) if 'exit_reason' in trades_test.columns else 0

        # Long vs Short breakdown
        if len(trades_test) > 0:
            long_trades = trades_test[trades_test['direction'] == 'LONG']
            short_trades = trades_test[trades_test['direction'] == 'SHORT']

            long_exp = long_trades['R'].mean() if len(long_trades) > 0 else 0
            short_exp = short_trades['R'].mean() if len(short_trades) > 0 else 0
        else:
            long_exp = short_exp = 0
            long_trades = short_trades = pd.DataFrame()

        results.append({
            'rank': rank,
            'entry_offset': row['entry_offset'],
            'pullback': row['pullback'],
            'rr': row['rr'],
            'sl_buffer': row['sl_buffer'],
            # Train/Val reference
            'train_expectancy': row['train_expectancy'],
            'val_expectancy': row['val_expectancy'],
            # Test (2024 OOS)
            'test_trades': metrics_test['trades_count'],
            'test_expectancy': metrics_test['expectancy_R'],
            'test_wr': metrics_test['win_rate'],
            'test_pf': metrics_test['profit_factor'],
            'test_maxdd': metrics_test['max_dd_pct'],
            'test_violations': test_violations,
            'tp_in_conflict': tp_in_conflict,
            # Long/Short
            'long_trades': len(long_trades),
            'long_expectancy': long_exp,
            'short_trades': len(short_trades),
            'short_expectancy': short_exp
        })

        print(f"Test (2024) Results:")
        print(f"  Trades: {metrics_test['trades_count']}")
        print(f"  Expectancy: {metrics_test['expectancy_R']:.4f}R")
        print(f"  Win Rate: {metrics_test['win_rate']:.2f}%")
        print(f"  Profit Factor: {metrics_test['profit_factor']:.2f}")
        print(f"  Max DD: {metrics_test['max_dd_pct']:.2f}%")
        print(f"  Feasibility violations: {test_violations}")
        print(f"  Long: {len(long_trades)} trades, {long_exp:.3f}R")
        print(f"  Short: {len(short_trades)} trades, {short_exp:.3f}R")
        print()

        # Save trades
        trades_file = f'data/outputs/postfix_oos2024_config{rank}.csv'
        trades_test.to_csv(trades_file, index=False)
        print(f"[OK] Saved: {trades_file}")
        print()

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        print()

# Save results
results_df = pd.DataFrame(results)
results_df.to_csv('data/outputs/postfix_oos2024_results.csv', index=False)
print("[OK] Saved: data/outputs/postfix_oos2024_results.csv")

print()
print("="*80)
print("OOS TEST 2024 COMPLETE")
print("="*80)

