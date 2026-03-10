"""
Update bars_validated CSVs with recent H1 data from Yahoo Finance.
Downloads from last known date to today and appends to existing validated files.
Then seeds live_bars/SYMBOL.csv and uploads to VM via gcloud scp.

NOTE: Used as fallback when IBKR HMDS (cashhmds farm) is unavailable.
      The primary script is update_bars_from_ibkr.py (uses IBKR directly).

Usage:
  python scripts/update_validated_bars.py            # update + upload to VM
  python scripts/update_validated_bars.py --no-upload  # local only
"""
import argparse
import subprocess
import pandas as pd
import pathlib
import yfinance as yf
from datetime import datetime, timezone

BASE = pathlib.Path(__file__).parent.parent
VALIDATED_DIR = BASE / "data" / "bars_validated"
LIVE_BARS_DIR = BASE / "data" / "live_bars_local"
LIVE_BARS_DIR.mkdir(parents=True, exist_ok=True)

VM_USER    = "macie"
VM_HOST    = "bojkofx-vm"
VM_ZONE    = "us-central1-a"
VM_PROJECT = "sandbox-439719"
VM_LIVE_BARS_PATH = "/home/macie/bojkofx/app/data/live_bars/"
VM_VALIDATED_PATH = "/home/macie/bojkofx/app/data/bars_validated/"

# Yahoo Finance symbol mapping
YF_MAP = {
    "EURUSD": "EURUSD=X",
    "USDJPY": "JPY=X",
    "USDCHF": "CHF=X",
    "AUDJPY": "AUDJPY=X",
    "CADJPY": "CADJPY=X",
}

parser = argparse.ArgumentParser()
parser.add_argument("--no-upload", action="store_true", help="Skip gcloud scp upload to VM")
parser.add_argument("--symbols", nargs="+", default=list(YF_MAP.keys()))
args = parser.parse_args()

END = datetime.now(timezone.utc).strftime("%Y-%m-%d")

print(f"Yahoo Finance H1 bars updater (fallback — use when IBKR HMDS is down)")
print(f"Target date: {END}")
print(f"Upload to VM: {not args.no_upload}\n")

updated_validated = []
updated_live      = []

for sym in [s.upper() for s in args.symbols]:
    yf_sym = YF_MAP.get(sym)
    if not yf_sym:
        print(f"--- {sym}: no Yahoo Finance mapping, SKIP")
        continue

    print(f"--- {sym} ({yf_sym}) ---")

    val_path = VALIDATED_DIR / f"{sym.lower()}_1h_validated.csv"
    if not val_path.exists() or val_path.stat().st_size < 10:
        print(f"  SKIP: no validated file at {val_path}")
        continue

    df_existing = pd.read_csv(val_path)
    df_existing.columns = [c.strip().lower() for c in df_existing.columns]
    ts_col = next((c for c in df_existing.columns if 'time' in c or 'date' in c or c == 'datetime'), df_existing.columns[0])
    df_existing[ts_col] = pd.to_datetime(df_existing[ts_col], utc=True, errors='coerce')
    df_existing = df_existing.dropna(subset=[ts_col]).sort_values(ts_col)

    last_existing = df_existing[ts_col].max()
    # Start download from day after last known bar
    start_dt = (last_existing - pd.Timedelta(days=3)).strftime("%Y-%m-%d")
    print(f"  Existing: {len(df_existing)} bars, last={last_existing.date()}")
    print(f"  Fetching from {start_dt} to {END}...")

    try:
        ticker = yf.Ticker(yf_sym)
        df_new = ticker.history(start=start_dt, end=END, interval="1h", auto_adjust=True)

        if df_new.empty:
            print(f"  WARNING: No data from Yahoo for {yf_sym}")
            continue

        df_new.index = df_new.index.tz_convert("UTC")
        df_new.columns = [c.lower() for c in df_new.columns]
        df_new.index.name = ts_col
        df_new = df_new.reset_index()
        df_new[ts_col] = pd.to_datetime(df_new[ts_col], utc=True)

        keep_cols = [ts_col, "open", "high", "low", "close", "volume"]
        df_new = df_new[[c for c in keep_cols if c in df_new.columns]]
        if "volume" not in df_new.columns:
            df_new["volume"] = 0

        df_new = df_new[df_new[ts_col] > last_existing]
        print(f"  New bars: {len(df_new)}")

        if not df_new.empty:
            df_merged = pd.concat([df_existing, df_new], ignore_index=True)
            df_merged = df_merged.sort_values(ts_col).drop_duplicates(subset=[ts_col])
            df_merged.to_csv(val_path, index=False)
            print(f"  Saved {len(df_merged)} total bars -> {val_path.name}")
            updated_validated.append(str(val_path))
        else:
            print(f"  Already up to date.")

        # Reload final version for live_bars seed
        df_final = pd.read_csv(val_path)
        df_final.columns = [c.strip().lower() for c in df_final.columns]
        ts_col2 = next((c for c in df_final.columns if 'time' in c or 'date' in c or c == 'datetime'), df_final.columns[0])
        df_final[ts_col2] = pd.to_datetime(df_final[ts_col2], utc=True, errors='coerce')
        df_final = df_final.dropna(subset=[ts_col2]).sort_values(ts_col2)

        if 'open' not in df_final.columns and 'open_bid' in df_final.columns:
            df_final['open']  = (df_final['open_bid']  + df_final['open_ask'])  / 2
            df_final['high']  = (df_final['high_bid']  + df_final['high_ask'])  / 2
            df_final['low']   = (df_final['low_bid']   + df_final['low_ask'])   / 2
            df_final['close'] = (df_final['close_bid'] + df_final['close_ask']) / 2
        if 'volume' not in df_final.columns:
            df_final['volume'] = 0

        df_live = df_final.tail(500).copy()
        df_live = df_live.rename(columns={ts_col2: 'datetime'}).set_index('datetime')
        live_path = LIVE_BARS_DIR / f"{sym}.csv"
        df_live[['open','high','low','close','volume']].to_csv(live_path)
        print(f"  Live bars: {len(df_live)} bars, last={df_live.index[-1].date()}")
        updated_live.append(str(live_path))

    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()

# ── Upload to VM ───────────────────────────────────────────────────────────────
if not args.no_upload and updated_live:
    print(f"\nUploading {len(updated_live)} live_bars files to VM...")
    cmd = [
        "gcloud", "compute", "scp",
        *updated_live,
        f"{VM_USER}@{VM_HOST}:{VM_LIVE_BARS_PATH}",
        f"--zone={VM_ZONE}",
        f"--project={VM_PROJECT}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("  live_bars upload OK")
    else:
        print(f"  live_bars upload FAILED: {result.stderr.strip()}")

if not args.no_upload and updated_validated:
    print(f"\nUploading {len(updated_validated)} bars_validated files to VM...")
    cmd = [
        "gcloud", "compute", "scp",
        *updated_validated,
        f"{VM_USER}@{VM_HOST}:{VM_VALIDATED_PATH}",
        f"--zone={VM_ZONE}",
        f"--project={VM_PROJECT}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("  bars_validated upload OK")
    else:
        print(f"  bars_validated upload FAILED: {result.stderr.strip()}")

print(f"\nDONE.")
print(f"NOTE: When IBKR cashhmds farm recovers, use update_bars_from_ibkr.py instead.")
