"""
update_bars_from_ibkr.py
========================
Pobiera dane H1 bezpośrednio z IBKR Gateway i aktualizuje:
  - data/bars_validated/{symbol}_1h_validated.csv
  - data/live_bars/{symbol}.csv  (ostatnie 500 barów)

Uruchamiany NA VM (lub lokalnie przez SSH tunnel do portu 4002).

Użycie:
  # na VM:
  /home/macie/bojkofx/venv/bin/python scripts/update_bars_from_ibkr.py

  # lokalnie przez SSH tunnel:
  ssh -L 4002:localhost:4002 macie@34.31.64.224 -N &
  python scripts/update_bars_from_ibkr.py --host 127.0.0.1 --port 4002

Opcje:
  --host       IBKR Gateway host (default: 127.0.0.1)
  --port       IBKR Gateway port (default: 4002)
  --client-id  IB client ID (default: 10, żeby nie kolidować z botem=7)
  --days       Ile dni historii pobrać (default: 400)
  --symbols    Które pary (default: wszystkie 5)
  --dry-run    Tylko wyświetl co by pobrało, nie zapisuj
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time
from datetime import datetime, timezone

import pandas as pd
from ib_insync import IB, Forex, util

# ── Konfiguracja ───────────────────────────────────────────────────────────────

BASE_DIR = pathlib.Path(__file__).parent.parent  # korzeń projektu

VALIDATED_DIR = BASE_DIR / "data" / "bars_validated"
LIVE_BARS_DIR  = BASE_DIR / "data" / "live_bars"

VALIDATED_DIR.mkdir(parents=True, exist_ok=True)
LIVE_BARS_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = ["EURUSD", "USDJPY", "USDCHF", "AUDJPY", "CADJPY"]

HALF_SPREAD = {
    "EURUSD": 0.00010,
    "USDJPY": 0.010,
    "USDCHF": 0.00012,
    "AUDJPY": 0.014,
    "CADJPY": 0.015,
}

# Maksymalny request IBKR: 365 D jednorazowo (H1 bar size)
MAX_DAYS_PER_REQUEST = 365

from datetime import timedelta

# ── Helpers ────────────────────────────────────────────────────────────────────

def _apply_half_spread(df: pd.DataFrame, half: float) -> pd.DataFrame:
    for col in ("open", "high", "low", "close"):
        df[f"{col}_bid"] = df[col] - half
        df[f"{col}_ask"] = df[col] + half
    df.drop(columns=["open", "high", "low", "close"], inplace=True, errors="ignore")
    return df


def fetch_h1_via_ticks(ib: IB, symbol: str, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
    """
    Pobiera bary H1 przez reqHistoricalTicks (BID_ASK).
    Działa bez HMDS — używa cashfarm/real-time data.
    Agreguje ticki do barów H1 (mid = (bid+ask)/2).
    """
    contract = Forex(symbol)
    all_ticks = []

    # reqHistoricalTicks zwraca max 1000 ticków — musimy iterować
    cur = start_dt.replace(tzinfo=timezone.utc) if start_dt.tzinfo is None else start_dt
    end = end_dt.replace(tzinfo=timezone.utc) if end_dt.tzinfo is None else end_dt

    print(f"  Fetching ticks {cur.strftime('%Y-%m-%d %H:%M')} → {end.strftime('%Y-%m-%d %H:%M')}...")

    iterations = 0
    while cur < end and iterations < 200:
        iterations += 1
        start_str = cur.strftime("%Y%m%d %H:%M:%S")
        try:
            ticks = ib.reqHistoricalTicks(
                contract,
                startDateTime=start_str,
                endDateTime="",
                numberOfTicks=1000,
                whatToShow="BID_ASK",
                useRth=False,
            )
        except Exception as exc:
            print(f"  reqHistoricalTicks ERROR: {exc}")
            break

        if not ticks:
            break

        for t in ticks:
            ts = pd.Timestamp(t.time).tz_convert("UTC").tz_localize(None)
            mid = (t.priceBid + t.priceAsk) / 2
            all_ticks.append({"datetime": ts, "mid": mid})

        last_ts = pd.Timestamp(ticks[-1].time).tz_convert("UTC")
        if last_ts <= cur:
            break
        cur = last_ts + timedelta(milliseconds=1)

        if len(ticks) < 999:
            break  # got all ticks up to end

    if not all_ticks:
        return pd.DataFrame()

    df = pd.DataFrame(all_ticks).set_index("datetime")
    df.sort_index(inplace=True)

    # Aggregate ticks to H1 bars
    df_h1 = df["mid"].resample("1h").ohlc()
    df_h1.columns = ["open", "high", "low", "close"]
    df_h1 = df_h1.dropna()
    print(f"  Ticks→H1: {len(all_ticks)} ticks → {len(df_h1)} bars "
          f"({df_h1.index[0]} → {df_h1.index[-1]})")
    return df_h1


def fetch_h1_bars(ib: IB, symbol: str, days: int) -> pd.DataFrame:
    """
    Pobiera do `days` dni barów H1 z IBKR Gateway.
    Próbuje kolejno: BID → ASK → MIDPOINT
    BID/ASK działa przez cashfarm (bez HMDS), MIDPOINT wymaga cashhmds.
    """
    contract = Forex(symbol)
    all_dfs = []

    remaining = days
    end_dt = ""

    # IBKR Forex historical data: try each whatToShow in order
    # MIDPOINT/BID/ASK all go through HMDS for Forex on IDEALPRO
    # Try all options — one may work depending on gateway state
    for what_to_show in ["MIDPOINT", "BID", "ASK"]:
        print(f"  Trying whatToShow={what_to_show}...")
        remaining = days
        end_dt = ""
        all_dfs = []

        while remaining > 0:
            chunk = min(remaining, MAX_DAYS_PER_REQUEST)
            duration = f"{chunk} D"
            print(f"  Requesting {chunk}D H1 {what_to_show} for {symbol}...")

            try:
                raw = ib.reqHistoricalData(
                    contract,
                    endDateTime=end_dt,
                    durationStr=duration,
                    barSizeSetting="1 hour",
                    whatToShow=what_to_show,
                    useRTH=False,
                    formatDate=1,
                    keepUpToDate=False,
                    timeout=15,
                )
            except Exception as exc:
                print(f"  ERROR ({what_to_show}): {exc}")
                raw = []

            if not raw:
                print(f"  No bars for {what_to_show} — trying next option.")
                break  # break while, try next what_to_show

            df = util.df(raw)[["date", "open", "high", "low", "close"]].copy()
            df.rename(columns={"date": "datetime"}, inplace=True)
            df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
            df.set_index("datetime", inplace=True)
            df.sort_index(inplace=True)

            print(f"  Got {len(df)} bars: {df.index[0]} → {df.index[-1]}")
            all_dfs.append(df)

            end_dt = df.index[0].strftime("%Y%m%d %H:%M:%S")
            remaining -= chunk

            if len(raw) < chunk * 20:
                break

            time.sleep(1)

        if all_dfs:
            break  # success — stop trying other what_to_show values

    if not all_dfs:
        return pd.DataFrame()

    result = pd.concat(all_dfs)
    result = result[~result.index.duplicated(keep="last")]
    result.sort_index(inplace=True)

    # Normalizuj index → UTC-naive
    if result.index.tz is not None:
        result.index = result.index.tz_convert("UTC").tz_localize(None)

    return result


def load_existing_validated(symbol: str) -> pd.DataFrame:
    """Wczytaj istniejący plik bars_validated jeśli istnieje."""
    path = VALIDATED_DIR / f"{symbol.lower()}_1h_validated.csv"
    if not path.exists() or path.stat().st_size < 100:
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        df.columns = [c.strip().lower() for c in df.columns]
        ts_col = next(
            (c for c in df.columns if c in ("datetime", "timestamp") or "time" in c or "date" in c),
            df.columns[0]
        )
        df[ts_col] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
        df = df.dropna(subset=[ts_col]).sort_values(ts_col)
        df = df.rename(columns={ts_col: "datetime"}).set_index("datetime")
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        return df
    except Exception as exc:
        print(f"  WARN: could not load existing {path.name}: {exc}")
        return pd.DataFrame()


def save_validated(symbol: str, df: pd.DataFrame, dry_run: bool = False):
    """Zapisz do bars_validated CSV."""
    path = VALIDATED_DIR / f"{symbol.lower()}_1h_validated.csv"
    if dry_run:
        print(f"  [DRY-RUN] would save {len(df)} bars → {path.name}")
        return
    df_save = df.copy()
    df_save.index.name = "datetime"
    # Upewnij się że mamy podstawowe kolumny (open, high, low, close lub bid/ask)
    df_save.to_csv(path)
    print(f"  Saved {len(df_save)} bars → {path.name}")


def save_live_bars(symbol: str, df: pd.DataFrame, dry_run: bool = False):
    """Zapisz ostatnie 500 barów do live_bars CSV (format dashboard)."""
    path = LIVE_BARS_DIR / f"{symbol}.csv"
    if dry_run:
        print(f"  [DRY-RUN] would save live_bars {len(df.tail(500))} bars → {path.name}")
        return

    df_live = df.tail(500).copy()

    # Jeśli mamy bid/ask → policz mid dla OHLC
    if "open_bid" in df_live.columns and "open" not in df_live.columns:
        df_live["open"]  = (df_live["open_bid"]  + df_live["open_ask"])  / 2
        df_live["high"]  = (df_live["high_bid"]  + df_live["high_ask"])  / 2
        df_live["low"]   = (df_live["low_bid"]   + df_live["low_ask"])   / 2
        df_live["close"] = (df_live["close_bid"] + df_live["close_ask"]) / 2

    if "volume" not in df_live.columns:
        df_live["volume"] = 0

    df_live.index.name = "datetime"
    df_live[["open", "high", "low", "close", "volume"]].to_csv(path)
    print(f"  Saved live_bars {len(df_live)} bars → {path.name}  (last: {df_live.index[-1]})")


# ── Główna logika ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Update bars_validated from IBKR Gateway")
    parser.add_argument("--host",      default="127.0.0.1")
    parser.add_argument("--port",      type=int, default=4002)
    parser.add_argument("--client-id", type=int, default=10,
                        help="IB client ID (użyj !=7 żeby nie kolidować z botem)")
    parser.add_argument("--days",      type=int, default=400,
                        help="Ile dni historii pobrać")
    parser.add_argument("--symbols",   nargs="+", default=SYMBOLS,
                        help="Które pary walutowe zaktualizować")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Nie zapisuj plików — tylko pokaż co by pobrało")
    args = parser.parse_args()

    symbols = [s.upper() for s in args.symbols]
    print(f"\n{'='*60}")
    print(f"IBKR bars updater")
    print(f"  Host: {args.host}:{args.port}  clientId={args.client_id}")
    print(f"  Days: {args.days}  Symbols: {symbols}")
    print(f"  Dry-run: {args.dry_run}")
    print(f"{'='*60}\n")

    # Połącz z IBKR Gateway
    ib = IB()
    try:
        ib.connect(args.host, args.port, clientId=args.client_id, timeout=20)
        ts = ib.reqCurrentTime()
        print(f"Connected to IBKR Gateway — server time: {ts}\n")
    except Exception as exc:
        print(f"ERROR: Cannot connect to IBKR Gateway at {args.host}:{args.port}: {exc}")
        print("Upewnij się że IB Gateway działa i port 4002 jest dostępny.")
        sys.exit(1)

    results = {}

    for symbol in symbols:
        print(f"\n{'─'*50}")
        print(f"Processing {symbol}...")

        # 1. Wczytaj istniejące dane
        df_existing = load_existing_validated(symbol)
        if not df_existing.empty:
            last_dt = df_existing.index[-1]
            print(f"  Existing: {len(df_existing)} bars, last={last_dt}")
            days_missing = (datetime.utcnow() - last_dt.to_pydatetime()).days + 2
            fetch_days = min(days_missing, args.days)
            print(f"  Missing ~{days_missing} days → will fetch {fetch_days} days from IBKR")
        else:
            fetch_days = args.days
            last_dt = None
            print(f"  No existing data → fetching {fetch_days} days from IBKR")

        # 2a. Próbuj reqHistoricalData (MIDPOINT/BID/ASK)
        df_new = fetch_h1_bars(ib, symbol, fetch_days)

        # 2b. Fallback: reqHistoricalTicks — działa bez HMDS dla ostatnich kilku dni
        if df_new.empty and last_dt is not None:
            print(f"  reqHistoricalData failed — trying reqHistoricalTicks fallback...")
            tick_start = last_dt.to_pydatetime() + timedelta(hours=1)
            tick_end   = datetime.utcnow()
            df_new = fetch_h1_via_ticks(ib, symbol, tick_start, tick_end)

        if df_new.empty:
            print(f"  SKIP: no new bars from IBKR for {symbol}")
            results[symbol] = "SKIP (no IBKR data)"
            continue

        # 3. Połącz z istniejącymi
        if not df_existing.empty:
            # Istniejące mogą mieć bid/ask kolumny — wyciągnij mid jeśli trzeba
            df_existing_ohlc = df_existing.copy()
            if "open_bid" in df_existing_ohlc.columns and "open" not in df_existing_ohlc.columns:
                df_existing_ohlc["open"]  = (df_existing_ohlc["open_bid"]  + df_existing_ohlc["open_ask"])  / 2
                df_existing_ohlc["high"]  = (df_existing_ohlc["high_bid"]  + df_existing_ohlc["high_ask"])  / 2
                df_existing_ohlc["low"]   = (df_existing_ohlc["low_bid"]   + df_existing_ohlc["low_ask"])   / 2
                df_existing_ohlc["close"] = (df_existing_ohlc["close_bid"] + df_existing_ohlc["close_ask"]) / 2

            # Zachowaj tylko OHLC z obu
            cols = ["open", "high", "low", "close"]
            existing_cols = [c for c in cols if c in df_existing_ohlc.columns]
            new_cols      = [c for c in cols if c in df_new.columns]

            df_merged = pd.concat([
                df_existing_ohlc[existing_cols],
                df_new[new_cols]
            ])
            df_merged = df_merged[~df_merged.index.duplicated(keep="last")]
            df_merged.sort_index(inplace=True)
            added = len(df_merged) - len(df_existing)
            print(f"  Merged: {len(df_existing)} existing + {len(df_new)} new = {len(df_merged)} total (+{added} unique)")
        else:
            df_merged = df_new[["open", "high", "low", "close"]].copy()
            print(f"  New dataset: {len(df_merged)} bars")

        if "volume" not in df_merged.columns:
            df_merged["volume"] = 0

        # 4. Zapisz bars_validated
        save_validated(symbol, df_merged, dry_run=args.dry_run)

        # 5. Zapisz live_bars (bez bid/ask — tylko OHLCV)
        save_live_bars(symbol, df_merged, dry_run=args.dry_run)

        results[symbol] = f"OK ({len(df_merged)} bars, last={df_merged.index[-1]})"

    # Podsumowanie
    print(f"\n{'='*60}")
    print("SUMMARY:")
    for sym, res in results.items():
        print(f"  {sym}: {res}")
    print(f"{'='*60}\n")

    ib.disconnect()
    print("Disconnected from IBKR Gateway.")


if __name__ == "__main__":
    main()

