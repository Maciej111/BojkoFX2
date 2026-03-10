"""
BojkoFx Trading Dashboard — Flask API (IBKR edition)
=====================================================
Data sources (all relative to BASE_DIR):
  logs/paper_trading_ibkr.csv  — all trade events (primary log)
  logs/paper_trading.csv       — legacy compact log (fallback)
  logs/bojkofx.log             — bot stdout (liveness check)
  data/bars_validated/         — OHLC bars for candle charts

Symbols: EURUSD, USDJPY, USDCHF, AUDJPY, CADJPY
"""
import os
import sys
import json
import math
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stderr, level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("dashboard")

# ── Config ────────────────────────────────────────────────────────────────────
DASHBOARD_API_KEY = os.environ.get("DASHBOARD_API_KEY", "changeme")
DASHBOARD_PORT    = int(os.environ.get("DASHBOARD_PORT", 8080))
BASE_DIR          = Path(os.environ.get("BASE_DIR", "/home/macie/bojkofx/app"))
INITIAL_EQUITY    = float(os.environ.get("INITIAL_EQUITY", 10000.0))

IBKR_CSV    = BASE_DIR / "logs" / "paper_trading_ibkr.csv"
LEGACY_CSV  = BASE_DIR / "logs" / "paper_trading.csv"
# bojkofx.log written by systemd to /home/macie/bojkofx/logs/ (one level up from app/)
BOT_LOG     = BASE_DIR.parent / "logs" / "bojkofx.log"
BARS_DIR    = BASE_DIR / "data" / "bars_validated"

SYMBOLS = ["EURUSD", "USDJPY", "USDCHF", "AUDJPY", "CADJPY"]

# Search order for H1 bars per symbol (first existing file wins)
def _bars_search_paths(sym: str):
    s = sym.lower()
    return [
        BASE_DIR / "data" / "live_bars" / f"{sym}.csv",          # live bars written by bot (priority)
        BASE_DIR / "data" / "outputs" / "live_bars" / f"{sym}.csv",
        BARS_DIR / f"{s}_1h_validated.csv",                       # historical fallback
        BARS_DIR / f"{s}_4h_validated.csv",
        BASE_DIR / "data" / "bars" / f"{s}_1h.csv",
    ]

# ── App ───────────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


# ── Auth ──────────────────────────────────────────────────────────────────────
@app.before_request
def check_auth():
    if request.endpoint == "health":
        return
    if request.headers.get("X-API-Key", "") != DASHBOARD_API_KEY:
        return jsonify({"error": "unauthorized"}), 401


# ── Helpers ───────────────────────────────────────────────────────────────────
def _nan(v):
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return None
    except TypeError:
        pass
    return v


def _f(v):
    try:
        r = float(v)
        return _nan(r)
    except (TypeError, ValueError):
        return None


def _i(v):
    try:
        f = float(v)
        return 0 if math.isnan(f) else int(f)
    except (TypeError, ValueError):
        return 0


def _s(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v).strip()
    return None if s in ("", "nan", "NaT", "None") else s


def _load_ibkr_csv() -> pd.DataFrame:
    """Load paper_trading_ibkr.csv, parse timestamps, return DataFrame."""
    for path in [IBKR_CSV, LEGACY_CSV]:
        if path.exists() and path.stat().st_size > 10:
            df = pd.read_csv(path)
            if df.empty:
                continue
            # normalise column names
            df.columns = [c.strip().lower() for c in df.columns]
            # parse timestamp columns
            for col in ["timestamp", "fill_time", "exit_time", "order_create_time"]:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
            return df
    return pd.DataFrame()


def _bot_alive() -> bool:
    """
    Check bot liveness:
    1. systemctl is-active bojkofx  (most reliable)
    2. bojkofx.log mtime < 24h     (fallback, covers weekends/quiet markets)
    """
    import subprocess
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "bojkofx"],
            capture_output=True, text=True, timeout=3
        )
        if r.stdout.strip() in ("active", "activating"):
            return True
    except Exception:
        pass

    # Fallback: log file mtime (24h threshold covers weekends)
    if not BOT_LOG.exists():
        return False
    mtime = datetime.fromtimestamp(BOT_LOG.stat().st_mtime, tz=timezone.utc)
    return (datetime.now(timezone.utc) - mtime) < timedelta(hours=24)


def _last_bot_ts() -> str:
    if not BOT_LOG.exists():
        return ""
    mtime = datetime.fromtimestamp(BOT_LOG.stat().st_mtime, tz=timezone.utc)
    return mtime.isoformat()


# ── Status builder ────────────────────────────────────────────────────────────

def _build_status(df: pd.DataFrame) -> dict:
    """Build /api/status payload from IBKR event log."""
    alive = _bot_alive()
    last_update = _last_bot_ts()

    # Equity from closed trades ------------------------------------------------
    closed = df[df.get("event_type", pd.Series(dtype=str)).str.upper().isin(
        ["TRADE_CLOSED", "FILL", "CLOSED_TP", "CLOSED_SL"]
    )] if not df.empty else pd.DataFrame()

    # Prefer 'realized_r' / 'r_multiple_realized' column
    r_col = None
    for c in ["realized_r", "r_multiple_realized", "r_multiple"]:
        if not df.empty and c in df.columns:
            r_col = c; break

    # Per-symbol state from last FILL (open) and TRADE_CLOSED (flat) ----------
    sym_state = {}
    for sym in SYMBOLS:
        sym_state[sym] = _build_sym_state(df, sym, r_col)

    open_count    = sum(1 for s in sym_state.values() if s["pos"] != "NONE")
    pending_count = sum(1 for s in sym_state.values() if s["pending"])

    # Closed trades count
    closed_all = df[
        df.get("event_type", pd.Series(dtype=str)).str.upper() == "TRADE_CLOSED"
    ] if not df.empty else pd.DataFrame()
    trades_total = len(closed_all)

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    trades_today = 0
    if not closed_all.empty and "exit_time" in closed_all.columns:
        trades_today = int((closed_all["exit_time"] >= today_start).sum())

    # Equity calc: INITIAL + sum of PnL from all closed trades
    equity = INITIAL_EQUITY
    pnl_col = None
    for c in ["pnl", "realized_pnl"]:
        if not df.empty and c in df.columns:
            pnl_col = c; break
    if pnl_col and not closed_all.empty:
        equity = INITIAL_EQUITY + float(closed_all[pnl_col].fillna(0).sum())

    pnl_total = equity - INITIAL_EQUITY
    pnl_pct   = pnl_total / INITIAL_EQUITY * 100

    # Last closed trade
    last_R = last_pnl = last_reason = last_exit_ts = None
    if not closed_all.empty:
        row = closed_all.iloc[-1]
        last_R      = _f(row.get(r_col)) if r_col else None
        last_pnl    = _f(row.get(pnl_col)) if pnl_col else None
        last_reason = _s(row.get("exit_reason"))
        et = row.get("exit_time")
        last_exit_ts = et.isoformat() if pd.notna(et) and hasattr(et, "isoformat") else _s(et)

    import subprocess
    try:
        svc = subprocess.run(["systemctl","is-active","bojkofx"],
                             capture_output=True,text=True,timeout=3).stdout.strip()
    except Exception:
        svc = "unknown"

    return {
        "bot_alive":   alive,
        "service_state": svc,
        "last_update": last_update,
        "bar_ts":      last_update,
        "portfolio": {
            "equity":                  round(equity, 2),
            "pnl_total":               round(pnl_total, 2),
            "pnl_pct":                 round(pnl_pct, 4),
            "open_positions":          open_count,
            "pending_orders":          pending_count,
            "trades_closed_total":     trades_total,
            "trades_closed_today":     trades_today,
            "last_trade_R":            last_R,
            "last_trade_pnl":          last_pnl,
            "last_trade_exit_reason":  last_reason,
            "last_trade_exit_ts":      last_exit_ts,
            "kill_switch":             False,
        },
        "symbols": sym_state,
    }


def _build_sym_state(df: pd.DataFrame, sym: str, r_col) -> dict:
    """Derive current position state for one symbol from event log."""
    blank = {
        "equity": round(INITIAL_EQUITY / len(SYMBOLS), 2),
        "pos": "NONE",
        "pos_entry": None, "pos_sl": None, "pos_tp": None, "pos_entry_ts": None,
        "pending": False, "last_bar_ts": None,
        "trades_closed_total": 0,
        "last_trade_R": None, "last_trade_pnl": None,
        "last_trade_exit_reason": None,
    }
    if df.empty:
        return blank

    sym_col = "symbol" if "symbol" in df.columns else None
    if sym_col is None:
        return blank

    sdf = df[df[sym_col].str.upper() == sym.upper()].copy()
    if sdf.empty:
        return blank

    evt_col = "event_type" if "event_type" in sdf.columns else None

    # Closed trades for this symbol
    closed = sdf[sdf[evt_col].str.upper() == "TRADE_CLOSED"] if evt_col else pd.DataFrame()
    trades_total = len(closed)
    last_R = last_pnl = last_reason = None

    pnl_col = None
    for c in ["pnl", "realized_pnl"]:
        if c in sdf.columns:
            pnl_col = c; break

    if not closed.empty:
        last_row = closed.iloc[-1]
        last_R      = _f(last_row.get(r_col)) if r_col else None
        last_pnl    = _f(last_row.get(pnl_col)) if pnl_col else None
        last_reason = _s(last_row.get("exit_reason"))

    # Per-symbol equity = initial_share + sum pnl
    share = INITIAL_EQUITY / len(SYMBOLS)
    sym_pnl = float(closed[pnl_col].fillna(0).sum()) if pnl_col and not closed.empty else 0.0
    sym_equity = round(share + sym_pnl, 2)

    # Current position: last FILL without a matching TRADE_CLOSED after it
    pos = "NONE"; pos_entry = pos_sl = pos_tp = pos_entry_ts = None
    pending = False

    if evt_col:
        fills   = sdf[sdf[evt_col].str.upper() == "FILL"]
        intents = sdf[sdf[evt_col].str.upper() == "INTENT"]

        if not fills.empty:
            last_fill = fills.iloc[-1]
            fill_ts   = last_fill.get("fill_time") or last_fill.get("timestamp")
            # Check if there's a TRADE_CLOSED AFTER this fill
            if not closed.empty:
                close_col = "exit_time" if "exit_time" in closed.columns else "timestamp"
                if pd.notna(fill_ts):
                    still_open = (closed[close_col] >= fill_ts).sum() == 0
                else:
                    still_open = True
            else:
                still_open = True

            if still_open:
                side = _s(last_fill.get("side", ""))
                pos  = "LONG" if side and "BUY" in side.upper() else "SHORT"
                pos_entry = _f(last_fill.get("fill_price") or last_fill.get("entry_price_intent"))
                pos_sl    = _f(last_fill.get("sl_price"))
                pos_tp    = _f(last_fill.get("tp_price"))
                ft = last_fill.get("fill_time") or last_fill.get("timestamp")
                pos_entry_ts = ft.isoformat() if pd.notna(ft) and hasattr(ft, "isoformat") else _s(ft)

        # Pending: INTENT with no FILL yet and no ORDER_CANCELLED/RISK_BLOCK after it
        if pos == "NONE" and not intents.empty:
            last_intent = intents.iloc[-1]
            intent_ts   = last_intent.get("timestamp")
            intent_sig  = _s(last_intent.get("signal_id", ""))

            # Check if there's a matching ORDER_CANCELLED or RISK_BLOCK for this signal
            blocking_events = sdf[sdf[evt_col].str.upper().isin(
                ["ORDER_CANCELLED", "RISK_BLOCK", "CANCELLED"]
            )] if evt_col else pd.DataFrame()
            is_cancelled = False
            if not blocking_events.empty and intent_sig:
                sig_col = "signal_id" if "signal_id" in blocking_events.columns else None
                if sig_col:
                    is_cancelled = (blocking_events[sig_col] == intent_sig).any()
                if not is_cancelled and pd.notna(intent_ts):
                    # Fallback: any blocking event after the intent timestamp
                    is_cancelled = (blocking_events["timestamp"] > intent_ts).any()

            # Only "pending" if intent is recent (< 2h) AND not cancelled/blocked
            # Use 2h = typical TTL expiry window to avoid stale pending flags
            if (not is_cancelled and pd.notna(intent_ts)
                    and (datetime.now(timezone.utc) - intent_ts) < timedelta(hours=2)):
                pending = True
                pos_entry = _f(last_intent.get("entry_price_intent"))
                pos_sl    = _f(last_intent.get("sl_price"))
                pos_tp    = _f(last_intent.get("tp_price"))

    return {
        "equity":                 round(sym_equity, 2),
        "pos":                    pos,
        "pos_entry":              pos_entry,
        "pos_sl":                 pos_sl,
        "pos_tp":                 pos_tp,
        "pos_entry_ts":           pos_entry_ts,
        "pending":                pending,
        "last_bar_ts":            _last_bot_ts(),
        "trades_closed_total":    trades_total,
        "last_trade_R":           last_R,
        "last_trade_pnl":         last_pnl,
        "last_trade_exit_reason": last_reason,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"ok": True, "ts": datetime.now(timezone.utc).isoformat()})


@app.route("/api/status")
def status():
    try:
        df = _load_ibkr_csv()
        return jsonify(_build_status(df))
    except Exception as e:
        log.error("status error: %s", e, exc_info=True)
        return jsonify({"error": "parse error", "detail": str(e)}), 500


@app.route("/api/equity_history")
def equity_history():
    """Return equity curve built from cumulative PnL of closed trades."""
    try:
        df = _load_ibkr_csv()
        if df.empty:
            return jsonify([])

        evt_col = "event_type" if "event_type" in df.columns else None
        if evt_col is None:
            return jsonify([])

        closed = df[df[evt_col].str.upper() == "TRADE_CLOSED"].copy()
        if closed.empty:
            return jsonify([])

        pnl_col = next((c for c in ["pnl", "realized_pnl"] if c in closed.columns), None)
        ts_col  = next((c for c in ["exit_time", "timestamp"] if c in closed.columns), None)
        if not ts_col:
            return jsonify([])

        closed = closed.dropna(subset=[ts_col]).sort_values(ts_col)
        eq = INITIAL_EQUITY
        result = [{"ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                   "equity": round(eq, 2)}]  # starting point
        for _, row in closed.iterrows():
            pnl = float(row[pnl_col]) if pnl_col and pd.notna(row.get(pnl_col)) else 0.0
            eq += pnl
            ts  = row[ts_col]
            result.append({
                "ts":     ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "equity": round(eq, 2),
            })
        return jsonify(result[-500:])  # last 500 points
    except Exception as e:
        log.error("equity_history error: %s", e, exc_info=True)
        return jsonify({"error": "parse error", "detail": str(e)}), 500


@app.route("/api/candles/<symbol>")
def candles(symbol):
    sym = symbol.upper()
    if sym not in SYMBOLS:
        return jsonify({"error": f"unknown symbol: {sym}"}), 400

    # Find first existing bars file
    path = None
    for p in _bars_search_paths(sym):
        if p.exists():
            path = p
            break

    if path is None:
        log.info("candles[%s]: no bars file found — returning empty", sym)
        return jsonify([])

    # Empty file guard
    if path.stat().st_size == 0:
        log.info("candles[%s]: bars file is empty (%s)", sym, path.name)
        return jsonify([])

    try:
        # Detect if file has a header row or not
        with open(path, "r") as _f_peek:
            first_line = _f_peek.readline().strip()
        first_cell = first_line.split(",")[0].strip().strip('"')
        has_header = not (first_cell[:4].isdigit())  # header starts with "datetime", not "2026-..."

        df = pd.read_csv(path, header=0 if has_header else None)
        if df.empty:
            return jsonify([])
        df.columns = [c.strip().lower() if isinstance(c, str) else f"col{c}" for c in df.columns]

        # If no header, assign standard column names
        if not has_header:
            col_count = len(df.columns)
            std_names = ["datetime", "open", "high", "low", "close", "volume"]
            df.columns = std_names[:col_count] + [f"col{i}" for i in range(col_count - len(std_names))]

        # Find timestamp column
        ts_col = next((c for c in df.columns if c in ("datetime","time","date","ts","timestamp") or "time" in c or "date" in c), df.columns[0])
        df[ts_col] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
        df = df.dropna(subset=[ts_col]).sort_values(ts_col)

        # Remove weekend bars (Sat=5, Sun=6) — show only trading hours
        df = df[df[ts_col].dt.dayofweek < 5]

        df = df.tail(72)

        # Normalise OHLC — bars_validated uses bid/ask columns; derive midpoint
        def _mid(col_a, col_b):
            if col_a in df.columns and col_b in df.columns:
                return ((df[col_a] + df[col_b]) / 2)
            return df.get(col_a, pd.Series([None]*len(df)))

        if "open" not in df.columns and "open_bid" in df.columns:
            df["open"]  = _mid("open_bid",  "open_ask")
            df["high"]  = _mid("high_bid",  "high_ask")
            df["low"]   = _mid("low_bid",   "low_ask")
            df["close"] = _mid("close_bid", "close_ask")

        # Remove forward-filled (flat) bars: open==high==low==close
        if "open" in df.columns:
            flat = (df["open"] == df["high"]) & (df["high"] == df["low"]) & (df["low"] == df["close"])
            n_flat = flat.sum()
            if n_flat > 0:
                log.info("candles[%s]: removing %d flat/forward-filled bars", sym, n_flat)
            df = df[~flat]

        result = [{
            "ts":     row[ts_col].isoformat(),
            "open":   _f(row.get("open")),
            "high":   _f(row.get("high")),
            "low":    _f(row.get("low")),
            "close":  _f(row.get("close")),
            "volume": _f(row.get("volume", 0)),
        } for _, row in df.iterrows()]
        return jsonify(result)
    except Exception as e:
        log.error("candles[%s] error: %s", sym, e, exc_info=True)
        return jsonify({"error": "parse error", "detail": str(e)}), 500


@app.route("/api/trades/<symbol>")
def trades(symbol):
    sym = symbol.upper()
    if sym not in SYMBOLS:
        return jsonify({"error": f"unknown symbol: {sym}"}), 400

    try:
        df = _load_ibkr_csv()
        if df.empty:
            return jsonify([])

        evt_col = "event_type" if "event_type" in df.columns else None
        if evt_col is None:
            return jsonify([])

        sym_col = "symbol" if "symbol" in df.columns else None
        if sym_col is None:
            return jsonify([])

        closed = df[
            (df[sym_col].str.upper() == sym) &
            (df[evt_col].str.upper() == "TRADE_CLOSED")
        ].copy()

        if closed.empty:
            return jsonify([])

        if "exit_time" in closed.columns:
            closed = closed.sort_values("exit_time", ascending=False, na_position="last")

        r_col   = next((c for c in ["realized_r", "r_multiple_realized"] if c in closed.columns), None)
        pnl_col = next((c for c in ["pnl", "realized_pnl"] if c in closed.columns), None)

        result = []
        for _, row in closed.iterrows():
            et = row.get("exit_time")
            ft = row.get("fill_time") or row.get("order_create_time")
            result.append({
                "symbol":      sym,
                "side":        _s(row.get("side")),
                "entry_price": _f(row.get("fill_price") or row.get("entry_price_intent")),
                "sl_price":    _f(row.get("sl_price")),
                "tp_price":    _f(row.get("tp_price")),
                "entry_ts":    ft.isoformat()  if pd.notna(ft) and hasattr(ft, "isoformat") else _s(ft),
                "exit_ts":     et.isoformat()  if pd.notna(et) and hasattr(et, "isoformat") else _s(et),
                "exit_price":  _f(row.get("exit_price")),
                "exit_reason": _s(row.get("exit_reason")),
                "pnl":         _f(row.get(pnl_col)) if pnl_col else None,
                "commission":  _f(row.get("commissions")),
                "R":           _f(row.get(r_col)) if r_col else None,
                "bars_held":   _i(row.get("ttl_bars")),
                "slippage_entry_pips": _f(row.get("slippage_entry_pips")),
                "slippage_exit_pips":  _f(row.get("slippage_exit_pips")),
                "latency_ms":  _f(row.get("latency_ms")),
                "status":      _s(row.get("status_timeline")),
            })
        return jsonify(result)
    except Exception as e:
        log.error("trades[%s] error: %s", sym, e, exc_info=True)
        return jsonify({"error": "parse error", "detail": str(e)}), 500


@app.route("/api/events")
def events():
    """Return last 200 raw events from IBKR log (for debugging)."""
    try:
        df = _load_ibkr_csv()
        if df.empty:
            return jsonify([])
        df = df.tail(200)
        # convert timestamps to strings
        for col in df.select_dtypes(include=["datetime64[ns, UTC]", "datetimetz"]).columns:
            df[col] = df[col].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        return jsonify(df.fillna("").to_dict(orient="records"))
    except Exception as e:
        log.error("events error: %s", e, exc_info=True)
        return jsonify({"error": "parse error", "detail": str(e)}), 500


@app.route("/api/log_tail")
def log_tail():
    """Return last 50 lines of bojkofx.log."""
    if not BOT_LOG.exists():
        # Bot not yet started — return empty gracefully
        return jsonify({"lines": [], "note": "bot log not found"})
    try:
        with open(BOT_LOG, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return jsonify({"lines": [l.rstrip() for l in lines[-50:]]})
    except Exception as e:
        return jsonify({"lines": [], "error": str(e)})


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("BojkoFx Dashboard (IBKR) starting on 0.0.0.0:%d", DASHBOARD_PORT)
    log.info("Reading trades from: %s", IBKR_CSV)
    log.info("Bars from: %s", BARS_DIR)
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False)

