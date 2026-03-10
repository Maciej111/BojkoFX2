import sys
import os
import subprocess
import yaml
from datetime import datetime

# Adjust path to find src
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.utils.config import load_config

def download_ticks():
    config = load_config()
    symbol = config['data']['symbol']
    start_date = config['data']['start_date']
    end_date = config['data']['end_date']
    output_dir = config['data']['raw_dir']

    # Ensure output dir exists
    os.makedirs(output_dir, exist_ok=True)

    # Check if file already exists (dukascopy-node naming convention)
    expected_filename = f"{symbol}-tick-{start_date}-{end_date}.csv"
    expected_filepath = os.path.join(output_dir, expected_filename)

    if os.path.exists(expected_filepath):
        print(f"✓ File already exists: {expected_filename}")
        print(f"  Skipping download. Delete the file if you want to re-download.")
        return

    print(f"Downloading {symbol} ticks from {start_date} to {end_date}...")

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
        # Windows requires shell=True for npx often, or full path
        cmd[0] = "npx.cmd"

    try:
        subprocess.run(cmd, check=True)
        print("Download complete.")

        # Rename file to standard name if needed
        # dukascopy-node names files like "eurusd-tick-bid-ask-2024-06-01-2024-12-31.csv"
        # We might want to standardize it.
        # But for now let's just assert it downloaded something.
        files = os.listdir(output_dir)
        csv_files = [f for f in files if f.endswith(".csv")]
        print(f"Files in {output_dir}: {csv_files}")

    except subprocess.CalledProcessError as e:
        print(f"Error downloading data: {e}")
    except FileNotFoundError:
        print("Error: npx not found. Please install Node.js and ensure npx is in PATH.")

if __name__ == "__main__":
    download_ticks()

