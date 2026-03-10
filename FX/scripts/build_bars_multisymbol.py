"""
Build H1 bars from tick data for multiple symbols
"""
import pandas as pd
import os
import sys

sys.path.append('.')

from src.data_processing.tick_to_bars import build_bars_from_ticks

SYMBOLS = ['gbpusd', 'usdjpy', 'xauusd']
START_DATE = "2021-01-01"
END_DATE = "2024-12-31"

RAW_DIR = "data/raw"
BARS_DIR = "data/bars"

def build_bars_for_symbol(symbol):
    """Build H1 bars for one symbol"""
    print("="*80)
    print(f"Building H1 bars for {symbol.upper()}")
    print("="*80)

    # Check if tick file exists
    tick_filename = f"{symbol}-tick-{START_DATE}-{END_DATE}.csv"
    tick_filepath = os.path.join(RAW_DIR, tick_filename)

    if not os.path.exists(tick_filepath):
        print(f"✗ Tick file not found: {tick_filename}")
        print(f"  Run download_multisymbol_ticks.py first")
        return False

    file_size = os.path.getsize(tick_filepath) / (1024*1024)
    print(f"✓ Tick file found: {tick_filename} ({file_size:.2f} MB)")

    # Check if bars already exist
    bars_filename = f"{symbol}_h1_bars.csv"
    bars_filepath = os.path.join(BARS_DIR, bars_filename)

    if os.path.exists(bars_filepath):
        print(f"✓ Bars file already exists: {bars_filename}")
        bars_df = pd.read_csv(bars_filepath)
        print(f"  Bars: {len(bars_df)}")
        print(f"  Skipping build. Delete file to rebuild.")
        return True

    print(f"Loading tick data...")

    try:
        # Load ticks
        ticks_df = pd.read_csv(tick_filepath)
        print(f"✓ Loaded {len(ticks_df)} ticks")

        # Build bars
        print(f"Building H1 bars...")
        bars_df = build_bars_from_ticks(
            ticks_df,
            timeframe='1H',
            start_date=START_DATE,
            end_date=END_DATE
        )

        print(f"✓ Built {len(bars_df)} H1 bars")

        # Save bars
        os.makedirs(BARS_DIR, exist_ok=True)
        bars_df.to_csv(bars_filepath, index=True)
        print(f"✓ Saved: {bars_filename}")

        # Show sample
        print()
        print("Sample bars:")
        print(bars_df.head(3))
        print()

        return True

    except Exception as e:
        print(f"✗ Error building bars: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("="*80)
    print("MULTI-SYMBOL BARS BUILDER")
    print("="*80)
    print()
    print(f"Symbols: {', '.join([s.upper() for s in SYMBOLS])}")
    print(f"Timeframe: H1")
    print()

    results = {}

    for symbol in SYMBOLS:
        success = build_bars_for_symbol(symbol)
        results[symbol] = success
        print()

    # Summary
    print("="*80)
    print("BUILD SUMMARY")
    print("="*80)
    print()

    for symbol, success in results.items():
        status_icon = "✓" if success else "✗"
        print(f"{status_icon} {symbol.upper()}: {'success' if success else 'failed'}")

    print()

    success_count = sum(1 for s in results.values() if s)
    print(f"Successfully built: {success_count}/{len(results)}")

    if success_count > 0:
        print()
        print("Available bars files:")
        for symbol, success in results.items():
            if success:
                bars_file = f"{BARS_DIR}/{symbol}_h1_bars.csv"
                if os.path.exists(bars_file):
                    df = pd.read_csv(bars_file)
                    print(f"  {symbol.upper()}: {len(df)} bars")

    return results

if __name__ == "__main__":
    results = main()

