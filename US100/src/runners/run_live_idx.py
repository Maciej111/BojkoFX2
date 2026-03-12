"""
BojkoIDX — Live Trading Runner for US100 / NAS100USD
══════════════════════════════════════════════════════
Connects to the existing IB Gateway (shared with BojkoFX) using a
separate client_id (default 8) so both bots connect simultaneously.

Default safety posture:
  IBKR_READONLY=true   → all orders blocked (DRY mode)
  ALLOW_LIVE_ORDERS=false

To enable paper trading:
  set IBKR_READONLY=false
  set ALLOW_LIVE_ORDERS=true
  run with: --allow_live_orders

Dry-run test (no orders):
  python -m src.runners.run_live_idx --minutes 10

Live paper orders:
  python -m src.runners.run_live_idx --allow_live_orders

Deployment (via systemd):
  EnvironmentFile=/home/macie/bojkoidx/config/ibkr.env
  ExecStart=... python -m src.runners.run_live_idx --allow_live_orders

Strategy: BOS + Pullback  |  LTF=5m  |  HTF=4h  |  Session=13–20 UTC
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

from src.core.config import StrategyConfig, RiskConfig, IBKRConfig
from src.core.strategy import TrendFollowingStrategy
from src.core.state_store import SQLiteStateStore, OrderStatus, get_default_db_path
from src.data.ibkr_marketdata_idx import IBKRMarketDataIdx, SYMBOL
from src.execution.ibkr_exec import IBKRExecutionEngine
from src.reporting.logger import TradingLogger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger(__name__)

# ── Runtime constants ─────────────────────────────────────────────────────────
POLL_INTERVAL_S: int = 30          # seconds between update_bars() calls
STALE_FEED_WARN_S: float = 300     # 5 min without ticks → warn
STALE_FEED_RESUB_S: float = 600    # 10 min without ticks → resubscribe
PROBE_INTERVAL_S: float = 300      # proactive heartbeat every 5 min

# Session filter: only look for signals during these UTC hours (US/NYSE session)
SESSION_START_H: int = 13
SESSION_END_H:   int = 20

# bar minutes (5m LTF)
BAR_MINUTES: int = 5


def _parse_args():
    p = argparse.ArgumentParser(description="BojkoIDX live runner — US100 (NAS100USD)")
    p.add_argument("--allow_live_orders", action="store_true",
                   help="Enable real order submission (overrides IBKR_READONLY)")
    p.add_argument("--host", default=None, help="IB Gateway host (default: IBKR_HOST env or 127.0.0.1)")
    p.add_argument("--port", type=int, default=None, help="IB Gateway port (default: IBKR_PORT env or 4002)")
    p.add_argument("--client_id", type=int, default=None, help="IBKR client ID (default: IBKR_CLIENT_ID env or 8)")
    p.add_argument("--minutes", type=int, default=0, help="Run for N minutes then stop (0=infinite)")
    p.add_argument("--log_dir", default="logs", help="Log output directory")
    p.add_argument("--config", default="config/config.yaml", help="YAML config path (optional)")
    p.add_argument("--session_start", type=int, default=SESSION_START_H,
                   help=f"Session filter start UTC hour (default {SESSION_START_H})")
    p.add_argument("--session_end", type=int, default=SESSION_END_H,
                   help=f"Session filter end UTC hour (default {SESSION_END_H})")
    return p.parse_args()


def _load_ibkr_env(args) -> IBKRConfig:
    """Read IBKR connection params from ENV, then override with CLI args."""
    import os
    cfg = IBKRConfig()
    cfg.host       = os.getenv("IBKR_HOST", cfg.host)
    cfg.port       = int(os.getenv("IBKR_PORT", str(cfg.port)))
    cfg.client_id  = int(os.getenv("IBKR_CLIENT_ID", "8"))  # IDX uses 8 by default
    cfg.account    = os.getenv("IBKR_ACCOUNT", cfg.account)
    cfg.readonly   = os.getenv("IBKR_READONLY", "true").lower() != "false"
    cfg.allow_live_orders = os.getenv("ALLOW_LIVE_ORDERS", "false").lower() == "true"
    kill_switch_env = os.getenv("KILL_SWITCH", "false").lower() == "true"

    # CLI overrides
    if args.host:       cfg.host      = args.host
    if args.port:       cfg.port      = args.port
    if args.client_id:  cfg.client_id = args.client_id
    if args.allow_live_orders:
        cfg.allow_live_orders = True

    return cfg, kill_switch_env


def _build_strategy_config() -> StrategyConfig:
    """
    Production parameters for IDX 5m (from backtest: E=+0.46R, WR=46%, PF=1.49).
    These are fixed and NOT loaded from YAML to avoid accidental production changes.
    """
    return StrategyConfig(
        pivot_lookback_ltf=3,
        pivot_lookback_htf=5,
        confirmation_bars=1,
        require_close_break=True,
        entry_offset_atr_mult=0.3,
        pullback_max_bars=20,
        sl_anchor="last_pivot",
        sl_buffer_atr_mult=0.5,
        risk_reward=2.0,
    )


def _build_risk_config() -> RiskConfig:
    """
    Risk config for IDX.
    Equity override can be set via RISK_EQUITY_OVERRIDE env var to fix
    account equity (useful when paper account equity is unreliable).
    """
    import os
    cfg = RiskConfig(
        risk_fraction_start=float(os.getenv("RISK_FRACTION", "0.005")),  # 0.5% default
        sizing_mode="risk_first",
        max_open_positions_total=1,     # Only 1 position in NAS100USD at a time
        max_open_positions_per_symbol=1,
        daily_loss_limit_pct=3.0,
        monthly_dd_stop_pct=15.0,
        kill_switch_dd_pct=10.0,
    )
    equity_override = float(os.getenv("RISK_EQUITY_OVERRIDE", "0"))
    if equity_override > 0:
        cfg.equity_override = equity_override
    return cfg


def main():
    args = _parse_args()
    ibkr_cfg, kill_switch_env = _load_ibkr_env(args)
    strategy_cfg = _build_strategy_config()
    risk_cfg     = _build_risk_config()

    session_start = args.session_start
    session_end   = args.session_end

    # ── Banner ────────────────────────────────────────────────────────────────
    print()
    print("=" * 72)
    print("  BOJKOIDX — US100 LIVE PAPER TRADING RUNNER")
    print("=" * 72)
    print(f"  Symbol          : {SYMBOL}")
    print(f"  LTF / HTF       : 5m / 4h")
    print(f"  Session filter  : {session_start:02d}:00–{session_end:02d}:00 UTC")
    print(f"  Gateway         : {ibkr_cfg.host}:{ibkr_cfg.port}  clientId={ibkr_cfg.client_id}")
    print(f"  IBKR_READONLY   : {ibkr_cfg.readonly}")
    print(f"  ALLOW_LIVE_ORDERS: {ibkr_cfg.allow_live_orders}")
    print(f"  KILL_SWITCH(ENV): {kill_switch_env}")
    print(f"  Risk per trade  : {risk_cfg.risk_fraction_start * 100:.1f}%")
    print(f"  Strategy        : E=+0.46R WR=46% PF=1.49 (backtest 2021-2024)")
    print(f"  Log dir         : {args.log_dir}")
    if args.minutes:
        print(f"  Run duration    : {args.minutes} minutes")
    print("=" * 72)
    print()

    if ibkr_cfg.readonly or not ibkr_cfg.allow_live_orders:
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
    marketdata = IBKRMarketDataIdx(
        host=ibkr_cfg.host,
        port=ibkr_cfg.port,
        client_id=ibkr_cfg.client_id,
        historical_days=30,
    )

    if not marketdata.connect():
        print()
        print("[ERROR] Could not connect to IB Gateway. Troubleshooting:")
        print("  1) Is IB Gateway (paper) running on the same machine?")
        print("  2) Gateway > API Settings > Enable ActiveX and Socket Clients")
        print("  3) Add 127.0.0.1 to Trusted IPs")
        print(f"  4) Correct port? Paper gateway = 4002. Currently: {ibkr_cfg.port}")
        print(f"  5) Is clientId={ibkr_cfg.client_id} already in use?")
        sys.exit(1)

    # ── Persistent state store ────────────────────────────────────────────────
    db_path = get_default_db_path()
    store = SQLiteStateStore(db_path)
    store.migrate()
    log.info("StateStore ready: %s", db_path)
    print(f"[DB] State store: {db_path}")

    risk_state = store.load_risk_state()
    if risk_state:
        log.info("Loaded risk state from DB: %s", list(risk_state.keys()))

    # ── Strategy + execution + logging ────────────────────────────────────────
    strategy  = TrendFollowingStrategy(strategy_cfg, store=store)

    execution = IBKRExecutionEngine(
        ib=marketdata.ib,
        risk_config=risk_cfg,
        readonly=ibkr_cfg.readonly,
        allow_live_orders=ibkr_cfg.allow_live_orders,
        store=store,
        trail_config_by_symbol={},   # no trailing stop for IDX
    )
    logger = TradingLogger(log_dir=args.log_dir)

    # Restore kill-switch from DB
    if risk_state.get("kill_switch_active", False):
        execution.kill_switch_active = True
        log.warning("Kill switch restored from DB — all orders blocked")
        print("[KILL_SWITCH] Restored from DB — all orders blocked.")

    if kill_switch_env:
        execution.kill_switch_active = True
        logger.log_kill_switch("Activated from ENV KILL_SWITCH=true")
        print("[KILL_SWITCH] Activated from ENV — all orders blocked.")

    # ── Subscribe market data ─────────────────────────────────────────────────
    marketdata.store = store
    if not marketdata.subscribe():
        print("[ERROR] Could not subscribe to NAS100USD market data. Exiting.")
        marketdata.disconnect()
        sys.exit(1)

    print(f"\n[READY] Subscribed to {SYMBOL} — {marketdata.bar_count()} 5m bars loaded")
    print("  Waiting for 5m bar close to generate signals…")
    print(f"  Session filter: {session_start:02d}:00–{session_end:02d}:00 UTC")
    print("  Press Ctrl+C to stop.\n")

    # ── Restore open positions from IBKR ─────────────────────────────────────
    ibkr_brackets, restored_fill_rows = execution.restore_positions_from_ibkr(
        known_symbols=[SYMBOL]
    )
    for _fill_row in restored_fill_rows:
        logger.log_exit_row(_fill_row)
        log.info("Logged restored FILL row for %s @ %.2f",
                 _fill_row.get("symbol"), _fill_row.get("fill_price", 0))

    brackets_for_merge = []
    for pid, rec in execution._records.items():
        brackets_for_merge.append({
            "parent_id": pid,
            "symbol":    rec.intent.symbol,
            "status":    OrderStatus.PENDING if rec.fill_price is None else OrderStatus.FILLED,
            "tp_id":     rec.tp_id,
            "sl_id":     rec.sl_id,
        })
    merge_counts = store.merge_ibkr_state(brackets_for_merge)
    log.info("DB startup merge: %s", merge_counts)
    print(f"[DB] Startup merge: {merge_counts}")

    store.save_risk_state("kill_switch_active", execution.kill_switch_active)
    store.save_risk_state("peak_equity", execution._peak_equity)
    store.append_event("STARTUP_MERGE_SUMMARY", {
        "subscribed": [SYMBOL],
        "ibkr_brackets": len(brackets_for_merge),
        **merge_counts,
    })

    # ── Seal any bars already complete at startup ─────────────────────────────
    log.info("Startup seal: running initial update_bars...")
    marketdata.update_bars()
    log.info("Startup seal complete — %d bars", marketdata.bar_count())

    # ── Main loop ─────────────────────────────────────────────────────────────
    last_bar_count = marketdata.bar_count()
    start_ts       = datetime.now(timezone.utc)
    run_limit_s    = args.minutes * 60 if args.minutes > 0 else float("inf")
    _last_probe_ts: float = 0.0

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
                    if not marketdata.subscribe():
                        log.error("Re-subscribe failed — will retry")
                        time.sleep(POLL_INTERVAL_S)
                        continue
                    last_bar_count = marketdata.bar_count()
                    execution.ib = marketdata.ib
                    purged, zombie_exit_rows = execution.purge_zombie_records()
                    for row in zombie_exit_rows:
                        logger.log_exit_row(row)
                        log.warning(
                            "Post-reconnect zombie purge: emitting TRADE_CLOSED for filled "
                            "record %s signal_id=%s (was open, now untracked)",
                            row.get("symbol"), row.get("signal_id"),
                        )
                    if purged:
                        log.info("Post-reconnect zombie purge: removed %d record(s)", purged)
                        print(f"[RECONNECT] Zombie purge: removed {purged} stale record(s)")
                    log.info("Reconnected and re-subscribed %s", SYMBOL)
                    print(f"[OK] Reconnected. Subscribed: {SYMBOL}")
                except Exception as exc:
                    log.error("Reconnect error: %s", exc)
                    time.sleep(POLL_INTERVAL_S)
                    continue

            # ── Proactive feed heartbeat ──────────────────────────────────────
            now_mono = time.monotonic()
            if now_mono - _last_probe_ts > PROBE_INTERVAL_S:
                marketdata.probe_feed()
                _last_probe_ts = now_mono

            # ── Stale feed detection ──────────────────────────────────────────
            tick_age = marketdata.last_tick_age_seconds()
            if tick_age > STALE_FEED_RESUB_S:
                log.warning("Stale feed: %.0fs since last tick — resubscribing", tick_age)
                print(f"[WARN] Stale feed ({tick_age:.0f}s) — resubscribing {SYMBOL}")
                marketdata.resubscribe()
            elif tick_age > STALE_FEED_WARN_S:
                log.debug("Feed quiet: %.0fs since last tick", tick_age)

            # ── Poll orders ───────────────────────────────────────────────────
            bid, ask = marketdata.get_current_quote()
            spread_dict = {SYMBOL: (ask - bid)} if bid and ask else {}
            log_rows = execution.poll_order_events(spread_by_symbol=spread_dict)
            for row in log_rows:
                logger.log_exit_row(row)
                log.info("Order event logged: %s %s R=%.2f",
                         row.get("symbol"), row.get("event_type"), row.get("realized_R", 0))

            # Kill-switch: stop trading after daily/monthly loss breach
            if not execution.kill_switch_active:
                execution.check_kill_switch()
                if execution.kill_switch_active:
                    logger.log_kill_switch("Risk limit triggered — DD protection active")
                    print("[KILL_SWITCH] Risk limit triggered — all orders blocked.")

            # ── Update bars ───────────────────────────────────────────────────
            marketdata.update_bars()
            cur_count = marketdata.bar_count()

            if cur_count <= last_bar_count:
                marketdata.ib.sleep(POLL_INTERVAL_S)
                continue

            # ── New 5m bar arrived ────────────────────────────────────────────
            last_bar_count = cur_count
            ltf = marketdata.ltf_bars
            htf = marketdata.htf_bars
            bar_ts  = ltf.index[-1]
            bar_hour = bar_ts.hour
            print(f"\n[BAR] {SYMBOL} 5m closed: {bar_ts}  (total bars: {cur_count})")

            # ── Session filter ────────────────────────────────────────────────
            # FIX BUG-US-04: use <= (inclusive end) to match backtest is_allowed_session()
            if not (session_start <= bar_hour <= session_end):
                log.debug("Skipped — %02d:00 UTC outside session %02d–%02d",
                          bar_hour, session_start, session_end)
                print(f"  [SESSION] Skipped — {bar_hour:02d}:00 UTC outside "
                      f"{session_start:02d}:00–{session_end:02d}:00")
                marketdata.ib.sleep(POLL_INTERVAL_S)
                continue

            if htf is None or len(htf) < 10:
                print(f"  [SKIP] Insufficient HTF bars ({len(htf) if htf is not None else 0})")
                marketdata.ib.sleep(POLL_INTERVAL_S)
                continue

            # ── Risk gate check ───────────────────────────────────────────────
            n_open = execution.open_position_count(SYMBOL)
            if n_open >= risk_cfg.max_open_positions_per_symbol:
                print(f"  [RISK] Position already open for {SYMBOL} ({n_open}) — skip signal")
                marketdata.ib.sleep(POLL_INTERVAL_S)
                continue

            # ── Strategy signal ───────────────────────────────────────────────
            try:
                # FIX BUG-US-05: pass symbol so state is stored under correct key
                intents = strategy.process_bar(ltf, htf, len(ltf) - 1, symbol=SYMBOL)
            except Exception as exc:
                log.error("strategy.process_bar error: %s", exc, exc_info=True)
                marketdata.ib.sleep(POLL_INTERVAL_S)
                continue

            if not intents:
                print(f"  [SIGNAL] No signal for {SYMBOL}")
                marketdata.ib.sleep(POLL_INTERVAL_S)
                continue

            print(f"  [SIGNAL] {len(intents)} intent(s) for {SYMBOL}")

            # ── Place orders ──────────────────────────────────────────────────
            _bid, _ask = marketdata.get_current_quote()

            for intent in intents:
                intent.symbol = SYMBOL

                # Convert TTL from 5m bars to hours for IBKR GTD
                # pullback_max_bars=20 × 5min = 100min → 2h
                intent.ttl_bars = max(1, round(intent.ttl_bars * BAR_MINUTES / 60))

                # Apply 2.0 RR (production config)
                risk_dist = abs((intent.entry_price or 0.0) - intent.sl_price)
                if risk_dist > 0:
                    from src.core.models import Side
                    if intent.side == Side.LONG:
                        intent.tp_price = (intent.entry_price or 0.0) + strategy_cfg.risk_reward * risk_dist
                    else:
                        intent.tp_price = (intent.entry_price or 0.0) - strategy_cfg.risk_reward * risk_dist

                order_id = execution.place_order(intent)

                if order_id is not None:
                    spread = (_ask - _bid) if _bid and _ask else 0.0
                    log_row = {
                        "symbol":         SYMBOL,
                        "signal_id":      intent.signal_id,
                        "event_type":     "ENTRY",
                        "side":           intent.side.value,
                        "entry_type":     intent.entry_type.value,
                        "entry_price_intent": intent.entry_price,
                        "sl_price":       intent.sl_price,
                        "tp_price":       intent.tp_price,
                        "ttl_bars":       intent.ttl_bars,
                        "parentOrderId":  order_id,
                        "order_create_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                        "spread_at_entry": spread,
                    }
                    logger.log_entry_row(log_row)
                    print(f"  [ORDER] {intent.side.value} {SYMBOL} "
                          f"entry={intent.entry_price:.2f} "
                          f"sl={intent.sl_price:.2f} "
                          f"tp={intent.tp_price:.2f} "
                          f"orderId={order_id}")
                else:
                    print(f"  [SKIP] Order blocked (dry-run or risk gate): {intent.side.value} {SYMBOL}")

            marketdata.ib.sleep(POLL_INTERVAL_S)

    except KeyboardInterrupt:
        print("\n[INFO] Interrupted — shutting down...")

    finally:
        print("\n[SHUTDOWN] Saving state and disconnecting...")
        try:
            store.save_risk_state("kill_switch_active", execution.kill_switch_active)
            store.save_risk_state("peak_equity", execution._peak_equity)
            store.append_event("SHUTDOWN", {"ts": datetime.now(timezone.utc).isoformat()})
        except Exception as exc:
            log.warning("State save on shutdown failed: %s", exc)
        marketdata.disconnect()
        print("[SHUTDOWN] Done.")


if __name__ == "__main__":
    main()
