"""
rebuild_live_bars.py
====================
Rebuilds live_bars CSVs from bars_validated + any sealed live bars.
- Merges bars_validated (historical) with existing live_bars sealed bars
- Converts all bid/ask formats to plain OHLCV mid-price
- Fills gaps (e.g. missing hours at start of day when bot was offline)
- Output: clean datetime,open,high,low,close,volume CSV per symbol
"""
import pandas as pd
import pathlib

BASE     = pathlib.Path(__file__).parent.parent
VAL_DIR  = BASE / "data" / "bars_validated"
LIVE_DIR = BASE / "data" / "live_bars"

SYMBOLS = ["EURUSD", "USDJPY", "USDCHF", "AUDJPY", "CADJPY"]
KEEP_BARS = 500  # rows to keep in live_bars file

HALF_SPREAD = {
    "EURUSD": 0.00010, "USDJPY": 0.010, "USDCHF": 0.00012,
    "AUDJPY": 0.014,   "CADJPY": 0.015,
}


def read_any_csv(path: pathlib.Path) -> pd.DataFrame:
    """Read CSV regardless of header presence or bid/ask vs OHLC format."""
    if not path.exists() or path.stat().st_size < 20:
        return pd.DataFrame()
    try:
        # Peek at first line to detect header
        first = path.read_text(encoding="utf-8", errors="replace").split("\n")[0].strip()
        first_cell = first.split(",")[0].strip().strip('"')
        has_header = not first_cell[:4].isdigit()

        df = pd.read_csv(path, header=0 if has_header else None)
        df.columns = [
            c.strip().lower() if isinstance(c, str) else f"col{c}"
            for c in df.columns
        ]
        if not has_header:
            names = ["datetime", "open", "high", "low", "close", "volume"]
            extras = [f"col{i}" for i in range(len(df.columns) - len(names))]
            df.columns = (names + extras)[:len(df.columns)]

        # Find timestamp column
        ts_col = next(
            (c for c in df.columns if c in ("datetime","timestamp") or "time" in c or "date" in c),
            df.columns[0]
        )
        df[ts_col] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
        df = df.dropna(subset=[ts_col]).rename(columns={ts_col: "datetime"})
        df = df.sort_values("datetime")

        # Convert bid/ask → mid OHLC
        if "open_bid" in df.columns:
            df["open"]  = (df["open_bid"]  + df["open_ask"])  / 2
            df["high"]  = (df["high_bid"]  + df["high_ask"])  / 2
            df["low"]   = (df["low_bid"]   + df["low_ask"])   / 2
            df["close"] = (df["close_bid"] + df["close_ask"]) / 2
        elif "open" not in df.columns:
            return pd.DataFrame()

        if "volume" not in df.columns:
            df["volume"] = 0

        df = df[["datetime","open","high","low","close","volume"]].dropna(subset=["open","close"])
        # Strip timezone → store as UTC-naive strings
        df["datetime"] = df["datetime"].dt.tz_convert("UTC").dt.tz_localize(None)
        return df
    except Exception as e:
        print(f"  read_any_csv({path.name}): {e}")
        return pd.DataFrame()


for sym in SYMBOLS:
    print(f"\n--- {sym} ---")

    # 1. Load bars_validated (historical base)
    val_path = VAL_DIR / f"{sym.lower()}_1h_validated.csv"
    df_val   = read_any_csv(val_path)
    if df_val.empty:
        print(f"  SKIP: no validated file")
        continue
    print(f"  validated: {len(df_val)} bars, {df_val['datetime'].iloc[0].date()} → {df_val['datetime'].iloc[-1].date()}")

    # 2. Load existing live_bars (may have sealed bars newer than validated)
    live_path = LIVE_DIR / f"{sym}.csv"
    df_live   = read_any_csv(live_path)
    if not df_live.empty:
        print(f"  live_bars: {len(df_live)} bars, last={df_live['datetime'].iloc[-1]}")
    else:
        print(f"  live_bars: empty/missing")

    # 3. Merge — validated is base, live_bars fills in newer
    frames = [df for df in [df_val, df_live] if not df.empty]
    df_merged = pd.concat(frames, ignore_index=True)
    df_merged = df_merged.drop_duplicates(subset=["datetime"], keep="last")
    df_merged = df_merged.sort_values("datetime").reset_index(drop=True)

    # 4. Keep last KEEP_BARS rows
    df_out = df_merged.tail(KEEP_BARS).copy()

    # 5. Save
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(live_path, index=False)
    print(f"  SAVED: {len(df_out)} bars, {df_out['datetime'].iloc[0].date()} → {df_out['datetime'].iloc[-1]}")

print("\nDone.")

