"""
Download historical tick data for years 2021-2023
For walk-forward validation
"""
import sys
import os
import subprocess

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.utils.config import load_config


def download_year_ticks(symbol, year, output_dir):
    """
    Download ticks for a full year.

    Args:
        symbol: e.g., 'eurusd'
        year: e.g., 2021
        output_dir: path to save CSV
    """
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    expected_filename = f"{symbol}-tick-{start_date}-{end_date}.csv"
    expected_filepath = os.path.join(output_dir, expected_filename)


    # Check if already exists
    if os.path.exists(expected_filepath):
        print(f"✓ {year}: File already exists ({expected_filename})")
        print(f"  Skipping. Delete to re-download.")
        return True

    print(f"\n{'='*60}")
    print(f"Downloading {symbol.upper()} ticks for year {year}")
    print(f"Date range: {start_date} to {end_date}")
    print(f"{'='*60}\n")

    # Construct npx command
    cmd = [
        "npx", "dukascopy-node",
        "-i", symbol,
        "-from", start_date,
        "-to", end_date,
        "-t", "tick",
        "-f", "csv",
        "-dir", output_dir
    ]

    if os.name == 'nt':
        cmd[0] = "npx.cmd"

    try:
        print(f"Executing: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
        print(f"\n✓ Year {year} download complete!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Year {year} download failed: {e}")
        return False
    except Exception as e:
        print(f"\n✗ Year {year} download error: {e}")
        return False


def main():
    print(f"\n{'='*60}")
    print("HISTORICAL DATA DOWNLOAD")
    print("Years: 2021, 2022, 2023")
    print("For Walk-Forward Validation")
    print(f"{'='*60}\n")

    config = load_config()
    symbol = config['data']['symbol'].lower()
    output_dir = config['data']['raw_dir']

    # Ensure output dir exists
    os.makedirs(output_dir, exist_ok=True)

    print(f"Symbol: {symbol.upper()}")
    print(f"Output directory: {output_dir}")

    # Check if npx/dukascopy-node is available
    print(f"\nChecking if dukascopy-node is installed...")
    try:
        result = subprocess.run(["npx.cmd" if os.name == 'nt' else "npx",
                               "dukascopy-node", "--version"],
                               capture_output=True, text=True)
        print(f"✓ dukascopy-node is available")
    except:
        print(f"✗ dukascopy-node not found!")
        print(f"\nInstall it with:")
        print(f"  npm install -g dukascopy-node")
        return

    # Download years
    years = [2021, 2022, 2023]
    results = {}

    for year in years:
        success = download_year_ticks(symbol, year, output_dir)
        results[year] = success

    # Summary
    print(f"\n{'='*60}")
    print("DOWNLOAD SUMMARY")
    print(f"{'='*60}\n")

    for year, success in results.items():
        status = "✓" if success else "✗"
        print(f"  {status} {year}: {'Downloaded' if success else 'Failed'}")

    successful = sum(1 for s in results.values() if s)

    print(f"\nTotal: {successful}/{len(years)} years downloaded")

    if successful == len(years):
        print("\n✅ ALL YEARS DOWNLOADED!")
        print("\nNext steps:")
        print("  1. Build H1 bars: python scripts/build_h1_bars.py")
        print("  2. Run walk-forward: python scripts/run_walkforward_validation.py")
    elif successful > 0:
        print(f"\n⚠️ PARTIAL SUCCESS: {successful}/{len(years)} years")
        print("\nYou can still run validation on available years.")
    else:
        print("\n✗ NO DOWNLOADS SUCCESSFUL")
        print("\nCheck:")
        print("  - Internet connection")
        print("  - dukascopy-node installation")
        print("  - Dukascopy server availability")

    print(f"\n{'='*60}")

    # Estimate file sizes
    print("\nNote: Each year ~2-4 GB of tick data")
    print("Total expected: ~6-12 GB for 3 years")
    print("Download time: ~10-30 minutes per year (varies by connection)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

