"""
Download one symbol at a time - manual execution
"""
import subprocess
import os

def download_one(symbol, start="2021-01-01", end="2024-12-31"):
    """Download single symbol"""
    output_dir = "data/raw"
    os.makedirs(output_dir, exist_ok=True)

    # Check if exists
    expected_file = f"{output_dir}/{symbol}-tick-{start}-{end}.csv"
    if os.path.exists(expected_file):
        size_mb = os.path.getsize(expected_file) / (1024*1024)
        print(f"✓ Already exists: {expected_file} ({size_mb:.2f} MB)")
        return True

    print(f"Downloading {symbol}...")

    cmd = ["npx.cmd", "dukascopy-node",
           "-i", symbol,
           "-from", start,
           "-to", end,
           "-t", "tick",
           "-f", "csv",
           "-dir", output_dir]

    try:
        subprocess.run(cmd, check=True)
        if os.path.exists(expected_file):
            size_mb = os.path.getsize(expected_file) / (1024*1024)
            print(f"✓ Downloaded: {expected_file} ({size_mb:.2f} MB)")
            return True
        else:
            print(f"✗ File not created")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        symbol = sys.argv[1]
        download_one(symbol)
    else:
        print("Usage: python download_single.py <symbol>")
        print("Example: python download_single.py usdjpy")

