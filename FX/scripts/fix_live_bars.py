"""Fix live_bars CSVs on VM — convert bid/ask format to plain OHLCV mid-price."""
import pandas as pd
import pathlib

live_dir = pathlib.Path("data/live_bars")
for csv_path in sorted(live_dir.glob("*.csv")):
    try:
        df = pd.read_csv(csv_path)
        df.columns = [c.strip().lower() for c in df.columns]

        if "open" in df.columns and "open_bid" not in df.columns:
            print(f"{csv_path.name}: already OHLC ({len(df)} rows, last={df.iloc[-1,0]})")
            continue

        ts_col = next(
            (c for c in df.columns if c in ("datetime","timestamp") or "time" in c or "date" in c),
            df.columns[0]
        )

        if "open_bid" in df.columns:
            df["open"]  = (df["open_bid"]  + df["open_ask"])  / 2
            df["high"]  = (df["high_bid"]  + df["high_ask"])  / 2
            df["low"]   = (df["low_bid"]   + df["low_ask"])   / 2
            df["close"] = (df["close_bid"] + df["close_ask"]) / 2

        if "volume" not in df.columns:
            df["volume"] = 0

        df = df.dropna(subset=["open", "close"])
        out = df[[ts_col, "open", "high", "low", "close", "volume"]].copy()
        out = out.rename(columns={ts_col: "datetime"})
        out.to_csv(csv_path, index=False)
        print(f"{csv_path.name}: FIXED -> {len(out)} rows, last={out['datetime'].iloc[-1]}")
    except Exception as e:
        print(f"{csv_path.name}: ERROR {e}")

