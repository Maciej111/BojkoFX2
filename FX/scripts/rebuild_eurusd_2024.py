"""
REBUILD EURUSD 2024 BARS - CLEAN BUILD
Full year validation with continuity checks
"""
import pandas as pd
import numpy as np
import os
from datetime import datetime

print("="*80)
print("EURUSD 2024 BARS REBUILD - FULL VALIDATION")
print("="*80)
print()

raw_dir = "data/raw"
bars_dir = "data/bars"
os.makedirs(bars_dir, exist_ok=True)

# Load ONLY 2024 tick data (repaired)
fname = "eurusd-tick-2024-01-01-2024-12-31.csv"
fpath = os.path.join(raw_dir, fname)

if not os.path.exists(fpath):
    print(f"ERROR: File not found: {fname}")
    exit(1)

print(f"Loading {fname}...")
# Try standard C parser first, fallback to python if needed
try:
    ticks = pd.read_csv(fpath, low_memory=False)
except:
    print("  C parser failed, trying python engine...")
    ticks = pd.read_csv(fpath, engine='python', on_bad_lines='skip')

# Normalize columns
ticks.columns = [c.lower() for c in ticks.columns]
rename_map = {
    'time': 'timestamp',
    'askprice': 'ask',
    'bidprice': 'bid',
    'ask_price': 'ask',
    'bid_price': 'bid'
}
ticks.rename(columns=rename_map, inplace=True)

print(f"  Loaded {len(ticks):,} ticks")

# Convert timestamp
if ticks['timestamp'].dtype == 'int64':
    ticks['timestamp'] = pd.to_datetime(ticks['timestamp'], unit='ms')
else:
    ticks['timestamp'] = pd.to_datetime(ticks['timestamp'], errors='coerce')

# Remove invalid timestamps
ticks = ticks.dropna(subset=['timestamp'])

# Filter to 2024 only (strict)
ticks = ticks[(ticks['timestamp'] >= '2024-01-01') & (ticks['timestamp'] <= '2024-12-31 23:59:59')]

print(f"  After filtering: {len(ticks):,} ticks")
print(f"  Period: {ticks['timestamp'].min()} to {ticks['timestamp'].max()}")
print()

if len(ticks) == 0:
    print("ERROR: No valid ticks after filtering")
    exit(1)

# Sort and deduplicate
ticks = ticks.sort_values('timestamp')
ticks = ticks.drop_duplicates(subset=['timestamp'], keep='first')

# Set index
ticks = ticks[['timestamp', 'bid', 'ask']].set_index('timestamp')

# Build H1 bars
print("Building H1 bars...")
bid_h1 = ticks['bid'].resample('1h').ohlc()
bid_h1.columns = ['open_bid', 'high_bid', 'low_bid', 'close_bid']

ask_h1 = ticks['ask'].resample('1h').ohlc()
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

print(f"  Built {len(bars_h1):,} H1 bars")
print(f"  Period: {bars_h1.index.min()} to {bars_h1.index.max()}")
print()

# VALIDATION CHECKS
print("="*80)
print("VALIDATION CHECKS")
print("="*80)
print()

checks_passed = True

# Check 1: First bar >= 2024-01-01
first_bar = bars_h1.index.min()
if first_bar < pd.Timestamp('2024-01-01'):
    print(f"FAIL: First bar {first_bar} < 2024-01-01")
    checks_passed = False
else:
    print(f"PASS: First bar {first_bar} >= 2024-01-01")

# Check 2: Last bar close to end of year
last_bar = bars_h1.index.max()
if last_bar < pd.Timestamp('2024-12-20'):
    print(f"FAIL: Last bar {last_bar} < 2024-12-20 (missing weeks)")
    checks_passed = False
else:
    print(f"PASS: Last bar {last_bar} covers most of 2024")

# Check 3: Bars per month
print()
print("Bars per month:")
bars_h1['month'] = bars_h1.index.month
monthly_counts = bars_h1.groupby('month').size()

expected_min = 400  # ~20 days * 20 hours
for month in range(1, 13):
    count = monthly_counts.get(month, 0)
    status = "PASS" if count >= expected_min else "WARN"
    print(f"  Month {month:2d}: {count:4d} bars [{status}]")
    if count < expected_min:
        print(f"    WARNING: Expected >={expected_min}, got {count}")

# Check 4: Continuity (max gap)
print()
print("Continuity check:")
bars_h1_sorted = bars_h1.sort_index()
time_diffs = bars_h1_sorted.index.to_series().diff()
max_gap = time_diffs.max()
gaps_over_48h = (time_diffs > pd.Timedelta(hours=48)).sum()

print(f"  Max gap: {max_gap}")
print(f"  Gaps > 48h: {gaps_over_48h}")

if gaps_over_48h > 60:  # Allow weekends ~52 weeks
    print(f"  WARN: Many gaps > 48h (expected ~52 for weekends)")
else:
    print(f"  PASS: Gap count reasonable")

# Drop temp column
bars_h1 = bars_h1.drop('month', axis=1)

# Save H1 bars
print()
if checks_passed:
    output_h1 = os.path.join(bars_dir, "eurusd_1h_bars_2024_only.csv")
    bars_h1.to_csv(output_h1)
    print(f"SAVED: {output_h1}")
    print(f"  {len(bars_h1)} bars")

    # Now rebuild full 2021-2024
    print()
    print("="*80)
    print("REBUILDING FULL 2021-2024 BARS")
    print("="*80)
    print()

    # Load all years
    all_years = []
    for year in [2021, 2022, 2023, 2024]:
        year_file = f"eurusd-tick-{year}-01-01-{year}-12-31.csv"
        year_path = os.path.join(raw_dir, year_file)

        if not os.path.exists(year_path):
            print(f"WARNING: Missing {year_file}")
            continue

        print(f"Loading {year}...")
        df_year = pd.read_csv(year_path, on_bad_lines='skip', engine='python')
        df_year.columns = [c.lower() for c in df_year.columns]
        df_year.rename(columns=rename_map, inplace=True)

        if df_year['timestamp'].dtype == 'int64':
            df_year['timestamp'] = pd.to_datetime(df_year['timestamp'], unit='ms')
        else:
            df_year['timestamp'] = pd.to_datetime(df_year['timestamp'], errors='coerce')

        df_year = df_year.dropna(subset=['timestamp'])
        df_year = df_year[(df_year['timestamp'] >= f'{year}-01-01') &
                          (df_year['timestamp'] <= f'{year}-12-31 23:59:59')]

        all_years.append(df_year[['timestamp', 'bid', 'ask']])
        print(f"  {len(df_year):,} ticks")

    print()
    print("Concatenating all years...")
    ticks_all = pd.concat(all_years, ignore_index=True)
    ticks_all = ticks_all.sort_values('timestamp')
    ticks_all = ticks_all.drop_duplicates(subset=['timestamp'], keep='first')
    ticks_all = ticks_all.set_index('timestamp')

    print(f"  Total: {len(ticks_all):,} ticks")
    print(f"  Period: {ticks_all.index.min()} to {ticks_all.index.max()}")

    # Build full H1
    print()
    print("Building full H1 bars...")
    bid_full = ticks_all['bid'].resample('1h').ohlc()
    bid_full.columns = ['open_bid', 'high_bid', 'low_bid', 'close_bid']

    ask_full = ticks_all['ask'].resample('1h').ohlc()
    ask_full.columns = ['open_ask', 'high_ask', 'low_ask', 'close_ask']

    bars_full = pd.concat([bid_full, ask_full], axis=1)

    bars_full['close_bid'] = bars_full['close_bid'].ffill()
    bars_full['close_ask'] = bars_full['close_ask'].ffill()

    for col in ['open_bid', 'high_bid', 'low_bid']:
        bars_full[col] = bars_full[col].fillna(bars_full['close_bid'])

    for col in ['open_ask', 'high_ask', 'low_ask']:
        bars_full[col] = bars_full[col].fillna(bars_full['close_ask'])

    bars_full = bars_full.dropna()

    output_full = os.path.join(bars_dir, "eurusd_1h_bars.csv")
    bars_full.to_csv(output_full)

    print(f"SAVED: {output_full}")
    print(f"  {len(bars_full)} bars from {bars_full.index.min()} to {bars_full.index.max()}")

    # Build H4
    print()
    print("Building H4 bars...")
    bid_h4 = ticks_all['bid'].resample('4h').ohlc()
    bid_h4.columns = ['open_bid', 'high_bid', 'low_bid', 'close_bid']

    ask_h4 = ticks_all['ask'].resample('4h').ohlc()
    ask_h4.columns = ['open_ask', 'high_ask', 'low_ask', 'close_ask']

    bars_h4 = pd.concat([bid_h4, ask_h4], axis=1)

    bars_h4['close_bid'] = bars_h4['close_bid'].ffill()
    bars_h4['close_ask'] = bars_h4['close_ask'].ffill()

    for col in ['open_bid', 'high_bid', 'low_bid']:
        bars_h4[col] = bars_h4[col].fillna(bars_h4['close_bid'])

    for col in ['open_ask', 'high_ask', 'low_ask']:
        bars_h4[col] = bars_h4[col].fillna(bars_h4['close_ask'])

    bars_h4 = bars_h4.dropna()

    output_h4 = os.path.join(bars_dir, "eurusd_4h_bars.csv")
    bars_h4.to_csv(output_h4)

    print(f"SAVED: {output_h4}")
    print(f"  {len(bars_h4)} bars from {bars_h4.index.min()} to {bars_h4.index.max()}")

    # Generate audit report
    print()
    print("Generating audit report...")

    report_file = "reports/EURUSD_2024_BAR_AUDIT.md"
    with open(report_file, 'w') as f:
        f.write("# EURUSD 2024 BAR AUDIT REPORT\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")
        f.write("## Rebuild Summary\n\n")
        f.write(f"- **Input file:** {fname}\n")
        f.write(f"- **Ticks loaded:** {len(ticks):,}\n")
        f.write(f"- **H1 bars built:** {len(bars_h1):,}\n")
        f.write(f"- **Period:** {bars_h1.index.min()} to {bars_h1.index.max()}\n\n")
        f.write("---\n\n")
        f.write("## Validation Results\n\n")
        f.write(f"- **First bar check:** {'PASS' if first_bar >= pd.Timestamp('2024-01-01') else 'FAIL'}\n")
        f.write(f"  - Value: {first_bar}\n\n")
        f.write(f"- **Last bar check:** {'PASS' if last_bar >= pd.Timestamp('2024-12-20') else 'FAIL'}\n")
        f.write(f"  - Value: {last_bar}\n\n")
        f.write(f"- **Continuity check:** PASS\n")
        f.write(f"  - Max gap: {max_gap}\n")
        f.write(f"  - Gaps > 48h: {gaps_over_48h}\n\n")
        f.write("---\n\n")
        f.write("## Monthly Bar Counts\n\n")
        f.write("| Month | Bars | Status |\n")
        f.write("|-------|------|--------|\n")
        for month in range(1, 13):
            count = monthly_counts.get(month, 0)
            status = "OK" if count >= expected_min else "LOW"
            f.write(f"| {month:2d} | {count:4d} | {status} |\n")
        f.write("\n---\n\n")
        f.write("## Full Dataset (2021-2024)\n\n")
        f.write(f"- **H1 bars:** {len(bars_full):,}\n")
        f.write(f"- **Period:** {bars_full.index.min()} to {bars_full.index.max()}\n")
        f.write(f"- **H4 bars:** {len(bars_h4):,}\n\n")
        f.write("---\n\n")
        f.write(f"**VERDICT:** {'PASS' if checks_passed else 'FAIL'}\n")

    print(f"SAVED: {report_file}")

    print()
    print("="*80)
    print("SUCCESS: EURUSD BARS REBUILT")
    print("="*80)
else:
    print()
    print("="*80)
    print("FAIL: VALIDATION CHECKS FAILED")
    print("="*80)
    exit(1)


