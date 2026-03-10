"""
IBKR Gateway Paper Trading Runner
══════════════════════════════════
Designed for IB Gateway (paper account) on port 4002.

Default safety posture:
  IBKR_READONLY=true   → all orders are blocked (DRY mode)
  ALLOW_LIVE_ORDERS=false
  KILL_SWITCH=false

To enable real paper orders (IBKR demo account only):
  set IBKR_READONLY=false
  set ALLOW_LIVE_ORDERS=true
  run with: --allow_live_orders

Dry-run (no orders):
  python -m src.runners.run_paper_ibkr_gateway --symbol EURUSD --minutes 5

Live paper orders (after you understand the risk):
  python -m src.runners.run_paper_ibkr_gateway --symbol EURUSD --allow_live_orders
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ── Add project root to sys.path so we can be run as __main__ ─────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from src.core.config import Config, IBKRConfig
from src.core.strategy import TrendFollowingStrategy
from src.core.state_store import SQLiteStateStore, OrderStatus, get_default_db_path
from src.data.ibkr_marketdata import IBKRMarketData
from src.execution.ibkr_exec import IBKRExecutionEngine
from src.reporting.logger import TradingLogger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Enable DEBUG for market data module to diagnose tick/bar issues
logging.getLogger("src.data.ibkr_marketdata").setLevel(logging.DEBUG)
log = logging.getLogger("gateway_runner")

# ── Minimum bars required before strategy produces signals ────────────────────
MIN_BARS = 200
# ── Main loop poll interval (seconds) ────────────────────────────────────────
POLL_INTERVAL_S = 30


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _current_spread(marketdata: IBKRMarketData, symbol: str) -> float:
    """Return spread (ask_close - bid_close) from the latest sealed bar."""
    h1 = marketdata.get_h1_bars(symbol)
    if h1 is None or h1.empty:
        return 0.0
    row = h1.iloc[-1]
    ask = row.get("close_ask", 0.0)
    bid = row.get("close_bid", 0.0)
    return max(float(ask) - float(bid), 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="IBKR Gateway Paper Trading Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 5-minute dry run (no orders)
  python -m src.runners.run_paper_ibkr_gateway --symbol EURUSD --minutes 5

  # Dry run on multiple symbols
  python -m src.runners.run_paper_ibkr_gateway --symbol EURUSD,GBPUSD

  # Enable real paper orders (requires IBKR_READONLY=false in ENV)
  python -m src.runners.run_paper_ibkr_gateway --symbol EURUSD --allow_live_orders
""",
    )
    parser.add_argument("--symbol", type=str, default="EURUSD",
                        help="Comma-separated symbols, e.g. EURUSD,GBPUSD,USDJPY")
    parser.add_argument("--config", type=str, default="config/config.yaml")
    parser.add_argument("--host", type=str, default=None,
                        help="IBKR host (default from ENV IBKR_HOST or 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None,
                        help="IBKR port (default from ENV IBKR_PORT or 4002)")
    parser.add_argument("--client_id", type=int, default=None,
                        help="IBKR client ID (default from ENV IBKR_CLIENT_ID or 7)")
    parser.add_argument("--minutes", type=int, default=0,
                        help="Run for N minutes then exit (0 = run until Ctrl+C)")
    parser.add_argument("--allow_live_orders", action="store_true",
                        help="Enable real paper orders (requires IBKR_READONLY=false)")
    parser.add_argument("--log_dir", type=str, default="logs")

    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbol.split(",") if s.strip()]

    # ── Load config + ENV overrides ───────────────────────────────────────────
    config = Config.from_env(args.config)
    ibkr_cfg: IBKRConfig = config.ibkr

    # CLI overrides take priority over ENV
    host = args.host or ibkr_cfg.host
    port = args.port or ibkr_cfg.port
    client_id = args.client_id or ibkr_cfg.client_id

    # ── Per-symbol configs ────────────────────────────────────────────────────
    sym_configs = {s: config.get_symbol_config(s) for s in symbols}

    kill_switch_env: bool = getattr(config, "_kill_switch_from_env", False)

    # ENV KILL_SWITCH=true overrides everything
    readonly = ibkr_cfg.readonly
    allow_live_orders = args.allow_live_orders or ibkr_cfg.allow_live_orders

    # ── Banner ────────────────────────────────────────────────────────────────
    print()
    print("=" * 72)
    print("  IBKR GATEWAY PAPER TRADING RUNNER")
    print("=" * 72)
    print(f"  Symbols         : {', '.join(symbols)}")
    for s in symbols:
        sc = sym_configs[s]
        if sc.session_filter:
            sess = f"{sc.session_start_h:02d}:00–{sc.session_end_h:02d}:00 UTC"
        else:
            sess = "24h"
        print(f"    {s:10s}  LTF={sc.ltf}  HTF={sc.htf}  session={sess}  enabled={sc.enabled}")
    print(f"  Config          : {args.config}")
    print(f"  Gateway         : {host}:{port}  clientId={client_id}")
    print(f"  IBKR_READONLY   : {readonly}")
    print(f"  ALLOW_LIVE_ORDERS: {allow_live_orders}")
    print(f"  KILL_SWITCH(ENV): {kill_switch_env}")
    print(f"  Risk per trade  : {config.risk.risk_fraction_start * 100:.1f}%")
    print(f"  Max positions   : {config.risk.max_open_positions_total} total / "
          f"{config.risk.max_open_positions_per_symbol} per symbol")
    print(f"  Log dir         : {args.log_dir}")
    if args.minutes:
        print(f"  Run duration    : {args.minutes} minutes")
    print("=" * 72)
    print()

    if readonly or not allow_live_orders:
        print("  ⚠  DRY-RUN MODE — no orders will be sent to IBKR.")
        print("     Set IBKR_READONLY=false + ALLOW_LIVE_ORDERS=true to trade.")
        print()
    else:
        print("  🔴 LIVE PAPER ORDERS ENABLED — trades will hit your demo account!")
        if sys.stdin.isatty():
            confirm = input("  Type 'YES' to confirm: ").strip()
            if confirm != "YES":
                print("  Aborted.")
                sys.exit(0)
        else:
            print("  Non-interactive mode (systemd) — skipping confirmation prompt.")
        print()

    # ── Connect to IBKR ───────────────────────────────────────────────────────
    marketdata = IBKRMarketData(
        host=host,
        port=port,
        client_id=client_id,
        historical_days=ibkr_cfg.historical_days,
    )

    if not marketdata.connect():
        print()
        print("[ERROR] Could not connect to IBKR Gateway / TWS. Troubleshooting:")
        print("  1) Is IB Gateway (paper) running? Start it and enable API.")
        print("  2) Gateway > Configuration > API > Settings > Enable ActiveX and Socket Clients")
        print("  3) Trust the 127.0.0.1 IP address in Trusted IPs list.")
        print("  4) Correct port? Gateway paper = 4002, TWS paper = 7497")
        print(f"     Currently trying: {host}:{port}")
        print("  5) Is clientId {client_id} already in use by another connection?")
        sys.exit(1)

    # ── Persistent state store ────────────────────────────────────────────────
    db_path = get_default_db_path()
    store = SQLiteStateStore(db_path)
    store.migrate()
    log.info("StateStore ready: %s", db_path)
    print(f"[DB] State store: {db_path}")

    # Load risk state from previous session
    risk_state = store.load_risk_state()
    if risk_state:
        log.info("Loaded risk state from DB: %s", list(risk_state.keys()))

    # ── Strategy + execution + logger ─────────────────────────────────────────
    strategy = TrendFollowingStrategy(config.strategy, store=store)

    # Build per-symbol trailing stop config from SymbolConfig
    trail_config_by_symbol: dict = {}
    for sym in symbols:
        sc = config.get_symbol_config(sym)
        if sc.trailing_stop and sc.trailing_stop.get("enabled", False):
            trail_config_by_symbol[sym] = sc.trailing_stop
            print(f"[TS] {sym} trailing stop enabled: "
                  f"ts_r={sc.trailing_stop.get('ts_r')}R "
                  f"lock_r={sc.trailing_stop.get('lock_r')}R")

    execution = IBKRExecutionEngine(
        ib=marketdata.ib,
        risk_config=config.risk,
        readonly=readonly,
        allow_live_orders=allow_live_orders,
        store=store,
        trail_config_by_symbol=trail_config_by_symbol,
    )
    logger = TradingLogger(log_dir=args.log_dir)

    # Restore kill-switch from DB if it was active
    if risk_state.get("kill_switch_active", False):
        execution.kill_switch_active = True
        log.warning("Kill switch restored from DB — all orders blocked")
        print("[KILL_SWITCH] Restored from DB — all orders blocked.")

    if kill_switch_env:
        execution.kill_switch_active = True
        logger.log_kill_switch("Activated from ENV KILL_SWITCH=true")
        print("[KILL_SWITCH] Activated from ENV — all orders blocked.")

    # ── Subscribe symbols ─────────────────────────────────────────────────────
    marketdata.store = store   # inject state store for bar-processed guard
    subscribed: list[str] = []
    for sym in symbols:
        sc = sym_configs[sym]
        if not sc.enabled:
            print(f"[SKIP] {sym} disabled in config.")
            continue
        if marketdata.subscribe_symbol(sym, ltf=sc.ltf, htf=sc.htf):
            subscribed.append(sym)
        else:
            print(f"[WARN] Could not subscribe to {sym} — skipping.")

    if not subscribed:
        print("[ERROR] No symbols subscribed. Exiting.")
        marketdata.disconnect()
        sys.exit(1)

    print(f"\n[READY] Subscribed: {', '.join(subscribed)}")
    print("  Waiting for H1 bar close to generate signals…")
    print("  Press Ctrl+C to stop.\n")

    # ── Restore open positions / pending orders from IBKR ─────────────────────
    # If the bot was restarted while orders were already on IBKR, rebuild
    # _records so the risk gate doesn't open duplicate positions and
    # poll_order_events() can track existing fills/exits.
    ibkr_brackets, restored_fill_rows = execution.restore_positions_from_ibkr(known_symbols=subscribed)

    # Log any restored FILL rows so the dashboard sees the active positions immediately
    for _fill_row in restored_fill_rows:
        logger.log_exit_row(_fill_row)
        log.info("Logged restored FILL row for %s @ %.5f",
                 _fill_row.get("symbol"), _fill_row.get("fill_price", 0))

    # ── Merge IBKR state into DB (source-of-truth reconciliation) ────────────
    # Collect bracket info for merge from restored _records
    brackets_for_merge = []
    for pid, rec in execution._records.items():
        brackets_for_merge.append({
            "parent_id": pid,
            "symbol": rec.intent.symbol,
            "status": OrderStatus.PENDING
                if rec.fill_price is None else OrderStatus.FILLED,
            "tp_id": rec.tp_id,
            "sl_id": rec.sl_id,
        })
    merge_counts = store.merge_ibkr_state(brackets_for_merge)
    log.info("DB startup merge: %s", merge_counts)
    print(f"[DB] Startup merge: {merge_counts}")

    # ── Save risk state to DB ─────────────────────────────────────────────────
    store.save_risk_state("kill_switch_active", execution.kill_switch_active)
    store.save_risk_state("peak_equity", execution._peak_equity)
    store.append_event("STARTUP_MERGE_SUMMARY", {
        "subscribed": subscribed,
        "ibkr_brackets": len(brackets_for_merge),
        **merge_counts,
    })

    # ── Immediately seal any bars already complete at startup ─────────────────
    # After bootstrap, last_sealed may be behind current time by 1+ hours.
    # Calling update_bars now processes any ticks already in the buffer so
    # the strategy can fire on the very next loop cycle instead of waiting
    # up to 1h for the next bar boundary.
    log.info("Startup seal: running initial update_bars for all symbols...")
    for sym in subscribed:
        marketdata.update_bars(sym)
    log.info("Startup seal complete.")

    # ── Main loop ─────────────────────────────────────────────────────────────
    last_bar_count: dict[str, int] = {s: marketdata.bar_count(s) for s in subscribed}
    start_ts = datetime.now(timezone.utc)
    run_limit_s = args.minutes * 60 if args.minutes > 0 else float("inf")
    _last_probe_ts: dict[str, float] = {}   # symbol -> last probe timestamp
    _bars_dump_counter = 0                  # export live bars every N cycles
    _bars_dump_dir = Path(args.log_dir).parent / "data" / "live_bars"
    _bars_dump_dir.mkdir(parents=True, exist_ok=True)

    try:
        while True:
            # ── Time limit ────────────────────────────────────────────────────
            elapsed = (datetime.now(timezone.utc) - start_ts).total_seconds()
            if elapsed >= run_limit_s:
                print(f"\n[INFO] Time limit reached ({args.minutes} min). Stopping.")
                break

            # ── Auto-reconnect if Gateway dropped us ──────────────────────────
            if not marketdata.ib.isConnected():
                log.warning("IBKR connection lost — attempting reconnect...")
                print("[WARN] Connection lost — reconnecting...")
                try:
                    marketdata.disconnect()
                    time.sleep(10)
                    if not marketdata.connect():
                        log.error("Reconnect failed — will retry next cycle")
                        time.sleep(POLL_INTERVAL_S)
                        continue
                    # Re-subscribe all symbols with their per-symbol TF config
                    subscribed = []
                    for sym in symbols:
                        sc = sym_configs[sym]
                        if sc.enabled and marketdata.subscribe_symbol(sym, ltf=sc.ltf, htf=sc.htf):
                            subscribed.append(sym)
                    last_bar_count = {s: marketdata.bar_count(s) for s in subscribed}
                    execution.ib = marketdata.ib
                    # Purge any stale/zombie _records against fresh IBKR state
                    purged = execution.purge_zombie_records()
                    if purged:
                        log.info("Post-reconnect zombie purge: removed %d record(s)", purged)
                        print(f"[RECONNECT] Zombie purge: removed {purged} stale record(s)")
                    log.info("Reconnected and re-subscribed: %s", subscribed)
                    print(f"[OK] Reconnected. Subscribed: {', '.join(subscribed)}")
                except Exception as exc:
                    log.error("Reconnect error: %s", exc)
                    time.sleep(POLL_INTERVAL_S)
                    continue

            # ── Active feed probe — snapshot every 5 min to refresh last_tick_time ──
            # IBKR Paper Gateway does NOT push ticker events when price is flat,
            # so passive stale-feed detection gives false alarms (EURUSD off-peak).
            # Probing snapshots every 5 min definitively keeps the timer alive.
            PROBE_INTERVAL_S = 300
            now_ts = datetime.now(timezone.utc).timestamp()
            for sym in subscribed:
                if now_ts - _last_probe_ts.get(sym, 0) >= PROBE_INTERVAL_S:
                    marketdata.probe_feed(sym)
                    _last_probe_ts[sym] = now_ts

            # ── Stale feed check — resubscribe if no tick for >10 min ────────
            STALE_SECONDS = 600
            for sym in subscribed:
                age = marketdata.last_tick_age_seconds(sym)
                if age > STALE_SECONDS:
                    # Use INFO for normal quiet-market resubscribes (e.g. EURUSD flat 10 min).
                    # Escalate to WARNING only if truly stale (>30 min) — likely a real issue.
                    level = logging.WARNING if age > 1800 else logging.INFO
                    log.log(level, "Stale feed for %s (%.0fs) — resubscribing...", sym, age)
                    print(f"[{'WARN' if age > 1800 else 'INFO'}] No tick for {sym} in {age:.0f}s — re-subscribing...")
                    marketdata.resubscribe_symbol(sym)

            # ── Kill switch ───────────────────────────────────────────────────
            execution.check_kill_switch()
            if execution.kill_switch_active:
                logger.log_kill_switch("Auto-activated: drawdown threshold exceeded")
                store.save_risk_state("kill_switch_active", True)
                store.save_risk_state("peak_equity", execution._peak_equity)
                print("\n[KILL_SWITCH] Trading halted — drawdown limit hit.")
                break

            for sym in subscribed:
                # ── Update tick buffer → sealed bars ──────────────────────────
                marketdata.update_bars(sym)

                h1  = marketdata.get_h1_bars(sym)
                htf = marketdata.get_htf_bars(sym)   # D1 or H4 per config

                if h1 is None or len(h1) < MIN_BARS:
                    n = len(h1) if h1 is not None else 0
                    log.debug("%s waiting for bars %d/%d", sym, n, MIN_BARS)
                    continue

                # ── New bar? ──────────────────────────────────────────────────
                cur_count = marketdata.bar_count(sym)
                if cur_count <= last_bar_count[sym]:
                    continue  # No new bar yet

                last_bar_count[sym] = cur_count
                bar_ts = h1.index[-1]
                print(f"\n[BAR] {sym} H1 closed: {bar_ts}  (total bars: {cur_count})")

                # ── Session filter ────────────────────────────────────────────
                sc = sym_configs[sym]
                bar_hour = bar_ts.hour
                if not sc.in_session(bar_hour):
                    log.debug("%s skipped — hour %02d UTC outside session %02d-%02d",
                              sym, bar_hour, sc.session_start_h, sc.session_end_h)
                    print(f"  [SESSION] {sym} skipped — {bar_hour:02d}:00 UTC outside "
                          f"{sc.session_start_h:02d}:00–{sc.session_end_h:02d}:00")
                    continue

                # ── ATR percentile filter (per-symbol, optional) ──────────────
                # Aktywny tylko gdy atr_pct_filter_min/max ustawione w config.yaml
                # Backtesty: CADJPY +0.245R delta z filtrem 10-80 (9-fold 2021-2025)
                if sc.atr_pct_filter_min is not None or sc.atr_pct_filter_max is not None:
                    _pct_min = sc.atr_pct_filter_min if sc.atr_pct_filter_min is not None else 0.0
                    _pct_max = sc.atr_pct_filter_max if sc.atr_pct_filter_max is not None else 100.0
                    try:
                        _atr_s = (h1['high_bid'] - h1['low_bid']).rolling(14).mean()
                        _cur_atr = _atr_s.iloc[-1]
                        _window = _atr_s.dropna().iloc[-100:]
                        if len(_window) >= 20 and not pd.isna(_cur_atr):
                            _pct_val = float((_window < _cur_atr).mean() * 100)
                            if not (_pct_min <= _pct_val <= _pct_max):
                                log.info("%s ATR filter: pct=%.1f outside [%.0f, %.0f] — skip",
                                         sym, _pct_val, _pct_min, _pct_max)
                                print(f"  [ATR_FILTER] {sym} skipped — "
                                      f"ATR pct={_pct_val:.1f} outside "
                                      f"[{_pct_min:.0f}, {_pct_max:.0f}]")
                                continue
                            else:
                                log.debug("%s ATR filter: pct=%.1f in [%.0f, %.0f] — OK",
                                          sym, _pct_val, _pct_min, _pct_max)
                    except Exception as _atr_err:
                        log.warning("%s ATR filter error (skipping filter): %s", sym, _atr_err)

                # ── H4 ADX gate (per-symbol, optional) ───────────────────────
                # Aktywny gdy adx_h4_gate ustawione w config.yaml (EURUSD/USDJPY/USDCHF/AUDJPY).
                # CADJPY: None — ATR filtr wystarczy (H4 ADX niszczyłby -24% ExpR).
                # Backtesty: adxv2_h4_thr16 +0.179R vs baseline +0.116R (+55%), Δ=+0.007R.
                if sc.adx_h4_gate is not None:
                    try:
                        # Oblicz H4 z resample H1 (no-lookahead: tylko zamknięte H4 bary)
                        _h4 = h1.resample("4h").agg({
                            "open_bid":  "first", "high_bid": "max",
                            "low_bid":   "min",   "close_bid": "last",
                        }).dropna(how="all")
                        # Odrzuć ostatni bar H4 jeśli nie jest zamknięty
                        # (ostatni H1 bar mógł trafić w środek H4 baru)
                        _now_h4 = pd.Timestamp(bar_ts).floor("4h")
                        _h4 = _h4[_h4.index < _now_h4]

                        if len(_h4) >= 20:
                            # ADX(14) Wildera na H4
                            _hi = _h4["high_bid"]
                            _lo = _h4["low_bid"]
                            _cl = _h4["close_bid"]
                            _prev_cl = _cl.shift(1)
                            _tr = pd.concat([
                                _hi - _lo,
                                (_hi - _prev_cl).abs(),
                                (_lo - _prev_cl).abs(),
                            ], axis=1).max(axis=1)
                            _atr14 = _tr.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
                            _up   = _hi - _hi.shift(1)
                            _dn   = _lo.shift(1) - _lo
                            _pdm  = pd.Series(
                                __import__("numpy").where((_up > _dn) & (_up > 0), _up, 0.0),
                                index=_h4.index)
                            _mdm  = pd.Series(
                                __import__("numpy").where((_dn > _up) & (_dn > 0), _dn, 0.0),
                                index=_h4.index)
                            _alpha = 1/14
                            _pdi = 100 * _pdm.ewm(alpha=_alpha, min_periods=14,
                                                   adjust=False).mean() / _atr14
                            _mdi = 100 * _mdm.ewm(alpha=_alpha, min_periods=14,
                                                   adjust=False).mean() / _atr14
                            _dx  = (100 * (_pdi - _mdi).abs() /
                                    (_pdi + _mdi).replace(0, float("nan"))).fillna(0)
                            _adx_h4 = _dx.ewm(alpha=_alpha, min_periods=14,
                                               adjust=False).mean()
                            _adx_val = float(_adx_h4.iloc[-1])

                            if pd.isna(_adx_val) or _adx_val < sc.adx_h4_gate:
                                log.info("%s H4 ADX gate: ADX=%.1f < thr=%.0f — skip",
                                         sym, _adx_val if not pd.isna(_adx_val) else -1,
                                         sc.adx_h4_gate)
                                print(f"  [ADX_H4] {sym} skipped — "
                                      f"ADX(H4)={_adx_val:.1f} < {sc.adx_h4_gate:.0f}")
                                continue
                            else:
                                log.info("%s H4 ADX gate: ADX=%.1f >= %.0f — OK",
                                         sym, _adx_val, sc.adx_h4_gate)
                        else:
                            log.info("%s H4 ADX gate: insufficient H4 bars (%d) — skip filter",
                                     sym, len(_h4))
                    except Exception as _adx_err:
                        log.warning("%s H4 ADX gate error (skipping filter): %s", sym, _adx_err)

                # ── Strategy ──────────────────────────────────────────────────
                try:
                    intents = strategy.process_bar(h1, htf, len(h1) - 1)
                except Exception as exc:
                    log.error("strategy.process_bar error for %s: %s", sym, exc)
                    continue

                if not intents:
                    print(f"  [SIGNAL] No signal for {sym}")
                    continue

                print(f"  [SIGNAL] {len(intents)} intent(s) for {sym}")

                spread = _current_spread(marketdata, sym)

                for intent in intents:
                    intent.symbol = sym

                    # ── Per-symbol risk_reward override ───────────────────────
                    # If SymbolConfig has risk_reward set (e.g. USDJPY=2.5 for TS),
                    # recalculate tp_price using the override instead of global config.
                    _sc = sym_configs.get(sym)
                    if _sc and _sc.risk_reward is not None:
                        _rr = _sc.risk_reward
                        _risk = abs((intent.entry_price or 0.0) - intent.sl_price)
                        if _risk > 0:
                            _old_tp = intent.tp_price
                            if intent.side.value == "LONG":
                                intent.tp_price = (intent.entry_price or 0.0) + _rr * _risk
                            else:
                                intent.tp_price = (intent.entry_price or 0.0) - _rr * _risk
                            log.info(
                                "[RR_OVERRIDE] %s rr=%.1f tp: %.5f -> %.5f",
                                sym, _rr, _old_tp, intent.tp_price,
                            )

                    # ── Patch strategy state symbol in DB (was "UNKNOWN") ─────
                    try:
                        _db_state = store.load_strategy_state("UNKNOWN")
                        if _db_state is not None:
                            from src.core.state_store import StrategyState
                            _db_state.symbol = sym
                            store.save_strategy_state(_db_state)
                    except Exception:
                        pass

                    logger.log_intent(intent, notes=f"bar_close={bar_ts}")

                    if execution.kill_switch_active:
                        logger.log_risk_block(intent, "KILL_SWITCH_ACTIVE")
                        continue

                    order_id = execution.execute_intent(intent)

                    if order_id is None:
                        logger.log_risk_block(intent, "RISK_BLOCK or SIZING_ERROR")
                    elif order_id == -1:
                        # Dry run — logged inside execute_intent
                        pass
                    else:
                        # Real order placed
                        logger.log_order_placed(intent, str(order_id))

            # ── Poll fills / exits (real orders only) ─────────────────────────
            spread_map = {s: _current_spread(marketdata, s) for s in subscribed}
            exit_rows = execution.poll_order_events(spread_by_symbol=spread_map)
            for row in exit_rows:
                logger.log_exit_row(row)
                print(
                    f"  [EXIT] {row.get('symbol')} {row.get('exit_reason')} "
                    f"R={row.get('realized_R', '?')}"
                )

            # ── Export live bars for dashboard (every 60 cycles ≈ 30 min) ────
            _bars_dump_counter += 1
            if _bars_dump_counter >= 60:
                _bars_dump_counter = 0
                for sym in subscribed:
                    h1 = marketdata.get_h1_bars(sym)
                    if h1 is not None and not h1.empty:
                        try:
                            out = _bars_dump_dir / f"{sym}.csv"
                            h1.tail(200).to_csv(out)
                            log.debug("Exported %d live bars for %s → %s", len(h1.tail(200)), sym, out)
                        except Exception as _exc:
                            log.warning("Failed to export bars for %s: %s", sym, _exc)

            time.sleep(POLL_INTERVAL_S)

    except KeyboardInterrupt:
        print("\n[STOP] Keyboard interrupt — shutting down…")

    except Exception as exc:
        log.exception("Unexpected error in main loop: %s", exc)
        # ── Auto-reconnect: don't exit, try to recover ────────────────────────
        print(f"\n[AUTO-RECONNECT] Error in main loop — reconnecting in 30s...")
        try:
            marketdata.disconnect()
        except Exception:
            pass
        time.sleep(30)
        log.info("Auto-reconnect: restarting main loop...")
        return main()  # restart without full process exit

    finally:
        # ── Graceful shutdown ─────────────────────────────────────────────────
        try:
            marketdata.disconnect()
        except Exception:
            pass
        print(f"\nSession ended.")
        print(f"Logs: {Path(args.log_dir).resolve()}/paper_trading_ibkr.csv")


if __name__ == "__main__":
    main()

