import pandas as pd
import numpy as np
import os
import sys

# To support being run as a script or module
try:
    from src.utils.config import load_config
except ImportError:
    # Add project root to sys path
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
    from src.utils.config import load_config

def ticks_to_bars():
    config = load_config()
    raw_dir = config['data']['raw_dir']
    bars_dir = config['data']['bars_dir']
    symbol = config['data']['symbol']
    # timeframe = config['data']['timeframe']  # e.g. "15min"

    # We will resample to 15min.
    # Pandas uses '15min' or '15T'
    timeframe = '15min'

    # Find the latest tick file
    # For simplicity, let's assume one file or pick the latest modified
    files = [f for f in os.listdir(raw_dir) if f.endswith(".csv")]
    if not files:
        print("No tick files found in raw_dir.")
        return

    tick_file = os.path.join(raw_dir, files[0]) # pick first for now
    print(f"Processing {tick_file}...")

    # Duckascopy node format usually: time, ask, bid, askVolume, bidVolume
    # Time is in ms since epoch usually.
    # But let's check format. It depends on args.
    # Assuming CSV has headers. If not, we need to inspect.
    # Usually: 'timestamp', 'ask', 'bid', 'askVolume', 'bidVolume'

    # Let's read a few lines to be sure or assume standard
    # Assuming standard for now.

    try:
        df = pd.read_csv(tick_file)

        # Normalize column names to lowercase
        df.columns = [c.lower() for c in df.columns]

        # Mapping variations to standard names
        rename_map = {
            'time': 'timestamp',
            'askprice': 'ask',
            'bidprice': 'bid',
            'ask_price': 'ask',
            'bid_price': 'bid'
        }
        df.rename(columns=rename_map, inplace=True)

        if 'timestamp' not in df.columns:
            # Fallback for headerless: assume time, ask, bid, aVol, bVol
            df = pd.read_csv(tick_file, header=None, names=['timestamp', 'ask', 'bid', 'av', 'bv'])

        # Convert timestamp
        # Check if ms or string
        if df['timestamp'].dtype == 'int64':
             df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        else:
             df['timestamp'] = pd.to_datetime(df['timestamp'])

        df.set_index('timestamp', inplace=True)

        # Resample - explicitly use '15min' as per config but hardcoded for now to match file
        # The user requested '15min' in plan.
        # Ensure we have bid and ask columns
        if 'bid' not in df.columns or 'ask' not in df.columns:
            raise ValueError("CSV must contain 'bid' and 'ask' columns")

        # Resample Bid
        bid_ohlc = df['bid'].resample(timeframe).ohlc()
        bid_ohlc.columns = ['open_bid', 'high_bid', 'low_bid', 'close_bid']

        # Resample Ask
        ask_ohlc = df['ask'].resample(timeframe).ohlc()
        ask_ohlc.columns = ['open_ask', 'high_ask', 'low_ask', 'close_ask']

        bars = pd.concat([bid_ohlc, ask_ohlc], axis=1)

        # Forward fill empty bars
        # Logic: If no ticks, OHLC = previous Close

        # 1. Forward fill Close
        bars['close_bid'] = bars['close_bid'].ffill()
        bars['close_ask'] = bars['close_ask'].ffill()

        # 2. Backfill Open/High/Low from filled Close (for rows that were NaN)
        # However, we only do this where Open is NaN
        for col in ['open_bid', 'high_bid', 'low_bid']:
            bars[col] = bars[col].fillna(bars['close_bid'])

        for col in ['open_ask', 'high_ask', 'low_ask']:
            bars[col] = bars[col].fillna(bars['close_ask'])

        # Drop any remaining NaNs (at the start)
        bars.dropna(inplace=True)

        # Save
        output_file = os.path.join(bars_dir, f"{symbol}_m15_bars.csv")
        bars.to_csv(output_file)
        print(f"Bars saved to {output_file}")

    except Exception as e:
        print(f"Error processing ticks: {e}")

if __name__ == "__main__":
    ticks_to_bars()
