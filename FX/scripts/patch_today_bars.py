"""
patch_today_bars.py — fills missing H1 bars from Yahoo Finance into live_bars.
"""
import argparse
import subprocess
import pathlib
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

BASE      = pathlib.Path(__file__).parent.parent
LIVE_DIR  = BASE / "data" / "live_bars_local"
LIVE_DIR.mkdir(parents=True, exist_ok=True)

VM_USER    = "macie"
VM_HOST    = "bojkofx-vm"
VM_ZONE    = "us-central1-a"
VM_PROJECT = "sandbox-439719"
VM_LIVE_PATH = "/home/macie/bojkofx/app/data/live_bars/"

YF_MAP = {
    "EURUSD": "EURUSD=X",
    "USDJPY": "JPY=X",
    "USDCHF": "CHF=X",
    "AUDJPY": "AUDJPY=X",
    "CADJPY": "CADJPY=X",
}

parser = argparse.ArgumentParser()
parser.add_argument("--no-upload", action="store_true")
args = parser.parse_args()

now_utc = datetime.now(timezone.utc)

print(f"Patching live_bars with Yahoo Finance (period=5d, up to now)\n")

updated = []

def to_naive_utc(series: pd.Series) -> pd.Series:
    """Convert datetime series to UTC-naive."""
    s = pd.to_datetime(series, errors="coerce")
    if s.dt.tz is not None:
        s = s.dt.tz_convert("UTC").dt.tz_localize(None)
    return s

for sym, yf_sym in YF_MAP.items():
    print(f"--- {sym} ---")

    try:
        ticker = yf.Ticker(yf_sym)
        df_yf = ticker.history(period="5d", interval="1h", auto_adjust=True)
        if df_yf.empty:
            print(f"  No data from Yahoo")
            continue
        df_yf.index = to_naive_utc(df_yf.index.to_series()).values
        df_yf.index = pd.DatetimeIndex(df_yf.index)
        df_yf.columns = [c.lower() for c in df_yf.columns]
        df_yf.index.name = "datetime"
        df_yf = df_yf.reset_index()[["datetime","open","high","low","close"]]
        df_yf["volume"] = 0
        df_yf["datetime"] = pd.to_datetime(df_yf["datetime"])
        print(f"  Yahoo: {len(df_yf)} bars, {df_yf['datetime'].iloc[0]} → {df_yf['datetime'].iloc[-1]}")
    except Exception as e:
        print(f"  Yahoo error: {e}")
        continue

    # Load local bars_validated as base
    val_path = BASE / "data" / "bars_validated" / f"{sym.lower()}_1h_validated.csv"
    if val_path.exists():
        try:
            df_val = pd.read_csv(val_path)
            df_val.columns = [c.strip().lower() for c in df_val.columns]
            ts_col = next((c for c in df_val.columns
                           if c in ("datetime","timestamp") or "time" in c or "date" in c),
                          df_val.columns[0])
            df_val[ts_col] = to_naive_utc(df_val[ts_col])
            df_val = df_val.dropna(subset=[ts_col]).rename(columns={ts_col: "datetime"})
            if "open_bid" in df_val.columns and "open" not in df_val.columns:
                df_val["open"]  = (df_val["open_bid"]  + df_val["open_ask"])  / 2
                df_val["high"]  = (df_val["high_bid"]  + df_val["high_ask"])  / 2
                df_val["low"]   = (df_val["low_bid"]   + df_val["low_ask"])   / 2
                df_val["close"] = (df_val["close_bid"] + df_val["close_ask"]) / 2
            df_val = df_val[["datetime","open","high","low","close"]].dropna()
            df_val["volume"] = 0
        except Exception as e:
            print(f"  validated read error: {e}")
            df_val = pd.DataFrame(columns=["datetime","open","high","low","close","volume"])
    else:
        df_val = pd.DataFrame(columns=["datetime","open","high","low","close","volume"])

    # Merge: validated base + Yahoo (Yahoo wins on overlap)
    df_merged = pd.concat([df_val, df_yf], ignore_index=True)
    df_merged["datetime"] = pd.to_datetime(df_merged["datetime"])
    df_merged = df_merged.drop_duplicates(subset=["datetime"], keep="last")
    df_merged = df_merged.sort_values("datetime").reset_index(drop=True)

    df_out = df_merged.tail(500)
    out_path = LIVE_DIR / f"{sym}.csv"
    df_out.to_csv(out_path, index=False)

    last = df_out["datetime"].iloc[-1]
    today_date = now_utc.date()
    today_count = (df_out["datetime"].dt.date == today_date).sum()
    print(f"  Saved: {len(df_out)} bars, last={last}, today bars: {today_count}")
    updated.append(str(out_path))

# Upload to VM using gcloud (Windows-compatible)
if not args.no_upload and updated:
    import shutil
    gcloud = shutil.which("gcloud") or r"C:\Users\macie\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    print(f"\nUploading {len(updated)} files to VM...")
    for fpath in updated:
        cmd = (f'"{gcloud}" compute scp "{fpath}" '
               f'{VM_USER}@{VM_HOST}:{VM_LIVE_PATH} '
               f'--zone={VM_ZONE} --project={VM_PROJECT}')
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        fname = pathlib.Path(fpath).name
        if r.returncode == 0:
            print(f"  {fname}: OK")
        else:
            print(f"  {fname}: FAILED — {r.stderr.strip()[-200:]}")

print("\nDone. Refresh dashboard (Ctrl+Shift+R).")

