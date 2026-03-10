"""
H1 Timeframe Tests - Complete Suite
Runs same tests as M15 but on H1 timeframe.
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


def run_h1_tests(symbol='EURUSD', start_date='2024-06-01', end_date='2024-12-31', config_path='config/config.yaml'):
    """
    Run H1 tests:
    - Baseline BOS
    - Test D (BOS + HTF Location with H4)
    - Test F (BOS + Partial TP)
    """

    print(f"\n{'='*60}")
    print("H1 TIMEFRAME TESTS")
    print(f"{'='*60}")
    print(f"Symbol: {symbol}")
    print(f"Period: {start_date} to {end_date}")
    print(f"{'='*60}\n")

    # Load config and bars
    base_config = load_config(config_path)
    initial_balance = base_config['execution']['initial_balance']

    # Load H1 bars
    bars_file = os.path.join(base_config['data']['bars_dir'], f"{symbol.lower()}_h1_bars.csv")

    if not os.path.exists(bars_file):
        print(f"✗ H1 bars file not found: {bars_file}")
        print(f"  Run: python scripts/build_h1_bars.py")
        return []

    print(f"Loading H1 bars...")
    bars_df = pd.read_csv(bars_file, index_col='timestamp', parse_dates=True)

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    bars_df = filter_bars_by_date(bars_df, start_dt, end_dt)

    print(f"✓ Loaded {len(bars_df)} H1 bars\n")

    results = []

    # TEST 1: Baseline BOS (H1)
    print(f"\n{'='*60}")
    print("Running: H1 Baseline BOS")
    print(f"{'='*60}")

    config = copy.deepcopy(base_config)
    trades_df = run_enhanced_backtest(
        config=config,
        bars_df=bars_df,
        output_suffix="_h1_baseline_bos",
        enable_filters={'use_bos_filter': True, 'use_htf_location_filter': False,
                       'use_session_filter': False, 'use_partial_tp': False}
    )

    results.append(process_result("H1 Baseline BOS", trades_df, bars_df, initial_balance))

    # TEST 2: BOS + HTF Location (H1 with H4 as HTF)
    print(f"\n{'='*60}")
    print("Running: H1 BOS + HTF Location (H4)")
    print(f"{'='*60}")

    config = copy.deepcopy(base_config)
    config['strategy']['htf_period'] = '4h'  # Use H4 as HTF for H1

    trades_df = run_enhanced_backtest(
        config=config,
        bars_df=bars_df,
        output_suffix="_h1_testD_bos_htf",
        enable_filters={'use_bos_filter': True, 'use_htf_location_filter': True,
                       'use_session_filter': False, 'use_partial_tp': False}
    )

    results.append(process_result("H1 Test D (BOS+HTF H4)", trades_df, bars_df, initial_balance))

    # TEST 3: BOS + Partial TP
    print(f"\n{'='*60}")
    print("Running: H1 BOS + Partial TP")
    print(f"{'='*60}")

    config = copy.deepcopy(base_config)
    trades_df = run_enhanced_backtest(
        config=config,
        bars_df=bars_df,
        output_suffix="_h1_testF_bos_partial_tp",
        enable_filters={'use_bos_filter': True, 'use_htf_location_filter': False,
                       'use_session_filter': False, 'use_partial_tp': True}
    )

    results.append(process_result("H1 Test F (BOS+Partial TP)", trades_df, bars_df, initial_balance))

    return results


def process_result(name, trades_df, bars_df, initial_balance):
    """Process single test result."""
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


def run_h1_walkforward(symbol='EURUSD', config_path='config/config.yaml'):
    """
    Run walk-forward on H1 for 2021-2024.
    Only Baseline BOS per year.
    """

    print(f"\n{'='*60}")
    print("H1 WALK-FORWARD 2021-2024")
    print(f"{'='*60}\n")

    years = [2021, 2022, 2023, 2024]
    all_results = []

    for year in years:
        print(f"\n{'#'*60}")
        print(f"# H1 - YEAR {year}")
        print(f"{'#'*60}\n")

        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"

        # Load config and bars
        base_config = load_config(config_path)
        initial_balance = base_config['execution']['initial_balance']

        # Load H1 bars
        bars_file = os.path.join(base_config['data']['bars_dir'], f"{symbol.lower()}_h1_bars.csv")

        if not os.path.exists(bars_file):
            print(f"✗ H1 bars not found")
            continue

        bars_df = pd.read_csv(bars_file, index_col='timestamp', parse_dates=True)
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        bars_df = filter_bars_by_date(bars_df, start_dt, end_dt)

        print(f"✓ Loaded {len(bars_df)} H1 bars for {year}")

        # Run Baseline BOS
        config = copy.deepcopy(base_config)
        trades_df = run_enhanced_backtest(
            config=config,
            bars_df=bars_df,
            output_suffix=f"_h1_baseline_{year}",
            enable_filters={'use_bos_filter': True, 'use_htf_location_filter': False,
                           'use_session_filter': False, 'use_partial_tp': False}
        )

        result = process_result(f"H1 Baseline BOS {year}", trades_df, bars_df, initial_balance)
        result['year'] = year
        all_results.append(result)

    return all_results


def generate_h1_report(h1_results, walkforward_results, m15_baseline, output_path):
    """Generate complete H1 report with M15 comparison."""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# H1 Timeframe Complete Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")

        # H1 Results
        f.write("## H1 Test Results (2024 H2)\n\n")

        f.write("| Test | Trades | Win Rate (%) | Expectancy (R) | Profit Factor | Max DD (%) | Return (%) |\n")
        f.write("|------|--------|--------------|----------------|---------------|------------|------------|\n")

        for r in h1_results:
            f.write(f"| {r['name']} | {r['trades_count']} | {r['win_rate']:.2f} | {r['expectancy_R']:.3f} | {r['profit_factor']:.2f} | {r['max_dd_percent']:.2f} | {r['return_pct']:.2f} |\n")

        f.write("\n")

        # M15 vs H1 Comparison
        f.write("## M15 vs H1 Comparison (Baseline BOS)\n\n")

        h1_baseline = next((r for r in h1_results if 'Baseline' in r['name']), None)

        if m15_baseline and h1_baseline:
            f.write("| Timeframe | Trades | Win Rate (%) | Expectancy (R) | Profit Factor | Max DD (%) | Return (%) |\n")
            f.write("|-----------|--------|--------------|----------------|---------------|------------|------------|\n")
            f.write(f"| M15 | {m15_baseline['trades']} | {m15_baseline['win_rate']:.2f} | {m15_baseline['expectancy']:.3f} | {m15_baseline['pf']:.2f} | {m15_baseline['dd']:.2f} | {m15_baseline['return']:.2f} |\n")
            f.write(f"| H1 | {h1_baseline['trades_count']} | {h1_baseline['win_rate']:.2f} | {h1_baseline['expectancy_R']:.3f} | {h1_baseline['profit_factor']:.2f} | {h1_baseline['max_dd_percent']:.2f} | {h1_baseline['return_pct']:.2f} |\n")

            f.write("\n### Differences (H1 vs M15)\n\n")

            trades_diff = h1_baseline['trades_count'] - m15_baseline['trades']
            wr_diff = h1_baseline['win_rate'] - m15_baseline['win_rate']
            exp_diff = h1_baseline['expectancy_R'] - m15_baseline['expectancy']
            dd_diff = h1_baseline['max_dd_percent'] - m15_baseline['dd']

            f.write(f"- **Trades:** {trades_diff:+d} ({(trades_diff/m15_baseline['trades']*100):+.1f}%)\n")
            f.write(f"- **Win Rate:** {wr_diff:+.2f}pp\n")
            f.write(f"- **Expectancy:** {exp_diff:+.3f}R\n")
            f.write(f"- **Max DD:** {dd_diff:+.2f}pp\n\n")

        # Walk-Forward Results
        if walkforward_results:
            f.write("## H1 Walk-Forward Analysis (2021-2024)\n\n")

            f.write("| Year | Trades | Win Rate (%) | Expectancy (R) | Profit Factor | Max DD (%) |\n")
            f.write("|------|--------|--------------|----------------|---------------|------------|\n")

            for r in walkforward_results:
                f.write(f"| {r['year']} | {r['trades_count']} | {r['win_rate']:.2f} | {r['expectancy_R']:.3f} | {r['profit_factor']:.2f} | {r['max_dd_percent']:.2f} |\n")

            f.write("\n### 4-Year Statistics\n\n")

            exps = [r['expectancy_R'] for r in walkforward_results]
            wrs = [r['win_rate'] for r in walkforward_results]

            avg_exp = sum(exps) / len(exps)
            std_exp = (sum([(x - avg_exp)**2 for x in exps]) / len(exps)) ** 0.5
            avg_wr = sum(wrs) / len(wrs)

            best_year = max(walkforward_results, key=lambda x: x['expectancy_R'])
            worst_year = min(walkforward_results, key=lambda x: x['expectancy_R'])

            f.write(f"- **Average Expectancy:** {avg_exp:.3f}R\n")
            f.write(f"- **Std Dev Expectancy:** {std_exp:.3f}R\n")
            f.write(f"- **Average Win Rate:** {avg_wr:.2f}%\n")
            f.write(f"- **Best Year:** {best_year['year']} ({best_year['expectancy_R']:.3f}R)\n")
            f.write(f"- **Worst Year:** {worst_year['year']} ({worst_year['expectancy_R']:.3f}R)\n\n")

        # Conclusions
        f.write("## Conclusions\n\n")

        if h1_baseline and m15_baseline:
            f.write("### Does H1 have higher Win Rate?\n\n")
            if h1_baseline['win_rate'] > m15_baseline['win_rate']:
                f.write(f"✅ YES - H1: {h1_baseline['win_rate']:.2f}% vs M15: {m15_baseline['win_rate']:.2f}% (+{wr_diff:.2f}pp)\n\n")
            else:
                f.write(f"❌ NO - H1: {h1_baseline['win_rate']:.2f}% vs M15: {m15_baseline['win_rate']:.2f}% ({wr_diff:.2f}pp)\n\n")

            f.write("### Does H1 have higher Expectancy?\n\n")
            if h1_baseline['expectancy_R'] > m15_baseline['expectancy']:
                f.write(f"✅ YES - H1: {h1_baseline['expectancy_R']:.3f}R vs M15: {m15_baseline['expectancy']:.3f}R (+{exp_diff:.3f}R)\n\n")
            else:
                f.write(f"❌ NO - H1: {h1_baseline['expectancy_R']:.3f}R vs M15: {m15_baseline['expectancy']:.3f}R ({exp_diff:.3f}R)\n\n")

            f.write("### Does H1 have lower Drawdown?\n\n")
            if h1_baseline['max_dd_percent'] < m15_baseline['dd']:
                f.write(f"✅ YES - H1: {h1_baseline['max_dd_percent']:.2f}% vs M15: {m15_baseline['dd']:.2f}% ({dd_diff:.2f}pp)\n\n")
            else:
                f.write(f"❌ NO - H1: {h1_baseline['max_dd_percent']:.2f}% vs M15: {m15_baseline['dd']:.2f}% (+{dd_diff:.2f}pp)\n\n")

            f.write("### Does Edge Grow with Higher Timeframe?\n\n")
            if h1_baseline['expectancy_R'] > m15_baseline['expectancy'] and h1_baseline['win_rate'] > m15_baseline['win_rate']:
                f.write("✅ YES - Both WR and Expectancy improved on H1\n\n")
            elif h1_baseline['expectancy_R'] > m15_baseline['expectancy']:
                f.write("⚠️ PARTIALLY - Expectancy improved but Win Rate didn't\n\n")
            else:
                f.write("❌ NO - H1 did not improve over M15\n\n")

        f.write("### Final Verdict: Does S&D Work Better on Higher TF?\n\n")

        if h1_baseline and m15_baseline:
            if h1_baseline['expectancy_R'] > m15_baseline['expectancy']:
                f.write(f"✅ **YES** - H1 shows improvement over M15\n\n")
                f.write(f"**Recommendation:** Use H1 timeframe for S&D strategy.\n\n")
            else:
                f.write(f"❌ **NO** - M15 remains superior to H1\n\n")
                f.write(f"**Recommendation:** Stick with M15 timeframe.\n\n")

        f.write("---\n\n")
        f.write(f"*Report generated: {datetime.now()}*\n")


def main():
    parser = argparse.ArgumentParser(description='Run H1 timeframe tests')
    parser.add_argument('--symbol', type=str, default='EURUSD', help='Symbol')
    parser.add_argument('--mode', type=str, default='tests',
                       choices=['tests', 'walkforward', 'both'],
                       help='Run mode: tests, walkforward, or both')
    parser.add_argument('--config', type=str, default='config/config.yaml', help='Config file')

    args = parser.parse_args()

    h1_results = []
    walkforward_results = []

    if args.mode in ['tests', 'both']:
        # Run H1 tests on 2024 H2
        h1_results = run_h1_tests(
            symbol=args.symbol,
            start_date='2024-06-01',
            end_date='2024-12-31',
            config_path=args.config
        )

    if args.mode in ['walkforward', 'both']:
        # Run walk-forward
        walkforward_results = run_h1_walkforward(
            symbol=args.symbol,
            config_path=args.config
        )

    # Generate report
    print(f"\n{'='*60}")
    print("Generating H1 Complete Report...")
    print(f"{'='*60}\n")

    # M15 baseline reference (from Phase 1 results)
    m15_baseline = {
        'trades': 121,
        'win_rate': 42.98,
        'expectancy': -0.018,
        'pf': 0.97,
        'dd': 24.92,
        'return': -2.34
    }

    report_path = f"data/outputs/H1_COMPLETE_REPORT_{args.symbol}.md"
    generate_h1_report(h1_results, walkforward_results, m15_baseline, report_path)

    print(f"✓ Report saved to: {report_path}")

    print(f"\n{'='*60}")
    print("H1 TESTS COMPLETE!")
    print(f"{'='*60}\n")

    # Quick summary
    if h1_results:
        print("H1 Test Results (2024 H2):")
        for r in h1_results:
            print(f"  {r['name']:30s} | {r['trades_count']:3d} trades | {r['expectancy_R']:+.3f}R | {r['return_pct']:+6.2f}%")

    if h1_results:
        best = max(h1_results, key=lambda x: x['expectancy_R'])
        print(f"\n🏆 Best H1: {best['name']} ({best['expectancy_R']:+.3f}R)")


if __name__ == "__main__":
    main()

