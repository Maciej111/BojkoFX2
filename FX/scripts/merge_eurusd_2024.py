"""
Merge EURUSD 2024 tick data files (H1 and H2) into single file.
Validate data quality and completeness.
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime


def merge_eurusd_2024():
    """Merge EURUSD 2024 tick data files."""

    print("="*60)
    print("EURUSD 2024 DATA MERGER")
    print("="*60)

    raw_dir = "data/raw"

    # Files to merge
    file1 = os.path.join(raw_dir, "eurusd-tick-2024-01-01-2024-05-31.csv")
    file2 = os.path.join(raw_dir, "eurusd-tick-2024-06-01-2024-12-31.csv")

    # Check files exist
    if not os.path.exists(file1):
        print(f"❌ File not found: {file1}")
        return None

    if not os.path.exists(file2):
        print(f"❌ File not found: {file2}")
        return None

    print(f"\n📂 Reading file 1: {os.path.basename(file1)}")
    df1 = pd.read_csv(file1)

    # Normalize columns
    df1.columns = [c.lower() for c in df1.columns]
    rename_map = {
        'time': 'timestamp',
        'askprice': 'ask',
        'bidprice': 'bid',
        'ask_price': 'ask',
        'bid_price': 'bid'
    }
    df1.rename(columns=rename_map, inplace=True)

    # Convert timestamp
    if df1['timestamp'].dtype == 'int64':
        df1['timestamp'] = pd.to_datetime(df1['timestamp'], unit='ms')
    else:
        df1['timestamp'] = pd.to_datetime(df1['timestamp'])

    print(f"  ✓ Loaded {len(df1):,} ticks")
    print(f"    Period: {df1['timestamp'].min()} to {df1['timestamp'].max()}")

    print(f"\n📂 Reading file 2: {os.path.basename(file2)}")
    df2 = pd.read_csv(file2)

    # Normalize columns
    df2.columns = [c.lower() for c in df2.columns]
    df2.rename(columns=rename_map, inplace=True)

    # Convert timestamp
    if df2['timestamp'].dtype == 'int64':
        df2['timestamp'] = pd.to_datetime(df2['timestamp'], unit='ms')
    else:
        df2['timestamp'] = pd.to_datetime(df2['timestamp'])

    print(f"  ✓ Loaded {len(df2):,} ticks")
    print(f"    Period: {df2['timestamp'].min()} to {df2['timestamp'].max()}")

    # Concatenate
    print(f"\n🔗 Merging dataframes...")
    df = pd.concat([df1, df2], ignore_index=True)

    print(f"  ✓ Combined: {len(df):,} ticks")

    # Sort by timestamp
    print(f"\n📊 Sorting by timestamp...")
    df = df.sort_values('timestamp').reset_index(drop=True)

    is_sorted = df['timestamp'].is_monotonic_increasing
    print(f"  ✓ Data sorted: {'Yes' if is_sorted else 'No'}")

    # Check for duplicates
    print(f"\n🔍 Checking for duplicate timestamps...")
    duplicates = df.duplicated(subset=['timestamp'], keep=False)
    dup_count = duplicates.sum()

    if dup_count > 0:
        print(f"  ⚠ Found {dup_count} duplicate timestamps")
        print(f"  Removing duplicates (keeping first)...")
        df = df.drop_duplicates(subset=['timestamp'], keep='first')
        print(f"  ✓ After deduplication: {len(df):,} ticks")
    else:
        print(f"  ✓ No duplicates found")

    # Validate period
    first_tick = df['timestamp'].min()
    last_tick = df['timestamp'].max()

    print(f"\n📅 Final period:")
    print(f"  First tick: {first_tick}")
    print(f"  Last tick: {last_tick}")

    # Calculate days covered
    days_covered = (last_tick - first_tick).days + 1
    print(f"  Days covered: {days_covered}/366 (2024 is leap year)")
    print(f"  Completeness: {(days_covered/366)*100:.1f}%")

    # Spread statistics
    if 'ask' in df.columns and 'bid' in df.columns:
        df['spread'] = df['ask'] - df['bid']

        print(f"\n📈 Spread statistics:")
        print(f"  Mean spread: {df['spread'].mean():.5f}")
        print(f"  Median spread: {df['spread'].median():.5f}")
        print(f"  Min spread: {df['spread'].min():.5f}")
        print(f"  Max spread: {df['spread'].max():.5f}")

        # Drop temporary spread column
        df = df.drop('spread', axis=1)

    # Gap analysis
    print(f"\n🔍 Gap analysis...")
    df['time_diff'] = df['timestamp'].diff()

    max_gap = df['time_diff'].max()
    gaps_over_1h = (df['time_diff'] > pd.Timedelta(hours=1)).sum()

    print(f"  Max gap: {max_gap}")
    print(f"  Gaps > 1 hour: {gaps_over_1h}")

    if gaps_over_1h > 0:
        print(f"\n  Top 5 largest gaps:")
        top_gaps = df.nlargest(5, 'time_diff')[['timestamp', 'time_diff']]
        for idx, row in top_gaps.iterrows():
            print(f"    {row['timestamp']}: {row['time_diff']}")

    # Drop temporary time_diff column
    df = df.drop('time_diff', axis=1)

    # Save merged file
    output_file = os.path.join(raw_dir, "eurusd-tick-2024-01-01-2024-12-31.csv")
    print(f"\n💾 Saving to {os.path.basename(output_file)}...")
    df.to_csv(output_file, index=False)

    print(f"  ✓ Saved {len(df):,} ticks")

    # Generate quality report
    quality_report = {
        'total_ticks': len(df),
        'first_tick': first_tick,
        'last_tick': last_tick,
        'days_covered': days_covered,
        'completeness_pct': (days_covered/366)*100,
        'is_sorted': is_sorted,
        'duplicates_removed': dup_count,
        'max_gap': max_gap,
        'gaps_over_1h': gaps_over_1h,
        'output_file': output_file
    }

    if 'spread' in locals():
        quality_report['mean_spread'] = df['ask'].sub(df['bid']).mean()

    return quality_report


if __name__ == "__main__":
    result = merge_eurusd_2024()

    if result:
        print("\n" + "="*60)
        print("✅ MERGE COMPLETED SUCCESSFULLY")
        print("="*60)
        print(f"\nFinal statistics:")
        print(f"  Total ticks: {result['total_ticks']:,}")
        print(f"  Period: {result['first_tick']} to {result['last_tick']}")
        print(f"  Completeness: {result['completeness_pct']:.1f}%")
        print(f"  Data quality: ✓ Sorted, {result['duplicates_removed']} dups removed")
    else:
        print("\n❌ MERGE FAILED")

