"""
IBKR Market Data Adapter (Gateway version)
Bootstraps H1/H4 bars from historical data, then streams live ticks
and closes bars on the hour boundary.

Gateway paper defaults:
  host: 127.0.0.1
  port: 4002
  clientId: 7
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

import pandas as pd
from ib_insync import IB, Forex, util

# (no core model imports needed in this module)

log = logging.getLogger(__name__)

# Optional state store — injected by runner
try:
    from ..core.state_store import SQLiteStateStore as _StoreType
except ImportError:
    _StoreType = None  # type: ignore

# ── Supported FX symbols ──────────────────────────────────────────────────────
SUPPORTED_SYMBOLS = {
    "EURUSD", "GBPUSD", "USDJPY",
    "USDCHF", "EURJPY", "GBPJPY",
    "AUDJPY", "CADJPY",
}

# Approximate half-spread for bootstrap (bid/ask not available in MIDPOINT bars)
BOOTSTRAP_HALF_SPREAD: Dict[str, float] = {
    "EURUSD": 0.00010,
    "GBPUSD": 0.00012,
    "USDJPY": 0.010,
    "USDCHF": 0.00012,
    "EURJPY": 0.012,
    "GBPJPY": 0.015,
    "AUDJPY": 0.014,
    "CADJPY": 0.015,
}


def _make_contract(symbol: str):
    """Return the ib_insync contract object for an FX pair."""
    if symbol in SUPPORTED_SYMBOLS:
        return Forex(symbol)
    raise ValueError(f"Unsupported symbol: {symbol}. Supported: {SUPPORTED_SYMBOLS}")


def _apply_half_spread(df: pd.DataFrame, half: float) -> pd.DataFrame:
    """Split midpoint OHLC into bid / ask columns."""
    for col in ("open", "high", "low", "close"):
        df[f"{col}_bid"] = df[col] - half
        df[f"{col}_ask"] = df[col] + half
    df.drop(columns=["open", "high", "low", "close"], inplace=True, errors="ignore")
    return df


class IBKRMarketData:
    """
    Market data handler for IBKR Gateway paper trading.

    Lifecycle:
        1. connect()           - connect to running Gateway / TWS
        2. subscribe_symbol()  - bootstrap history + subscribe live tick
        3. update_bars()       - call each loop iteration; fires on_h1_bar_close
                                 callback when a new H1 bar is sealed.
        4. disconnect()
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 7,
        historical_days: int = 60,
    ):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.historical_days = historical_days

        self.ib: IB = IB()
        self.connected: bool = False

        # symbol -> DataFrame(DatetimeIndex, open/high/low/close bid+ask)
        self.h1_bars: Dict[str, pd.DataFrame] = {}
        self.h4_bars: Dict[str, pd.DataFrame] = {}   # kept for backward compat
        self.htf_bars: Dict[str, pd.DataFrame] = {}  # per-symbol HTF (D1 or H4)
        self.m30_bars: Dict[str, pd.DataFrame] = {}  # 30m bars (when ltf=30m)

        # per-symbol timeframe config: symbol -> {"ltf": "H1"|"30m", "htf": "D1"|"H4"}
        self._symbol_tf: Dict[str, Dict[str, str]] = {}

        # Intra-bar tick accumulation: symbol -> list of (ts, bid, ask)
        self._tick_buf: Dict[str, List] = defaultdict(list)
        # Track the "open" of the current incomplete bar
        self._cur_bar_open: Dict[str, Optional[datetime]] = {}
        # Last tick timestamp per symbol (for stale-feed detection)
        self._last_tick_time: Dict[str, datetime] = {}
        # Store ticker objects for resubscription
        self._tickers: Dict[str, object] = {}
        # Store updateEvent handler references so we can remove them on resubscribe
        # (prevents accumulating duplicate handlers after each stale-feed cycle)
        self._ticker_handlers: Dict[str, object] = {}

        # Callback fired with (symbol: str) on each sealed H1 bar
        self.on_h1_bar_close: Optional[Callable[[str], None]] = None

        # pendingTickersEvent heartbeat — fires every IB loop cycle even when
        # price is flat; used to keep _last_tick_time alive for quiet symbols
        # (EURUSD off-peak: bid/ask unchanged for >10 min → ticker.updateEvent silent)
        self._pending_tickers_handler = self._on_pending_tickers

        # Optional persistent state store (injected by runner after init)
        self.store: Optional[object] = None   # SQLiteStateStore | None
    # ── Connection ─────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to IBKR Gateway / TWS."""
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=20)
            self.connected = True

            # ── Register event hooks ──────────────────────────────────────────
            # Fires immediately when TCP connection drops
            self.ib.disconnectedEvent += self._on_disconnected
            # Fires when API is fully ready after reconnect
            self.ib.connectedEvent += self._on_reconnected
            # Fires every IB event loop cycle — used as feed heartbeat
            # so that _last_tick_time stays fresh even when price is flat
            self.ib.pendingTickersEvent += self._pending_tickers_handler

            ts = self.ib.reqCurrentTime()
            log.info("Connected to IBKR %s:%s (clientId=%s) — server time: %s",
                     self.host, self.port, self.client_id, ts)
            print(f"[IBKR] Connected to {self.host}:{self.port} | server time: {ts}")
            return True
        except Exception as exc:
            log.error("IBKR connect failed: %s", exc)
            print(f"[ERROR] IBKR connect failed: {exc}")
            self.connected = False
            return False

    def _on_disconnected(self):
        """Called immediately by ib_insync when connection is lost."""
        self.connected = False
        log.warning("IBKR disconnectedEvent — connection lost, will resubscribe on reconnect")
        print("[WARN] IBKR connection lost (disconnectedEvent)")

    def _on_reconnected(self):
        """Called by ib_insync when connection is restored and API is ready."""
        self.connected = True
        log.info("IBKR connectedEvent — reconnected, resubscribing all symbols...")
        print("[INFO] IBKR reconnected — resubscribing feeds...")
        for symbol in list(self._tickers.keys()):
            self.resubscribe_symbol(symbol)
        log.info("All feeds resubscribed after reconnect")

    def disconnect(self):
        if self.connected:
            self.ib.disconnectedEvent -= self._on_disconnected
            self.ib.connectedEvent -= self._on_reconnected
            self.ib.pendingTickersEvent -= self._pending_tickers_handler
            self.ib.disconnect()
            self.connected = False
            print("[IBKR] Disconnected")

    # ── Symbol subscription ────────────────────────────────────────────────────

    def subscribe_symbol(self, symbol: str,
                         ltf: str = "H1", htf: str = "D1") -> bool:
        """
        Bootstrap historical H1 bars (last N days) and subscribe to live
        tick data for the symbol.

        Args:
            symbol: FX pair, e.g. "EURUSD"
            ltf:    LTF timeframe — "H1" or "30m"  (live always streams H1)
            htf:    HTF timeframe — "D1" or "H4"
        """
        symbol = symbol.upper()
        log.info("subscribe_symbol(%s) ltf=%s htf=%s starting...", symbol, ltf, htf)
        if symbol not in SUPPORTED_SYMBOLS:
            print(f"[ERROR] {symbol} not in supported list: {SUPPORTED_SYMBOLS}")
            return False

        # Store TF config for this symbol
        self._symbol_tf[symbol] = {"ltf": ltf, "htf": htf}

        try:
            contract = _make_contract(symbol)

            # ── 1. Bootstrap historical H1 ──────────────────────────────────
            self._bootstrap_h1(symbol, contract)

            # ── 2. Subscribe live ticks ────────────────────────────────────
            # genericTickList "233" = RTVolume; "" = default ticks (bid/ask/last)
            # snapshot=False, regulatorySnapshot=False
            ticker = self.ib.reqMktData(contract, "233", False, False)
            sym_copy = symbol  # avoid closure capture bug in lambda
            handler = lambda t, s=sym_copy: self._on_ticker_update(s, t)
            ticker.updateEvent += handler

            self._tick_buf[symbol] = []
            self._cur_bar_open[symbol] = None
            self._tickers[symbol] = ticker
            self._ticker_handlers[symbol] = handler  # store for later removal
            self._last_tick_time[symbol] = datetime.utcnow()

            # Give it 2s and log first tick received
            self.ib.sleep(2)
            log.info("subscribe_symbol(%s) initial ticker: bid=%s ask=%s",
                     symbol, ticker.bid, ticker.ask)

            print(f"[IBKR] Subscribed to {symbol}  (bid={ticker.bid} ask={ticker.ask})")
            log.info("subscribe_symbol(%s) complete", symbol)
            return True

        except Exception as exc:
            log.error("subscribe_symbol(%s) failed: %s", symbol, exc)
            print(f"[ERROR] subscribe_symbol({symbol}): {exc}")
            return False

    def resubscribe_symbol(self, symbol: str) -> bool:
        """Cancel existing market data subscription and re-request it (stale feed fix)."""
        symbol = symbol.upper()
        log.info("resubscribe_symbol(%s) — cancelling stale feed...", symbol)
        try:
            old_ticker = self._tickers.get(symbol)
            if old_ticker is not None:
                # Remove our handler from the OLD ticker before cancelling
                # to prevent accumulating duplicate event handlers on each resubscribe.
                old_handler = self._ticker_handlers.get(symbol)
                if old_handler is not None:
                    try:
                        old_ticker.updateEvent -= old_handler
                    except Exception:
                        pass
                self.ib.cancelMktData(old_ticker.contract)
                self.ib.sleep(1)

            contract = _make_contract(symbol)
            ticker = self.ib.reqMktData(contract, "233", False, False)
            sym_copy = symbol
            handler = lambda t, s=sym_copy: self._on_ticker_update(s, t)
            ticker.updateEvent += handler
            self._ticker_handlers[symbol] = handler  # store reference for future removal
            self._tickers[symbol] = ticker
            self._last_tick_time[symbol] = datetime.utcnow()
            self.ib.sleep(2)
            log.info("resubscribe_symbol(%s) done: bid=%s ask=%s", symbol, ticker.bid, ticker.ask)
            print(f"[IBKR] Re-subscribed {symbol}  (bid={ticker.bid} ask={ticker.ask})")
            return True
        except Exception as exc:
            log.error("resubscribe_symbol(%s) failed: %s", symbol, exc)
            return False

    def last_tick_age_seconds(self, symbol: str) -> float:
        """Return seconds since last tick for symbol. 9999 if never received."""
        t = self._last_tick_time.get(symbol)
        if t is None:
            return 9999.0
        return (datetime.utcnow() - t).total_seconds()

    def probe_feed(self, symbol: str) -> bool:
        """
        Actively probe the current bid/ask via a snapshot request.

        Called periodically (e.g. every 5 min) as a heartbeat for symbols
        whose feeds go quiet when price is flat (e.g. EURUSD off-peak hours).
        Unlike passive ticker.updateEvent — which IBKR Paper Gateway does NOT
        fire when price hasn't moved — a snapshot always returns the current
        quote and lets us refresh _last_tick_time.

        Returns True if a valid quote was obtained.
        """
        symbol = symbol.upper()
        if not self.connected:
            return False
        try:
            contract = _make_contract(symbol)
            # snapshot=True → one-shot request, no persistent subscription
            ticker = self.ib.reqMktData(contract, "", True, False)
            self.ib.sleep(1.5)          # give IB time to fill the snapshot
            bid = getattr(ticker, "bid", None)
            ask = getattr(ticker, "ask", None)
            self.ib.cancelMktData(contract)   # clean up immediately
            if bid and ask and bid > 0 and ask > 0:
                now = datetime.utcnow()
                self._last_tick_time[symbol] = now
                # Also inject into tick buffer so bar-sealing has fresh data
                self._tick_buf[symbol].append((now, bid, ask))
                log.debug("probe_feed(%s): snapshot bid=%.5f ask=%.5f → last_tick refreshed",
                          symbol, bid, ask)
                return True
            log.debug("probe_feed(%s): snapshot returned no valid quote (bid=%s ask=%s)",
                      symbol, bid, ask)
            return False
        except Exception as exc:
            log.warning("probe_feed(%s) failed: %s", symbol, exc)
            return False

    # ── Historical bootstrap ───────────────────────────────────────────────────

    def _load_csv_fallback(self, symbol: str) -> bool:
        """
        Load H1 bars from CSV when IBKR HMDS is unavailable.
        Priority:
          1. live_bars/{SYMBOL}.csv   — has sealed live bars (most recent)
          2. bars_validated/{symbol}_1h_validated.csv — historical seed

        After loading, merges both sources so we never lose sealed bars.
        Does NOT overwrite live_bars if it already has newer data.
        Returns True if bars were loaded successfully.
        """
        import pathlib
        base = pathlib.Path(__file__).parent.parent.parent
        validated_path = base / "data" / "bars_validated" / f"{symbol.lower()}_1h_validated.csv"
        live_path      = base / "data" / "live_bars" / f"{symbol}.csv"

        def _read_csv(path) -> pd.DataFrame:
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
                df = df.dropna(subset=[ts_col]).sort_values(ts_col).set_index(ts_col)
                if df.index.tz is not None:
                    df.index = df.index.tz_convert("UTC").tz_localize(None)
                return df
            except Exception as exc:
                log.warning("CSV fallback read failed (%s): %s", path.name, exc)
                return pd.DataFrame()

        df_validated = _read_csv(validated_path)
        df_live      = _read_csv(live_path)

        if df_validated.empty and df_live.empty:
            return False

        # Merge: validated is the base (OHLC), live_bars may have newer sealed bars
        # live_bars has plain open/high/low/close; validated also has open/high/low/close
        frames = []
        for df in [df_validated, df_live]:
            if df.empty:
                continue
            # Normalise to plain OHLC
            if "open" in df.columns:
                frames.append(df[["open","high","low","close"]].copy())
            elif "open_bid" in df.columns:
                tmp = pd.DataFrame(index=df.index)
                tmp["open"]  = (df["open_bid"]  + df["open_ask"])  / 2
                tmp["high"]  = (df["high_bid"]  + df["high_ask"])  / 2
                tmp["low"]   = (df["low_bid"]   + df["low_ask"])   / 2
                tmp["close"] = (df["close_bid"] + df["close_ask"]) / 2
                frames.append(tmp)

        if not frames:
            return False

        df_merged = pd.concat(frames)
        df_merged = df_merged[~df_merged.index.duplicated(keep="last")]
        df_merged.sort_index(inplace=True)
        # Keep last N bars for strategy context
        df_merged = df_merged.tail(max(self.historical_days * 24, 500))

        # Convert to bid/ask for h1_bars internal format
        half = BOOTSTRAP_HALF_SPREAD.get(symbol, 0.0001)
        df_merged = _apply_half_spread(df_merged, half)

        self.h1_bars[symbol] = df_merged
        self._rebuild_h4(symbol)
        log.info("CSV fallback loaded %d H1 bars for %s (%s -> %s)",
                 len(df_merged), symbol, df_merged.index[0], df_merged.index[-1])
        print(f"[IBKR] CSV fallback: {len(df_merged)} H1 bars for {symbol} "
              f"({df_merged.index[0].date()} → {df_merged.index[-1].date()})")

        # Only update live_bars if merged data is newer than existing live_bars
        if not df_live.empty:
            merged_last = df_merged.index[-1]
            live_last   = df_live.index[-1]
            if merged_last <= live_last:
                log.info("CSV fallback: live_bars already up-to-date (%s), not overwriting", live_last)
                return True

        self._save_live_bars(symbol)
        return True

    def _bootstrap_h1(self, symbol: str, contract):
        """
        Fetch last `historical_days` of H1 MIDPOINT bars from IBKR and
        convert to bid/ask DataFrame.
        """
        duration = f"{self.historical_days} D"
        log.info("Bootstrapping %dd H1 history for %s...", self.historical_days, symbol)
        print(f"[IBKR] Bootstrapping {self.historical_days}d H1 history for {symbol}...")

        raw_bars = []
        try:
            raw_bars = self.ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting="1 hour",
                whatToShow="MIDPOINT",
                useRTH=False,
                formatDate=1,
                keepUpToDate=False,
                timeout=60,
            )
        except Exception as exc:
            log.warning("reqHistoricalData failed for %s: %s — will try CSV fallback", symbol, exc)
            print(f"[WARN] Historical data unavailable for {symbol}: {exc} — trying CSV fallback")

        if not raw_bars:
            log.warning("No historical bars from IBKR for %s — trying CSV fallback", symbol)
            if self._load_csv_fallback(symbol):
                return
            print(f"[WARN] No bars available for {symbol} (IBKR + CSV both failed)")
            self.h1_bars[symbol] = pd.DataFrame()
            self.h4_bars[symbol] = pd.DataFrame()
            return

        df = util.df(raw_bars)[["date", "open", "high", "low", "close"]].copy()
        df.rename(columns={"date": "timestamp"}, inplace=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)

        # ── Strip timezone → UTC-naive to avoid tz-aware/naive mix crash ──────
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)

        half = BOOTSTRAP_HALF_SPREAD.get(symbol, 0.0001)
        df = _apply_half_spread(df, half)

        self.h1_bars[symbol] = df
        self._rebuild_h4(symbol)

        log.info("Loaded %d H1 bars for %s (%s -> %s)", len(df), symbol, df.index[0], df.index[-1])
        print(f"[IBKR] Loaded {len(df)} H1 bars for {symbol} ({df.index[0]} -> {df.index[-1]})")

        # ── Persist to live_bars immediately so dashboard is up-to-date ────────
        self._save_live_bars(symbol)

    # ── H4 aggregation ─────────────────────────────────────────────────────────

    def _rebuild_h4(self, symbol: str):
        """Backward-compat wrapper — rebuilds both h4_bars and htf_bars."""
        self._rebuild_htf(symbol)
        self.h4_bars[symbol] = self.htf_bars.get(symbol, pd.DataFrame())

    def _rebuild_htf(self, symbol: str):
        """Aggregate H1 bars into the configured HTF (D1 or H4) for this symbol."""
        df = self.h1_bars.get(symbol)
        if df is None or df.empty:
            self.htf_bars[symbol] = pd.DataFrame()
            return

        tf_cfg = self._symbol_tf.get(symbol, {})
        htf = tf_cfg.get("htf", "D1")
        resample_rule = {"D1": "1D", "H4": "4h", "H8": "8h"}.get(htf, "1D")

        agg = {
            "open_bid": "first", "high_bid": "max", "low_bid": "min", "close_bid": "last",
            "open_ask": "first", "high_ask": "max", "low_ask": "min", "close_ask": "last",
        }
        agg = {k: v for k, v in agg.items() if k in df.columns}
        self.htf_bars[symbol] = df.resample(resample_rule).agg(agg).dropna(how="all")
        # Also keep m30_bars (aggregate from h1 → 30min is just the h1 down-sampled;
        # for 30m LTF we store h1_bars as the source and htf separately)
        self.m30_bars[symbol] = df  # H1 bars = finest granularity we have live

    def get_ltf_bars(self, symbol: str) -> Optional[pd.DataFrame]:
        """Return LTF bars for this symbol (H1 regardless of configured ltf — live uses H1)."""
        return self.h1_bars.get(symbol)

    def get_htf_bars(self, symbol: str) -> Optional[pd.DataFrame]:
        """Return HTF bars for this symbol (D1 or H4 depending on config)."""
        df = self.htf_bars.get(symbol)
        if df is not None and not df.empty:
            return df
        return self.h4_bars.get(symbol)

    # ── Live tick handling ─────────────────────────────────────────────────────

    def _on_pending_tickers(self, tickers):
        """
        Heartbeat callback — fired by ib_insync every event loop cycle for any
        tickers that have pending updates (including unchanged snapshots).

        This fires even when bid/ask has NOT changed, which prevents false
        'stale feed' alarms for quiet symbols like EURUSD off-peak hours where
        the price can be flat for >10 minutes but the feed is perfectly alive.
        """
        now = datetime.utcnow()
        for ticker in tickers:
            symbol = None
            # Map ticker back to our symbol name
            for sym, t in self._tickers.items():
                if t is ticker:
                    symbol = sym
                    break
            if symbol is None:
                continue
            bid = getattr(ticker, "bid", None)
            ask = getattr(ticker, "ask", None)
            if bid and ask and bid > 0 and ask > 0:
                self._last_tick_time[symbol] = now

    def _on_ticker_update(self, symbol: str, ticker):
        """Callback from ib_insync when new quote arrives."""
        bid = getattr(ticker, "bid", None)
        ask = getattr(ticker, "ask", None)

        # Always update last_tick_time on any callback — even if bid/ask haven't
        # changed.  This prevents false "stale feed" alarms when price is quiet
        # (EURUSD can be flat for >10 min during off-peak hours but ticker is alive).
        if bid and ask and bid > 0 and ask > 0:
            self._last_tick_time[symbol] = datetime.now(tz=timezone.utc).replace(tzinfo=None)

        if not bid or not ask or bid <= 0 or ask <= 0:
            log.debug("_on_ticker_update(%s): skipped — bid=%s ask=%s", symbol, bid, ask)
            return

        ts = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        self._tick_buf[symbol].append((ts, bid, ask))
        log.debug("_on_ticker_update(%s): tick saved bid=%.5f ask=%.5f buf_len=%d",
                  symbol, bid, ask, len(self._tick_buf[symbol]))

        # Limit memory
        if len(self._tick_buf[symbol]) > 2000:
            self._tick_buf[symbol] = self._tick_buf[symbol][-1000:]

    def update_bars(self, symbol: str):
        """
        Inspect the tick buffer; if one or more H1 boundaries have been crossed,
        seal each completed bar, append to h1_bars, rebuild H4, and fire callback.

        Call this from the main loop (e.g. every 30 s).
        """
        ticks = self._tick_buf.get(symbol)
        log.debug("update_bars(%s): %d ticks in buffer", symbol, len(ticks) if ticks else 0)
        if not ticks:
            return

        now = datetime.utcnow()
        # last_completed_hour: the open-time of the most recently FINISHED bar.
        # E.g. when now=13:05, bar 12:00-13:00 just finished → last_completed_hour=12:00.
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        last_completed_hour = current_hour_start - timedelta(hours=1)

        h1 = self.h1_bars.get(symbol)
        if h1 is None or h1.empty:
            return

        last_sealed = h1.index[-1].to_pydatetime().replace(tzinfo=None)
        log.debug("update_bars(%s): now=%s last_sealed=%s", symbol, current_hour_start, last_sealed)

        # Have we moved past the last sealed bar's hour?
        if last_completed_hour <= last_sealed:
            return  # Most recent completed bar already sealed

        # ── Seal ALL fully-completed bars since last_sealed ──────────────────
        # Bar opening at X:00 is complete when now >= X+1:00,
        # i.e. last_completed_hour >= X:00.
        # Start from last_sealed + 1h (first bar not yet in h1_bars).
        sealed_any = False
        bar_start = last_sealed + timedelta(hours=1)

        while bar_start <= last_completed_hour:
            bar_end = bar_start + timedelta(hours=1)

            # Skip timestamps already in the DataFrame (avoid duplicates on re-entry)
            if pd.Timestamp(bar_start) in self.h1_bars[symbol].index:
                bar_start = bar_end
                continue

            bar_ticks = [(ts, b, a) for ts, b, a in ticks if bar_start <= ts < bar_end]

            if bar_ticks:
                bids = [b for _, b, _ in bar_ticks]
                asks = [a for _, _, a in bar_ticks]
                new_row = pd.DataFrame(
                    [{
                        "open_bid": bids[0], "high_bid": max(bids),
                        "low_bid": min(bids), "close_bid": bids[-1],
                        "open_ask": asks[0], "high_ask": max(asks),
                        "low_ask": min(asks), "close_ask": asks[-1],
                    }],
                    index=pd.DatetimeIndex([bar_start]),
                )
                self.h1_bars[symbol] = pd.concat([self.h1_bars[symbol], new_row])
                self.h1_bars[symbol].sort_index(inplace=True)  # ensure last_sealed is correct
                log.info("Sealed H1 bar %s for %s", bar_start, symbol)
                print(f"[BAR] Sealed H1 bar {bar_start} for {symbol}")
                sealed_any = True
            else:
                # No ticks for this bar (bot was offline / reconnected mid-hour).
                # Forward-fill using last known close so that last_sealed advances
                # and the bot is not permanently stuck skipping the same gap.
                last_row = self.h1_bars[symbol].iloc[-1]
                ffill_row = pd.DataFrame(
                    [{
                        "open_bid":  last_row["close_bid"], "high_bid":  last_row["close_bid"],
                        "low_bid":   last_row["close_bid"], "close_bid": last_row["close_bid"],
                        "open_ask":  last_row["close_ask"], "high_ask":  last_row["close_ask"],
                        "low_ask":   last_row["close_ask"], "close_ask": last_row["close_ask"],
                    }],
                    index=pd.DatetimeIndex([bar_start]),
                )
                self.h1_bars[symbol] = pd.concat([self.h1_bars[symbol], ffill_row])
                self.h1_bars[symbol].sort_index(inplace=True)
                log.info("update_bars(%s): no ticks for bar %s-%s — forward-filled (gap in data)",
                         symbol, bar_start, bar_end)
                sealed_any = True  # advance last_sealed even for ffill bars

            bar_start = bar_end

        if sealed_any:
            self._rebuild_h4(symbol)
            # Remove all processed ticks (older than current_hour_start)
            self._tick_buf[symbol] = [(ts, b, a) for ts, b, a in ticks if ts >= current_hour_start]
            self._save_live_bars(symbol)

            # ── Persistent state guard ─────────────────────────────────────
            # Skip callback if this bar was already processed before restart.
            sealed_bar_ts = self.h1_bars[symbol].index[-1]
            sealed_bar_ts_iso = str(sealed_bar_ts.isoformat())

            if self.store is not None:
                try:
                    db_state = self.store.load_strategy_state(symbol)
                    if db_state and db_state.last_processed_bar_ts:
                        if sealed_bar_ts_iso <= db_state.last_processed_bar_ts:
                            log.debug(
                                "update_bars(%s): bar %s already processed "
                                "(last_processed=%s) — skipping callback",
                                symbol, sealed_bar_ts_iso,
                                db_state.last_processed_bar_ts,
                            )
                            return  # do not re-run strategy on already-processed bar
                except Exception as _e:
                    log.warning("update_bars: DB guard check failed: %s", _e)

            if self.on_h1_bar_close:
                self.on_h1_bar_close(symbol)

            # ── Save last processed bar to DB ──────────────────────────────
            if self.store is not None:
                try:
                    from ..core.state_store import StrategyState
                    existing = self.store.load_strategy_state(symbol)
                    if existing is None:
                        from ..core.state_store import StrategyState as _SS
                        existing = _SS(symbol=symbol)
                    existing.last_processed_bar_ts = sealed_bar_ts_iso
                    self.store.save_strategy_state(existing)
                except Exception as _e:
                    log.warning("update_bars: DB state save failed: %s", _e)

    def _save_live_bars(self, symbol: str):
        """Write last 500 H1 bars to data/live_bars/SYMBOL.csv for the dashboard.
        Always merges with existing file so Yahoo-patched historical bars are preserved.
        """
        import pathlib
        try:
            df = self.h1_bars.get(symbol)
            if df is None or df.empty:
                return
            live_dir = pathlib.Path(__file__).parent.parent.parent / "data" / "live_bars"
            live_dir.mkdir(parents=True, exist_ok=True)
            out_path = live_dir / f"{symbol}.csv"
            df_out = df.tail(500).copy()

            # Compute mid-price OHLC from internal bid/ask format
            rows = []
            for ts, row in df_out.iterrows():
                try:
                    if "open_bid" in row.index and pd.notna(row.get("open_bid")) and pd.notna(row.get("open_ask")):
                        o  = (row["open_bid"]  + row["open_ask"])  / 2
                        h  = (row["high_bid"]  + row["high_ask"])  / 2
                        lo = (row["low_bid"]   + row["low_ask"])   / 2
                        c  = (row["close_bid"] + row["close_ask"]) / 2
                    elif "open" in row.index and pd.notna(row.get("open")):
                        o, h, lo, c = row["open"], row["high"], row["low"], row["close"]
                    else:
                        continue
                    v = row.get("volume", 0)
                    rows.append({"datetime": ts, "open": o, "high": h, "low": lo, "close": c,
                                 "volume": 0 if pd.isna(v) else v})
                except Exception:
                    continue

            if not rows:
                return
            df_new = pd.DataFrame(rows).set_index("datetime")

            # Merge with existing file — keep existing bars for timestamps not in df_new
            # This preserves Yahoo-patched historical bars when bot seals a single new bar
            if out_path.exists() and out_path.stat().st_size > 100:
                try:
                    df_existing = pd.read_csv(out_path)
                    df_existing.columns = [c.strip().lower() for c in df_existing.columns]
                    ts_col = next(
                        (c for c in df_existing.columns if c in ("datetime","timestamp") or "time" in c),
                        df_existing.columns[0]
                    )
                    df_existing[ts_col] = pd.to_datetime(df_existing[ts_col], utc=False, errors="coerce")
                    df_existing = df_existing.dropna(subset=[ts_col]).set_index(ts_col)
                    if df_existing.index.tz is not None:
                        df_existing.index = df_existing.index.tz_localize(None)
                    # Only keep OHLCV columns from existing
                    ohlcv = ["open","high","low","close","volume"]
                    existing_ohlcv = [c for c in ohlcv if c in df_existing.columns]
                    if existing_ohlcv:
                        df_existing = df_existing[existing_ohlcv]
                        # Remove flat (forward-filled) bars from existing
                        flat = ((df_existing.get("open") == df_existing.get("high")) &
                                (df_existing.get("high") == df_existing.get("low")) &
                                (df_existing.get("low")  == df_existing.get("close")))
                        df_existing = df_existing[~flat]
                        # Merge: new bars override, keep existing for older timestamps
                        df_merged = pd.concat([df_existing, df_new])
                        df_merged = df_merged[~df_merged.index.duplicated(keep="last")]
                        df_merged.sort_index(inplace=True)
                        df_new = df_merged.tail(500)
                except Exception as exc:
                    log.debug("Could not merge existing live_bars for %s: %s", symbol, exc)

            df_new.index.name = "datetime"
            df_new.to_csv(out_path, index=True, index_label="datetime")
            log.debug("Saved %d live bars for %s -> %s", len(df_new), symbol, out_path.name)
        except Exception as exc:
            log.warning("Could not save live bars for %s: %s", symbol, exc)

    # ── Accessors ──────────────────────────────────────────────────────────────

    def get_h1_bars(self, symbol: str) -> Optional[pd.DataFrame]:
        return self.h1_bars.get(symbol)

    def get_h4_bars(self, symbol: str) -> Optional[pd.DataFrame]:
        return self.h4_bars.get(symbol)

    def bar_count(self, symbol: str) -> int:
        df = self.h1_bars.get(symbol)
        return 0 if df is None else len(df)
