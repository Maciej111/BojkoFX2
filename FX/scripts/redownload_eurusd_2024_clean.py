"""
Re-download EURUSD 2024 full year from Dukascopy
Clean download without using corrupted cache
"""
import subprocess
import os
from datetime import datetime

print("="*80)
print("EURUSD 2024 FULL YEAR DOWNLOAD")
print("="*80)
print()

output_dir = "data/raw"
os.makedirs(output_dir, exist_ok=True)

symbol = "eurusd"
start = "2024-01-01"
end = "2024-12-31"

expected_file = f"{output_dir}/{symbol}-tick-{start}-{end}.csv"
temp_file = f"{output_dir}/{symbol}-tick-{start}-{end}_NEW.csv"

# Check if old file exists and rename it
if os.path.exists(expected_file):
    size_mb = os.path.getsize(expected_file) / (1024*1024)
    print(f"Old file exists: {expected_file} ({size_mb:.1f} MB)")

    # Rename to backup
    backup_file = f"{expected_file}.OLD"
    if os.path.exists(backup_file):
        os.remove(backup_file)
    os.rename(expected_file, backup_file)
    print(f"Renamed to: {backup_file}")
    print()

print(f"Downloading {symbol.upper()} {start} to {end}...")
print(f"Target: {temp_file}")
print()
print("This may take 10-20 minutes for full year...")
print()

cmd = [
    "npx.cmd", "dukascopy-node",
    "-i", symbol,
    "-from", start,
    "-to", end,
    "-t", "tick",
    "-f", "csv",
    "-dir", output_dir
]

print(f"Command: {' '.join(cmd)}")
print()

try:
    result = subprocess.run(cmd, check=True, capture_output=False, text=True)

    # Check if file was created
    if os.path.exists(expected_file):
        size_mb = os.path.getsize(expected_file) / (1024*1024)
        line_count = sum(1 for _ in open(expected_file, 'r', encoding='utf-8'))

        print()
        print("="*80)
        print("DOWNLOAD COMPLETE")
        print("="*80)
        print(f"File: {expected_file}")
        print(f"Size: {size_mb:.1f} MB")
        print(f"Lines: {line_count:,}")
        print()

        # Quick validation - check first and last lines
        with open(expected_file, 'r') as f:
            lines = f.readlines()
            print("First line (header):")
            print(f"  {lines[0].strip()}")
            print("Second line (first data):")
            print(f"  {lines[1].strip()}")
            print("Last line:")
            print(f"  {lines[-1].strip()}")

        print()

        # Parse first and last timestamps
        import pandas as pd

        first_ts = int(lines[1].split(',')[0])
        last_ts = int(lines[-1].split(',')[0])

        first_date = pd.to_datetime(first_ts, unit='ms')
        last_date = pd.to_datetime(last_ts, unit='ms')

        print(f"Date range:")
        print(f"  First: {first_date}")
        print(f"  Last:  {last_date}")
        print()

        # Check if it's really full year
        if first_date.month <= 1 and last_date.month >= 12:
            print("✓ Looks like FULL YEAR data!")

            # Delete old backup
            backup_file = f"{expected_file}.OLD"
            if os.path.exists(backup_file):
                os.remove(backup_file)
                print(f"✓ Deleted old incomplete file")
        else:
            print("⚠ WARNING: Data may be incomplete!")
            print(f"  Expected: January to December")
            print(f"  Got: {first_date.strftime('%B')} to {last_date.strftime('%B')}")

        print()
        print("="*80)
        print("SUCCESS")
        print("="*80)

    else:
        print()
        print("="*80)
        print("ERROR: File not created")
        print("="*80)
        exit(1)

except subprocess.CalledProcessError as e:
    print()
    print("="*80)
    print(f"ERROR: Download failed")
    print("="*80)
    print(f"Error: {e}")
    exit(1)
except KeyboardInterrupt:
    print()
    print("="*80)
    print("INTERRUPTED")
    print("="*80)
    exit(1)
except Exception as e:
    print()
    print("="*80)
    print(f"ERROR: {e}")
    print("="*80)
    import traceback
    traceback.print_exc()
    exit(1)

