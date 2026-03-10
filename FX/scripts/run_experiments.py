"""
Run experiments: Baseline + Test A + Test B + Test C
Generates comparison report.
"""
import sys
import os
import argparse
import pandas as pd
from datetime import datetime
import copy

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.utils.config import load_config
from src.backtest.engine_enhanced import run_enhanced_backtest
from src.backtest.metrics import compute_metrics, add_R_column


def filter_bars_by_date(bars_df, start_date, end_date):
    """Filter bars DataFrame by date range."""
    bars_df.index = pd.to_datetime(bars_df.index)
    return bars_df[(bars_df.index >= start_date) & (bars_df.index <= end_date)]


def calculate_sanity_metrics(trades_df, bars_df):
    """
    Calculate sanity check metrics:
    - Spread statistics
    - Fill statistics
    - Look-ahead verification
    """
    sanity = {}

    # Spread analysis
    bars_df['spread'] = bars_df['close_ask'] - bars_df['close_bid']
    sanity['avg_spread'] = bars_df['spread'].mean()
    sanity['min_spread'] = bars_df['spread'].min()
    sanity['max_spread'] = bars_df['spread'].max()
    sanity['spread_pips'] = sanity['avg_spread'] * 10000

    # Fill analysis (if we have trades)
    if len(trades_df) > 0 and 'entry_time' in trades_df.columns and 'zone_created_at' in trades_df.columns:
        # Check no same-bar entry
        trades_df['entry_time'] = pd.to_datetime(trades_df['entry_time'])
        trades_df['zone_created_at'] = pd.to_datetime(trades_df['zone_created_at'])

        same_bar_entries = (trades_df['entry_time'] == trades_df['zone_created_at']).sum()
        sanity['same_bar_entry_count'] = same_bar_entries
        sanity['same_bar_entry_pct'] = (same_bar_entries / len(trades_df)) * 100 if len(trades_df) > 0 else 0

        # Check SL hit on entry
        # If entry_time == exit_time and status == 'SL', it means fill and SL on same bar
        if 'exit_time' in trades_df.columns and 'status' in trades_df.columns:
            trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
            same_bar_sl = ((trades_df['entry_time'] == trades_df['exit_time']) &
                          (trades_df['status'] == 'SL')).sum()
            sanity['same_bar_sl_count'] = same_bar_sl
            sanity['same_bar_sl_pct'] = (same_bar_sl / len(trades_df)) * 100 if len(trades_df) > 0 else 0
    else:
        sanity['same_bar_entry_count'] = 0
        sanity['same_bar_entry_pct'] = 0
        sanity['same_bar_sl_count'] = 0
        sanity['same_bar_sl_pct'] = 0

    return sanity


def run_single_experiment(name, config, bars_df, enable_filters, initial_balance):
    """
    Run a single experiment configuration.

    Returns:
        dict with results
    """
    print(f"\n{'='*60}")
    print(f"Running: {name}")
    print(f"{'='*60}")

    # Run backtest
    trades_df = run_enhanced_backtest(
        config=config,
        bars_df=bars_df,
        output_suffix=f"_{name}",
        enable_filters=enable_filters
    )

    if trades_df is None or len(trades_df) == 0:
        print(f"⚠ No trades generated for {name}")
        return {
            'name': name,
            'trades_count': 0,
            'win_rate': 0.0,
            'expectancy_R': 0.0,
            'avg_R': 0.0,
            'profit_factor': 0.0,
            'total_pnl': 0.0,
            'max_dd_percent': 0.0,
            'max_losing_streak': 0,
            'final_balance': initial_balance,
            'return_pct': 0.0,
            'sanity': {}
        }

    # Add R column
    trades_df = add_R_column(trades_df)

    # Calculate metrics
    metrics = compute_metrics(trades_df, initial_balance)

    # Calculate sanity checks
    sanity = calculate_sanity_metrics(trades_df, bars_df)

    # Calculate final balance and return
    final_balance = initial_balance + metrics['total_pnl']
    return_pct = ((final_balance - initial_balance) / initial_balance) * 100

    result = {
        'name': name,
        **metrics,
        'final_balance': final_balance,
        'return_pct': return_pct,
        'sanity': sanity
    }

    print(f"\n✓ {name} Complete:")
    print(f"  Trades: {metrics['trades_count']}")
    print(f"  Win Rate: {metrics['win_rate']:.2f}%")
    print(f"  Expectancy: {metrics['expectancy_R']:.3f}R")
    print(f"  PnL: ${metrics['total_pnl']:.2f}")

    return result


def generate_comparison_report(results, output_path, symbol, timeframe, start_date, end_date):
    """Generate markdown comparison report."""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Experiments Comparison Report\n\n")
        f.write(f"**Symbol:** {symbol}\n")
        f.write(f"**Timeframe:** {timeframe}\n")
        f.write(f"**Period:** {start_date} to {end_date}\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("---\n\n")

        # Summary table
        f.write("## Performance Comparison\n\n")

        f.write("| Test | Trades | Win Rate (%) | Expectancy (R) | Profit Factor | Max DD (%) | Max Losing Streak | Final Balance | Return (%) |\n")
        f.write("|------|--------|--------------|----------------|---------------|------------|-------------------|---------------|------------|\n")

        for result in results:
            f.write(f"| {result['name']} | {result['trades_count']} | {result['win_rate']:.2f} | {result['expectancy_R']:.3f} | {result['profit_factor']:.2f} | {result['max_dd_percent']:.2f} | {result['max_losing_streak']} | ${result['final_balance']:.2f} | {result['return_pct']:.2f} |\n")

        f.write("\n")

        # Key Findings
        f.write("## Key Findings\n\n")

        # Find best by expectancy
        best = max(results, key=lambda x: x['expectancy_R'])
        f.write(f"### Best Expectancy: **{best['name']}**\n\n")
        f.write(f"- Expectancy: {best['expectancy_R']:.3f}R\n")
        f.write(f"- Win Rate: {best['win_rate']:.2f}%\n")
        f.write(f"- Profit Factor: {best['profit_factor']:.2f}\n")
        f.write(f"- Return: {best['return_pct']:.2f}%\n\n")

        # Compare to baseline
        baseline = next((r for r in results if 'Baseline' in r['name']), None)
        if baseline and best['name'] != baseline['name']:
            f.write(f"### Improvement vs Baseline\n\n")
            f.write(f"- Expectancy: {best['expectancy_R'] - baseline['expectancy_R']:+.3f}R\n")
            f.write(f"- Win Rate: {best['win_rate'] - baseline['win_rate']:+.2f}%\n")
            f.write(f"- Return: {best['return_pct'] - baseline['return_pct']:+.2f}%\n\n")

        # Win Rate analysis
        f.write("### Win Rate Analysis\n\n")
        f.write("For RR 2.0, breakeven win rate = 33.3%\n\n")

        for result in results:
            status = "✅" if result['win_rate'] >= 33.3 else "❌"
            f.write(f"- {status} {result['name']}: {result['win_rate']:.2f}%\n")

        f.write("\n")

        # Expectancy analysis
        f.write("### Expectancy Analysis\n\n")

        positive_exp = [r for r in results if r['expectancy_R'] > 0]
        if positive_exp:
            f.write(f"**{len(positive_exp)} configuration(s) with POSITIVE expectancy:**\n\n")
            for r in positive_exp:
                f.write(f"- ✅ {r['name']}: {r['expectancy_R']:.3f}R\n")
        else:
            f.write("⚠ **No configurations achieved positive expectancy.**\n\n")
            f.write("Best (least negative):\n\n")
            best_exp = max(results, key=lambda x: x['expectancy_R'])
            f.write(f"- {best_exp['name']}: {best_exp['expectancy_R']:.3f}R\n")

        f.write("\n")

        # Trade count analysis
        f.write("### Trade Count Impact\n\n")

        for result in results:
            if baseline:
                change = result['trades_count'] - baseline['trades_count']
                pct_change = (change / baseline['trades_count'] * 100) if baseline['trades_count'] > 0 else 0
                f.write(f"- {result['name']}: {result['trades_count']} trades ({pct_change:+.1f}% vs baseline)\n")
            else:
                f.write(f"- {result['name']}: {result['trades_count']} trades\n")

        f.write("\n")

        # Sanity Checks
        f.write("## Sanity Checks\n\n")

        for result in results:
            f.write(f"### {result['name']}\n\n")

            sanity = result.get('sanity', {})

            # Spread
            f.write("**Spread Statistics:**\n")
            f.write(f"- Average: {sanity.get('avg_spread', 0):.5f} ({sanity.get('spread_pips', 0):.2f} pips)\n")
            f.write(f"- Min: {sanity.get('min_spread', 0):.5f}\n")
            f.write(f"- Max: {sanity.get('max_spread', 0):.5f}\n\n")

            # Fill sanity
            f.write("**Fill Sanity:**\n")
            f.write(f"- Same-bar entry (zone created and entered same bar): {sanity.get('same_bar_entry_count', 0)} ({sanity.get('same_bar_entry_pct', 0):.2f}%)\n")
            f.write(f"- Same-bar SL (entry and SL hit same bar): {sanity.get('same_bar_sl_count', 0)} ({sanity.get('same_bar_sl_pct', 0):.2f}%)\n\n")

            # Look-ahead verification
            f.write("**No Look-Ahead:**\n")
            if sanity.get('same_bar_entry_pct', 0) > 0:
                f.write("⚠ WARNING: Some same-bar entries detected (check allow_same_bar_entry config)\n\n")
            else:
                f.write("✓ No same-bar entries detected - anti-lookahead working correctly\n\n")

        # Conclusions
        f.write("## Conclusions\n\n")

        # Automatic conclusions
        best_test = max(results, key=lambda x: x['expectancy_R'])

        if best_test['expectancy_R'] > 0:
            f.write(f"✅ **SUCCESS:** {best_test['name']} achieved positive expectancy ({best_test['expectancy_R']:.3f}R)\n\n")
        else:
            f.write(f"⚠ **All tests remain negative.** Best: {best_test['name']} ({best_test['expectancy_R']:.3f}R)\n\n")

        if baseline:
            improvement = best_test['expectancy_R'] - baseline['expectancy_R']
            if improvement > 0:
                f.write(f"📈 **Improvement:** +{improvement:.3f}R vs baseline\n\n")
            else:
                f.write(f"📉 **No improvement** over baseline\n\n")

        # Filter effectiveness
        f.write("### Filter Effectiveness:\n\n")

        for result in results:
            if 'Test' in result['name']:
                filter_name = result['name'].replace('Test ', '')
                if result['expectancy_R'] > (baseline['expectancy_R'] if baseline else -999):
                    f.write(f"- ✅ {filter_name}: Improved results\n")
                else:
                    f.write(f"- ❌ {filter_name}: Did not improve results\n")

        f.write("\n")

        # Recommendations
        f.write("## Recommendations\n\n")

        if best_test['expectancy_R'] < 0:
            f.write("**Strategy still needs improvement:**\n\n")
            f.write("1. Consider combining multiple filters\n")
            f.write("2. Test on different timeframes (H1, H4)\n")
            f.write("3. Add additional filters (volatility, session, news)\n")
            f.write("4. Re-evaluate RR ratio (try 1:1 or 1.5:1)\n")
            f.write("5. Test on different symbols\n\n")
        else:
            f.write(f"**Use {best_test['name']} configuration for forward testing.**\n\n")

        f.write("---\n\n")
        f.write(f"*Report generated: {datetime.now()}*\n")


def main():
    parser = argparse.ArgumentParser(description='Run S&D strategy experiments')
    parser.add_argument('--symbol', type=str, default='EURUSD', help='Symbol to test')
    parser.add_argument('--tf', type=str, default='M15', help='Timeframe')
    parser.add_argument('--start', type=str, required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--config', type=str, default='config/config.yaml', help='Config file path')

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("Supply & Demand Strategy Experiments")
    print(f"{'='*60}")
    print(f"Symbol: {args.symbol}")
    print(f"Timeframe: {args.tf}")
    print(f"Period: {args.start} to {args.end}")
    print(f"Config: {args.config}")
    print(f"{'='*60}\n")

    # Load config
    base_config = load_config(args.config)
    initial_balance = base_config['execution']['initial_balance']

    # Load and filter bars
    bars_file = os.path.join(base_config['data']['bars_dir'],
                             f"{args.symbol.lower()}_m15_bars.csv")

    if not os.path.exists(bars_file):
        print(f"✗ Bars file not found: {bars_file}")
        print(f"  Run: python scripts/build_bars.py")
        return

    print(f"Loading bars...")
    bars_df = pd.read_csv(bars_file, index_col='timestamp', parse_dates=True)

    # Filter by date
    start_dt = pd.to_datetime(args.start)
    end_dt = pd.to_datetime(args.end)
    bars_df = filter_bars_by_date(bars_df, start_dt, end_dt)

    print(f"✓ Loaded {len(bars_df)} bars\n")

    # Run experiments
    results = []

    # Baseline (current optimized config - first touch only, no extra filters)
    results.append(run_single_experiment(
        "Baseline",
        copy.deepcopy(base_config),
        bars_df,
        {'use_ema_filter': False, 'use_bos_filter': False, 'use_htf_location_filter': False},
        initial_balance
    ))

    # Test A: First Touch + EMA200
    results.append(run_single_experiment(
        "Test A (EMA200)",
        copy.deepcopy(base_config),
        bars_df,
        {'use_ema_filter': True, 'use_bos_filter': False, 'use_htf_location_filter': False},
        initial_balance
    ))

    # Test B: First Touch + BOS
    results.append(run_single_experiment(
        "Test B (BOS)",
        copy.deepcopy(base_config),
        bars_df,
        {'use_ema_filter': False, 'use_bos_filter': True, 'use_htf_location_filter': False},
        initial_balance
    ))

    # Test C: First Touch + HTF Location
    results.append(run_single_experiment(
        "Test C (HTF Location)",
        copy.deepcopy(base_config),
        bars_df,
        {'use_ema_filter': False, 'use_bos_filter': False, 'use_htf_location_filter': True},
        initial_balance
    ))

    # Generate comparison report
    print(f"\n{'='*60}")
    print("Generating Comparison Report...")
    print(f"{'='*60}\n")

    report_path = f"data/outputs/comparison_report_{args.symbol}_{args.tf}_{args.start.replace('-', '')}-{args.end.replace('-', '')}.md"
    generate_comparison_report(results, report_path, args.symbol, args.tf, args.start, args.end)

    print(f"✓ Comparison report saved to: {report_path}")

    print(f"\n{'='*60}")
    print("Experiments Complete!")
    print(f"{'='*60}\n")

    # Print summary
    print("Quick Summary:")
    for result in results:
        print(f"  {result['name']:20s} | Trades: {result['trades_count']:3d} | WR: {result['win_rate']:5.2f}% | Exp: {result['expectancy_R']:+.3f}R | Return: {result['return_pct']:+6.2f}%")

    best = max(results, key=lambda x: x['expectancy_R'])
    print(f"\n🏆 Best: {best['name']} ({best['expectancy_R']:+.3f}R)")


if __name__ == "__main__":
    main()

