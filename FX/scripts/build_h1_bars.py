"""
Build H1 bars directly from tick data.
"""
import pandas as pd
import os
import sys
import glob

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.utils.config import load_config


def build_h1_bars_from_ticks_silent(tick_file):
    """
    Build H1 bars from tick file (silent version for batch).
    Returns DataFrame instead of saving.
    """
    try:
        # Read ticks
        df = pd.read_csv(tick_file)

        # Normalize column names
        df.columns = [c.lower() for c in df.columns]

        # Mapping variations
        rename_map = {
            'time': 'timestamp',
            'askprice': 'ask',
            'bidprice': 'bid',
            'ask_price': 'ask',
            'bid_price': 'bid'
        }
        df.rename(columns=rename_map, inplace=True)

        # Check if timestamp is int64 (milliseconds) or string
        if df['timestamp'].dtype == 'int64':
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        else:
            df['timestamp'] = pd.to_datetime(df['timestamp'])

        df.set_index('timestamp', inplace=True)

        # Verify columns
        if 'bid' not in df.columns or 'ask' not in df.columns:
            raise ValueError("CSV must contain 'bid' and 'ask' columns")

        # Resample to H1
        bid_ohlc = df[['bid']].resample('1h').agg({
            'bid': ['first', 'max', 'min', 'last']
        })
        bid_ohlc.columns = ['open_bid', 'high_bid', 'low_bid', 'close_bid']

        ask_ohlc = df[['ask']].resample('1h').agg({
            'ask': ['first', 'max', 'min', 'last']
        })
        ask_ohlc.columns = ['open_ask', 'high_ask', 'low_ask', 'close_ask']

        # Combine
        bars = pd.concat([bid_ohlc, ask_ohlc], axis=1)

        # Forward fill
        bars['close_bid'] = bars['close_bid'].ffill()
        bars['close_ask'] = bars['close_ask'].ffill()

        for col in ['open_bid', 'high_bid', 'low_bid']:
            bars[col] = bars[col].fillna(bars['close_bid'])

        for col in ['open_ask', 'high_ask', 'low_ask']:
            bars[col] = bars[col].fillna(bars['close_ask'])

        # Drop rows with NaN
        bars.dropna(inplace=True)

        return bars

    except Exception as e:
        print(f"  ✗ Error processing {tick_file}: {e}")
        return None


def build_h1_bars_from_ticks(tick_file, output_file):
    # ...existing code...
    """
    Build H1 bars from tick data.

    Logic:
    - Open = first tick in hour
    - High = max in hour
    - Low = min in hour
    - Close = last tick in hour

    Args:
        tick_file: Path to tick CSV
        output_file: Path to output H1 bars CSV
    """
    print(f"Loading ticks from {tick_file}...")

    # Read ticks
    df = pd.read_csv(tick_file)

    # Normalize column names (like in tick_to_bars.py)
    df.columns = [c.lower() for c in df.columns]

    # Mapping variations
    rename_map = {
        'time': 'timestamp',
        'askprice': 'ask',
        'bidprice': 'bid',
        'ask_price': 'ask',
        'bid_price': 'bid'
    }
    df.rename(columns=rename_map, inplace=True)

    # Check if timestamp is int64 (milliseconds) or string
    if df['timestamp'].dtype == 'int64':
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    else:
        df['timestamp'] = pd.to_datetime(df['timestamp'])

    df.set_index('timestamp', inplace=True)

    # Verify columns
    if 'bid' not in df.columns or 'ask' not in df.columns:
        raise ValueError("CSV must contain 'bid' and 'ask' columns")

    print(f"Loaded {len(df)} ticks")

    # Resample to H1
    print("Resampling to H1...")

    # BID OHLC
    bid_ohlc = df[['bid']].resample('1h').agg({
        'bid': ['first', 'max', 'min', 'last']
    })
    bid_ohlc.columns = ['open_bid', 'high_bid', 'low_bid', 'close_bid']

    # ASK OHLC
    ask_ohlc = df[['ask']].resample('1h').agg({
        'ask': ['first', 'max', 'min', 'last']
    })
    ask_ohlc.columns = ['open_ask', 'high_ask', 'low_ask', 'close_ask']

    # Combine
    bars = pd.concat([bid_ohlc, ask_ohlc], axis=1)

    # Forward fill missing bars
    bars['close_bid'] = bars['close_bid'].ffill()
    bars['close_ask'] = bars['close_ask'].ffill()

    for col in ['open_bid', 'high_bid', 'low_bid']:
        bars[col] = bars[col].fillna(bars['close_bid'])

    for col in ['open_ask', 'high_ask', 'low_ask']:
        bars[col] = bars[col].fillna(bars['close_ask'])

    # Drop rows with NaN (beginning)
    bars.dropna(inplace=True)

    print(f"Generated {len(bars)} H1 bars")

    # Save
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    bars.to_csv(output_file)

    print(f"✓ Saved to {output_file}")

    return bars


def main():
    """Build H1 bars for EURUSD - all available tick files."""
    config = load_config()

    symbol = config['data']['symbol']
    raw_dir = config['data']['raw_dir']
    bars_dir = config['data']['bars_dir']

    # Find all tick files
    tick_files = glob.glob(os.path.join(raw_dir, f"{symbol}-tick-*.csv"))

    if not tick_files:
        print(f"✗ No tick files found in {raw_dir}")
        print("  Run: python scripts/download_historical_data.py")
        return

    print(f"\nFound {len(tick_files)} tick file(s):")
    for f in tick_files:
        print(f"  - {os.path.basename(f)}")

    # Combine all bars into one file
    all_bars = []

    for tick_file in sorted(tick_files):
        print(f"\nProcessing {os.path.basename(tick_file)}...")

        # Build H1 bars for this file
        bars = build_h1_bars_from_ticks_silent(tick_file)

        if bars is not None and len(bars) > 0:
            all_bars.append(bars)
            print(f"  ✓ Generated {len(bars)} H1 bars")

    if not all_bars:
        print("\n✗ No bars generated")
        return

    # Concatenate all bars
    print(f"\nCombining all bars...")
    combined = pd.concat(all_bars, axis=0)
    combined.sort_index(inplace=True)

    # Remove duplicates (if any overlap)
    combined = combined[~combined.index.duplicated(keep='first')]

    print(f"Total: {len(combined)} H1 bars")

    # Save
    output_file = os.path.join(bars_dir, f"{symbol}_h1_bars.csv")
    os.makedirs(bars_dir, exist_ok=True)
    combined.to_csv(output_file)

    print(f"\n✓ H1 bars saved to: {output_file}")
    print(f"  Date range: {combined.index[0]} to {combined.index[-1]}")
    print("\n✓ H1 bars ready for all years!")



if __name__ == "__main__":
    main()


