"""
Filter Decomposition Analysis
Analyze impact of each filter on trade frequency and edge
"""
import sys
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import copy

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.utils.config import load_config
from src.backtest.engine_enhanced import run_enhanced_backtest
from src.backtest.metrics import compute_metrics, add_R_column


def run_strategy_variant(variant_name, config, bars_df, initial_balance):
    """
    Run a specific strategy variant.

    Variants:
    - BOS_ONLY: Only BOS signal, no RR filter, no HTF filter
    - BOS_RR: BOS + minimum RR requirement
    - BOS_HTF: BOS + HTF location filter
    - FULL: All filters (BOS + HTF + location thresholds)
    """

    print(f"\n{'='*60}")
    print(f"Running: {variant_name}")
    print(f"{'='*60}")

    # Configure filters based on variant
    config_copy = copy.deepcopy(config)
    config_copy['strategy']['strategy_mode'] = variant_name

    if variant_name == 'BOS_ONLY':
        enable_filters = {
            'use_bos_filter': True,
            'use_htf_location_filter': False,
            'use_session_filter': False,
            'use_partial_tp': False
        }
    elif variant_name == 'BOS_RR':
        enable_filters = {
            'use_bos_filter': True,
            'use_htf_location_filter': False,
            'use_session_filter': False,
            'use_partial_tp': False
        }
    elif variant_name == 'BOS_HTF':
        enable_filters = {
            'use_bos_filter': True,
            'use_htf_location_filter': True,
            'use_session_filter': False,
            'use_partial_tp': False
        }
    elif variant_name == 'FULL':
        enable_filters = {
            'use_bos_filter': True,
            'use_htf_location_filter': True,
            'use_session_filter': False,
            'use_partial_tp': False
        }
    else:
        raise ValueError(f"Unknown variant: {variant_name}")

    # Run backtest
    trades_df = run_enhanced_backtest(
        config=config_copy,
        bars_df=bars_df,
        output_suffix=f"_decomp_{variant_name.lower()}",
        enable_filters=enable_filters
    )

    # Calculate metrics
    if trades_df is None or len(trades_df) == 0:
        return {
            'variant': variant_name,
            'total_trades': 0,
            'win_rate': 0.0,
            'expectancy_R': 0.0,
            'profit_factor': 0.0,
            'max_dd_pct': 0.0,
            'max_losing_streak': 0,
            'avg_R': 0.0,
            'median_R': 0.0,
            'trades_per_year': 0.0
        }

    trades_df = add_R_column(trades_df)
    metrics = compute_metrics(trades_df, initial_balance)

    # Calculate trades per year
    date_range = (trades_df['exit_time'].max() - trades_df['entry_time'].min()).days
    years = date_range / 365.25
    trades_per_year = len(trades_df) / years if years > 0 else 0

    result = {
        'variant': variant_name,
        'total_trades': len(trades_df),
        'win_rate': metrics['win_rate'],
        'expectancy_R': metrics['expectancy_R'],
        'profit_factor': metrics['profit_factor'],
        'max_dd_pct': metrics['max_dd_percent'],
        'max_losing_streak': metrics['max_losing_streak'],
        'avg_R': trades_df['R'].mean(),
        'median_R': trades_df['R'].median(),
        'trades_per_year': trades_per_year,
        'trades_df': trades_df
    }

    print(f"\n✓ {variant_name} Complete:")
    print(f"  Total Trades: {result['total_trades']}")
    print(f"  Win Rate: {result['win_rate']:.2f}%")
    print(f"  Expectancy: {result['expectancy_R']:.3f}R")
    print(f"  Trades/Year: {result['trades_per_year']:.1f}")

    return result


def generate_frequency_vs_expectancy_plot(results, output_path):
    """Generate scatter plot of frequency vs expectancy."""

    plt.figure(figsize=(10, 6))

    for result in results:
        plt.scatter(
            result['trades_per_year'],
            result['expectancy_R'],
            s=200,
            alpha=0.7,
            label=result['variant']
        )

        # Add label
        plt.annotate(
            result['variant'],
            (result['trades_per_year'], result['expectancy_R']),
            textcoords="offset points",
            xytext=(0, 10),
            ha='center',
            fontsize=9
        )

    plt.axhline(y=0, color='red', linestyle='--', alpha=0.5, label='Breakeven')
    plt.xlabel('Trades per Year', fontsize=12)
    plt.ylabel('Expectancy (R)', fontsize=12)
    plt.title('Trade Frequency vs Expectancy by Strategy Variant', fontsize=14, fontweight='bold')
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()

    print(f"✓ Saved: {output_path}")


def generate_equity_overlay_plot(results, initial_balance, output_path):
    """Generate overlaid equity curves for all variants."""

    plt.figure(figsize=(14, 8))

    for result in results:
        if result['total_trades'] == 0:
            continue

        trades_df = result['trades_df']

        # Calculate equity curve
        equity = [initial_balance]
        for _, trade in trades_df.iterrows():
            equity.append(equity[-1] + trade['pnl'])

        # Plot
        plt.plot(
            range(len(equity)),
            equity,
            label=result['variant'],
            linewidth=2,
            alpha=0.8
        )

    plt.axhline(y=initial_balance, color='gray', linestyle='--', alpha=0.5, label='Initial Balance')
    plt.xlabel('Trade Number', fontsize=12)
    plt.ylabel('Equity ($)', fontsize=12)
    plt.title('Equity Curves - All Strategy Variants', fontsize=14, fontweight='bold')
    plt.legend(loc='best')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()

    print(f"✓ Saved: {output_path}")


def generate_decomposition_report(results, output_path):
    """Generate comprehensive markdown report."""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Filter Decomposition Analysis Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("**Objective:** Understand impact of each filter on trade frequency and edge\n\n")

        f.write("---\n\n")

        # Comparative Table
        f.write("## Comparative Results\n\n")

        f.write("| Variant | Trades | Trades/Year | Win Rate (%) | Expectancy (R) | PF | Max DD (%) | Avg R | Median R |\n")
        f.write("|---------|--------|-------------|--------------|----------------|-----|-----------|-------|----------|\n")

        for r in results:
            f.write(f"| {r['variant']} | {r['total_trades']} | {r['trades_per_year']:.1f} | {r['win_rate']:.2f} | {r['expectancy_R']:.3f} | {r['profit_factor']:.2f} | {r['max_dd_pct']:.2f} | {r['avg_R']:.3f} | {r['median_R']:.3f} |\n")

        f.write("\n")

        # Signal Reduction Funnel
        f.write("## Signal Reduction Funnel\n\n")

        f.write("Shows how many signals survive each filter:\n\n")

        bos_only = next((r for r in results if r['variant'] == 'BOS_ONLY'), None)
        bos_rr = next((r for r in results if r['variant'] == 'BOS_RR'), None)
        bos_htf = next((r for r in results if r['variant'] == 'BOS_HTF'), None)
        full = next((r for r in results if r['variant'] == 'FULL'), None)

        if bos_only:
            f.write(f"1. **BOS Signals Detected:** {bos_only['total_trades']} trades\n")

        if bos_rr:
            reduction = ((bos_only['total_trades'] - bos_rr['total_trades']) / bos_only['total_trades'] * 100) if bos_only['total_trades'] > 0 else 0
            f.write(f"2. **After RR Filter:** {bos_rr['total_trades']} trades (-{reduction:.1f}%)\n")

        if bos_htf:
            reduction = ((bos_only['total_trades'] - bos_htf['total_trades']) / bos_only['total_trades'] * 100) if bos_only['total_trades'] > 0 else 0
            f.write(f"3. **After HTF Location Filter:** {bos_htf['total_trades']} trades (-{reduction:.1f}%)\n")

        if full:
            reduction = ((bos_only['total_trades'] - full['total_trades']) / bos_only['total_trades'] * 100) if bos_only['total_trades'] > 0 else 0
            f.write(f"4. **Final (FULL Strategy):** {full['total_trades']} trades (-{reduction:.1f}%)\n")

        f.write("\n")

        # Edge vs Frequency Analysis
        f.write("## Edge vs Frequency Analysis\n\n")

        f.write("### Key Findings:\n\n")

        # Best expectancy
        best_exp = max(results, key=lambda x: x['expectancy_R'])
        f.write(f"- **Highest Expectancy:** {best_exp['variant']} ({best_exp['expectancy_R']:.3f}R)\n")

        # Most trades
        most_trades = max(results, key=lambda x: x['total_trades'])
        f.write(f"- **Most Trades:** {most_trades['variant']} ({most_trades['total_trades']} trades)\n")

        # Best balance (expectancy × frequency)
        for r in results:
            r['edge_score'] = r['expectancy_R'] * r['trades_per_year']

        best_balance = max(results, key=lambda x: x['edge_score'])
        f.write(f"- **Best Edge×Frequency Balance:** {best_balance['variant']} (score: {best_balance['edge_score']:.2f})\n")

        f.write("\n")

        # Filter Impact
        f.write("### Filter Impact:\n\n")

        if bos_only and full:
            trade_reduction = ((bos_only['total_trades'] - full['total_trades']) / bos_only['total_trades'] * 100)
            exp_improvement = full['expectancy_R'] - bos_only['expectancy_R']

            f.write(f"**All Filters Combined:**\n")
            f.write(f"- Trade Reduction: {trade_reduction:.1f}%\n")
            f.write(f"- Expectancy Change: {exp_improvement:+.3f}R\n")
            f.write(f"- Worth it? {'✅ YES' if exp_improvement > 0 else '❌ NO'}\n\n")

        if bos_only and bos_htf:
            trade_reduction = ((bos_only['total_trades'] - bos_htf['total_trades']) / bos_only['total_trades'] * 100)
            exp_improvement = bos_htf['expectancy_R'] - bos_only['expectancy_R']

            f.write(f"**HTF Filter Alone:**\n")
            f.write(f"- Trade Reduction: {trade_reduction:.1f}%\n")
            f.write(f"- Expectancy Change: {exp_improvement:+.3f}R\n")
            f.write(f"- Worth it? {'✅ YES' if exp_improvement > 0 else '❌ NO'}\n\n")

        # Recommendations
        f.write("## Recommendations\n\n")

        if best_exp['expectancy_R'] > 0.20:
            f.write(f"✅ **Use {best_exp['variant']}** for maximum edge\n\n")
        elif best_balance['edge_score'] > 2.0:
            f.write(f"✅ **Use {best_balance['variant']}** for best balance of edge and frequency\n\n")
        else:
            f.write(f"⚠️ All variants show marginal edge. Consider further optimization.\n\n")

        # Charts
        f.write("## Visual Analysis\n\n")
        f.write("See generated charts:\n")
        f.write("- `frequency_vs_expectancy.png` - Trade-off between frequency and expectancy\n")
        f.write("- `equity_overlay.png` - Equity curves comparison\n\n")

        f.write("---\n\n")
        f.write(f"*Report generated: {datetime.now()}*\n")


def save_csv_summary(results, output_path):
    """Save results to CSV."""

    data = []
    for r in results:
        data.append({
            'strategy_mode': r['variant'],
            'total_trades': r['total_trades'],
            'win_rate': r['win_rate'],
            'expectancy_R': r['expectancy_R'],
            'profit_factor': r['profit_factor'],
            'max_dd_pct': r['max_dd_pct'],
            'max_losing_streak': r['max_losing_streak'],
            'avg_R': r['avg_R'],
            'median_R': r['median_R'],
            'trades_per_year': r['trades_per_year']
        })

    df = pd.DataFrame(data)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)

    print(f"✓ Saved: {output_path}")


def main():
    print(f"\n{'='*60}")
    print("FILTER DECOMPOSITION ANALYSIS")
    print(f"{'='*60}\n")

    # Load configuration
    config = load_config()
    initial_balance = config['execution']['initial_balance']

    # Load H1 bars
    symbol = config['data']['symbol']
    bars_file = os.path.join(config['data']['bars_dir'], f"{symbol}_h1_bars.csv")

    if not os.path.exists(bars_file):
        print(f"✗ H1 bars not found: {bars_file}")
        return

    print(f"Loading H1 bars...")
    bars_df = pd.read_csv(bars_file, index_col='timestamp', parse_dates=True)

    # Filter to 2021-2024
    bars_df = bars_df[(bars_df.index >= '2021-01-01') & (bars_df.index <= '2024-12-31')]

    print(f"✓ Loaded {len(bars_df)} H1 bars")
    print(f"  Date range: {bars_df.index[0]} to {bars_df.index[-1]}\n")

    # Run all variants
    variants = ['BOS_ONLY', 'BOS_RR', 'BOS_HTF', 'FULL']
    results = []

    for variant in variants:
        result = run_strategy_variant(variant, config, bars_df, initial_balance)
        results.append(result)

    # Generate outputs
    print(f"\n{'='*60}")
    print("Generating Outputs...")
    print(f"{'='*60}\n")

    # CSV
    save_csv_summary(results, 'data/outputs/filter_decomposition.csv')

    # Report
    generate_decomposition_report(results, 'reports/filter_decomposition.md')

    # Charts
    generate_frequency_vs_expectancy_plot(results, 'reports/frequency_vs_expectancy.png')
    generate_equity_overlay_plot(results, initial_balance, 'reports/equity_overlay.png')

    print(f"\n{'='*60}")
    print("ANALYSIS COMPLETE!")
    print(f"{'='*60}\n")

    print("Summary:")
    print(f"{'Variant':<15} {'Trades':>8} {'T/Year':>8} {'Exp(R)':>8} {'Status':>10}")
    print("-" * 60)
    for r in results:
        status = "✅" if r['expectancy_R'] > 0 else "❌"
        print(f"{r['variant']:<15} {r['total_trades']:>8} {r['trades_per_year']:>8.1f} {r['expectancy_R']:>8.3f} {status:>10}")


if __name__ == "__main__":
    main()

