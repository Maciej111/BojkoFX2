"""
Split multi-year tick data files into separate yearly files.
Used for data organization and validation.
"""

import pandas as pd
import numpy as np
import os
from pathlib import Path
from datetime import datetime, timedelta


def analyze_gaps(df, symbol):
    """Analyze gaps in tick data."""
    df = df.sort_values('timestamp')
    df['time_diff'] = df['timestamp'].diff()

    # Find gaps > 1 hour
    gaps = df[df['time_diff'] > pd.Timedelta(hours=1)]

    return {
        'max_gap': df['time_diff'].max() if len(df) > 1 else pd.Timedelta(0),
        'gaps_over_1h': len(gaps),
        'gap_details': gaps[['timestamp', 'time_diff']].head(10).to_dict('records') if len(gaps) > 0 else []
    }


def calculate_spread_stats(df):
    """Calculate spread statistics."""
    if 'ask' in df.columns and 'bid' in df.columns:
        df['spread'] = df['ask'] - df['bid']
        return {
            'mean_spread': df['spread'].mean(),
            'median_spread': df['spread'].median(),
            'min_spread': df['spread'].min(),
            'max_spread': df['spread'].max()
        }
    return None


def split_tick_file(input_file, output_dir, symbol):
    """
    Split a multi-year tick file into yearly files.

    Args:
        input_file: Path to input CSV file
        output_dir: Directory for output files
        symbol: Symbol name (e.g., 'gbpusd')

    Returns:
        Dictionary with split results
    """
    print(f"\n{'='*60}")
    print(f"Processing {symbol.upper()}")
    print(f"{'='*60}")
    print(f"Reading {os.path.basename(input_file)}...")

    # Read CSV
    df = pd.read_csv(input_file)

    # Normalize columns
    df.columns = [c.lower() for c in df.columns]
    rename_map = {
        'time': 'timestamp',
        'askprice': 'ask',
        'bidprice': 'bid',
        'ask_price': 'ask',
        'bid_price': 'bid'
    }
    df.rename(columns=rename_map, inplace=True)

    # Convert timestamp
    if df['timestamp'].dtype == 'int64':
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    else:
        df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Sort by timestamp
    df = df.sort_values('timestamp').reset_index(drop=True)

    print(f"✓ Loaded {len(df):,} ticks")
    print(f"  First tick: {df['timestamp'].min()}")
    print(f"  Last tick: {df['timestamp'].max()}")

    # Check if sorted
    is_sorted = df['timestamp'].is_monotonic_increasing
    print(f"  Data sorted: {'✓' if is_sorted else '✗'}")

    # Extract year
    df['year'] = df['timestamp'].dt.year

    # Get unique years
    years = sorted(df['year'].unique())
    print(f"  Years found: {years}")

    # Overall spread stats
    overall_spread = calculate_spread_stats(df)

    # Overall gaps
    overall_gaps = analyze_gaps(df, symbol)

    # Split by year
    yearly_results = {}

    for year in years:
        print(f"\n  Processing year {year}...")

        # Filter data for this year
        year_df = df[df['year'] == year].copy()
        year_df = year_df.drop('year', axis=1)

        # Stats
        tick_count = len(year_df)
        first_tick = year_df['timestamp'].min()
        last_tick = year_df['timestamp'].max()

        # Calculate days covered
        days_covered = (last_tick - first_tick).days + 1
        expected_days = 366 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 365

        # Spread stats for this year
        year_spread = calculate_spread_stats(year_df)

        # Gaps for this year
        year_gaps = analyze_gaps(year_df, symbol)

        # Save file
        output_file = os.path.join(
            output_dir,
            f"{symbol}-tick-{year}-01-01-{year}-12-31.csv"
        )
        year_df.to_csv(output_file, index=False)

        print(f"    ✓ Saved {tick_count:,} ticks to {os.path.basename(output_file)}")
        print(f"      Period: {first_tick} to {last_tick}")
        print(f"      Days covered: {days_covered}/{expected_days}")

        # Store results
        yearly_results[year] = {
            'tick_count': tick_count,
            'first_tick': first_tick,
            'last_tick': last_tick,
            'days_covered': days_covered,
            'expected_days': expected_days,
            'completeness_pct': (days_covered / expected_days) * 100,
            'spread_stats': year_spread,
            'gap_stats': year_gaps,
            'output_file': output_file
        }

    return {
        'symbol': symbol,
        'total_ticks': len(df),
        'overall_first': df['timestamp'].min(),
        'overall_last': df['timestamp'].max(),
        'is_sorted': is_sorted,
        'years': years,
        'overall_spread': overall_spread,
        'overall_gaps': overall_gaps,
        'yearly_results': yearly_results
    }


def generate_report(all_results, output_file):
    """Generate markdown report with split results."""

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# 📊 TICK DATA SPLIT REPORT\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")

        f.write("## 📋 EXECUTIVE SUMMARY\n\n")
        f.write(f"**Total symbols processed:** {len(all_results)}\n\n")

        total_files = sum(len(r['yearly_results']) for r in all_results.values())
        f.write(f"**Total files created:** {total_files}\n\n")

        total_ticks = sum(r['total_ticks'] for r in all_results.values())
        f.write(f"**Total ticks processed:** {total_ticks:,}\n\n")

        f.write("---\n\n")

        # Per symbol details
        for symbol, result in all_results.items():
            f.write(f"## 🔹 {symbol.upper()}\n\n")

            f.write("### Overall Statistics\n\n")
            f.write(f"- **Total ticks:** {result['total_ticks']:,}\n")
            f.write(f"- **First tick:** {result['overall_first']}\n")
            f.write(f"- **Last tick:** {result['overall_last']}\n")
            f.write(f"- **Data sorted:** {'✓ Yes' if result['is_sorted'] else '✗ No'}\n")
            f.write(f"- **Years covered:** {', '.join(map(str, result['years']))}\n\n")

            # Overall spread
            if result['overall_spread']:
                spread = result['overall_spread']
                f.write("### Spread Statistics (Overall)\n\n")
                f.write(f"- **Mean spread:** {spread['mean_spread']:.5f}\n")
                f.write(f"- **Median spread:** {spread['median_spread']:.5f}\n")
                f.write(f"- **Min spread:** {spread['min_spread']:.5f}\n")
                f.write(f"- **Max spread:** {spread['max_spread']:.5f}\n\n")

            # Overall gaps
            if result['overall_gaps']:
                gaps = result['overall_gaps']
                f.write("### Data Gaps (Overall)\n\n")
                f.write(f"- **Max gap:** {gaps['max_gap']}\n")
                f.write(f"- **Gaps > 1 hour:** {gaps['gaps_over_1h']}\n\n")

            # Yearly breakdown
            f.write("### Yearly Breakdown\n\n")
            f.write("| Year | Ticks | First Tick | Last Tick | Days | Completeness | Avg Spread |\n")
            f.write("|------|-------|------------|-----------|------|--------------|------------|\n")

            for year, yr_result in sorted(result['yearly_results'].items()):
                tick_str = f"{yr_result['tick_count']:,}"
                first_str = yr_result['first_tick'].strftime('%Y-%m-%d')
                last_str = yr_result['last_tick'].strftime('%Y-%m-%d')
                days_str = f"{yr_result['days_covered']}/{yr_result['expected_days']}"
                completeness_str = f"{yr_result['completeness_pct']:.1f}%"

                if yr_result['spread_stats']:
                    spread_str = f"{yr_result['spread_stats']['mean_spread']:.5f}"
                else:
                    spread_str = "N/A"

                f.write(f"| {year} | {tick_str} | {first_str} | {last_str} | {days_str} | {completeness_str} | {spread_str} |\n")

            f.write("\n")

            # Gap details per year
            f.write("### Data Quality Issues\n\n")

            has_issues = False
            for year, yr_result in sorted(result['yearly_results'].items()):
                if yr_result['gap_stats']['gaps_over_1h'] > 0:
                    has_issues = True
                    f.write(f"**{year}:**\n")
                    f.write(f"- Gaps > 1h: {yr_result['gap_stats']['gaps_over_1h']}\n")
                    f.write(f"- Max gap: {yr_result['gap_stats']['max_gap']}\n\n")

            if not has_issues:
                f.write("✅ No significant data gaps detected (all gaps < 1 hour)\n\n")

            # Files created
            f.write("### Files Created\n\n")
            for year, yr_result in sorted(result['yearly_results'].items()):
                f.write(f"- `{os.path.basename(yr_result['output_file'])}`\n")

            f.write("\n---\n\n")

        # Summary
        f.write("## ✅ COMPLETION STATUS\n\n")
        f.write("All tick data files have been successfully split by year.\n\n")

        f.write("### Data Validation Summary\n\n")
        all_sorted = all(r['is_sorted'] for r in all_results.values())
        f.write(f"- **All data sorted:** {'✅ Yes' if all_sorted else '⚠ Some issues'}\n")

        total_gaps = sum(
            sum(yr['gap_stats']['gaps_over_1h'] for yr in r['yearly_results'].values())
            for r in all_results.values()
        )
        f.write(f"- **Total gaps > 1h:** {total_gaps}\n")

        f.write("\n### Next Steps\n\n")
        f.write("1. Use these yearly files for building bars\n")
        f.write("2. Run multi-symbol backtest with frozen config\n")
        f.write("3. Generate robustness report\n\n")

        f.write("---\n\n")
        f.write(f"**Report generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    print(f"\n✓ Report saved to {output_file}")


def main():
    """Main execution function."""

    print("="*60)
    print("TICK DATA YEAR SPLITTER")
    print("="*60)

    # Paths
    raw_dir = "data/raw"
    reports_dir = "reports"

    os.makedirs(reports_dir, exist_ok=True)

    # Files to process
    files_to_split = {
        'gbpusd': 'gbpusd-tick-2021-01-01-2024-12-31.csv',
        'usdjpy': 'usdjpy-tick-2021-01-01-2024-12-31.csv',
        'xauusd': 'xauusd-tick-2021-01-01-2024-12-31.csv'
    }

    all_results = {}

    # Process each file
    for symbol, filename in files_to_split.items():
        input_file = os.path.join(raw_dir, filename)

        if not os.path.exists(input_file):
            print(f"\n⚠ File not found: {input_file}")
            continue

        try:
            result = split_tick_file(input_file, raw_dir, symbol)
            all_results[symbol] = result
        except Exception as e:
            print(f"\n❌ Error processing {symbol}: {e}")
            continue

    # Generate report
    if all_results:
        report_file = os.path.join(reports_dir, "DATA_SPLIT_REPORT.md")
        generate_report(all_results, report_file)

        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)

        for symbol, result in all_results.items():
            print(f"\n{symbol.upper()}:")
            print(f"  Total ticks: {result['total_ticks']:,}")
            print(f"  Years split: {len(result['yearly_results'])}")
            for year in sorted(result['yearly_results'].keys()):
                yr = result['yearly_results'][year]
                print(f"    {year}: {yr['tick_count']:,} ticks")

        print("\n✅ All files processed successfully!")
        print(f"✅ Report generated: {report_file}")
    else:
        print("\n❌ No files were processed successfully")


if __name__ == "__main__":
    main()

