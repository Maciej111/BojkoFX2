"""
Full Run TOP 3 Configurations from Grid Search
Runs backtest on full period 2021-2024 for best configs
"""
import sys
import os
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import hashlib

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.strategies.trend_following_v1 import run_trend_backtest
from src.backtest.metrics import compute_yearly_metrics, compute_metrics, add_R_column


def load_top_n_configs(grid_results_path, top_n=3):
    """
    Load top N configurations from grid search results.

    Args:
        grid_results_path: Path to trend_grid_results.csv
        top_n: Number of top configs to load

    Returns:
        List of config dicts
    """

    if not os.path.exists(grid_results_path):
        print(f"[!] Grid results not found: {grid_results_path}")
        return []

    # Load results
    results_df = pd.read_csv(grid_results_path)

    # Sort by test_expectancy_R descending
    results_df = results_df.sort_values('test_expectancy_R', ascending=False)

    # Take top N
    top_configs = []

    for i in range(min(top_n, len(results_df))):
        row = results_df.iloc[i]

        config = {
            'entry_offset_atr_mult': float(row['entry_offset_atr']),
            'pullback_max_bars': int(row['pullback_max_bars']),
            'risk_reward': float(row['risk_reward']),
            'sl_anchor': str(row['sl_anchor']),
            'sl_buffer_atr_mult': float(row['sl_buffer_atr']),
            # Fixed params
            'pivot_lookback_ltf': 3,
            'pivot_lookback_htf': 5,
            'confirmation_bars': 1,
            'require_close_break': True
        }

        top_configs.append(config)

        print(f"[OK] Loaded config #{i+1}: entry_offset={config['entry_offset_atr_mult']}, "
              f"pullback={config['pullback_max_bars']}, RR={config['risk_reward']}")

    return top_configs


def compute_params_hash(params):
    """Generate short hash for config params."""
    param_str = f"{params['entry_offset_atr_mult']:.1f}_{params['pullback_max_bars']}_" \
                f"{params['risk_reward']:.1f}_{params['sl_anchor'][:4]}_{params['sl_buffer_atr_mult']:.1f}"
    return hashlib.md5(param_str.encode()).hexdigest()[:8]


def run_single_config_full(rank, params, symbol, ltf_df, htf_df, initial_balance=10000):
    """
    Run backtest for single config on full period.

    Returns:
        (trades_df, metrics_dict)
    """

    print(f"\n[{rank}] Running config #{rank}...")
    print(f"  Parameters: {params}")

    # Run backtest
    trades_df, metrics = run_trend_backtest(symbol, ltf_df, htf_df, params, initial_balance)

    if len(trades_df) == 0:
        print(f"  [!] No trades generated")
        return trades_df, {}

    # Add R column if needed
    trades_df = add_R_column(trades_df)

    # Compute overall metrics
    overall_metrics = compute_metrics(trades_df, initial_balance)

    # Compute yearly metrics
    yearly_data = compute_yearly_metrics(trades_df, initial_balance)

    # Combine
    result = {
        'params': params,
        'params_hash': compute_params_hash(params),
        'overall': overall_metrics,
        'yearly': yearly_data['yearly_metrics'],
        'maxDD_pct': yearly_data['overall_maxDD_pct'],
        'maxDD_usd': yearly_data['overall_maxDD_usd']
    }

    print(f"  [OK] Trades: {len(trades_df)}, Overall Exp: {overall_metrics['expectancy_R']:.3f}R, "
          f"MaxDD: {yearly_data['overall_maxDD_pct']:.1f}%")

    return trades_df, result


def save_results_csv(results, output_path):
    """Save results to CSV."""

    rows = []

    for rank, result in enumerate(results, 1):
        if not result:
            continue

        params = result['params']
        overall = result['overall']
        yearly = result['yearly']

        row = {
            'rank': rank,
            'params_hash': result['params_hash'],
            'entry_offset_atr_mult': params['entry_offset_atr_mult'],
            'pullback_max_bars': params['pullback_max_bars'],
            'risk_reward': params['risk_reward'],
            'sl_anchor': params['sl_anchor'],
            'sl_buffer_atr_mult': params['sl_buffer_atr_mult'],
            'overall_trades': overall['trades_count'],
            'overall_expectancy_R': overall['expectancy_R'],
            'overall_win_rate': overall['win_rate'],
            'overall_profit_factor': overall['profit_factor'],
            'overall_maxDD_pct': result['maxDD_pct'],
            'overall_maxDD_usd': result['maxDD_usd'],
            'overall_max_losing_streak': overall['max_losing_streak']
        }

        # Add per-year data
        for year in [2021, 2022, 2023, 2024]:
            if year in yearly:
                row[f'trades_{year}'] = yearly[year]['trades']
                row[f'expR_{year}'] = yearly[year]['expectancy_R']
            else:
                row[f'trades_{year}'] = 0
                row[f'expR_{year}'] = 0.0

        rows.append(row)

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)

    print(f"[OK] Saved CSV: {output_path}")


def generate_markdown_report(results, output_path):
    """Generate markdown report."""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w') as f:
        f.write("# Full Run TOP 3 Configurations - Summary Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Period:** 2021-01-01 to 2024-12-31 (4 years)\n\n")

        f.write("---\n\n")

        # Overall comparison table
        f.write("## Overall Performance Comparison\n\n")

        f.write("| Rank | Entry Offset | Pullback | RR | SL Anchor | SL Buffer | Trades | Exp(R) | WR(%) | PF | MaxDD(%) |\n")
        f.write("|------|--------------|----------|-----|-----------|-----------|--------|--------|-------|-----|----------|\n")

        for rank, result in enumerate(results, 1):
            if not result:
                continue

            p = result['params']
            o = result['overall']

            f.write(f"| {rank} | {p['entry_offset_atr_mult']:.1f} | {p['pullback_max_bars']} | "
                   f"{p['risk_reward']:.1f} | {p['sl_anchor'][:4]} | {p['sl_buffer_atr_mult']:.1f} | "
                   f"{o['trades_count']} | {o['expectancy_R']:.3f} | {o['win_rate']:.1f} | "
                   f"{o['profit_factor']:.2f} | {result['maxDD_pct']:.1f} |\n")

        f.write("\n---\n\n")

        # Per-year breakdown
        f.write("## Year-by-Year Performance\n\n")

        for rank, result in enumerate(results, 1):
            if not result:
                continue

            f.write(f"### Config #{rank}\n\n")

            f.write("| Year | Trades | Expectancy(R) | Status |\n")
            f.write("|------|--------|---------------|--------|\n")

            yearly = result['yearly']
            for year in [2021, 2022, 2023, 2024]:
                if year in yearly:
                    trades = yearly[year]['trades']
                    exp_r = yearly[year]['expectancy_R']
                    status = "+" if exp_r > 0 else "-"
                    f.write(f"| {year} | {trades} | {exp_r:.3f} | {status} |\n")
                else:
                    f.write(f"| {year} | 0 | 0.000 | - |\n")

            f.write("\n")

        f.write("---\n\n")

        # Year-by-year stability analysis
        f.write("## Year-by-Year Stability Analysis\n\n")

        for rank, result in enumerate(results, 1):
            if not result:
                continue

            yearly = result['yearly']
            exp_values = [yearly[y]['expectancy_R'] for y in [2021, 2022, 2023, 2024] if y in yearly]

            if len(exp_values) > 0:
                min_exp = min(exp_values)
                max_exp = max(exp_values)
                mean_exp = sum(exp_values) / len(exp_values)
                positive_years = sum(1 for e in exp_values if e > 0)

                f.write(f"**Config #{rank}:**\n")
                f.write(f"- Min Expectancy: {min_exp:.3f}R\n")
                f.write(f"- Max Expectancy: {max_exp:.3f}R\n")
                f.write(f"- Mean Expectancy: {mean_exp:.3f}R\n")
                f.write(f"- Positive Years: {positive_years}/4 ({positive_years/4*100:.0f}%)\n")
                f.write(f"- Range: {max_exp - min_exp:.3f}R\n\n")

        f.write("---\n\n")

        # Recommendation
        f.write("## Recommendation\n\n")

        # Find best by overall expectancy
        best_overall = max(results, key=lambda r: r['overall']['expectancy_R'] if r else -999)

        # Find most stable (highest % positive years)
        def stability_score(r):
            if not r:
                return -999
            yearly = r['yearly']
            exp_values = [yearly[y]['expectancy_R'] for y in [2021, 2022, 2023, 2024] if y in yearly]
            if not exp_values:
                return -999
            positive = sum(1 for e in exp_values if e > 0)
            return positive / len(exp_values)

        best_stable = max(results, key=stability_score)

        best_rank = results.index(best_overall) + 1
        stable_rank = results.index(best_stable) + 1

        f.write(f"**Best Overall Performance:** Config #{best_rank}\n")
        f.write(f"- Overall Expectancy: {best_overall['overall']['expectancy_R']:.3f}R\n")
        f.write(f"- Total Trades: {best_overall['overall']['trades_count']}\n")
        f.write(f"- Max Drawdown: {best_overall['maxDD_pct']:.1f}%\n\n")

        f.write(f"**Most Stable (Positive Years):** Config #{stable_rank}\n")
        stable_yearly = best_stable['yearly']
        stable_exp_values = [stable_yearly[y]['expectancy_R'] for y in [2021, 2022, 2023, 2024] if y in stable_yearly]
        stable_positive = sum(1 for e in stable_exp_values if e > 0)
        f.write(f"- Positive Years: {stable_positive}/4\n")
        f.write(f"- Mean Expectancy: {sum(stable_exp_values)/len(stable_exp_values):.3f}R\n\n")

        if best_rank == stable_rank:
            f.write(f"[RECOMMENDED] Config #{best_rank} (Best AND Most Stable)\n\n")
        else:
            f.write(f"[CHOICE] Config #{best_rank} for performance OR Config #{stable_rank} for stability\n\n")

        f.write("---\n\n")
        f.write(f"*Report generated: {datetime.now()}*\n")

    print(f"[OK] Saved report: {output_path}")


def generate_equity_overlay_chart(all_trades, results, output_path, initial_balance=10000):
    """Generate equity curve overlay chart."""

    plt.figure(figsize=(14, 8))

    colors = ['blue', 'green', 'red']

    for rank, (trades_df, result) in enumerate(zip(all_trades, results), 1):
        if len(trades_df) == 0:
            continue

        # Sort by exit_time
        trades_sorted = trades_df.sort_values('exit_time') if 'exit_time' in trades_df.columns else trades_df

        # Build equity curve
        equity = initial_balance
        equity_curve = [equity]
        dates = [trades_sorted.iloc[0]['entry_time']]

        for idx, row in trades_sorted.iterrows():
            equity += row['pnl']
            equity_curve.append(equity)
            dates.append(row['exit_time'] if 'exit_time' in row else row['entry_time'])

        # Plot
        color = colors[(rank-1) % len(colors)]
        label = f"Config #{rank} ({result['overall']['expectancy_R']:.3f}R)"
        plt.plot(dates, equity_curve, label=label, linewidth=2, alpha=0.8, color=color)

    plt.axhline(y=initial_balance, color='gray', linestyle='--', alpha=0.5, label='Initial Balance')
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Equity ($)', fontsize=12)
    plt.title('Equity Curves - TOP 3 Configurations (2021-2024)', fontsize=14, fontweight='bold')
    plt.legend(loc='best')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=150)
    plt.close()

    print(f"[OK] Saved chart: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Full Run TOP 3 Configs')
    parser.add_argument('--symbol', type=str, default='EURUSD')
    parser.add_argument('--ltf', type=str, default='H1')
    parser.add_argument('--htf', type=str, default='H4')
    parser.add_argument('--start', type=str, default='2021-01-01')
    parser.add_argument('--end', type=str, default='2024-12-31')
    parser.add_argument('--top_n', type=int, default=3)
    parser.add_argument('--grid_results', type=str, default='data/outputs/trend_grid_results.csv')
    parser.add_argument('--config', type=str, default='config/config.yaml')

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("FULL RUN TOP 3 CONFIGURATIONS")
    print(f"{'='*60}\n")
    print(f"Symbol: {args.symbol}")
    print(f"Period: {args.start} to {args.end}")
    print(f"Top N: {args.top_n}\n")

    # Load H1 bars
    ltf_file = f"data/bars/{args.symbol.lower()}_h1_bars.csv"
    if not os.path.exists(ltf_file):
        print(f"[X] H1 bars not found: {ltf_file}")
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

    # Load top N configs
    print("Loading TOP configurations from grid search...")
    top_configs = load_top_n_configs(args.grid_results, args.top_n)

    if len(top_configs) == 0:
        print("[X] No configurations loaded")
        return

    print(f"\n[OK] Loaded {len(top_configs)} configurations\n")

    # Run backtests
    print(f"{'='*60}")
    print("Running Backtests...")
    print(f"{'='*60}")

    all_results = []
    all_trades = []

    for rank, params in enumerate(top_configs, 1):
        trades_df, result = run_single_config_full(rank, params, args.symbol, ltf_df, htf_df)

        all_results.append(result)
        all_trades.append(trades_df)

        # Save individual trades CSV
        trades_file = f"data/outputs/trades_full_{rank}_{args.symbol}_H1_2021_2024.csv"
        os.makedirs(os.path.dirname(trades_file), exist_ok=True)
        trades_df.to_csv(trades_file, index=False)
        print(f"  [OK] Saved trades: {trades_file}")

    # Generate outputs
    print(f"\n{'='*60}")
    print("Generating Reports...")
    print(f"{'='*60}\n")

    # CSV summary
    save_results_csv(all_results, 'data/outputs/full_run_top3_summary.csv')

    # Markdown report
    generate_markdown_report(all_results, 'reports/full_run_top3_summary.md')

    # Equity overlay chart
    generate_equity_overlay_chart(all_trades, all_results, 'reports/full_run_top3_equity_overlay.png')

    print(f"\n{'='*60}")
    print("FULL RUN COMPLETE!")
    print(f"{'='*60}\n")

    # Quick summary
    print("Summary:")
    for rank, result in enumerate(all_results, 1):
        if result:
            print(f"  Config #{rank}: {result['overall']['trades_count']} trades, "
                  f"{result['overall']['expectancy_R']:.3f}R, "
                  f"{result['maxDD_pct']:.1f}% DD")


if __name__ == "__main__":
    main()



