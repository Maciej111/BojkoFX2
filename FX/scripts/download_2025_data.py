"""
Download M60/H1 data for 2025 (Jan-Dec) for the 5 production pairs,
then append to existing 2021-2024 files → creates _2021_2025.csv files.

Production pairs: EURUSD, USDJPY, USDCHF, AUDJPY, CADJPY
"""
import subprocess
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

# ── Config ────────────────────────────────────────────────────────────────────
START_2025 = "2025-01-01"
END_2025   = "2025-12-31"
TF         = "h1"
DATA_DIR   = Path(__file__).parent.parent / "data" / "raw_dl_fx" / "download" / "m60"
TMP_DIR    = DATA_DIR / "_tmp_2025"

PROD_PAIRS = ["eurusd", "usdjpy", "usdchf", "audjpy", "cadjpy"]
SIDES      = ["bid", "ask"]

TMP_DIR.mkdir(parents=True, exist_ok=True)


# ── Step 1: Download 2025 data ────────────────────────────────────────────────

def download_2025(symbol: str, side: str) -> Path | None:
    tmp_file = TMP_DIR / f"{symbol}-h1-{side}-{START_2025}-{END_2025}.csv"
    if tmp_file.exists() and tmp_file.stat().st_size > 500:
        print(f"  [SKIP] already downloaded: {tmp_file.name}")
        return tmp_file

    cmd = [
        "npx.cmd", "dukascopy-node",
        "-i",    symbol,
        "-from", START_2025,
        "-to",   END_2025,
        "-t",    TF,
        "-p",    side,
        "-f",    "csv",
        "-dir",  str(TMP_DIR),
        "--silent",
        "-r",    "3",
    ]
    print(f"  Downloading {symbol.upper()} {side.upper()} 2025 ...", flush=True)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            print(f"  [ERROR] {r.stderr[:200]}")
            return None
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None

    if tmp_file.exists() and tmp_file.stat().st_size > 500:
        print(f"  [OK] {tmp_file.name}  ({tmp_file.stat().st_size:,} bytes)")
        return tmp_file

    # dukascopy may use slightly different filename — find it
    candidates = list(TMP_DIR.glob(f"{symbol}*{side}*.csv"))
    if candidates:
        found = candidates[0]
        found.rename(tmp_file)
        print(f"  [OK] renamed → {tmp_file.name}")
        return tmp_file

    print(f"  [WARN] file not found after download")
    return None


# ── Step 2: Parse downloaded CSV ──────────────────────────────────────────────

def parse_csv(path: Path, is_2025_raw: bool = False) -> pd.DataFrame:
    """Parse a Dukascopy CSV. Handles both original (ms) and 2025 raw format."""
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    ts_col = df.columns[0]  # first column is always timestamp
    if is_2025_raw:
        # 2025 raw file from dukascopy-node: timestamp in ms
        df["timestamp"] = pd.to_datetime(df[ts_col], unit="ms")
    else:
        # Existing files: timestamp in ms as well
        df["timestamp"] = pd.to_datetime(df[ts_col], unit="ms")
    df = df.set_index("timestamp").sort_index()
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[["open", "high", "low", "close"]].dropna()
    return df


# ── Step 3: Merge and save ────────────────────────────────────────────────────

def merge_and_save(symbol: str, side: str, df_2025: pd.DataFrame) -> bool:
    src = DATA_DIR / f"{symbol}_m60_{side}_2021_2024.csv"
    dst = DATA_DIR / f"{symbol}_m60_{side}_2021_2025.csv"

    if not src.exists():
        print(f"  [ERROR] source not found: {src.name}")
        return False

    df_old = parse_csv(src)
    df_new = pd.concat([df_old, df_2025])
    df_new = df_new[~df_new.index.duplicated(keep="last")].sort_index()

    # Save: Timestamp as ms epoch integer (same format as Dukascopy originals)
    df_out = df_new.copy().reset_index()
    df_out.columns = ["Timestamp", "Open", "High", "Low", "Close"]
    df_out["Timestamp"] = df_out["Timestamp"].astype("datetime64[ms]").astype("int64")
    df_out.to_csv(dst, index=False)

    first = df_new.index.min().date()
    last  = df_new.index.max().date()
    rows_2025 = (df_new.index.year == 2025).sum()
    print(f"  [MERGED] {dst.name}  total={len(df_new):,}  "
          f"range={first}→{last}  2025_rows={rows_2025:,}")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Step 1/2: Downloading 2025 data from Dukascopy")
    print("=" * 60)

    downloaded = {}
    for sym in PROD_PAIRS:
        for side in SIDES:
            path = download_2025(sym, side)
            downloaded[(sym, side)] = path
        print()

    print("=" * 60)
    print("Step 2/2: Merging 2025 into existing 2021-2024 files")
    print("=" * 60)

    ok = []
    fail = []
    for sym in PROD_PAIRS:
        for side in SIDES:
            path = downloaded.get((sym, side))
            if path is None or not path.exists():
                print(f"  [SKIP] {sym} {side} — no 2025 data downloaded")
                fail.append(f"{sym}_{side}")
                continue
            df_2025 = parse_csv(path)
            if df_2025.empty:
                print(f"  [SKIP] {sym} {side} — 2025 data empty")
                fail.append(f"{sym}_{side}")
                continue
            if merge_and_save(sym, side, df_2025):
                ok.append(f"{sym}_{side}")
            else:
                fail.append(f"{sym}_{side}")

    print()
    print("=" * 60)
    print(f"Done. OK: {len(ok)}  FAILED: {len(fail)}")
    if fail:
        print(f"  Failed: {', '.join(fail)}")
    print()
    print("Nowe pliki: data/raw_dl_fx/download/m60/*_2021_2025.csv")
    print("Następny krok: uruchom backtest OOS 2025")
    print("=" * 60)


if __name__ == "__main__":
    main()

