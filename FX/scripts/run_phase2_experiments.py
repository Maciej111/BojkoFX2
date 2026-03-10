"""
Phase 2 Experiments Runner
Tests: D (BOS+HTF), E (BOS+Session), F (BOS+Partial TP), Walk-Forward 2021-2024
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
from scripts.run_experiments import filter_bars_by_date, calculate_sanity_metrics


def run_phase2_experiments(symbol='EURUSD', start_date='2024-06-01', end_date='2024-12-31', config_path='config/config.yaml'):
    """
    Run Phase 2 experiments:
    - Baseline BOS (Test B from Phase 1)
    - Test D: BOS + HTF Location
    - Test E: BOS + Session (3 variants)
    - Test F: BOS + Partial TP
    """

    print(f"\n{'='*60}")
    print("PHASE 2 EXPERIMENTS")
    print(f"{'='*60}")
    print(f"Symbol: {symbol}")
    print(f"Period: {start_date} to {end_date}")
    print(f"{'='*60}\n")

    # Load config and bars
    base_config = load_config(config_path)
    initial_balance = base_config['execution']['initial_balance']

    bars_file = os.path.join(base_config['data']['bars_dir'], f"{symbol.lower()}_m15_bars.csv")

    if not os.path.exists(bars_file):
        print(f"✗ Bars file not found: {bars_file}")
        return []

    print(f"Loading bars...")
    bars_df = pd.read_csv(bars_file, index_col='timestamp', parse_dates=True)

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    bars_df = filter_bars_by_date(bars_df, start_dt, end_dt)

    print(f"✓ Loaded {len(bars_df)} bars\n")

    results = []

    # Baseline BOS (Test B from Phase 1)
    print(f"\n{'='*60}")
    print("Running: Baseline BOS (Test B)")
    print(f"{'='*60}")

    config = copy.deepcopy(base_config)
    trades_df = run_enhanced_backtest(
        config=config,
        bars_df=bars_df,
        output_suffix="_baseline_bos",
        enable_filters={'use_bos_filter': True, 'use_htf_location_filter': False,
                       'use_session_filter': False, 'use_partial_tp': False}
    )

    results.append(process_result("Baseline BOS", trades_df, bars_df, initial_balance))

    # Test D: BOS + HTF Location
    print(f"\n{'='*60}")
    print("Running: Test D (BOS + HTF Location)")
    print(f"{'='*60}")

    config = copy.deepcopy(base_config)
    trades_df = run_enhanced_backtest(
        config=config,
        bars_df=bars_df,
        output_suffix="_testD_bos_htf",
        enable_filters={'use_bos_filter': True, 'use_htf_location_filter': True,
                       'use_session_filter': False, 'use_partial_tp': False}
    )

    results.append(process_result("Test D (BOS+HTF)", trades_df, bars_df, initial_balance))

    # Test E: BOS + Session Filter (3 variants)
    for session_mode in ['london', 'ny', 'both']:
        print(f"\n{'='*60}")
        print(f"Running: Test E (BOS + Session {session_mode.upper()})")
        print(f"{'='*60}")

        config = copy.deepcopy(base_config)
        config['strategy']['session_mode'] = session_mode

        trades_df = run_enhanced_backtest(
            config=config,
            bars_df=bars_df,
            output_suffix=f"_testE_bos_session_{session_mode}",
            enable_filters={'use_bos_filter': True, 'use_htf_location_filter': False,
                           'use_session_filter': True, 'use_partial_tp': False}
        )

        results.append(process_result(f"Test E (BOS+Session {session_mode.capitalize()})",
                                     trades_df, bars_df, initial_balance))

    # Test F: BOS + Partial TP
    print(f"\n{'='*60}")
    print("Running: Test F (BOS + Partial TP)")
    print(f"{'='*60}")

    config = copy.deepcopy(base_config)
    trades_df = run_enhanced_backtest(
        config=config,
        bars_df=bars_df,
        output_suffix="_testF_bos_partial_tp",
        enable_filters={'use_bos_filter': True, 'use_htf_location_filter': False,
                       'use_session_filter': False, 'use_partial_tp': True}
    )

    results.append(process_result("Test F (BOS+Partial TP)", trades_df, bars_df, initial_balance))

    return results


def process_result(name, trades_df, bars_df, initial_balance):
    """Process single experiment result."""
    print(f"\n✓ {name} Complete")

    if trades_df is None or len(trades_df) == 0:
        print(f"  ⚠ No trades generated")
        return {
            'name': name,
            'trades_count': 0,
            'win_rate': 0.0,
            'expectancy_R': 0.0,
            'profit_factor': 0.0,
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

    # Sanity checks
    sanity = calculate_sanity_metrics(trades_df, bars_df)

    # Final balance
    final_balance = initial_balance + metrics['total_pnl']
    return_pct = ((final_balance - initial_balance) / initial_balance) * 100

    result = {
        'name': name,
        **metrics,
        'final_balance': final_balance,
        'return_pct': return_pct,
        'sanity': sanity
    }

    print(f"  Trades: {metrics['trades_count']}")
    print(f"  Win Rate: {metrics['win_rate']:.2f}%")
    print(f"  Expectancy: {metrics['expectancy_R']:.3f}R")
    print(f"  Return: {return_pct:.2f}%")

    return result


def run_walkforward(symbol='EURUSD', config_path='config/config.yaml'):
    """
    Run walk-forward analysis 2021-2024.

    For each year, run:
    - Baseline BOS
    - Test D (BOS+HTF)
    - Best session variant (Both)
    - Test F (BOS+Partial TP)
    """

    print(f"\n{'='*60}")
    print("WALK-FORWARD ANALYSIS 2021-2024")
    print(f"{'='*60}\n")

    years = [2021, 2022, 2023, 2024]
    all_results = []

    for year in years:
        print(f"\n{'#'*60}")
        print(f"# YEAR {year}")
        print(f"{'#'*60}\n")

        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"

        results = run_phase2_experiments(symbol, start_date, end_date, config_path)

        # Add year to each result
        for r in results:
            r['year'] = year

        all_results.extend(results)

    return all_results


def generate_phase2_report(results, walkforward_results, output_path):
    """Generate Phase 2 final report."""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Phase 2 Experiments - Final Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("---\n\n")

        # Phase 2 results table
        f.write("## Phase 2 Results (2024 H2)\n\n")

        f.write("| Test | Trades | Win Rate (%) | Expectancy (R) | Profit Factor | Max DD (%) | Return (%) |\n")
        f.write("|------|--------|--------------|----------------|---------------|------------|------------|\n")

        for r in results:
            f.write(f"| {r['name']} | {r['trades_count']} | {r['win_rate']:.2f} | {r['expectancy_R']:.3f} | {r['profit_factor']:.2f} | {r['max_dd_percent']:.2f} | {r['return_pct']:.2f} |\n")

        f.write("\n")

        # Key Findings
        f.write("## Key Findings\n\n")

        best = max(results, key=lambda x: x['expectancy_R'])
        f.write(f"### Best Configuration: **{best['name']}**\n\n")
        f.write(f"- Expectancy: {best['expectancy_R']:.3f}R\n")
        f.write(f"- Win Rate: {best['win_rate']:.2f}%\n")
        f.write(f"- Profit Factor: {best['profit_factor']:.2f}\n")
        f.write(f"- Return: {best['return_pct']:.2f}%\n\n")

        # Profitability check
        f.write("### Profitability Analysis\n\n")

        positive_exp = [r for r in results if r['expectancy_R'] > 0]
        pf_above_1 = [r for r in results if r['profit_factor'] > 1.0]

        if positive_exp:
            f.write(f"✅ **{len(positive_exp)} configuration(s) with POSITIVE expectancy:**\n\n")
            for r in positive_exp:
                f.write(f"- {r['name']}: {r['expectancy_R']:.3f}R (PF: {r['profit_factor']:.2f})\n")
            f.write("\n")
        else:
            f.write("❌ **No configurations achieved positive expectancy in 2024 H2.**\n\n")

        if pf_above_1:
            f.write(f"✅ **{len(pf_above_1)} configuration(s) with Profit Factor > 1.0:**\n\n")
            for r in pf_above_1:
                f.write(f"- {r['name']}: PF {r['profit_factor']:.2f}\n")
            f.write("\n")

        # Walk-Forward Results
        if walkforward_results:
            f.write("## Walk-Forward Analysis (2021-2024)\n\n")

            f.write("| Year | Configuration | Trades | WR (%) | Expectancy (R) | PF | Max DD (%) |\n")
            f.write("|------|---------------|--------|--------|----------------|----|-----------|\n")

            for r in walkforward_results:
                f.write(f"| {r['year']} | {r['name']} | {r['trades_count']} | {r['win_rate']:.2f} | {r['expectancy_R']:.3f} | {r['profit_factor']:.2f} | {r['max_dd_percent']:.2f} |\n")

            f.write("\n")

            # Calculate averages per configuration
            f.write("### 4-Year Averages\n\n")

            configs = set([r['name'] for r in walkforward_results])

            f.write("| Configuration | Avg Expectancy (R) | Std Dev | Avg WR (%) | Consistency |\n")
            f.write("|---------------|--------------------|---------|-----------|-----------|\n")

            for config_name in configs:
                config_results = [r for r in walkforward_results if r['name'] == config_name]

                exps = [r['expectancy_R'] for r in config_results]
                wrs = [r['win_rate'] for r in config_results]

                avg_exp = sum(exps) / len(exps)
                std_exp = (sum([(x - avg_exp)**2 for x in exps]) / len(exps)) ** 0.5
                avg_wr = sum(wrs) / len(wrs)

                # Consistency: years with positive expectancy / total years
                positive_years = len([e for e in exps if e > 0])
                consistency = f"{positive_years}/{len(exps)}"

                f.write(f"| {config_name} | {avg_exp:.3f} | {std_exp:.3f} | {avg_wr:.2f} | {consistency} |\n")

            f.write("\n")

        # Conclusions
        f.write("## Conclusions\n\n")

        f.write("### Expectancy > 0?\n\n")
        if positive_exp:
            f.write(f"✅ YES - {len(positive_exp)} config(s) achieved positive expectancy\n\n")
        else:
            f.write("❌ NO - All configurations remain negative or breakeven\n\n")

        f.write("### Profit Factor > 1?\n\n")
        if pf_above_1:
            f.write(f"✅ YES - {len(pf_above_1)} config(s) have PF > 1.0\n\n")
        else:
            f.write("❌ NO - All configurations have PF < 1.0\n\n")

        f.write("### Win Rate Stable?\n\n")
        wrs = [r['win_rate'] for r in results]
        wr_range = max(wrs) - min(wrs)
        f.write(f"Win rate range: {min(wrs):.2f}% to {max(wrs):.2f}% (spread: {wr_range:.2f}pp)\n\n")

        if wr_range < 10:
            f.write("✅ YES - Win rate relatively stable\n\n")
        else:
            f.write("⚠ MODERATE - Win rate shows some variation\n\n")

        f.write("### Does Any Filter Give Real Edge?\n\n")

        baseline = next((r for r in results if 'Baseline' in r['name']), None)
        if baseline:
            improvements = []
            for r in results:
                if r['name'] != baseline['name']:
                    improvement = r['expectancy_R'] - baseline['expectancy_R']
                    if improvement > 0.05:  # Threshold for "real" improvement
                        improvements.append((r['name'], improvement))

            if improvements:
                f.write("✅ YES - Following filters show improvement:\n\n")
                for name, imp in improvements:
                    f.write(f"- {name}: +{imp:.3f}R vs baseline\n")
                f.write("\n")
            else:
                f.write("❌ NO - No filter provides significant edge over baseline\n\n")

        f.write("---\n\n")
        f.write(f"*Report generated: {datetime.now()}*\n")


def main():
    parser = argparse.ArgumentParser(description='Run Phase 2 experiments')
    parser.add_argument('--symbol', type=str, default='EURUSD', help='Symbol')
    parser.add_argument('--mode', type=str, default='phase2',
                       choices=['phase2', 'walkforward', 'both'],
                       help='Run mode: phase2, walkforward, or both')
    parser.add_argument('--config', type=str, default='config/config.yaml', help='Config file')

    args = parser.parse_args()

    results = []
    walkforward_results = []

    if args.mode in ['phase2', 'both']:
        # Run Phase 2 experiments on 2024 H2
        results = run_phase2_experiments(
            symbol=args.symbol,
            start_date='2024-06-01',
            end_date='2024-12-31',
            config_path=args.config
        )

    if args.mode in ['walkforward', 'both']:
        # Run walk-forward 2021-2024
        walkforward_results = run_walkforward(
            symbol=args.symbol,
            config_path=args.config
        )

    # Generate report
    print(f"\n{'='*60}")
    print("Generating Phase 2 Report...")
    print(f"{'='*60}\n")

    report_path = f"data/outputs/final_phase2_report_{args.symbol}.md"
    generate_phase2_report(results, walkforward_results, report_path)

    print(f"✓ Report saved to: {report_path}")

    print(f"\n{'='*60}")
    print("PHASE 2 COMPLETE!")
    print(f"{'='*60}\n")

    # Quick summary
    if results:
        print("Phase 2 Results (2024 H2):")
        for r in results:
            print(f"  {r['name']:35s} | {r['trades_count']:3d} trades | {r['expectancy_R']:+.3f}R | {r['return_pct']:+6.2f}%")

    if results:
        best = max(results, key=lambda x: x['expectancy_R'])
        print(f"\n🏆 Best: {best['name']} ({best['expectancy_R']:+.3f}R)")


if __name__ == "__main__":
    main()

