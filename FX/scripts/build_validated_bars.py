"""
Build H1 OHLC bars (bid/ask midpoint) from raw m60 CSVs and save to
data/bars_validated/{sym}_1h_validated.csv for the dashboard.

Usage:
    python scripts/build_validated_bars.py
"""
import sys
from pathlib import Path
import pandas as pd

ROOT   = Path(__file__).resolve().parent.parent
M60DIR = ROOT / "data" / "raw_dl_fx" / "download" / "m60"
OUTDIR = ROOT / "data" / "bars_validated"
OUTDIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = {
    "EURUSD": ("eurusd_m60_bid_2021_2025.csv", "eurusd_m60_ask_2021_2025.csv"),
    "USDJPY": ("usdjpy_m60_bid_2021_2025.csv", "usdjpy_m60_ask_2021_2025.csv"),
    "USDCHF": ("usdchf_m60_bid_2021_2025.csv", "usdchf_m60_ask_2021_2025.csv"),
    "AUDJPY": ("audjpy_m60_bid_2021_2025.csv", "audjpy_m60_ask_2021_2025.csv"),
    "CADJPY": ("cadjpy_m60_bid_2021_2025.csv", "cadjpy_m60_ask_2021_2025.csv"),
}

COLS = ["datetime", "open", "high", "low", "close"]


def load_raw(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    # Timestamp column (unix ms)
    ts_col = next((c for c in df.columns if "time" in c), df.columns[0])
    ts_ms = pd.to_numeric(df[ts_col], errors="coerce")
    df["datetime"] = pd.to_datetime(ts_ms, unit="ms", utc=True)
    df = df.set_index("datetime").sort_index()
    return df[["open", "high", "low", "close"]].astype(float)


def build_midpoint(bid: pd.DataFrame, ask: pd.DataFrame) -> pd.DataFrame:
    mid = pd.DataFrame(index=bid.index)
    mid["open"]  = (bid["open"]  + ask["open"])  / 2
    mid["high"]  = (bid["high"]  + ask["high"])  / 2
    mid["low"]   = (bid["low"]   + ask["low"])   / 2
    mid["close"] = (bid["close"] + ask["close"]) / 2
    mid["volume"] = 0
    return mid


def main():
    for sym, (bid_file, ask_file) in SYMBOLS.items():
        bid_path = M60DIR / bid_file
        ask_path = M60DIR / ask_file

        if not bid_path.exists() or not ask_path.exists():
            print(f"  SKIP {sym} — files not found in {M60DIR}")
            continue

        print(f"  Building {sym}...", end=" ", flush=True)
        bid = load_raw(bid_path)
        ask = load_raw(ask_path)

        # Align on common timestamps
        common = bid.index.intersection(ask.index)
        bid = bid.loc[common]
        ask = ask.loc[common]

        mid = build_midpoint(bid, ask)

        out = OUTDIR / f"{sym.lower()}_1h_validated.csv"
        mid.to_csv(out, index_label="datetime")
        print(f"{len(mid)} bars → {out.name}")

    print("Done.")


if __name__ == "__main__":
    main()



