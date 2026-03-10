"""
Sensitivity Test Runner
Tests parameter sensitivity with ±20% grid.
Generates sensitivity analysis report.
"""
import sys
import os
import argparse
import pandas as pd
from datetime import datetime
from itertools import product
import copy

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.utils.config import load_config
from src.backtest.engine import run_backtest
from src.backtest.metrics import compute_segment_metrics, add_R_column


def filter_bars_by_date(bars_df, start_date, end_date):
    """Filter bars DataFrame by date range."""
    bars_df.index = pd.to_datetime(bars_df.index)
    return bars_df[(bars_df.index >= start_date) & (bars_df.index <= end_date)]


def generate_parameter_grid(config, multipliers=None):
    """
    Generate parameter grid for sensitivity test.

    Tests:
    - impulse_atr_mult
    - buffer_atr_mult
    - base_body_atr_threshold (interpreted from code: body < 0.6*ATR)
    """
    if multipliers is None:
        multipliers = [0.8, 1.0, 1.2]

    base_impulse = config['strategy']['impulse_atr_mult']
    base_buffer = config['strategy']['buffer_atr_mult']

    # For base body threshold, we need to add it to config or infer
    # Currently hardcoded as 0.6 in detect_zones.py
    # Let's add it as a parameter
    base_body_threshold = config['strategy'].get('base_body_atr_mult', 0.6)

    grid = []

    for imp_mult, buf_mult, body_mult in product(multipliers, multipliers, multipliers):
        params = {
            'impulse_atr_mult': base_impulse * imp_mult,
            'buffer_atr_mult': base_buffer * buf_mult,
            'base_body_atr_mult': base_body_threshold * body_mult,
            'multipliers': f"I:{imp_mult:.1f}x B:{buf_mult:.1f}x Body:{body_mult:.1f}x"
        }
        grid.append(params)

    return grid


def run_sensitivity_test(symbol, timeframe, start_date, end_date, config_path):
    """
    Run sensitivity test with parameter grid.

    Args:
        symbol: Symbol to test (e.g., 'EURUSD')
        timeframe: Timeframe (e.g., 'M15')
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        config_path: Path to config file
    """
    base_config = load_config(config_path)

    # Parse dates
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    print(f"\n{'='*60}")
    print(f"Sensitivity Test: {symbol} {timeframe}")
    print(f"Period: {start_date} to {end_date}")
    print(f"{'='*60}\n")

    # Update config with current symbol
    base_config['data']['symbol'] = symbol.lower()

    # Check if bars file exists
    bars_file = os.path.join(base_config['data']['bars_dir'],
                             f"{symbol.lower()}_m15_bars.csv")

    if not os.path.exists(bars_file):
        print(f"✗ Bars file not found: {bars_file}")
        print(f"  Please run data download and processing first.")
        return

    # Load bars
    print(f"Loading bars from {bars_file}...")
    bars_df = pd.read_csv(bars_file, index_col='timestamp', parse_dates=True)

    # Filter by date range
    bars_df = filter_bars_by_date(bars_df, start_dt, end_dt)

    if len(bars_df) == 0:
        print(f"✗ No data in date range {start_date} to {end_date}")
        return

    print(f"✓ Loaded {len(bars_df)} bars from {bars_df.index[0]} to {bars_df.index[-1]}")

    # Generate parameter grid
    param_grid = generate_parameter_grid(base_config)

    print(f"\n{'='*60}")
    print(f"Testing {len(param_grid)} parameter combinations")
    print(f"{'='*60}\n")

    results = []

    for i, params in enumerate(param_grid, 1):
        print(f"[{i}/{len(param_grid)}] Testing: {params['multipliers']}")

        # Create config copy with modified parameters
        test_config = copy.deepcopy(base_config)
        test_config['strategy']['impulse_atr_mult'] = params['impulse_atr_mult']
        test_config['strategy']['buffer_atr_mult'] = params['buffer_atr_mult']
        test_config['strategy']['base_body_atr_mult'] = params['base_body_atr_mult']

        # Run backtest (suppress output)
        import io
        import contextlib

        # Capture stdout to reduce noise
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            trades_df = run_backtest(config=test_config, bars_df=bars_df, output_suffix="")

        if trades_df is None or len(trades_df) == 0:
            print(f"  ⚠ No trades generated")

            # Add empty result
            results.append({
                'impulse_mult': params['impulse_atr_mult'],
                'buffer_mult': params['buffer_atr_mult'],
                'body_mult': params['base_body_atr_mult'],
                'config_label': params['multipliers'],
                'segment': 'ALL',
                'trades_count': 0,
                'win_rate': 0.0,
                'expectancy_R': 0.0,
                'profit_factor': 0.0,
                'max_dd_percent': 0.0,
                'max_losing_streak': 0
            })
            continue

        # Add R column
        trades_df = add_R_column(trades_df)

        # Compute metrics
        initial_balance = test_config['execution']['initial_balance']
        segments = compute_segment_metrics(trades_df, initial_balance, segment_col='touch_no')

        # Store results for ALL and FIRST_TOUCH
        for segment_name in ['ALL', 'TOUCH_1']:
            if segment_name in segments:
                metrics = segments[segment_name]
                result = {
                    'impulse_mult': params['impulse_atr_mult'],
                    'buffer_mult': params['buffer_atr_mult'],
                    'body_mult': params['base_body_atr_mult'],
                    'config_label': params['multipliers'],
                    'segment': segment_name,
                    'trades_count': metrics['trades_count'],
                    'win_rate': metrics['win_rate'],
                    'expectancy_R': metrics['expectancy_R'],
                    'profit_factor': metrics['profit_factor'],
                    'max_dd_percent': metrics['max_dd_percent'],
                    'max_losing_streak': metrics['max_losing_streak']
                }
                results.append(result)

        print(f"  ✓ Trades: {len(trades_df)}, Expectancy: {segments['ALL']['expectancy_R']:.3f}R")

    # Save results
    print(f"\n{'='*60}")
    print("Saving Results...")
    print(f"{'='*60}\n")

    results_df = pd.DataFrame(results)

    # Save CSV
    csv_path = os.path.join("data", "outputs", "sensitivity_results.csv")
    results_df.to_csv(csv_path, index=False)
    print(f"✓ Saved sensitivity results CSV to {csv_path}")

    # Generate Markdown report
    generate_sensitivity_summary_md(results_df, "reports/sensitivity_summary.md")
    print(f"✓ Generated sensitivity summary report: reports/sensitivity_summary.md")

    print(f"\n{'='*60}")
    print("Sensitivity Test Complete!")
    print(f"{'='*60}\n")


def generate_sensitivity_summary_md(results_df, output_path):
    """Generate markdown summary report from sensitivity results."""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Sensitivity Test Summary\n\n")
        f.write(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Filter ALL segment
        all_seg = results_df[results_df['segment'] == 'ALL'].copy()

        if len(all_seg) == 0:
            f.write("No results to display.\n")
            return

        # Overall statistics
        f.write("## Overall Statistics\n\n")
        f.write(f"- **Total Configurations Tested**: {len(all_seg)}\n")
        f.write(f"- **Average Expectancy (R)**: {all_seg['expectancy_R'].mean():.3f}\n")
        f.write(f"- **Std Dev Expectancy (R)**: {all_seg['expectancy_R'].std():.3f}\n")
        f.write(f"- **Average Win Rate**: {all_seg['win_rate'].mean():.2f}%\n")
        f.write(f"- **Average Max DD**: {all_seg['max_dd_percent'].mean():.2f}%\n\n")

        # Stability Analysis
        f.write("## Stability Analysis\n\n")
        exp_std = all_seg['expectancy_R'].std()
        if exp_std < 0.1:
            f.write("✓ **Results are STABLE** - Low variance in expectancy across parameters.\n\n")
        elif exp_std < 0.3:
            f.write("⚠ **Results show MODERATE sensitivity** - Some parameters impact performance.\n\n")
        else:
            f.write("✗ **Results are HIGHLY SENSITIVE** - Parameters significantly affect performance.\n\n")

        # Top configurations (with DD filter)
        f.write("## Top 10 Configurations by Expectancy (R)\n\n")
        f.write("*Filtered by Max DD ≤ 15%*\n\n")

        filtered = all_seg[all_seg['max_dd_percent'] <= 15]

        if len(filtered) == 0:
            f.write("⚠ No configurations meet the Max DD threshold. Showing all:\n\n")
            filtered = all_seg

        top10 = filtered.nlargest(10, 'expectancy_R')[
            ['config_label', 'trades_count', 'win_rate', 'expectancy_R',
             'profit_factor', 'max_dd_percent', 'max_losing_streak']
        ]

        f.write(top10.to_markdown(index=False))
        f.write("\n\n")

        # Worst configurations
        f.write("## Worst 5 Configurations by Expectancy (R)\n\n")
        worst5 = all_seg.nsmallest(5, 'expectancy_R')[
            ['config_label', 'trades_count', 'win_rate', 'expectancy_R',
             'profit_factor', 'max_dd_percent', 'max_losing_streak']
        ]

        f.write(worst5.to_markdown(index=False))
        f.write("\n\n")

        # Parameter impact analysis
        f.write("## Parameter Impact Analysis\n\n")

        # Group by each parameter dimension
        f.write("### By Impulse Multiplier\n\n")
        by_impulse = all_seg.groupby('impulse_mult').agg({
            'expectancy_R': 'mean',
            'win_rate': 'mean',
            'trades_count': 'sum'
        }).round(3)
        f.write(by_impulse.to_markdown())
        f.write("\n\n")

        f.write("### By Buffer Multiplier\n\n")
        by_buffer = all_seg.groupby('buffer_mult').agg({
            'expectancy_R': 'mean',
            'win_rate': 'mean',
            'trades_count': 'sum'
        }).round(3)
        f.write(by_buffer.to_markdown())
        f.write("\n\n")

        f.write("### By Base Body Multiplier\n\n")
        by_body = all_seg.groupby('body_mult').agg({
            'expectancy_R': 'mean',
            'win_rate': 'mean',
            'trades_count': 'sum'
        }).round(3)
        f.write(by_body.to_markdown())
        f.write("\n\n")

        # First touch analysis
        first_touch = results_df[results_df['segment'] == 'TOUCH_1']
        if len(first_touch) > 0:
            f.write("## First Touch Analysis\n\n")
            f.write(f"- **Average Expectancy (R)**: {first_touch['expectancy_R'].mean():.3f}\n")
            f.write(f"- **Average Win Rate**: {first_touch['win_rate'].mean():.2f}%\n\n")

            f.write("### Top 5 Configurations (First Touch Only)\n\n")
            top5_ft = first_touch.nlargest(5, 'expectancy_R')[
                ['config_label', 'trades_count', 'win_rate', 'expectancy_R', 'max_dd_percent']
            ]
            f.write(top5_ft.to_markdown(index=False))
            f.write("\n\n")


def main():
    parser = argparse.ArgumentParser(description='Run sensitivity test on backtest parameters')
    parser.add_argument('--symbol', type=str, default='EURUSD',
                       help='Symbol to test (e.g., EURUSD)')
    parser.add_argument('--tf', type=str, default='M15',
                       help='Timeframe (e.g., M15)')
    parser.add_argument('--start', type=str, required=True,
                       help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True,
                       help='End date (YYYY-MM-DD)')
    parser.add_argument('--config', type=str, default='config/config.yaml',
                       help='Path to config file')

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("Sensitivity Test Runner")
    print(f"{'='*60}")
    print(f"Symbol: {args.symbol}")
    print(f"Timeframe: {args.tf}")
    print(f"Period: {args.start} to {args.end}")
    print(f"Config: {args.config}")
    print(f"{'='*60}\n")

    run_sensitivity_test(
        symbol=args.symbol.upper(),
        timeframe=args.tf,
        start_date=args.start,
        end_date=args.end,
        config_path=args.config
    )


if __name__ == "__main__":
    main()


