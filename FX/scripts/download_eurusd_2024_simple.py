"""
Simple direct download for EURUSD 2024
"""
import subprocess
import os

print("="*60)
print("DOWNLOADING EURUSD 2024")
print("="*60)
print()

output_dir = "data/raw"
os.makedirs(output_dir, exist_ok=True)

symbol = "eurusd"
start = "2024-01-01"
end = "2024-12-31"

expected_file = f"{output_dir}/{symbol}-tick-{start}-{end}.csv"

# Remove empty file if exists
if os.path.exists(expected_file):
    size = os.path.getsize(expected_file)
    if size == 0:
        print(f"Removing corrupted file (0 bytes)")
        os.remove(expected_file)
    else:
        print(f"File already exists ({size/(1024*1024):.1f} MB)")
        print("Delete it to re-download")
        exit(0)

print(f"Downloading {symbol.upper()} {start} to {end}...")
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

print("Command:", " ".join(cmd))
print()
print("This may take 5-15 minutes...")
print()

try:
    subprocess.run(cmd, check=True)

    if os.path.exists(expected_file):
        size = os.path.getsize(expected_file)
        print()
        print("="*60)
        print("✅ DOWNLOAD COMPLETE!")
        print("="*60)
        print(f"File: {expected_file}")
        print(f"Size: {size/(1024*1024):.1f} MB")
    else:
        print()
        print("❌ Download failed - file not created")

except KeyboardInterrupt:
    print()
    print("⚠ Download interrupted by user")
except Exception as e:
    print()
    print(f"❌ Error: {e}")

