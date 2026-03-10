"""
IBKR Market Data for US100 / NAS100USD (CFD)
─────────────────────────────────────────────
5-minute bar resolution via live tick aggregation.

Key differences from ibkr_marketdata.py (FX):
  - Contract: CFD (NAS100USD) instead of Forex
  - Bar resolution: 5 minutes
  - Single-symbol design (no per-symbol dicts)
  - HTF (4h) built by resampling 5m bars

Usage lifecycle:
    md = IBKRMarketDataIdx(host, port, client_id=8)
    md.on_bar_close = callback          # fires on every sealed 5m bar
    md.connect()
    md.subscribe()
    while True:
        ib.sleep(30)
        md.update_bars()                # seals completed 5m bars
"""

from __future__ import annotations

import logging
import pathlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

import pandas as pd
from ib_insync import IB, Contract, util

log = logging.getLogger(__name__)

# ── Contract definition ────────────────────────────────────────────────────────
SYMBOL = "NAS100USD"      # internal symbol name
IBKR_SYMBOL = "NAS100USD" # IBKR CFD symbol

# Approximate half-spread from midpoint (NAS100USD bid-ask ≈ 1 point → 0.5 each side)
HALF_SPREAD: float = 0.5

# Minutes per LTF bar
BAR_MINUTES: int = 5

# Bootstrap: how many calendar days of 5m history to request from IBKR
BOOTSTRAP_DAYS: int = 30


def _make_contract() -> Contract:
    """Return the ib_insync CFD Contract for NAS100USD."""
    return Contract(
        symbol=IBKR_SYMBOL,
        secType="CFD",
        exchange="SMART",
        currency="USD",
    )


def _floor_bar(dt: datetime, minutes: int = BAR_MINUTES) -> datetime:
    """Truncate datetime to N-minute boundary (UTC-naive)."""
    total_minutes = dt.hour * 60 + dt.minute
    floored = (total_minutes // minutes) * minutes
    return dt.replace(hour=floored // 60, minute=floored % 60,
                      second=0, microsecond=0)


def _apply_half_spread(df: pd.DataFrame, half: float = HALF_SPREAD) -> pd.DataFrame:
    """Split midpoint OHLC into bid/ask columns (in-place, returns df)."""
    for col in ("open", "high", "low", "close"):
        df[f"{col}_bid"] = df[col] - half
        df[f"{col}_ask"] = df[col] + half
    df.drop(columns=["open", "high", "low", "close"], inplace=True, errors="ignore")
    return df


class IBKRMarketDataIdx:
    """
    Market data handler for NAS100USD CFD (5-minute bars).

    Lifecycle:
        1. connect()       — connect to running Gateway / TWS
        2. subscribe()     — bootstrap 5m history + subscribe live tick feed
        3. update_bars()   — call each loop iteration; seals completed 5m bars
                             and fires on_bar_close callback
        4. disconnect()
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 8,
        historical_days: int = BOOTSTRAP_DAYS,
    ):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.historical_days = historical_days

        self.ib: IB = IB()
        self.connected: bool = False

        # 5-minute LTF bars (DatetimeIndex, bid/ask OHLC)
        self.ltf_bars: Optional[pd.DataFrame] = None
        # 4-hour HTF bars (aggregated from 5m)
        self.htf_bars: Optional[pd.DataFrame] = None

        # Tick accumulation buffer: list of (ts, bid, ask)
        self._tick_buf: List = []
        # Last tick timestamp (stale-feed detection)
        self._last_tick_time: Optional[datetime] = None
        # IBKR ticker object
        self._ticker = None
        self._ticker_handler = None

        # Callback: fired whenever a new 5m bar is sealed
        self.on_bar_close: Optional[Callable[[], None]] = None

        # pendingTickersEvent heartbeat (flat-price detection)
        self._pending_tickers_handler = self._on_pending_tickers

        # Optional state store (injected by runner)
        self.store = None

    # ── Connection ─────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=20)
            self.connected = True
            self.ib.disconnectedEvent += self._on_disconnected
            self.ib.connectedEvent    += self._on_reconnected
            self.ib.pendingTickersEvent += self._pending_tickers_handler
            ts = self.ib.reqCurrentTime()
            log.info("Connected to IBKR %s:%s (clientId=%s) server time: %s",
                     self.host, self.port, self.client_id, ts)
            print(f"[IBKR-IDX] Connected to {self.host}:{self.port} | server time: {ts}")
            return True
        except Exception as exc:
            log.error("IBKR-IDX connect failed: %s", exc)
            print(f"[ERROR] IBKR-IDX connect failed: {exc}")
            self.connected = False
            return False

    def _on_disconnected(self):
        self.connected = False
        log.warning("IBKR-IDX disconnectedEvent — connection lost")
        print("[WARN] IBKR-IDX connection lost")

    def _on_reconnected(self):
        self.connected = True
        log.info("IBKR-IDX connectedEvent — reconnected, resubscribing...")
        print("[INFO] IBKR-IDX reconnected — resubscribing feed...")
        self.resubscribe()

    def disconnect(self):
        if self.connected:
            self.ib.disconnectedEvent   -= self._on_disconnected
            self.ib.connectedEvent      -= self._on_reconnected
            self.ib.pendingTickersEvent -= self._pending_tickers_handler
            self.ib.disconnect()
            self.connected = False
            print("[IBKR-IDX] Disconnected")

    # ── Subscription ──────────────────────────────────────────────────────────

    def subscribe(self) -> bool:
        """Bootstrap historical 5m bars and subscribe to live tick feed."""
        log.info("subscribe() starting bootstrap for %s", SYMBOL)
        try:
            contract = _make_contract()
            self._bootstrap(contract)

            # Subscribe live ticks
            ticker = self.ib.reqMktData(contract, "233", False, False)
            handler = lambda t: self._on_ticker_update(t)
            ticker.updateEvent += handler
            self._ticker = ticker
            self._ticker_handler = handler
            self._last_tick_time = datetime.utcnow()
            self.ib.sleep(2)
            log.info("subscribe() done: bid=%s ask=%s", ticker.bid, ticker.ask)
            print(f"[IBKR-IDX] Subscribed {SYMBOL}  (bid={ticker.bid} ask={ticker.ask})")
            return True
        except Exception as exc:
            log.error("subscribe() failed: %s", exc)
            print(f"[ERROR] IBKR-IDX subscribe: {exc}")
            return False

    def resubscribe(self) -> bool:
        """Cancel existing feed and re-request (stale-feed recovery)."""
        log.info("resubscribe() — stale feed fix")
        try:
            if self._ticker is not None:
                if self._ticker_handler is not None:
                    try:
                        self._ticker.updateEvent -= self._ticker_handler
                    except Exception:
                        pass
                self.ib.cancelMktData(self._ticker.contract)
                self.ib.sleep(1)

            contract = _make_contract()
            ticker = self.ib.reqMktData(contract, "233", False, False)
            handler = lambda t: self._on_ticker_update(t)
            ticker.updateEvent += handler
            self._ticker = ticker
            self._ticker_handler = handler
            self._last_tick_time = datetime.utcnow()
            self.ib.sleep(2)
            log.info("resubscribe() done: bid=%s ask=%s", ticker.bid, ticker.ask)
            print(f"[IBKR-IDX] Re-subscribed {SYMBOL}  (bid={ticker.bid} ask={ticker.ask})")
            return True
        except Exception as exc:
            log.error("resubscribe() failed: %s", exc)
            return False

    # ── Historical bootstrap ───────────────────────────────────────────────────

    def _bootstrap(self, contract: Contract):
        """Fetch last N days of 5m MIDPOINT bars from IBKR."""
        duration = f"{self.historical_days} D"
        log.info("Bootstrapping %dd of 5m history for %s...", self.historical_days, SYMBOL)
        print(f"[IBKR-IDX] Bootstrapping {self.historical_days}d 5m history for {SYMBOL}...")

        raw_bars = []
        try:
            raw_bars = self.ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting="5 mins",
                whatToShow="MIDPOINT",
                useRTH=False,
                formatDate=1,
                keepUpToDate=False,
                timeout=120,
            )
        except Exception as exc:
            log.warning("reqHistoricalData failed for %s: %s — trying CSV fallback", SYMBOL, exc)
            print(f"[WARN] IBKR-IDX: historical data failed ({exc}) — trying CSV fallback")

        if not raw_bars:
            log.warning("No 5m bars from IBKR for %s — trying CSV fallback", SYMBOL)
            if self._load_csv_fallback():
                return
            log.error("No bars available for %s (IBKR + CSV both failed)", SYMBOL)
            print(f"[ERROR] IBKR-IDX: no bars available for {SYMBOL}")
            self.ltf_bars = pd.DataFrame()
            self.htf_bars = pd.DataFrame()
            return

        df = util.df(raw_bars)[["date", "open", "high", "low", "close"]].copy()
        df.rename(columns={"date": "timestamp"}, inplace=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)

        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)

        df = _apply_half_spread(df, HALF_SPREAD)
        self.ltf_bars = df
        self._rebuild_htf()

        log.info("Loaded %d 5m bars for %s (%s -> %s)",
                 len(df), SYMBOL, df.index[0], df.index[-1])
        print(f"[IBKR-IDX] Loaded {len(df)} 5m bars for {SYMBOL} "
              f"({df.index[0]} -> {df.index[-1]})")

    def _load_csv_fallback(self) -> bool:
        """
        Load 5m bars from local CSV file.
        Looks for: data/bars_idx/usatechidxusd_5m_bars.csv
        Returns True if bars were loaded successfully.
        """
        base = pathlib.Path(__file__).parent.parent.parent
        csv_path = base / "data" / "bars_idx" / "usatechidxusd_5m_bars.csv"

        if not csv_path.exists():
            log.warning("CSV fallback not found: %s", csv_path)
            return False

        try:
            df = pd.read_csv(csv_path)
            df.columns = [c.strip().lower() for c in df.columns]

            # Find timestamp column
            ts_col = next(
                (c for c in df.columns if c in ("datetime", "timestamp") or "time" in c or "date" in c),
                df.columns[0]
            )
            df[ts_col] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
            df = df.dropna(subset=[ts_col]).sort_values(ts_col).set_index(ts_col)
            if df.index.tz is not None:
                df.index = df.index.tz_convert("UTC").tz_localize(None)

            # Keep last 60 days (12 × 24 × 60/5 = 17,280 bars max)
            if len(df) > 20_000:
                df = df.tail(20_000)

            # Normalise to bid/ask OHLC
            if "open_bid" in df.columns:
                df = df[["open_bid", "high_bid", "low_bid", "close_bid",
                          "open_ask", "high_ask", "low_ask", "close_ask"]]
            elif "open" in df.columns:
                df = _apply_half_spread(df[["open", "high", "low", "close"]].copy(), HALF_SPREAD)
            else:
                log.warning("CSV fallback: unrecognised column format")
                return False

            self.ltf_bars = df
            self._rebuild_htf()
            log.info("CSV fallback loaded %d 5m bars for %s (%s -> %s)",
                     len(df), SYMBOL, df.index[0], df.index[-1])
            print(f"[IBKR-IDX] CSV fallback: {len(df)} 5m bars "
                  f"({df.index[0].date()} → {df.index[-1].date()})")
            return True
        except Exception as exc:
            log.error("CSV fallback failed: %s", exc)
            return False

    # ── HTF aggregation ────────────────────────────────────────────────────────

    def _rebuild_htf(self):
        """Aggregate 5m LTF bars into 4h HTF bars."""
        df = self.ltf_bars
        if df is None or df.empty:
            self.htf_bars = pd.DataFrame()
            return

        agg_cols = {c: "first" if "open" in c else ("max" if "high" in c else ("min" if "low" in c else "last"))
                    for c in df.columns if any(x in c for x in ("open", "high", "low", "close"))}
        agg_cols = {k: v for k, v in agg_cols.items() if k in df.columns}

        # Proper aggregation: open=first, high=max, low=min, close=last
        agg = {}
        for col in df.columns:
            if "open" in col:
                agg[col] = "first"
            elif "high" in col:
                agg[col] = "max"
            elif "low" in col:
                agg[col] = "min"
            elif "close" in col:
                agg[col] = "last"

        self.htf_bars = df.resample("4h").agg(agg).dropna(how="all")

    # ── Live tick handling ─────────────────────────────────────────────────────

    def _on_pending_tickers(self, tickers):
        """Heartbeat callback — keep _last_tick_time alive even when price is flat."""
        now = datetime.utcnow()
        for ticker in tickers:
            if ticker is self._ticker:
                bid = getattr(ticker, "bid", None)
                ask = getattr(ticker, "ask", None)
                if bid and ask and bid > 0 and ask > 0:
                    self._last_tick_time = now

    def _on_ticker_update(self, ticker):
        """Callback from ib_insync when a new quote arrives."""
        bid = getattr(ticker, "bid", None)
        ask = getattr(ticker, "ask", None)

        if bid and ask and bid > 0 and ask > 0:
            self._last_tick_time = datetime.now(tz=timezone.utc).replace(tzinfo=None)

        if not bid or not ask or bid <= 0 or ask <= 0:
            return

        ts = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        self._tick_buf.append((ts, bid, ask))

        # Keep buffer bounded
        if len(self._tick_buf) > 5000:
            self._tick_buf = self._tick_buf[-2500:]

    # ── Bar sealing ───────────────────────────────────────────────────────────

    def update_bars(self):
        """
        Inspect tick buffer; seal any completed 5-minute bars, rebuild HTF,
        and fire on_bar_close callback for each sealed bar.

        Call from the main loop every 30s.
        """
        ticks = self._tick_buf
        log.debug("update_bars: %d ticks in buffer", len(ticks))
        if not ticks:
            return

        now = datetime.utcnow()
        # Current open 5m bar
        current_5m = _floor_bar(now, BAR_MINUTES)
        # Last completed 5m bar
        last_completed = current_5m - timedelta(minutes=BAR_MINUTES)

        if self.ltf_bars is None or self.ltf_bars.empty:
            return

        last_sealed = self.ltf_bars.index[-1].to_pydatetime().replace(tzinfo=None)
        log.debug("update_bars: now=%s last_sealed=%s last_completed=%s",
                  now, last_sealed, last_completed)

        if last_completed <= last_sealed:
            return  # Already up-to-date

        # ── Seal all completed bars since last_sealed ──────────────────────────
        sealed_any = False
        bar_start = last_sealed + timedelta(minutes=BAR_MINUTES)

        while bar_start <= last_completed:
            bar_end = bar_start + timedelta(minutes=BAR_MINUTES)

            # Skip if already in DataFrame (re-entry guard)
            if pd.Timestamp(bar_start) in self.ltf_bars.index:
                bar_start = bar_end
                continue

            bar_ticks = [(ts, b, a) for ts, b, a in ticks if bar_start <= ts < bar_end]

            if bar_ticks:
                bids = [b for _, b, _ in bar_ticks]
                asks = [a for _, _, a in bar_ticks]
                new_row = pd.DataFrame(
                    [{
                        "open_bid":  bids[0],  "high_bid":  max(bids),
                        "low_bid":   min(bids), "close_bid": bids[-1],
                        "open_ask":  asks[0],  "high_ask":  max(asks),
                        "low_ask":   min(asks), "close_ask": asks[-1],
                    }],
                    index=pd.DatetimeIndex([bar_start]),
                )
                self.ltf_bars = pd.concat([self.ltf_bars, new_row])
                self.ltf_bars.sort_index(inplace=True)
                log.info("Sealed 5m bar %s for %s", bar_start, SYMBOL)
                print(f"[BAR] Sealed 5m bar {bar_start} ({SYMBOL})")
                sealed_any = True
            else:
                # No ticks — forward-fill to advance last_sealed past the gap
                last_row = self.ltf_bars.iloc[-1]
                ffill_row = pd.DataFrame(
                    [{
                        "open_bid":  last_row["close_bid"], "high_bid":  last_row["close_bid"],
                        "low_bid":   last_row["close_bid"], "close_bid": last_row["close_bid"],
                        "open_ask":  last_row["close_ask"], "high_ask":  last_row["close_ask"],
                        "low_ask":   last_row["close_ask"], "close_ask": last_row["close_ask"],
                    }],
                    index=pd.DatetimeIndex([bar_start]),
                )
                self.ltf_bars = pd.concat([self.ltf_bars, ffill_row])
                self.ltf_bars.sort_index(inplace=True)
                log.info("update_bars: no ticks for %s–%s — forward-filled", bar_start, bar_end)
                sealed_any = True

            bar_start = bar_end

        if sealed_any:
            self._rebuild_htf()
            # Discard ticks older than the current open bar
            self._tick_buf = [(ts, b, a) for ts, b, a in ticks if ts >= current_5m]

            # ── Persistent state guard: skip callback if already processed ─────
            sealed_bar_ts = self.ltf_bars.index[-1]
            sealed_bar_ts_iso = str(sealed_bar_ts.isoformat())

            if self.store is not None:
                try:
                    db_state = self.store.load_strategy_state(SYMBOL)
                    if db_state and db_state.last_processed_bar_ts:
                        if sealed_bar_ts_iso <= db_state.last_processed_bar_ts:
                            log.debug(
                                "update_bars: bar %s already processed — skipping callback",
                                sealed_bar_ts_iso,
                            )
                            return
                except Exception as _e:
                    log.warning("update_bars: DB guard check failed: %s", _e)

            if self.on_bar_close:
                self.on_bar_close()

            # Persist last processed bar
            if self.store is not None:
                try:
                    from ..core.state_store import StrategyState
                    existing = self.store.load_strategy_state(SYMBOL)
                    if existing is None:
                        existing = StrategyState(symbol=SYMBOL)
                    existing.last_processed_bar_ts = sealed_bar_ts_iso
                    self.store.save_strategy_state(existing)
                except Exception as _e:
                    log.warning("update_bars: DB state save failed: %s", _e)

    # ── Convenience accessors ──────────────────────────────────────────────────

    def bar_count(self) -> int:
        """Return number of sealed 5m LTF bars."""
        if self.ltf_bars is None:
            return 0
        return len(self.ltf_bars)

    def last_tick_age_seconds(self) -> float:
        """Seconds since last tick received. Returns 9999 if never received."""
        if self._last_tick_time is None:
            return 9999.0
        return (datetime.utcnow() - self._last_tick_time).total_seconds()

    def probe_feed(self) -> bool:
        """One-shot snapshot request to refresh _last_tick_time (heartbeat)."""
        if not self.connected:
            return False
        try:
            contract = _make_contract()
            ticker = self.ib.reqMktData(contract, "", True, False)
            self.ib.sleep(1.5)
            bid = getattr(ticker, "bid", None)
            ask = getattr(ticker, "ask", None)
            self.ib.cancelMktData(contract)
            if bid and ask and bid > 0 and ask > 0:
                now = datetime.utcnow()
                self._last_tick_time = now
                self._tick_buf.append((now, bid, ask))
                log.debug("probe_feed: snapshot bid=%.2f ask=%.2f", bid, ask)
                return True
            return False
        except Exception as exc:
            log.warning("probe_feed failed: %s", exc)
            return False

    def get_current_quote(self):
        """Return (bid, ask) from the most recent tick. Returns (None, None) if unavailable."""
        if not self._tick_buf:
            if self._ticker is not None:
                bid = getattr(self._ticker, "bid", None)
                ask = getattr(self._ticker, "ask", None)
                if bid and ask and bid > 0 and ask > 0:
                    return bid, ask
            return None, None
        _, bid, ask = self._tick_buf[-1]
        return bid, ask
