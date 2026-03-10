"""
Build bars from 1-minute data for index instruments.

Reads all 1M CSV files from data/1M/, concatenates, deduplicates,
and resamples to the requested timeframe OHLC. Adds bid/ask columns (ASK = BID + spread).
Saves result to data/bars_idx/<symbol>_<timeframe>_bars.csv.

Usage:
    python -m scripts.build_h1_idx
    python -m scripts.build_h1_idx --symbol usatechidxusd --spread 1.0
    python -m scripts.build_h1_idx --timeframe 30min --spread 1.0
    python -m scripts.build_h1_idx --timeframe 4h --spread 1.0
"""
import argparse
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA_1M_DIR = ROOT / "data" / "1M"
BARS_IDX_DIR = ROOT / "data" / "bars_idx"


def load_and_concat_m1(symbol: str) -> pd.DataFrame:
    """Load all 1M CSV files for a given symbol prefix and concatenate."""
    files = sorted(DATA_1M_DIR.glob(f"{symbol}-m1-bid-*.csv"))
    if not files:
        # Also try without bid suffix
        files = sorted(DATA_1M_DIR.glob(f"{symbol}-m1-*.csv"))
    if not files:
        raise FileNotFoundError(
            f"No 1M files found for symbol '{symbol}' in {DATA_1M_DIR}\n"
            f"Files in dir: {[f.name for f in DATA_1M_DIR.glob('*.csv')]}"
        )

    print(f"Found {len(files)} 1M files for {symbol}:")
    frames = []
    for f in files:
        df = pd.read_csv(f)
        df.columns = [c.lower() for c in df.columns]
        # Timestamp is in milliseconds since epoch
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        frames.append(df)
        print(f"  {f.name}: {len(df):,} bars  [{df['timestamp'].iloc[0]} → {df['timestamp'].iloc[-1]}]")

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset="timestamp").sort_values("timestamp")
    combined = combined.set_index("timestamp")
    print(f"\nTotal 1M bars after dedup: {len(combined):,}")
    print(f"Date range: {combined.index[0]} → {combined.index[-1]}")
    return combined


def resample_m1(m1_df: pd.DataFrame, timeframe: str = "1h") -> pd.DataFrame:
    """Resample 1-minute OHLC to the requested timeframe using closed='left', label='left'."""
    bars = m1_df.resample(timeframe, closed="left", label="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
    )
    bars = bars.dropna(how="all")
    bars = bars[bars["open"].notna()]
    print(f"{timeframe} bars after resample: {len(bars):,}")
    return bars


# Keep old name for backward compatibility
def resample_m1_to_h1(m1_df: pd.DataFrame) -> pd.DataFrame:
    return resample_m1(m1_df, "1h")


def add_bid_ask_columns(h1_df: pd.DataFrame, spread: float) -> pd.DataFrame:
    """
    Add bid/ask OHLC columns expected by the strategy.
    The source data is BID prices.
    ASK = BID + spread (constant spread approximation).
    """
    df = h1_df.copy()
    # BID columns (source data)
    df["open_bid"]  = df["open"]
    df["high_bid"]  = df["high"]
    df["low_bid"]   = df["low"]
    df["close_bid"] = df["close"]
    # ASK columns (bid + spread)
    df["open_ask"]  = df["open"]  + spread
    df["high_ask"]  = df["high"]  + spread
    df["low_ask"]   = df["low"]   + spread
    df["close_ask"] = df["close"] + spread
    # Drop the plain OHLC columns (keep only bid/ask)
    df = df.drop(columns=["open", "high", "low", "close"])
    return df


def build_bars(symbol: str = "usatechidxusd", spread: float = 1.0,
               timeframe: str = "1h") -> pd.DataFrame:
    """Full pipeline: load 1M → resample to timeframe → add bid/ask → save."""
    # Normalize timeframe label for filename (e.g. '30min' → '30m', '1h' → '1h')
    tf_label = timeframe.replace("min", "m").replace("T", "m")
    print(f"\n=== Building {tf_label} bars for {symbol.upper()} (spread={spread}) ===\n")

    m1 = load_and_concat_m1(symbol)
    bars = resample_m1(m1, timeframe)
    bars = add_bid_ask_columns(bars, spread)

    BARS_IDX_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BARS_IDX_DIR / f"{symbol}_{tf_label}_bars.csv"
    bars.to_csv(out_path)
    print(f"\nSaved {len(bars):,} {tf_label} bars → {out_path}")
    return bars


# Keep old name for backward compatibility
def build_h1(symbol: str = "usatechidxusd", spread: float = 1.0) -> pd.DataFrame:
    return build_bars(symbol=symbol, spread=spread, timeframe="1h")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build bars from 1M index data")
    parser.add_argument("--symbol", default="usatechidxusd",
                        help="Symbol prefix (default: usatechidxusd)")
    parser.add_argument("--spread", type=float, default=1.0,
                        help="Fixed bid-ask spread in price points (default: 1.0)")
    parser.add_argument("--timeframe", default="1h",
                        help="Target timeframe: 1h, 30min, 15min, 4h, etc. (default: 1h)")
    args = parser.parse_args()

    build_bars(symbol=args.symbol, spread=args.spread, timeframe=args.timeframe)
