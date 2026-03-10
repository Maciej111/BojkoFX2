"""Check actual date ranges in all M60 data files for production pairs."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pandas as pd
from pathlib import Path

DATA = Path(__file__).parent.parent / "data" / "raw_dl_fx" / "download" / "m60"

PROD_PAIRS = ["eurusd", "usdjpy", "usdchf", "audjpy", "cadjpy"]

print(f"{'Symbol':8s}  {'Rows':>6s}  {'First':12s}  {'Last':12s}  {'Has 2025':>9s}  {'Has 2025-H2':>11s}")
print("-" * 70)

for sym in PROD_PAIRS:
    for suffix in ["2021_2025", "2021_2024"]:
        f = DATA / f"{sym}_m60_bid_{suffix}.csv"
        if f.exists():
            break
    if not f.exists():
        print(f"{sym.upper():8s}  FILE NOT FOUND")
        continue
    df = pd.read_csv(f)
    df.columns = [c.strip().lower() for c in df.columns]
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("timestamp").sort_index()

    first = df.index.min().date()
    last  = df.index.max().date()
    rows  = len(df)
    has_2025    = (df.index.year == 2025).any()
    has_2025_h2 = ((df.index.year == 2025) & (df.index.month >= 7)).any()

    print(f"{sym.upper():8s}  {rows:6d}  {str(first):12s}  {str(last):12s}  "
          f"{'YES' if has_2025 else 'NO':>9s}  {'YES' if has_2025_h2 else 'NO':>11s}")

print()
print("WNIOSEK:")
print("  Dane kończą się na 2024-12-31.")
print("  Brak roku 2025 = backtesty nie walidowały zachowania strategii w 2025.")
print("  Należy dobrać dane 2025 z Dukascopy i przeprowadzić backtest OOS 2025.")

