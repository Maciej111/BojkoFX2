"""
Copy all downloaded symbol files to raw_dl and run multi-symbol grid.
Run after all dukascopy downloads complete.
"""
import os, shutil, sys
from pathlib import Path

SRC  = Path(r'C:\dev\projects\BojkoFx\data\raw_dl\download')
DEST = Path(r'C:\dev\projects\BojkoFx\data\raw_dl')

NEEDED = [
    'usdcad_m30_bid_2021_2024.csv',
    'usdcad_m30_ask_2021_2024.csv',
    'nzdusd_m30_bid_2021_2024.csv',
    'nzdusd_m30_ask_2021_2024.csv',
    'usdchf_m30_bid_2021_2024.csv',
    'usdchf_m30_ask_2021_2024.csv',
]

print("Checking downloaded files...")
missing = []
for fn in NEEDED:
    src_path = SRC / fn
    if not src_path.exists() or src_path.stat().st_size < 100_000:
        missing.append(fn)
    else:
        shutil.copy2(src_path, DEST / fn)
        print(f"  copied: {fn}  ({src_path.stat().st_size:,} bytes)")

if missing:
    print(f"\nSTILL MISSING ({len(missing)}):")
    for f in missing: print(f"  {f}")
    sys.exit(1)

print("\nAll files ready. Starting grid...\n")

# run grid
sys.path.insert(0, r'C:\dev\projects\BojkoFx\scripts')
import importlib.util, runpy
runpy.run_path(r'C:\dev\projects\BojkoFx\scripts\multisym_grid_backtest.py',
               run_name='__main__')

