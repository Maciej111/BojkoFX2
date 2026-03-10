"""
Build H1 and H4 bars from tick data for multiple symbols.
Used for multi-symbol robustness testing.
"""

import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config import load_config


def build_bars_for_symbol(symbol: str, raw_dir: str, bars_dir: str, timeframes: list):
    """
    Build bars from tick data for a single symbol.

    Args:
        symbol: Symbol name (e.g., 'EURUSD')
        raw_dir: Directory containing raw tick CSV files
        bars_dir: Output directory for bars
        timeframes: List of timeframes to build (e.g., ['1H', '4H'])
    """
    print(f"\n{'='*60}")
    print(f"Processing {symbol}")
    print(f"{'='*60}")

    # Find tick files for this symbol
    symbol_lower = symbol.lower()
    tick_files = []

    for file in os.listdir(raw_dir):
        if file.startswith(symbol_lower) and file.endswith('.csv'):
            tick_files.append(os.path.join(raw_dir, file))

    if not tick_files:
        print(f"⚠ No tick files found for {symbol}")
        return False

    print(f"Found {len(tick_files)} tick file(s)")

    # Read and concatenate all tick files
    dfs = []

    for tick_file in sorted(tick_files):
        print(f"Reading {os.path.basename(tick_file)}...")
        try:
            df = pd.read_csv(tick_file)

            # Normalize column names
            df.columns = [c.lower() for c in df.columns]

            # Rename variations
            rename_map = {
                'time': 'timestamp',
                'askprice': 'ask',
                'bidprice': 'bid',
                'ask_price': 'ask',
                'bid_price': 'bid'
            }
            df.rename(columns=rename_map, inplace=True)

            # If no timestamp column, assume first column
            if 'timestamp' not in df.columns:
                if df.shape[1] >= 3:
                    df.columns = ['timestamp', 'ask', 'bid'] + list(df.columns[3:])

            # Convert timestamp
            if df['timestamp'].dtype == 'int64':
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            else:
                df['timestamp'] = pd.to_datetime(df['timestamp'])

            # Validate bid/ask columns
            if 'bid' not in df.columns or 'ask' not in df.columns:
                print(f"  ⚠ Missing bid/ask columns in {os.path.basename(tick_file)}")
                continue

            dfs.append(df[['timestamp', 'bid', 'ask']])

        except Exception as e:
            print(f"  ⚠ Error reading {os.path.basename(tick_file)}: {e}")
            continue

    if not dfs:
        print(f"⚠ No valid tick data loaded for {symbol}")
        return False

    # Concatenate all data
    print(f"Concatenating {len(dfs)} dataframes...")
    ticks = pd.concat(dfs, ignore_index=True)

    # Sort by timestamp
    ticks.sort_values('timestamp', inplace=True)

    # Remove duplicates
    ticks.drop_duplicates(subset=['timestamp'], keep='first', inplace=True)

    print(f"✓ Loaded {len(ticks):,} ticks from {ticks['timestamp'].min()} to {ticks['timestamp'].max()}")

    # Set index
    ticks.set_index('timestamp', inplace=True)

    # Build bars for each timeframe
    for tf in timeframes:
        print(f"\nBuilding {tf} bars...")

        try:
            # Resample BID
            bid_ohlc = ticks['bid'].resample(tf).ohlc()
            bid_ohlc.columns = ['open_bid', 'high_bid', 'low_bid', 'close_bid']

            # Resample ASK
            ask_ohlc = ticks['ask'].resample(tf).ohlc()
            ask_ohlc.columns = ['open_ask', 'high_ask', 'low_ask', 'close_ask']

            # Combine
            bars = pd.concat([bid_ohlc, ask_ohlc], axis=1)

            # Forward fill NaN bars (no ticks in period)
            bars['close_bid'] = bars['close_bid'].ffill()
            bars['close_ask'] = bars['close_ask'].ffill()

            for col in ['open_bid', 'high_bid', 'low_bid']:
                bars[col] = bars[col].fillna(bars['close_bid'])

            for col in ['open_ask', 'high_ask', 'low_ask']:
                bars[col] = bars[col].fillna(bars['close_ask'])

            # Drop any remaining NaNs
            bars.dropna(inplace=True)

            # Save
            tf_str = tf.lower().replace('h', 'h')  # '1H' -> '1h', '4H' -> '4h'
            output_file = os.path.join(bars_dir, f"{symbol_lower}_{tf_str}_bars.csv")
            bars.to_csv(output_file)

            print(f"✓ Saved {len(bars):,} bars to {output_file}")
            print(f"  Period: {bars.index.min()} to {bars.index.max()}")

        except Exception as e:
            print(f"⚠ Error building {tf} bars: {e}")
            continue

    return True


def main():
    """Build bars for all available symbols."""

    print("="*60)
    print("MULTI-SYMBOL BAR BUILDER")
    print("="*60)

    # Load config
    config = load_config()
    raw_dir = config['data']['raw_dir']
    bars_dir = config['data']['bars_dir']

    # Ensure bars directory exists
    os.makedirs(bars_dir, exist_ok=True)

    # Symbols to process (as confirmed by user)
    symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']

    # Timeframes to build
    timeframes = ['1h', '4h']

    print(f"\nSymbols: {', '.join(symbols)}")
    print(f"Timeframes: {', '.join(timeframes)}")
    print(f"Raw data dir: {raw_dir}")
    print(f"Output dir: {bars_dir}")

    # Process each symbol
    results = {}

    for symbol in symbols:
        success = build_bars_for_symbol(symbol, raw_dir, bars_dir, timeframes)
        results[symbol] = success

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    for symbol, success in results.items():
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"{symbol}: {status}")

    successful = sum(1 for s in results.values() if s)
    print(f"\nTotal: {successful}/{len(symbols)} symbols processed successfully")

    if successful == len(symbols):
        print("\n✅ All symbols processed successfully!")
    else:
        print(f"\n⚠ {len(symbols) - successful} symbol(s) failed")


if __name__ == "__main__":
    main()


