"""
Trend Following Parameter Grid Search
Grid search z walk-forward validation (train/test split)
"""
import sys
import os
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from itertools import product
import random
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.strategies.trend_following_v1 import run_trend_backtest


def generate_param_grid():
    """Generate full parameter grid."""
    grid = {
        'entry_offset_atr_mult': [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
        'pullback_max_bars': [10, 20, 30, 40],
        'risk_reward': [1.5, 1.8, 2.0, 2.5],
        'sl_anchor': ['last_pivot', 'pre_bos_pivot'],
        'sl_buffer_atr_mult': [0.1, 0.2, 0.3, 0.5]
    }

    # Fixed params
    fixed = {
        'pivot_lookback_ltf': 3,
        'pivot_lookback_htf': 5,
        'confirmation_bars': 1,
        'require_close_break': True
    }

    # Generate all combinations
    keys = list(grid.keys())
    values = list(grid.values())

    all_combos = []
    for combo in product(*values):
        params = dict(zip(keys, combo))
        params.update(fixed)
        all_combos.append(params)

    return all_combos


def sample_grid(all_combos, max_runs, random_sample):
    """Sample subset of grid."""
    if not random_sample or len(all_combos) <= max_runs:
        return all_combos[:max_runs]

    return random.sample(all_combos, max_runs)


def run_single_config(symbol, ltf_train, htf_train, ltf_test, htf_test, params, initial_balance=10000):
    """Run backtest for single config on train and test."""

    # Train
    trades_train, metrics_train = run_trend_backtest(symbol, ltf_train, htf_train, params, initial_balance)

    # Test
    trades_test, metrics_test = run_trend_backtest(symbol, ltf_test, htf_test, params, initial_balance)

    # Combine results
    result = {
        # Parameters
        'entry_offset_atr': params['entry_offset_atr_mult'],
        'pullback_max_bars': params['pullback_max_bars'],
        'risk_reward': params['risk_reward'],
        'sl_anchor': params['sl_anchor'],
        'sl_buffer_atr': params['sl_buffer_atr_mult'],

        # Train metrics
        'train_trades': metrics_train['trades_count'],
        'train_expectancy_R': metrics_train['expectancy_R'],
        'train_win_rate': metrics_train['win_rate'],
        'train_profit_factor': metrics_train['profit_factor'],
        'train_max_dd_pct': metrics_train['max_dd_pct'],
        'train_max_losing_streak': metrics_train['max_losing_streak'],
        'train_missed_rate': metrics_train['missed_rate'],
        'train_avg_bars_to_fill': metrics_train['avg_bars_to_fill'],

        # Test metrics
        'test_trades': metrics_test['trades_count'],
        'test_expectancy_R': metrics_test['expectancy_R'],
        'test_win_rate': metrics_test['win_rate'],
        'test_profit_factor': metrics_test['profit_factor'],
        'test_max_dd_pct': metrics_test['max_dd_pct'],
        'test_max_losing_streak': metrics_test['max_losing_streak'],
        'test_missed_rate': metrics_test['missed_rate'],
        'test_avg_bars_to_fill': metrics_test['avg_bars_to_fill']
    }

    return result


def generate_plots(results_df, output_dir='reports'):
    """Generate visualization plots."""

    os.makedirs(output_dir, exist_ok=True)

    # 1. Expectancy vs Trades
    plt.figure(figsize=(10, 6))
    plt.scatter(results_df['test_trades'], results_df['test_expectancy_R'], alpha=0.6)
    plt.axhline(y=0, color='red', linestyle='--', alpha=0.5)
    plt.xlabel('Test Trades Count')
    plt.ylabel('Test Expectancy (R)')
    plt.title('Trade Frequency vs Expectancy')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'grid_expectancy_vs_trades.png'), dpi=150)
    plt.close()

    # 2. Expectancy vs Missed Rate
    plt.figure(figsize=(10, 6))
    plt.scatter(results_df['test_missed_rate'] * 100, results_df['test_expectancy_R'], alpha=0.6)
    plt.axhline(y=0, color='red', linestyle='--', alpha=0.5)
    plt.xlabel('Test Missed Rate (%)')
    plt.ylabel('Test Expectancy (R)')
    plt.title('Missed Setup Rate vs Expectancy')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'grid_expectancy_vs_missed.png'), dpi=150)
    plt.close()

    # 3. Pareto Front (Expectancy vs Trades, filtered by DD)
    pareto_data = results_df[results_df['test_max_dd_pct'] <= 20].copy()

    plt.figure(figsize=(10, 6))

    # All points
    plt.scatter(results_df['test_trades'], results_df['test_expectancy_R'],
                alpha=0.3, label='All configs', color='gray')

    # Pareto front candidates (DD <= 20%)
    plt.scatter(pareto_data['test_trades'], pareto_data['test_expectancy_R'],
                alpha=0.7, label='DD <= 20%', color='blue')

    # Highlight top expectancy
    if len(pareto_data) > 0:
        best = pareto_data.nlargest(5, 'test_expectancy_R')
        plt.scatter(best['test_trades'], best['test_expectancy_R'],
                    color='red', s=100, marker='*', label='Top 5 Expectancy', zorder=5)

    plt.axhline(y=0, color='red', linestyle='--', alpha=0.5)
    plt.xlabel('Test Trades Count')
    plt.ylabel('Test Expectancy (R)')
    plt.title('Pareto Front: Expectancy vs Frequency (DD <= 20%)')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'grid_pareto.png'), dpi=150)
    plt.close()

    print(f"[OK] Generated 3 plots in {output_dir}/")


def generate_report(results_df, output_path='reports/trend_grid_summary.md'):
    """Generate summary report."""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w') as f:
        f.write("# Trend Following Grid Search Results\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Total Configurations Tested:** {len(results_df)}\n\n")

        f.write("---\n\n")

        # A) Top 20 by Expectancy (filtered)
        f.write("## A) Top 20 Configurations by Test Expectancy\n\n")
        f.write("**Filters:** test_trades >= 40 AND test_max_dd_pct <= 20\n\n")

        filtered = results_df[(results_df['test_trades'] >= 40) & (results_df['test_max_dd_pct'] <= 20)]
        top_exp = filtered.nlargest(20, 'test_expectancy_R')

        if len(top_exp) > 0:
            f.write("| Rank | Entry Offset | Pullback Bars | RR | SL Anchor | SL Buffer | Test Trades | Test Exp(R) | Test WR(%) | Test PF | Test DD(%) |\n")
            f.write("|------|--------------|---------------|-----|-----------|-----------|-------------|-------------|------------|---------|------------|\n")

            for idx, (i, row) in enumerate(top_exp.iterrows(), 1):
                f.write(f"| {idx} | {row['entry_offset_atr']:.1f} | {int(row['pullback_max_bars'])} | {row['risk_reward']:.1f} | "
                       f"{row['sl_anchor'][:4]} | {row['sl_buffer_atr']:.1f} | {int(row['test_trades'])} | "
                       f"{row['test_expectancy_R']:.3f} | {row['test_win_rate']:.1f} | {row['test_profit_factor']:.2f} | "
                       f"{row['test_max_dd_pct']:.1f} |\n")
        else:
            f.write("*No configurations meet the filter criteria.*\n")

        f.write("\n---\n\n")

        # B) Top 20 by Min Drawdown (filtered)
        f.write("## B) Top 20 Configurations by Lowest Test Drawdown\n\n")
        f.write("**Filter:** test_expectancy_R > 0\n\n")

        positive = results_df[results_df['test_expectancy_R'] > 0]
        top_dd = positive.nsmallest(20, 'test_max_dd_pct')

        if len(top_dd) > 0:
            f.write("| Rank | Entry Offset | Pullback Bars | RR | SL Anchor | SL Buffer | Test Trades | Test Exp(R) | Test DD(%) | Test PF |\n")
            f.write("|------|--------------|---------------|-----|-----------|-----------|-------------|-------------|------------|----------|\n")

            for idx, (i, row) in enumerate(top_dd.iterrows(), 1):
                f.write(f"| {idx} | {row['entry_offset_atr']:.1f} | {int(row['pullback_max_bars'])} | {row['risk_reward']:.1f} | "
                       f"{row['sl_anchor'][:4]} | {row['sl_buffer_atr']:.1f} | {int(row['test_trades'])} | "
                       f"{row['test_expectancy_R']:.3f} | {row['test_max_dd_pct']:.1f} | {row['test_profit_factor']:.2f} |\n")
        else:
            f.write("*No configurations with positive expectancy.*\n")

        f.write("\n---\n\n")

        # C) Pareto Summary
        f.write("## C) Pareto Front Analysis\n\n")
        f.write("Configurations with test_max_dd_pct <= 20%\n\n")

        pareto = results_df[results_df['test_max_dd_pct'] <= 20]

        f.write(f"- **Total Pareto Candidates:** {len(pareto)}\n")
        f.write(f"- **Positive Expectancy:** {len(pareto[pareto['test_expectancy_R'] > 0])}\n")
        f.write(f"- **Best Expectancy:** {pareto['test_expectancy_R'].max():.3f}R\n")
        f.write(f"- **Mean Expectancy:** {pareto['test_expectancy_R'].mean():.3f}R\n")
        f.write(f"- **Mean Trades:** {pareto['test_trades'].mean():.0f}\n\n")

        # Overall stats
        f.write("## Overall Statistics\n\n")
        f.write(f"- **Positive Test Expectancy:** {len(results_df[results_df['test_expectancy_R'] > 0])} / {len(results_df)} "
               f"({len(results_df[results_df['test_expectancy_R'] > 0]) / len(results_df) * 100:.1f}%)\n")
        f.write(f"- **Mean Test Expectancy:** {results_df['test_expectancy_R'].mean():.3f}R\n")
        f.write(f"- **Median Test Expectancy:** {results_df['test_expectancy_R'].median():.3f}R\n")
        f.write(f"- **Best Test Expectancy:** {results_df['test_expectancy_R'].max():.3f}R\n")
        f.write(f"- **Worst Test Expectancy:** {results_df['test_expectancy_R'].min():.3f}R\n\n")

        f.write("## Visualizations\n\n")
        f.write("- `grid_expectancy_vs_trades.png` - Frequency vs Expectancy\n")
        f.write("- `grid_expectancy_vs_missed.png` - Missed Rate vs Expectancy\n")
        f.write("- `grid_pareto.png` - Pareto Front (DD <= 20%)\n\n")

        f.write("---\n\n")
        f.write(f"*Report generated: {datetime.now()}*\n")

    print(f"[OK] Report saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Trend Following Grid Search')
    parser.add_argument('--symbol', type=str, default='EURUSD')
    parser.add_argument('--start', type=str, default='2021-01-01')
    parser.add_argument('--end', type=str, default='2024-12-31')
    parser.add_argument('--config', type=str, default='config/config.yaml')
    parser.add_argument('--max_runs', type=int, default=200)
    parser.add_argument('--random_sample', type=str, default='true')

    args = parser.parse_args()

    random_sample = args.random_sample.lower() == 'true'

    print(f"\n{'='*60}")
    print("TREND FOLLOWING GRID SEARCH")
    print(f"{'='*60}\n")
    print(f"Symbol: {args.symbol}")
    print(f"Period: {args.start} to {args.end}")
    print(f"Max Runs: {args.max_runs}")
    print(f"Random Sample: {random_sample}\n")

    # Load H1 bars
    ltf_file = f"data/bars/{args.symbol.lower()}_h1_bars.csv"
    if not os.path.exists(ltf_file):
        print(f"✗ H1 bars not found: {ltf_file}")
        return

    ltf_df = pd.read_csv(ltf_file, index_col='timestamp', parse_dates=True)
    ltf_df = ltf_df[(ltf_df.index >= args.start) & (ltf_df.index <= args.end)]
    print(f"[OK] Loaded {len(ltf_df)} H1 bars")

    # Build H4
    htf_df = ltf_df.resample('4h').agg({
        'open_bid': 'first', 'high_bid': 'max', 'low_bid': 'min', 'close_bid': 'last',
        'open_ask': 'first', 'high_ask': 'max', 'low_ask': 'min', 'close_ask': 'last'
    }).dropna()
    print(f"[OK] Built {len(htf_df)} H4 bars\n")

    # Split train/test
    train_end = '2022-12-31'
    test_start = '2023-01-01'

    ltf_train = ltf_df[ltf_df.index <= train_end]
    ltf_test = ltf_df[ltf_df.index >= test_start]

    htf_train = htf_df[htf_df.index <= train_end]
    htf_test = htf_df[htf_df.index >= test_start]

    print(f"Train: {ltf_train.index[0]} to {ltf_train.index[-1]} ({len(ltf_train)} bars)")
    print(f"Test:  {ltf_test.index[0]} to {ltf_test.index[-1]} ({len(ltf_test)} bars)\n")

    # Generate grid
    print("Generating parameter grid...")
    all_combos = generate_param_grid()
    print(f"[OK] Total combinations: {len(all_combos)}")

    # Sample
    selected = sample_grid(all_combos, args.max_runs, random_sample)
    print(f"[OK] Selected: {len(selected)} configurations\n")

    # Run grid
    print(f"{'='*60}")
    print("Running Grid Search...")
    print(f"{'='*60}\n")

    results = []
    for i, params in enumerate(selected, 1):
        print(f"[{i}/{len(selected)}] Testing config... ", end='', flush=True)

        try:
            result = run_single_config(args.symbol, ltf_train, htf_train, ltf_test, htf_test, params)
            results.append(result)
            print(f"[OK] Test: {result['test_trades']} trades, {result['test_expectancy_R']:.3f}R")
        except Exception as e:
            print(f"[X] Error: {e}")

    # Create DataFrame
    results_df = pd.DataFrame(results)

    # Save CSV
    output_csv = 'data/outputs/trend_grid_results.csv'
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    results_df.to_csv(output_csv, index=False)
    print(f"\n[OK] Saved results to {output_csv}")

    # Generate plots
    generate_plots(results_df)

    # Generate report
    generate_report(results_df)

    print(f"\n{'='*60}")
    print("GRID SEARCH COMPLETE!")
    print(f"{'='*60}\n")

    # Quick summary
    positive = results_df[results_df['test_expectancy_R'] > 0]
    print(f"Summary:")
    print(f"  Tested: {len(results_df)} configurations")
    print(f"  Positive Test Expectancy: {len(positive)} ({len(positive)/len(results_df)*100:.1f}%)")
    print(f"  Best Test Expectancy: {results_df['test_expectancy_R'].max():.3f}R")
    print(f"  Mean Test Expectancy: {results_df['test_expectancy_R'].mean():.3f}R")


if __name__ == "__main__":
    main()

