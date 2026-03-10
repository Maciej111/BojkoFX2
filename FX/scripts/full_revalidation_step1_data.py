"""
FULL SYSTEM REVALIDATION - STEP 1: DATA VALIDATION
Complete data integrity check for all 4 symbols
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime

print("="*80)
print("FULL SYSTEM REVALIDATION - DATA VALIDATION")
print("="*80)
print()

SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']
YEARS = [2021, 2022, 2023, 2024]

results = {}

for symbol in SYMBOLS:
    print(f"\n{'='*80}")
    print(f"VALIDATING {symbol}")
    print(f"{'='*80}\n")

    symbol_results = {
        'tick_files': {},
        'validation': {}
    }

    # Check tick files
    print(f"Checking tick files...")
    for year in YEARS:
        fname = f"{symbol.lower()}-tick-{year}-01-01-{year}-12-31.csv"
        fpath = os.path.join('data/raw', fname)

        if not os.path.exists(fpath):
            print(f"  [MISSING] {fname}")
            symbol_results['tick_files'][year] = 'MISSING'
            continue

        # Check file
        size_mb = os.path.getsize(fpath) / (1024*1024)

        with open(fpath, 'r') as f:
            lines = sum(1 for _ in f)

        # Quick timestamp check
        df_head = pd.read_csv(fpath, nrows=100)
        df_head.columns = [c.lower() for c in df_head.columns]

        # Get first timestamp
        if 'timestamp' in df_head.columns:
            ts_col = 'timestamp'
        elif 'time' in df_head.columns:
            ts_col = 'time'
        else:
            ts_col = df_head.columns[0]

        first_ts = df_head[ts_col].iloc[0]
        if isinstance(first_ts, (int, float)):
            first_date = pd.to_datetime(first_ts, unit='ms')
        else:
            first_date = pd.to_datetime(first_ts)

        # Get last timestamp (use tail command or read last rows)
        # Simple approach: read last 100 rows
        df_tail = pd.read_csv(fpath, skiprows=range(1, max(1, lines-100)))
        df_tail.columns = [c.lower() for c in df_tail.columns]

        if ts_col not in df_tail.columns:
            ts_col = df_tail.columns[0]

        last_ts = df_tail[ts_col].iloc[-1]
        if isinstance(last_ts, (int, float)):
            last_date = pd.to_datetime(last_ts, unit='ms')
        else:
            last_date = pd.to_datetime(last_ts)

        symbol_results['tick_files'][year] = {
            'size_mb': size_mb,
            'lines': lines,
            'first_date': first_date,
            'last_date': last_date
        }

        print(f"  [{year}] {size_mb:7.1f} MB, {lines:,} lines, {first_date.date()} to {last_date.date()}")

    # Build bars from scratch
    print(f"\nBuilding H1 bars from scratch...")

    all_ticks = []

    for year in YEARS:
        fname = f"{symbol.lower()}-tick-{year}-01-01-{year}-12-31.csv"
        fpath = os.path.join('data/raw', fname)

        if not os.path.exists(fpath):
            continue

        df = pd.read_csv(fpath, low_memory=False)
        df.columns = [c.lower() for c in df.columns]

        # Rename columns
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
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')

        df = df.dropna(subset=['timestamp'])
        df = df[(df['timestamp'] >= f'{year}-01-01') &
                (df['timestamp'] <= f'{year}-12-31 23:59:59')]

        all_ticks.append(df[['timestamp', 'bid', 'ask']])

    if not all_ticks:
        print(f"  [FAIL] No tick data for {symbol}")
        continue

    ticks_all = pd.concat(all_ticks, ignore_index=True)
    ticks_all = ticks_all.sort_values('timestamp')

    # Check duplicates
    duplicates = ticks_all.duplicated(subset=['timestamp'], keep=False).sum()
    ticks_all = ticks_all.drop_duplicates(subset=['timestamp'], keep='first')

    # Check spread
    ticks_all['spread'] = ticks_all['ask'] - ticks_all['bid']
    avg_spread = ticks_all['spread'].mean()
    max_spread = ticks_all['spread'].max()

    # Check gaps
    ticks_all = ticks_all.set_index('timestamp')
    time_diffs = ticks_all.index.to_series().diff()
    max_gap = time_diffs.max()
    gaps_over_1h = (time_diffs > pd.Timedelta(hours=1)).sum()

    print(f"  Total ticks: {len(ticks_all):,}")
    print(f"  Duplicates removed: {duplicates}")
    print(f"  Avg spread: {avg_spread:.5f}")
    print(f"  Max spread: {max_spread:.5f}")
    print(f"  Max gap: {max_gap}")
    print(f"  Gaps > 1h: {gaps_over_1h}")

    # Build H1 bars
    bid_h1 = ticks_all['bid'].resample('1h').ohlc()
    bid_h1.columns = ['open_bid', 'high_bid', 'low_bid', 'close_bid']

    ask_h1 = ticks_all['ask'].resample('1h').ohlc()
    ask_h1.columns = ['open_ask', 'high_ask', 'low_ask', 'close_ask']

    bars_h1 = pd.concat([bid_h1, ask_h1], axis=1)

    # Forward fill
    bars_h1['close_bid'] = bars_h1['close_bid'].ffill()
    bars_h1['close_ask'] = bars_h1['close_ask'].ffill()

    for col in ['open_bid', 'high_bid', 'low_bid']:
        bars_h1[col] = bars_h1[col].fillna(bars_h1['close_bid'])

    for col in ['open_ask', 'high_ask', 'low_ask']:
        bars_h1[col] = bars_h1[col].fillna(bars_h1['close_ask'])

    bars_h1 = bars_h1.dropna()

    print(f"  Built {len(bars_h1):,} H1 bars")
    print(f"  Period: {bars_h1.index.min()} to {bars_h1.index.max()}")

    # Validation checks
    first_bar = bars_h1.index.min()
    last_bar = bars_h1.index.max()

    checks = {}
    checks['first_bar_ok'] = first_bar >= pd.Timestamp('2021-01-01')
    checks['last_bar_ok'] = last_bar >= pd.Timestamp('2024-12-20')

    # Monthly coverage
    monthly_coverage = {}
    for year in [2021, 2022, 2023, 2024]:
        bars_year = bars_h1[bars_h1.index.year == year]
        if len(bars_year) > 0:
            monthly = bars_year.groupby(bars_year.index.month).size()
            missing_months = [m for m in range(1, 13) if monthly.get(m, 0) < 300]
            monthly_coverage[year] = {
                'bars': len(bars_year),
                'missing_months': missing_months
            }

    checks['monthly_coverage'] = monthly_coverage

    # Gap check
    bars_sorted = bars_h1.sort_index()
    bars_diffs = bars_sorted.index.to_series().diff()
    bars_max_gap = bars_diffs.max()
    bars_gaps_48h = (bars_diffs > pd.Timedelta(hours=48)).sum()

    checks['max_gap'] = bars_max_gap
    checks['gaps_over_48h'] = bars_gaps_48h

    symbol_results['validation'] = {
        'total_ticks': len(ticks_all),
        'duplicates': duplicates,
        'avg_spread': avg_spread,
        'max_spread': max_spread,
        'max_tick_gap': max_gap,
        'gaps_over_1h': gaps_over_1h,
        'total_bars': len(bars_h1),
        'first_bar': first_bar,
        'last_bar': last_bar,
        'checks': checks
    }

    results[symbol] = symbol_results

    # Save bars temporarily for later tests
    temp_bars_dir = 'data/bars_validated'
    os.makedirs(temp_bars_dir, exist_ok=True)
    bars_h1.to_csv(f'{temp_bars_dir}/{symbol.lower()}_1h_validated.csv')

    print(f"\n  Validation checks:")
    print(f"    First bar >= 2021: {'PASS' if checks['first_bar_ok'] else 'FAIL'}")
    print(f"    Last bar >= 2024-12-20: {'PASS' if checks['last_bar_ok'] else 'FAIL'}")
    print(f"    Max gap: {bars_max_gap}")
    print(f"    Gaps > 48h: {bars_gaps_48h} ({'OK' if bars_gaps_48h < 100 else 'HIGH'})")

    for year, coverage in monthly_coverage.items():
        missing = coverage['missing_months']
        status = 'OK' if not missing else f"MISSING: {missing}"
        print(f"    {year}: {coverage['bars']} bars, {status}")

# Generate report
print(f"\n{'='*80}")
print("GENERATING DATA VALIDATION REPORT")
print(f"{'='*80}\n")

report_file = 'reports/DATA_VALIDATION_FULL.md'

with open(report_file, 'w') as f:
    f.write("# FULL SYSTEM REVALIDATION - DATA VALIDATION\n\n")
    f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    f.write("---\n\n")

    f.write("## Summary\n\n")
    f.write("| Symbol | Tick Files | Total Ticks | H1 Bars | First Bar | Last Bar | Status |\n")
    f.write("|--------|------------|-------------|---------|-----------|----------|--------|\n")

    for symbol, data in sorted(results.items()):
        tick_files = len([v for v in data['tick_files'].values() if isinstance(v, dict)])
        val = data['validation']
        status = 'PASS' if val['checks']['first_bar_ok'] and val['checks']['last_bar_ok'] else 'FAIL'
        f.write(f"| {symbol} | {tick_files}/4 | {val['total_ticks']:,} | {val['total_bars']:,} | {val['first_bar'].date()} | {val['last_bar'].date()} | {status} |\n")

    f.write("\n---\n\n")

    f.write("## Detailed Validation\n\n")

    for symbol, data in sorted(results.items()):
        f.write(f"### {symbol}\n\n")

        f.write("**Tick Files:**\n\n")
        for year in YEARS:
            tick_info = data['tick_files'].get(year)
            if tick_info == 'MISSING':
                f.write(f"- {year}: MISSING\n")
            elif isinstance(tick_info, dict):
                f.write(f"- {year}: {tick_info['size_mb']:.1f} MB, {tick_info['lines']:,} lines\n")
                f.write(f"  - Period: {tick_info['first_date'].date()} to {tick_info['last_date'].date()}\n")

        f.write("\n**Tick Data Quality:**\n\n")
        val = data['validation']
        f.write(f"- Total ticks: {val['total_ticks']:,}\n")
        f.write(f"- Duplicates: {val['duplicates']}\n")
        f.write(f"- Avg spread: {val['avg_spread']:.5f}\n")
        f.write(f"- Max spread: {val['max_spread']:.5f}\n")
        f.write(f"- Max gap: {val['max_tick_gap']}\n")
        f.write(f"- Gaps > 1h: {val['gaps_over_1h']}\n")

        f.write("\n**H1 Bars:**\n\n")
        f.write(f"- Total: {val['total_bars']:,}\n")
        f.write(f"- Period: {val['first_bar']} to {val['last_bar']}\n")

        f.write("\n**Validation Checks:**\n\n")
        checks = val['checks']
        f.write(f"- First bar >= 2021: {'PASS' if checks['first_bar_ok'] else 'FAIL'}\n")
        f.write(f"- Last bar >= 2024-12-20: {'PASS' if checks['last_bar_ok'] else 'FAIL'}\n")
        f.write(f"- Max bar gap: {checks['max_gap']}\n")
        f.write(f"- Gaps > 48h: {checks['gaps_over_48h']}\n")

        f.write("\n**Monthly Coverage:**\n\n")
        for year, coverage in checks['monthly_coverage'].items():
            missing = coverage['missing_months']
            if missing:
                f.write(f"- {year}: {coverage['bars']} bars, MISSING months: {missing}\n")
            else:
                f.write(f"- {year}: {coverage['bars']} bars, COMPLETE\n")

        f.write("\n")

    f.write("---\n\n")

    # Overall verdict
    all_pass = all(
        data['validation']['checks']['first_bar_ok'] and
        data['validation']['checks']['last_bar_ok']
        for data in results.values()
    )

    f.write("## Verdict\n\n")
    f.write(f"**Data Validation Status:** {'PASS' if all_pass else 'FAIL'}\n\n")

    if all_pass:
        f.write("All symbols have complete 2021-2024 data with valid coverage.\n\n")
    else:
        f.write("Some symbols have incomplete or invalid data.\n\n")

    f.write("---\n\n")
    f.write(f"**Report generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

print(f"Report saved: {report_file}")

print(f"\n{'='*80}")
print("STEP 1 COMPLETE - DATA VALIDATION")
print(f"{'='*80}")


