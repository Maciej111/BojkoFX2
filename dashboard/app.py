"""
BojkoFx/BojkoIDX Unified Trading Dashboard — Flask API
=======================================================
Serves both FX (Forex) and US100 (NAS100 CFD) bots from a single API.

Endpoints:
  /api/health
  /api/<project>/status           project = fx | us100
  /api/<project>/equity_history
  /api/<project>/candles/<symbol>
  /api/<project>/trades/<symbol>
  /api/<project>/events
  /api/<project>/log_tail

Environment variables:
  DASHBOARD_API_KEY         shared auth key       (default: changeme)
  DASHBOARD_PORT            listen port           (default: 8080)
  FX_BASE_DIR               FX app root           (default: /home/macie/bojkofx/app)
  FX_INITIAL_EQUITY         FX starting equity    (default: 10000)
  US100_BASE_DIR            US100 app root        (default: /home/macie/bojkoidx/app)
  US100_INITIAL_EQUITY      US100 starting equity (default: 10000)
"""
import math
import os
import sys
import json
import logging
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stderr, level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("dashboard")

# ── Config ─────────────────────────────────────────────────────────────────────
DASHBOARD_API_KEY = os.environ.get("DASHBOARD_API_KEY", "changeme")
DASHBOARD_PORT    = int(os.environ.get("DASHBOARD_PORT", 8080))

# Per-project configuration
_PROJECTS = {
    "fx": {
        "base_dir":       Path(os.environ.get("FX_BASE_DIR",    "/home/macie/bojkofx/app")),
        "initial_equity": float(os.environ.get("FX_INITIAL_EQUITY", 10000)),
        "symbols":        ["EURUSD", "USDJPY", "USDCHF", "AUDJPY", "CADJPY"],
        "service":        os.environ.get("FX_SERVICE", "bojkofx"),
        "label":          "BojkoFX (Forex)",
    },
    "us100": {
        "base_dir":       Path(os.environ.get("US100_BASE_DIR", "/home/macie/bojkoidx/app")),
        "initial_equity": float(os.environ.get("US100_INITIAL_EQUITY", 10000)),
        "symbols":        ["NAS100USD"],
        "service":        os.environ.get("US100_SERVICE", "bojkoidx"),
        "label":          "BojkoIDX (NAS100)",
    },
}

# ── App ────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


# ── Auth ───────────────────────────────────────────────────────────────────────
@app.before_request
def check_auth():
    if request.endpoint == "health":
        return
    if request.headers.get("X-API-Key", "") != DASHBOARD_API_KEY:
        return jsonify({"error": "unauthorized"}), 401


# ── Project lookup ─────────────────────────────────────────────────────────────
def _get_project(project: str):
    p = _PROJECTS.get(project.lower())
    if p is None:
        return None, (jsonify({"error": f"unknown project: {project}. Use fx or us100."}), 404)
    return p, None


# ── Helpers ────────────────────────────────────────────────────────────────────
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


def _load_ibkr_csv(proj: dict) -> pd.DataFrame:
    base = proj["base_dir"]
    for path in [
        base / "logs" / "paper_trading_ibkr.csv",
        base / "logs" / "paper_trading.csv",
    ]:
        if path.exists() and path.stat().st_size > 10:
            df = pd.read_csv(path)
            if df.empty:
                continue
            df.columns = [c.strip().lower() for c in df.columns]
            for col in ["timestamp", "fill_time", "exit_time", "order_create_time"]:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
            return df
    return pd.DataFrame()


def _bot_log_path(proj: dict) -> Path:
    svc = f"{proj['service']}.log"
    # Try one level up (FX_BASE_DIR = .../app)
    p = proj["base_dir"].parent / "logs" / svc
    if p.exists():
        return p
    # Try two levels up (FX_BASE_DIR = .../app/FX)
    return proj["base_dir"].parents[1] / "logs" / svc


def _bot_alive(proj: dict) -> bool:
    svc = proj["service"]
    try:
        r = subprocess.run(
            ["systemctl", "is-active", svc],
            capture_output=True, text=True, timeout=3,
        )
        if r.stdout.strip() in ("active", "activating"):
            return True
    except Exception:
        pass
    bot_log = _bot_log_path(proj)
    if not bot_log.exists():
        return False
    mtime = datetime.fromtimestamp(bot_log.stat().st_mtime, tz=timezone.utc)
    return (datetime.now(timezone.utc) - mtime) < timedelta(hours=24)


def _last_bot_ts(proj: dict) -> str:
    bot_log = _bot_log_path(proj)
    if not bot_log.exists():
        return ""
    mtime = datetime.fromtimestamp(bot_log.stat().st_mtime, tz=timezone.utc)
    return mtime.isoformat()


def _bars_search_paths(proj: dict, sym: str):
    base = proj["base_dir"]
    s = sym.lower()
    return [
        base / "data" / "live_bars" / f"{sym}.csv",
        base / "data" / "outputs" / "live_bars" / f"{sym}.csv",
        base / "data" / "bars_validated" / f"{s}_5m_validated.csv",
        base / "data" / "bars_validated" / f"{s}_1h_validated.csv",
        base / "data" / "bars_validated" / f"{s}_4h_validated.csv",
        base / "data" / "bars" / f"{s}_5m.csv",
        base / "data" / "bars" / f"{s}_1h.csv",
    ]


# ── Status builder ─────────────────────────────────────────────────────────────
def _build_status(proj: dict, df: pd.DataFrame) -> dict:
    alive = _bot_alive(proj)
    last_update = _last_bot_ts(proj)
    symbols = proj["symbols"]
    initial_equity = proj["initial_equity"]

    evt_col = "event_type" if not df.empty and "event_type" in df.columns else None
    r_col = None
    for c in ["realized_r", "r_multiple_realized", "r_multiple"]:
        if not df.empty and c in df.columns:
            r_col = c
            break

    sym_state = {s: _build_sym_state(proj, df, s, r_col) for s in symbols}
    open_count    = sum(1 for s in sym_state.values() if s["pos"] != "NONE")
    pending_count = sum(1 for s in sym_state.values() if s["pending"])

    closed_all = df[
        df.get(evt_col, pd.Series(dtype=str)).str.upper() == "TRADE_CLOSED"
    ] if evt_col and not df.empty else pd.DataFrame()
    trades_total = len(closed_all)

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    trades_today = 0
    if not closed_all.empty and "exit_time" in closed_all.columns:
        trades_today = int((closed_all["exit_time"] >= today_start).sum())

    equity = initial_equity
    pnl_col = next((c for c in ["pnl", "realized_pnl"] if not df.empty and c in df.columns), None)
    if pnl_col and not closed_all.empty:
        equity = initial_equity + float(closed_all[pnl_col].fillna(0).sum())

    pnl_total = equity - initial_equity
    pnl_pct   = pnl_total / initial_equity * 100

    last_R = last_pnl = last_reason = last_exit_ts = None
    if not closed_all.empty:
        row = closed_all.iloc[-1]
        last_R      = _f(row.get(r_col)) if r_col else None
        last_pnl    = _f(row.get(pnl_col)) if pnl_col else None
        last_reason = _s(row.get("exit_reason"))
        et = row.get("exit_time")
        last_exit_ts = et.isoformat() if pd.notna(et) and hasattr(et, "isoformat") else _s(et)

    svc = proj["service"]
    try:
        svc_state = subprocess.run(
            ["systemctl", "is-active", svc],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip()
    except Exception:
        svc_state = "unknown"

    return {
        "project":       proj["label"],
        "bot_alive":     alive,
        "service_state": svc_state,
        "last_update":   last_update,
        "bar_ts":        last_update,
        "symbols_list":  symbols,
        "portfolio": {
            "equity":                 round(equity, 2),
            "pnl_total":              round(pnl_total, 2),
            "pnl_pct":                round(pnl_pct, 4),
            "open_positions":         open_count,
            "pending_orders":         pending_count,
            "trades_closed_total":    trades_total,
            "trades_closed_today":    trades_today,
            "last_trade_R":           last_R,
            "last_trade_pnl":         last_pnl,
            "last_trade_exit_reason": last_reason,
            "last_trade_exit_ts":     last_exit_ts,
            "kill_switch":            False,
        },
        "symbols": sym_state,
    }


def _build_sym_state(proj: dict, df: pd.DataFrame, sym: str, r_col) -> dict:
    symbols = proj["symbols"]
    initial_equity = proj["initial_equity"]
    blank = {
        "equity":   round(initial_equity / len(symbols), 2),
        "pos": "NONE",
        "pos_entry": None, "pos_sl": None, "pos_tp": None, "pos_entry_ts": None,
        "pending": False, "last_bar_ts": None,
        "trades_closed_total": 0,
        "last_trade_R":           None,
        "last_trade_pnl":         None,
        "last_trade_exit_reason": None,
    }
    if df.empty or "symbol" not in df.columns:
        return blank

    sdf = df[df["symbol"].str.upper() == sym.upper()].copy()
    if sdf.empty:
        return blank

    evt_col = "event_type" if "event_type" in sdf.columns else None
    closed = sdf[sdf[evt_col].str.upper() == "TRADE_CLOSED"] if evt_col else pd.DataFrame()
    trades_total = len(closed)
    last_R = last_pnl = last_reason = None

    pnl_col = next((c for c in ["pnl", "realized_pnl"] if c in sdf.columns), None)
    if not closed.empty:
        last_row = closed.iloc[-1]
        last_R      = _f(last_row.get(r_col)) if r_col else None
        last_pnl    = _f(last_row.get(pnl_col)) if pnl_col else None
        last_reason = _s(last_row.get("exit_reason"))

    share     = initial_equity / len(symbols)
    sym_pnl   = float(closed[pnl_col].fillna(0).sum()) if pnl_col and not closed.empty else 0.0
    sym_equity = round(share + sym_pnl, 2)

    pos = "NONE"; pos_entry = pos_sl = pos_tp = pos_entry_ts = None; pending = False

    if evt_col:
        fills   = sdf[sdf[evt_col].str.upper() == "FILL"]
        intents = sdf[sdf[evt_col].str.upper() == "INTENT"]

        if not fills.empty:
            last_fill = fills.iloc[-1]
            fill_ts   = last_fill.get("fill_time") or last_fill.get("timestamp")
            still_open = True
            if not closed.empty:
                # Use exit_time when available; fall back to row timestamp (exit_time is NaT
                # for cancelled/GTD-expired rows, but timestamp always has a real value).
                if "exit_time" in closed.columns and "timestamp" in closed.columns:
                    close_ts = closed["exit_time"].fillna(closed["timestamp"])
                elif "exit_time" in closed.columns:
                    close_ts = closed["exit_time"]
                else:
                    close_ts = closed["timestamp"]
                if pd.notna(fill_ts):
                    still_open = (close_ts >= fill_ts).sum() == 0
            if still_open:
                side = _s(last_fill.get("side", ""))
                # CSV can store "LONG"/"SHORT" or "BUY"/"SELL"
                pos  = "LONG" if side and ("BUY" in side.upper() or side.upper() == "LONG") else "SHORT"
                pos_entry = _f(last_fill.get("fill_price") or last_fill.get("entry_price_intent"))
                pos_sl    = _f(last_fill.get("sl_price")) or None
                pos_tp    = _f(last_fill.get("tp_price")) or None
                ft = last_fill.get("fill_time") or last_fill.get("timestamp")
                pos_entry_ts = ft.isoformat() if pd.notna(ft) and hasattr(ft, "isoformat") else _s(ft)

        if pos == "NONE" and not intents.empty:
            last_intent = intents.iloc[-1]
            intent_ts   = last_intent.get("timestamp")
            intent_sig  = _s(last_intent.get("signal_id", ""))
            blocking = sdf[sdf[evt_col].str.upper().isin(
                ["ORDER_CANCELLED", "RISK_BLOCK", "CANCELLED"]
            )] if evt_col else pd.DataFrame()
            is_cancelled = False
            if not blocking.empty and intent_sig and "signal_id" in blocking.columns:
                is_cancelled = (blocking["signal_id"] == intent_sig).any()
            if (not is_cancelled and pd.notna(intent_ts)
                    and (datetime.now(timezone.utc) - intent_ts) < timedelta(hours=2)):
                pending = True
                pos_entry = _f(last_intent.get("entry_price_intent"))
                pos_sl    = _f(last_intent.get("sl_price")) or None
                pos_tp    = _f(last_intent.get("tp_price")) or None

    return {
        "equity":                 sym_equity,
        "pos":                    pos,
        "pos_entry":              pos_entry,
        "pos_sl":                 pos_sl,
        "pos_tp":                 pos_tp,
        "pos_entry_ts":           pos_entry_ts,
        "pending":                pending,
        "last_bar_ts":            _last_bot_ts(proj),
        "trades_closed_total":    trades_total,
        "last_trade_R":           last_R,
        "last_trade_pnl":         last_pnl,
        "last_trade_exit_reason": last_reason,
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({
        "ok": True,
        "ts": datetime.now(timezone.utc).isoformat(),
        "projects": list(_PROJECTS.keys()),
    })


@app.route("/api/<project>/status")
def status(project):
    proj, err = _get_project(project)
    if err:
        return err
    try:
        df = _load_ibkr_csv(proj)
        return jsonify(_build_status(proj, df))
    except Exception as e:
        log.error("[%s] status error: %s", project, e, exc_info=True)
        return jsonify({"error": "parse error", "detail": str(e)}), 500


@app.route("/api/<project>/equity_history")
def equity_history(project):
    proj, err = _get_project(project)
    if err:
        return err
    try:
        df = _load_ibkr_csv(proj)
        if df.empty:
            return jsonify([])
        evt_col = "event_type" if "event_type" in df.columns else None
        if not evt_col:
            return jsonify([])
        closed = df[df[evt_col].str.upper() == "TRADE_CLOSED"].copy()
        if closed.empty:
            return jsonify([])
        pnl_col = next((c for c in ["pnl", "realized_pnl"] if c in closed.columns), None)
        ts_col  = next((c for c in ["exit_time", "timestamp"] if c in closed.columns), None)
        if not ts_col:
            return jsonify([])
        closed  = closed.dropna(subset=[ts_col]).sort_values(ts_col)
        eq      = proj["initial_equity"]
        result  = [{"ts": datetime.now(timezone.utc).isoformat(), "equity": round(eq, 2)}]
        for _, row in closed.iterrows():
            pnl = float(row[pnl_col]) if pnl_col and pd.notna(row.get(pnl_col)) else 0.0
            eq += pnl
            ts  = row[ts_col]
            result.append({
                "ts":     ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "equity": round(eq, 2),
            })
        return jsonify(result[-500:])
    except Exception as e:
        log.error("[%s] equity_history error: %s", project, e, exc_info=True)
        return jsonify({"error": "parse error", "detail": str(e)}), 500


@app.route("/api/<project>/candles/<symbol>")
def candles(project, symbol):
    proj, err = _get_project(project)
    if err:
        return err
    sym = symbol.upper()
    if sym not in proj["symbols"]:
        return jsonify({"error": f"unknown symbol: {sym}"}), 400
    path = None
    for p in _bars_search_paths(proj, sym):
        if p.exists():
            path = p
            break
    if path is None or path.stat().st_size == 0:
        return jsonify([])
    try:
        with open(path, "r") as _peek:
            first_line = _peek.readline().strip()
        first_cell = first_line.split(",")[0].strip().strip('"')
        has_header = not (first_cell[:4].isdigit())
        df = pd.read_csv(path, header=0 if has_header else None)
        if df.empty:
            return jsonify([])
        df.columns = [c.strip().lower() if isinstance(c, str) else f"col{c}" for c in df.columns]
        if not has_header:
            col_count = len(df.columns)
            std_names = ["datetime", "open", "high", "low", "close", "volume"]
            df.columns = std_names[:col_count] + [f"col{i}" for i in range(col_count - len(std_names))]
        ts_col = next(
            (c for c in df.columns if c in ("datetime","time","date","ts","timestamp")
             or "time" in c or "date" in c),
            df.columns[0]
        )
        df[ts_col] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
        df = df.dropna(subset=[ts_col]).sort_values(ts_col)
        df = df[df[ts_col].dt.dayofweek < 5]
        df = df.tail(72)
        if "open" not in df.columns and "open_bid" in df.columns:
            def _mid(a, b):
                return (df[a] + df[b]) / 2 if a in df.columns and b in df.columns else df.get(a, pd.Series([None]*len(df)))
            df["open"]  = _mid("open_bid",  "open_ask")
            df["high"]  = _mid("high_bid",  "high_ask")
            df["low"]   = _mid("low_bid",   "low_ask")
            df["close"] = _mid("close_bid", "close_ask")
        if "open" in df.columns:
            flat = (df["open"] == df["high"]) & (df["high"] == df["low"]) & (df["low"] == df["close"])
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
        log.error("[%s] candles[%s] error: %s", project, sym, e, exc_info=True)
        return jsonify({"error": "parse error", "detail": str(e)}), 500


@app.route("/api/<project>/trades/<symbol>")
def trades(project, symbol):
    proj, err = _get_project(project)
    if err:
        return err
    sym = symbol.upper()
    if sym not in proj["symbols"]:
        return jsonify({"error": f"unknown symbol: {sym}"}), 400
    try:
        df = _load_ibkr_csv(proj)
        if df.empty or "event_type" not in df.columns or "symbol" not in df.columns:
            return jsonify([])
        closed = df[
            (df["symbol"].str.upper() == sym) &
            (df["event_type"].str.upper() == "TRADE_CLOSED")
        ].copy()
        if closed.empty:
            return jsonify([])
        if "exit_time" in closed.columns:
            closed = closed.sort_values("exit_time", ascending=False, na_position="last")
        r_col   = next((c for c in ["realized_r", "r_multiple_realized"] if c in closed.columns), None)
        pnl_col = next((c for c in ["pnl", "realized_pnl"] if c in closed.columns), None)
        result = []
        for _, row in closed.iterrows():
            et = row.get("exit_time");  ft = row.get("fill_time") or row.get("order_create_time")
            result.append({
                "symbol":      sym,
                "side":        _s(row.get("side")),
                "entry_price": _f(row.get("fill_price") or row.get("entry_price_intent")),
                "sl_price":    _f(row.get("sl_price")),
                "tp_price":    _f(row.get("tp_price")),
                "entry_ts":    ft.isoformat() if pd.notna(ft) and hasattr(ft, "isoformat") else _s(ft),
                "exit_ts":     et.isoformat() if pd.notna(et) and hasattr(et, "isoformat") else _s(et),
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
        log.error("[%s] trades[%s] error: %s", project, sym, e, exc_info=True)
        return jsonify({"error": "parse error", "detail": str(e)}), 500


@app.route("/api/<project>/events")
def events(project):
    proj, err = _get_project(project)
    if err:
        return err
    try:
        df = _load_ibkr_csv(proj)
        if df.empty:
            return jsonify([])
        df = df.tail(200)
        for col in df.select_dtypes(include=["datetime64[ns, UTC]", "datetimetz"]).columns:
            df[col] = df[col].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        return jsonify(df.fillna("").to_dict(orient="records"))
    except Exception as e:
        log.error("[%s] events error: %s", project, e, exc_info=True)
        return jsonify({"error": "parse error", "detail": str(e)}), 500


@app.route("/api/<project>/log_tail")
def log_tail(project):
    proj, err = _get_project(project)
    if err:
        return err
    bot_log = _bot_log_path(proj)
    if not bot_log.exists():
        return jsonify({"lines": [], "note": "bot log not found"})
    try:
        with open(bot_log, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return jsonify({"lines": [ln.rstrip() for ln in lines[-50:]]})
    except Exception as e:
        return jsonify({"lines": [], "error": str(e)})


# ── Run ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("BojkoFx/IDX Unified Dashboard starting on 0.0.0.0:%d", DASHBOARD_PORT)
    log.info("FX base: %s", _PROJECTS["fx"]["base_dir"])
    log.info("US100 base: %s", _PROJECTS["us100"]["base_dir"])
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False)
