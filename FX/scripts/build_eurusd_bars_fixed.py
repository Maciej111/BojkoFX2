"""
Build EURUSD bars - handle 2024 separately due to parsing errors
"""
import pandas as pd
import os
import warnings
warnings.filterwarnings('ignore')

print("="*60)
print("BUILDING EURUSD BARS (2021-2024)")
print("="*60)
print()

raw_dir = "data/raw"
bars_dir = "data/bars"
os.makedirs(bars_dir, exist_ok=True)

# Load years separately
all_ticks = []

for year in [2021, 2022, 2023, 2024]:
    fname = f"eurusd-tick-{year}-01-01-{year}-12-31.csv"
    fpath = os.path.join(raw_dir, fname)

    if not os.path.exists(fpath):
        print(f"⚠ File not found: {fname}")
        continue

    print(f"Reading {year}...")

    try:
        # For 2024, use more aggressive error handling
        if year == 2024:
            print(f"  Using error-tolerant mode for {year}...")
            # Read with skip bad lines
            df = pd.read_csv(fpath, on_bad_lines='skip', engine='python')
        else:
            df = pd.read_csv(fpath, low_memory=False)

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

        # Validate required columns
        if 'timestamp' not in df.columns or 'bid' not in df.columns or 'ask' not in df.columns:
            print(f"  ⚠ Missing required columns in {year}")
            continue

        # Convert timestamp
        if df['timestamp'].dtype == 'int64':
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        else:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')

        # Remove rows with invalid timestamps
        df = df.dropna(subset=['timestamp'])

        # Filter to valid date range (2020-2025)
        df = df[(df['timestamp'] >= '2020-01-01') & (df['timestamp'] <= '2025-12-31')]

        # Keep only needed columns
        df = df[['timestamp', 'bid', 'ask']]

        all_ticks.append(df)
        print(f"  ✓ {len(df):,} ticks from {df['timestamp'].min()} to {df['timestamp'].max()}")

    except Exception as e:
        print(f"  ❌ Error reading {year}: {e}")
        continue

if not all_ticks:
    print("\n❌ No data loaded")
    exit(1)

# Concatenate all years
print(f"\nConcatenating {len(all_ticks)} dataframes...")
ticks = pd.concat(all_ticks, ignore_index=True)

# Sort and deduplicate
print("Sorting and deduplicating...")
ticks = ticks.sort_values('timestamp')
ticks = ticks.drop_duplicates(subset=['timestamp'], keep='first')

print(f"✓ Total: {len(ticks):,} ticks")
print(f"  Period: {ticks['timestamp'].min()} to {ticks['timestamp'].max()}")
print()

# Set index
ticks.set_index('timestamp', inplace=True)

# Build H1
print("Building H1 bars...")
bid_h1 = ticks['bid'].resample('1h').ohlc()
bid_h1.columns = ['open_bid', 'high_bid', 'low_bid', 'close_bid']

ask_h1 = ticks['ask'].resample('1h').ohlc()
ask_h1.columns = ['open_ask', 'high_ask', 'low_ask', 'close_ask']

bars_h1 = pd.concat([bid_h1, ask_h1], axis=1)

# Fill NaNs
bars_h1['close_bid'] = bars_h1['close_bid'].ffill()
bars_h1['close_ask'] = bars_h1['close_ask'].ffill()

for col in ['open_bid', 'high_bid', 'low_bid']:
    bars_h1[col] = bars_h1[col].fillna(bars_h1['close_bid'])

for col in ['open_ask', 'high_ask', 'low_ask']:
    bars_h1[col] = bars_h1[col].fillna(bars_h1['close_ask'])

bars_h1 = bars_h1.dropna()

out_h1 = os.path.join(bars_dir, "eurusd_1h_bars.csv")
bars_h1.to_csv(out_h1)
print(f"✓ Saved {len(bars_h1):,} H1 bars")
print(f"  Period: {bars_h1.index.min()} to {bars_h1.index.max()}")
print()

# Build H4
print("Building H4 bars...")
bid_h4 = ticks['bid'].resample('4h').ohlc()
bid_h4.columns = ['open_bid', 'high_bid', 'low_bid', 'close_bid']

ask_h4 = ticks['ask'].resample('4h').ohlc()
ask_h4.columns = ['open_ask', 'high_ask', 'low_ask', 'close_ask']

bars_h4 = pd.concat([bid_h4, ask_h4], axis=1)

# Fill NaNs
bars_h4['close_bid'] = bars_h4['close_bid'].ffill()
bars_h4['close_ask'] = bars_h4['close_ask'].ffill()

for col in ['open_bid', 'high_bid', 'low_bid']:
    bars_h4[col] = bars_h4[col].fillna(bars_h4['close_bid'])

for col in ['open_ask', 'high_ask', 'low_ask']:
    bars_h4[col] = bars_h4[col].fillna(bars_h4['close_ask'])

bars_h4 = bars_h4.dropna()

out_h4 = os.path.join(bars_dir, "eurusd_4h_bars.csv")
bars_h4.to_csv(out_h4)
print(f"✓ Saved {len(bars_h4):,} H4 bars")
print(f"  Period: {bars_h4.index.min()} to {bars_h4.index.max()}")
print()

print("="*60)
print("✅ BARS BUILT SUCCESSFULLY")
print("="*60)


