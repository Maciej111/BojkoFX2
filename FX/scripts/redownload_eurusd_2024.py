"""
Re-download EURUSD 2024 tick data (corrupted file recovery)
"""
import subprocess
import os

def download_eurusd_2024():
    """Download EURUSD 2024 tick data"""

    print("="*60)
    print("EURUSD 2024 DATA DOWNLOAD")
    print("="*60)
    print()

    output_dir = "data/raw"
    os.makedirs(output_dir, exist_ok=True)

    symbol = "eurusd"
    start = "2024-01-01"
    end = "2024-12-31"

    expected_file = f"{output_dir}/{symbol}-tick-{start}-{end}.csv"

    # Remove corrupted file if exists
    if os.path.exists(expected_file):
        size = os.path.getsize(expected_file)
        if size == 0:
            print(f"⚠ Removing corrupted file (0 bytes): {expected_file}")
            os.remove(expected_file)
        else:
            size_mb = size / (1024*1024)
            print(f"✓ File already exists: {expected_file} ({size_mb:.2f} MB)")
            return True

    print(f"Downloading {symbol.upper()} {start} to {end}...")
    print(f"Target: {expected_file}")
    print()

    cmd = ["npx.cmd", "dukascopy-node",
           "-i", symbol,
           "-from", start,
           "-to", end,
           "-t", "tick",
           "-f", "csv",
           "-dir", output_dir]

    print(f"Command: {' '.join(cmd)}")
    print()

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)

        if os.path.exists(expected_file):
            size_mb = os.path.getsize(expected_file) / (1024*1024)
            print()
            print(f"✅ Downloaded successfully!")
            print(f"   File: {expected_file}")
            print(f"   Size: {size_mb:.2f} MB")
            return True
        else:
            print()
            print(f"❌ File not created: {expected_file}")
            return False

    except subprocess.CalledProcessError as e:
        print()
        print(f"❌ Download failed: {e}")
        if e.stderr:
            print(f"Error output: {e.stderr}")
        return False
    except Exception as e:
        print()
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = download_eurusd_2024()

    if success:
        print()
        print("="*60)
        print("✅ DOWNLOAD COMPLETE")
        print("="*60)
        print()
        print("Next steps:")
        print("1. Rebuild H1 and H4 bars")
        print("2. Run OOS 2024 test")
        print("3. Generate final report")
    else:
        print()
        print("="*60)
        print("❌ DOWNLOAD FAILED")
        print("="*60)

