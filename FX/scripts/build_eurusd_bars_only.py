"""
Build H1 and H4 bars for EURUSD from tick data (2021-2024 full year)
"""
import pandas as pd
import os

print("="*60)
print("BUILDING EURUSD BARS")
print("="*60)
print()

raw_dir = "data/raw"
bars_dir = "data/bars"
os.makedirs(bars_dir, exist_ok=True)

# Files to load
files = [
    "eurusd-tick-2021-01-01-2021-12-31.csv",
    "eurusd-tick-2022-01-01-2022-12-31.csv",
    "eurusd-tick-2023-01-01-2023-12-31.csv",
    "eurusd-tick-2024-01-01-2024-12-31.csv"
]

print("Loading tick files...")
dfs = []

for fname in files:
    fpath = os.path.join(raw_dir, fname)
    if os.path.exists(fpath):
        print(f"  Reading {fname}...")
        # Skip bad lines in CSV
        df = pd.read_csv(fpath, on_bad_lines='skip', engine='python')
        df.columns = [c.lower() for c in df.columns]

        # Rename columns
        rename_map = {
            'time': 'timestamp',
            'askprice': 'ask',
            'bidprice': 'bid'
        }
        df.rename(columns=rename_map, inplace=True)

        # Convert timestamp
        if df['timestamp'].dtype == 'int64':
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        else:
            df['timestamp'] = pd.to_datetime(df['timestamp'])

        dfs.append(df[['timestamp', 'bid', 'ask']])
        print(f"    ✓ {len(df):,} ticks")
    else:
        print(f"    ⚠ File not found: {fname}")

if not dfs:
    print("\n❌ No tick data loaded")
    exit(1)

# Concatenate
print(f"\nConcatenating {len(dfs)} dataframes...")
ticks = pd.concat(dfs, ignore_index=True)
ticks.sort_values('timestamp', inplace=True)
ticks.drop_duplicates(subset=['timestamp'], keep='first', inplace=True)

print(f"✓ Total ticks: {len(ticks):,}")
print(f"  Period: {ticks['timestamp'].min()} to {ticks['timestamp'].max()}")
print()

# Set index
ticks.set_index('timestamp', inplace=True)

# Build H1 bars
print("Building H1 bars...")
bid_ohlc = ticks['bid'].resample('1h').ohlc()
bid_ohlc.columns = ['open_bid', 'high_bid', 'low_bid', 'close_bid']

ask_ohlc = ticks['ask'].resample('1h').ohlc()
ask_ohlc.columns = ['open_ask', 'high_ask', 'low_ask', 'close_ask']

bars_1h = pd.concat([bid_ohlc, ask_ohlc], axis=1)

# Forward fill NaNs
bars_1h['close_bid'] = bars_1h['close_bid'].ffill()
bars_1h['close_ask'] = bars_1h['close_ask'].ffill()

for col in ['open_bid', 'high_bid', 'low_bid']:
    bars_1h[col] = bars_1h[col].fillna(bars_1h['close_bid'])

for col in ['open_ask', 'high_ask', 'low_ask']:
    bars_1h[col] = bars_1h[col].fillna(bars_1h['close_ask'])

bars_1h.dropna(inplace=True)

output_1h = os.path.join(bars_dir, "eurusd_1h_bars.csv")
bars_1h.to_csv(output_1h)
print(f"✓ Saved {len(bars_1h):,} bars to {output_1h}")
print(f"  Period: {bars_1h.index.min()} to {bars_1h.index.max()}")
print()

# Build H4 bars
print("Building H4 bars...")
bid_ohlc_4h = ticks['bid'].resample('4h').ohlc()
bid_ohlc_4h.columns = ['open_bid', 'high_bid', 'low_bid', 'close_bid']

ask_ohlc_4h = ticks['ask'].resample('4h').ohlc()
ask_ohlc_4h.columns = ['open_ask', 'high_ask', 'low_ask', 'close_ask']

bars_4h = pd.concat([bid_ohlc_4h, ask_ohlc_4h], axis=1)

# Forward fill NaNs
bars_4h['close_bid'] = bars_4h['close_bid'].ffill()
bars_4h['close_ask'] = bars_4h['close_ask'].ffill()

for col in ['open_bid', 'high_bid', 'low_bid']:
    bars_4h[col] = bars_4h[col].fillna(bars_4h['close_bid'])

for col in ['open_ask', 'high_ask', 'low_ask']:
    bars_4h[col] = bars_4h[col].fillna(bars_4h['close_ask'])

bars_4h.dropna(inplace=True)

output_4h = os.path.join(bars_dir, "eurusd_4h_bars.csv")
bars_4h.to_csv(output_4h)
print(f"✓ Saved {len(bars_4h):,} bars to {output_4h}")
print(f"  Period: {bars_4h.index.min()} to {bars_4h.index.max()}")
print()

print("="*60)
print("✅ BARS BUILT SUCCESSFULLY")
print("="*60)


