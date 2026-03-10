"""
Batch Backtest Runner
Runs backtests for multiple symbols, timeframes, and periods.
Generates segmented reports (ALL, FIRST_TOUCH, SECOND_TOUCH).
"""
import sys
import os
import argparse
import pandas as pd
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.utils.config import load_config
from src.backtest.engine import run_backtest
from src.backtest.metrics import compute_segment_metrics, add_R_column


def filter_bars_by_date(bars_df, start_date, end_date):
    """Filter bars DataFrame by date range."""
    bars_df.index = pd.to_datetime(bars_df.index)
    return bars_df[(bars_df.index >= start_date) & (bars_df.index <= end_date)]


def run_batch_backtest(symbols, timeframe, start_date, end_date, config_path, yearly_split=True):
    """
    Run batch backtest for multiple symbols and periods.

    Args:
        symbols: List of symbols (e.g., ['EURUSD', 'GBPUSD'])
        timeframe: Timeframe (e.g., 'M15')
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        config_path: Path to config file
        yearly_split: Whether to split by year
    """
    config = load_config(config_path)

    # Parse dates
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    all_results = []

    for symbol in symbols:
        print(f"\n{'='*60}")
        print(f"Processing {symbol} {timeframe}")
        print(f"{'='*60}")

        # Update config with current symbol
        config['data']['symbol'] = symbol.lower()

        # Check if bars file exists
        bars_file = os.path.join(config['data']['bars_dir'],
                                 f"{symbol.lower()}_m15_bars.csv")

        if not os.path.exists(bars_file):
            print(f"⚠ Bars file not found: {bars_file}")
            print(f"  Please run: python scripts/download_ticks.py (with symbol={symbol})")
            print(f"  Then run: python scripts/build_bars.py")
            print(f"  Skipping {symbol}...\n")
            continue

        # Load bars
        print(f"Loading bars from {bars_file}...")
        bars_df = pd.read_csv(bars_file, index_col='timestamp', parse_dates=True)

        # Filter by date range
        bars_df = filter_bars_by_date(bars_df, start_dt, end_dt)

        if len(bars_df) == 0:
            print(f"⚠ No data in date range {start_date} to {end_date}")
            print(f"  Skipping {symbol}...\n")
            continue

        print(f"Loaded {len(bars_df)} bars from {bars_df.index[0]} to {bars_df.index[-1]}")

        # Determine periods to test
        periods = []

        if yearly_split:
            years = range(start_dt.year, end_dt.year + 1)
            for year in years:
                year_start = max(start_dt, pd.Timestamp(f"{year}-01-01"))
                year_end = min(end_dt, pd.Timestamp(f"{year}-12-31"))
                periods.append((f"{year}", year_start, year_end))

        # Always include overall period
        periods.append(("overall", start_dt, end_dt))

        # Run backtest for each period
        for period_name, period_start, period_end in periods:
            print(f"\n{'-'*60}")
            print(f"Running backtest: {symbol} {period_name}")
            print(f"  Period: {period_start.date()} to {period_end.date()}")
            print(f"{'-'*60}")

            # Filter bars for this period
            period_bars = filter_bars_by_date(bars_df, period_start, period_end)

            if len(period_bars) == 0:
                print(f"⚠ No data for period {period_name}, skipping...")
                continue

            # Run backtest
            output_suffix = f"_{symbol}_{period_name}"
            trades_df = run_backtest(config=config, bars_df=period_bars, output_suffix=output_suffix)

            if trades_df is None or len(trades_df) == 0:
                print(f"⚠ No trades generated for {symbol} {period_name}")

                # Add empty result
                all_results.append({
                    'symbol': symbol,
                    'period': period_name,
                    'segment': 'ALL',
                    'trades_count': 0,
                    'win_rate': 0.0,
                    'expectancy_R': 0.0,
                    'avg_R': 0.0,
                    'median_R': 0.0,
                    'profit_factor': 0.0,
                    'total_pnl': 0.0,
                    'max_dd_percent': 0.0,
                    'max_losing_streak': 0
                })
                continue

            # Add R column
            trades_df = add_R_column(trades_df)

            # Save detailed trades
            trades_filename = f"trades_{symbol}_{timeframe}_{period_name}.csv"
            trades_path = os.path.join("data", "outputs", trades_filename)
            trades_df.to_csv(trades_path, index=False)
            print(f"✓ Saved trades to {trades_path}")

            # Compute segment metrics
            initial_balance = config['execution']['initial_balance']
            segments = compute_segment_metrics(trades_df, initial_balance, segment_col='touch_no')

            # Add to results
            for segment_name, metrics in segments.items():
                result = {
                    'symbol': symbol,
                    'period': period_name,
                    'segment': segment_name,
                    **metrics
                }
                all_results.append(result)

            print(f"✓ Completed {symbol} {period_name}")

    # Generate batch summary
    if len(all_results) > 0:
        print(f"\n{'='*60}")
        print("Generating Batch Summary...")
        print(f"{'='*60}")

        results_df = pd.DataFrame(all_results)

        # Save CSV
        csv_path = os.path.join("data", "outputs", "batch_summary.csv")
        results_df.to_csv(csv_path, index=False)
        print(f"✓ Saved batch summary CSV to {csv_path}")

        # Generate Markdown report
        generate_batch_summary_md(results_df, "reports/batch_summary.md")
        print(f"✓ Generated batch summary report: reports/batch_summary.md")
    else:
        print("\n⚠ No results to summarize.")

    print(f"\n{'='*60}")
    print("Batch Backtest Complete!")
    print(f"{'='*60}\n")


def generate_batch_summary_md(results_df, output_path):
    """Generate markdown summary report from results DataFrame."""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Batch Backtest Summary\n\n")
        f.write(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Overall results
        f.write("## Overall Results\n\n")
        overall = results_df[results_df['period'] == 'overall']
        if len(overall) > 0:
            f.write(overall.to_markdown(index=False))
            f.write("\n\n")

        # Per-year results
        f.write("## Per-Year Results\n\n")
        yearly = results_df[results_df['period'] != 'overall']
        if len(yearly) > 0:
            f.write(yearly.to_markdown(index=False))
            f.write("\n\n")

        # Key Findings: Compare FIRST vs SECOND touch
        f.write("## Key Findings\n\n")

        # Filter for TOUCH_1 and TOUCH_2
        touch_1 = results_df[results_df['segment'] == 'TOUCH_1']
        touch_2 = results_df[results_df['segment'] == 'TOUCH_2']

        if len(touch_1) > 0 and len(touch_2) > 0:
            avg_exp_t1 = touch_1['expectancy_R'].mean()
            avg_exp_t2 = touch_2['expectancy_R'].mean()
            avg_wr_t1 = touch_1['win_rate'].mean()
            avg_wr_t2 = touch_2['win_rate'].mean()

            f.write("### First Touch vs Second Touch Comparison\n\n")
            f.write(f"- **First Touch Average Expectancy (R)**: {avg_exp_t1:.3f}\n")
            f.write(f"- **Second Touch Average Expectancy (R)**: {avg_exp_t2:.3f}\n")
            f.write(f"- **Difference**: {avg_exp_t2 - avg_exp_t1:.3f} R\n\n")

            f.write(f"- **First Touch Average Win Rate**: {avg_wr_t1:.2f}%\n")
            f.write(f"- **Second Touch Average Win Rate**: {avg_wr_t2:.2f}%\n")
            f.write(f"- **Difference**: {avg_wr_t2 - avg_wr_t1:.2f}%\n\n")

            if avg_exp_t2 > avg_exp_t1:
                f.write("**Conclusion**: Second touches show higher expectancy than first touches.\n\n")
            else:
                f.write("**Conclusion**: First touches show higher expectancy than second touches.\n\n")
        else:
            f.write("Not enough data to compare first vs second touch.\n\n")

        # Best performing configurations
        f.write("### Top 5 Configurations by Expectancy (R)\n\n")
        top5 = results_df.nlargest(5, 'expectancy_R')[['symbol', 'period', 'segment', 'expectancy_R', 'win_rate', 'max_dd_percent']]
        f.write(top5.to_markdown(index=False))
        f.write("\n\n")


def main():
    parser = argparse.ArgumentParser(description='Run batch backtest for multiple symbols and periods')
    parser.add_argument('--symbols', type=str, default='EURUSD',
                       help='Comma-separated list of symbols (e.g., EURUSD,GBPUSD)')
    parser.add_argument('--tf', type=str, default='M15',
                       help='Timeframe (e.g., M15)')
    parser.add_argument('--start', type=str, required=True,
                       help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True,
                       help='End date (YYYY-MM-DD)')
    parser.add_argument('--config', type=str, default='config/config.yaml',
                       help='Path to config file')
    parser.add_argument('--yearly_split', type=str, default='true',
                       help='Split by year (true/false)')

    args = parser.parse_args()

    # Parse symbols
    symbols = [s.strip().upper() for s in args.symbols.split(',')]

    # Parse yearly_split
    yearly_split = args.yearly_split.lower() in ['true', '1', 'yes']

    print(f"\n{'='*60}")
    print("Batch Backtest Runner")
    print(f"{'='*60}")
    print(f"Symbols: {symbols}")
    print(f"Timeframe: {args.tf}")
    print(f"Period: {args.start} to {args.end}")
    print(f"Yearly Split: {yearly_split}")
    print(f"Config: {args.config}")
    print(f"{'='*60}\n")

    run_batch_backtest(
        symbols=symbols,
        timeframe=args.tf,
        start_date=args.start,
        end_date=args.end,
        config_path=args.config,
        yearly_split=yearly_split
    )


if __name__ == "__main__":
    main()


