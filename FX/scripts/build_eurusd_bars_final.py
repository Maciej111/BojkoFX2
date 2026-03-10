"""
Build EURUSD bars after successful download
Full 2021-2024 dataset
"""
import pandas as pd
import numpy as np
import os
from datetime import datetime

print("="*80)
print("EURUSD BARS REBUILD - FULL 2021-2024")
print("="*80)
print()

raw_dir = "data/raw"
bars_dir = "data/bars"
os.makedirs(bars_dir, exist_ok=True)

# Load all years
all_ticks = []

for year in [2021, 2022, 2023, 2024]:
    fname = f"eurusd-tick-{year}-01-01-{year}-12-31.csv"
    fpath = os.path.join(raw_dir, fname)

    if not os.path.exists(fpath):
        print(f"WARNING: Missing {fname}")
        continue

    print(f"Loading {fname}...")

    try:
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

        # Remove invalid timestamps
        df = df.dropna(subset=['timestamp'])

        # Filter to correct year
        df = df[(df['timestamp'] >= f'{year}-01-01') &
                (df['timestamp'] <= f'{year}-12-31 23:59:59')]

        all_ticks.append(df[['timestamp', 'bid', 'ask']])
        print(f"  ✓ {len(df):,} ticks from {df['timestamp'].min()} to {df['timestamp'].max()}")

    except Exception as e:
        print(f"  ERROR: {e}")
        continue

if not all_ticks:
    print("\n❌ No data loaded")
    exit(1)

print()
print("Concatenating all years...")
ticks_all = pd.concat(all_ticks, ignore_index=True)
ticks_all = ticks_all.sort_values('timestamp')
ticks_all = ticks_all.drop_duplicates(subset=['timestamp'], keep='first')

print(f"  Total: {len(ticks_all):,} ticks")
print(f"  Period: {ticks_all['timestamp'].min()} to {ticks_all['timestamp'].max()}")
print()

# Set index
ticks_all = ticks_all.set_index('timestamp')

# Build H1
print("Building H1 bars...")
bid_h1 = ticks_all['bid'].resample('1h').ohlc()
bid_h1.columns = ['open_bid', 'high_bid', 'low_bid', 'close_bid']

ask_h1 = ticks_all['ask'].resample('1h').ohlc()
ask_h1.columns = ['open_ask', 'high_ask', 'low_ask', 'close_ask']

bars_h1 = pd.concat([bid_h1, ask_h1], axis=1)

# Forward fill NaNs
bars_h1['close_bid'] = bars_h1['close_bid'].ffill()
bars_h1['close_ask'] = bars_h1['close_ask'].ffill()

for col in ['open_bid', 'high_bid', 'low_bid']:
    bars_h1[col] = bars_h1[col].fillna(bars_h1['close_bid'])

for col in ['open_ask', 'high_ask', 'low_ask']:
    bars_h1[col] = bars_h1[col].fillna(bars_h1['close_ask'])

bars_h1 = bars_h1.dropna()

# Save H1
output_h1 = os.path.join(bars_dir, "eurusd_1h_bars.csv")

# Backup old file if exists
if os.path.exists(output_h1):
    backup_h1 = output_h1.replace('.csv', '_OLD.csv')
    if os.path.exists(backup_h1):
        os.remove(backup_h1)
    os.rename(output_h1, backup_h1)
    print(f"Backed up old H1 bars to: {backup_h1}")

bars_h1.to_csv(output_h1)
print(f"✓ Saved {len(bars_h1):,} H1 bars")
print(f"  Period: {bars_h1.index.min()} to {bars_h1.index.max()}")
print()

# Build H4
print("Building H4 bars...")
bid_h4 = ticks_all['bid'].resample('4h').ohlc()
bid_h4.columns = ['open_bid', 'high_bid', 'low_bid', 'close_bid']

ask_h4 = ticks_all['ask'].resample('4h').ohlc()
ask_h4.columns = ['open_ask', 'high_ask', 'low_ask', 'close_ask']

bars_h4 = pd.concat([bid_h4, ask_h4], axis=1)

# Forward fill NaNs
bars_h4['close_bid'] = bars_h4['close_bid'].ffill()
bars_h4['close_ask'] = bars_h4['close_ask'].ffill()

for col in ['open_bid', 'high_bid', 'low_bid']:
    bars_h4[col] = bars_h4[col].fillna(bars_h4['close_bid'])

for col in ['open_ask', 'high_ask', 'low_ask']:
    bars_h4[col] = bars_h4[col].fillna(bars_h4['close_ask'])

bars_h4 = bars_h4.dropna()

# Save H4
output_h4 = os.path.join(bars_dir, "eurusd_4h_bars.csv")

# Backup old file if exists
if os.path.exists(output_h4):
    backup_h4 = output_h4.replace('.csv', '_OLD.csv')
    if os.path.exists(backup_h4):
        os.remove(backup_h4)
    os.rename(output_h4, backup_h4)
    print(f"Backed up old H4 bars to: {backup_h4}")

bars_h4.to_csv(output_h4)
print(f"✓ Saved {len(bars_h4):,} H4 bars")
print(f"  Period: {bars_h4.index.min()} to {bars_h4.index.max()}")
print()

# Validation checks for 2024
print("="*80)
print("2024 DATA VALIDATION")
print("="*80)
print()

bars_2024 = bars_h1[bars_h1.index.year == 2024]
print(f"2024 H1 bars: {len(bars_2024)}")

if len(bars_2024) > 0:
    print(f"First: {bars_2024.index.min()}")
    print(f"Last:  {bars_2024.index.max()}")

    # Monthly distribution
    monthly = bars_2024.groupby(bars_2024.index.month).size()
    print()
    print("Monthly distribution:")
    for month in range(1, 13):
        count = monthly.get(month, 0)
        status = "✓" if count >= 300 else ("⚠" if count > 0 else "✗")
        month_name = datetime(2024, month, 1).strftime('%B')
        print(f"  {status} {month_name:12s}: {count:4d} bars")

    # Check completeness
    complete_months = sum(1 for c in monthly if c >= 300)
    print()
    if complete_months >= 11:
        print(f"✓ FULL YEAR: {complete_months}/12 months complete")
    elif complete_months >= 6:
        print(f"⚠ PARTIAL: {complete_months}/12 months complete")
    else:
        print(f"✗ INCOMPLETE: Only {complete_months}/12 months")
else:
    print("✗ NO 2024 DATA!")

print()
print("="*80)
print("BARS BUILD COMPLETE")
print("="*80)
print()
print(f"Files created:")
print(f"  - {output_h1}")
print(f"  - {output_h4}")
print()

# Generate report
report_file = "reports/EURUSD_BARS_REBUILD_FINAL.md"
with open(report_file, 'w') as f:
    f.write("# EURUSD BARS REBUILD - FINAL\n\n")
    f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    f.write("---\n\n")
    f.write("## Summary\n\n")
    f.write(f"- **Total ticks:** {len(ticks_all):,}\n")
    f.write(f"- **H1 bars:** {len(bars_h1):,}\n")
    f.write(f"- **H4 bars:** {len(bars_h4):,}\n")
    f.write(f"- **Period:** {bars_h1.index.min()} to {bars_h1.index.max()}\n\n")
    f.write("## 2024 Validation\n\n")
    f.write(f"- **2024 bars:** {len(bars_2024)}\n")
    if len(bars_2024) > 0:
        f.write(f"- **First:** {bars_2024.index.min()}\n")
        f.write(f"- **Last:** {bars_2024.index.max()}\n")
        f.write(f"- **Complete months:** {complete_months}/12\n\n")
        f.write("### Monthly Distribution\n\n")
        f.write("| Month | Bars | Status |\n")
        f.write("|-------|------|--------|\n")
        for month in range(1, 13):
            count = monthly.get(month, 0)
            status = "OK" if count >= 300 else ("Partial" if count > 0 else "Missing")
            month_name = datetime(2024, month, 1).strftime('%B')
            f.write(f"| {month_name} | {count} | {status} |\n")
    f.write("\n---\n\n")
    f.write("**Status:** ")
    if len(bars_2024) > 0 and complete_months >= 11:
        f.write("✓ SUCCESS - Full year data\n")
    elif len(bars_2024) > 0:
        f.write("⚠ PARTIAL - Some months missing\n")
    else:
        f.write("✗ FAILED - No 2024 data\n")

print(f"Report saved: {report_file}")

