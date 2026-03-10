"""
Download tick data for multiple symbols
For multi-symbol robustness testing
"""
import subprocess
import os
from datetime import datetime

# Symbols to download
SYMBOLS = {
    'GBPUSD': 'gbpusd',
    'USDJPY': 'usdjpy',
    'XAUUSD': 'xauusd',
    # Note: US100 and SPX500 may not be available on Dukascopy (FX broker)
    # Will try but expect failures
}

# Period for testing (2021-2024)
START_DATE = "2021-01-01"
END_DATE = "2024-12-31"

OUTPUT_DIR = "data/raw"

def check_file_exists(symbol, start, end):
    """Check if tick data already downloaded"""
    # Dukascopy-node naming convention
    expected_filename = f"{symbol}-tick-{start}-{end}.csv"
    expected_filepath = os.path.join(OUTPUT_DIR, expected_filename)
    return os.path.exists(expected_filepath), expected_filepath

def download_symbol(symbol, dukascopy_symbol):
    """Download tick data for one symbol"""
    print("="*80)
    print(f"Symbol: {symbol} ({dukascopy_symbol})")
    print("="*80)

    # Check if already exists
    exists, filepath = check_file_exists(dukascopy_symbol, START_DATE, END_DATE)

    if exists:
        file_size = os.path.getsize(filepath) / (1024*1024)  # MB
        print(f"✓ Already downloaded: {os.path.basename(filepath)}")
        print(f"  Size: {file_size:.2f} MB")
        print(f"  Skipping download.")
        return True, "already_exists"

    print(f"Downloading {symbol} ticks from {START_DATE} to {END_DATE}...")
    print(f"This may take 10-30 minutes depending on data size...")

    # Construct command
    cmd = [
        "npx", "dukascopy-node",
        "-i", dukascopy_symbol,
        "-from", START_DATE,
        "-to", END_DATE,
        "-t", "tick",
        "-f", "csv",
        "-dir", OUTPUT_DIR
    ]

    if os.name == 'nt':
        cmd[0] = "npx.cmd"

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✓ Download complete!")

        # Check if file was created
        exists, filepath = check_file_exists(dukascopy_symbol, START_DATE, END_DATE)
        if exists:
            file_size = os.path.getsize(filepath) / (1024*1024)
            print(f"  File: {os.path.basename(filepath)}")
            print(f"  Size: {file_size:.2f} MB")
            return True, "success"
        else:
            print("✗ File not found after download (unexpected)")
            return False, "file_not_created"

    except subprocess.CalledProcessError as e:
        print(f"✗ Download failed!")
        print(f"  Error: {e}")
        if "not found" in str(e).lower() or "unknown" in str(e).lower():
            return False, "symbol_not_available"
        return False, "download_error"
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False, "unexpected_error"

def main():
    print("="*80)
    print("MULTI-SYMBOL TICK DATA DOWNLOAD")
    print("="*80)
    print()
    print(f"Period: {START_DATE} to {END_DATE}")
    print(f"Symbols: {', '.join(SYMBOLS.keys())}")
    print(f"Output: {OUTPUT_DIR}")
    print()

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Download each symbol
    results = {}

    for symbol, dukascopy_symbol in SYMBOLS.items():
        success, status = download_symbol(symbol, dukascopy_symbol)
        results[symbol] = (success, status)
        print()

    # Summary
    print("="*80)
    print("DOWNLOAD SUMMARY")
    print("="*80)
    print()

    for symbol, (success, status) in results.items():
        status_icon = "✓" if success else "✗"
        print(f"{status_icon} {symbol}: {status}")

    print()

    success_count = sum(1 for s, _ in results.values() if s)
    total_count = len(results)

    print(f"Successfully downloaded: {success_count}/{total_count}")

    if success_count > 0:
        print()
        print("Next steps:")
        print("1. Run scripts/build_bars_multisymbol.py to convert ticks to H1 bars")
        print("2. Run scripts/multisymbol_test.py with real data")

    return results

if __name__ == "__main__":
    results = main()

