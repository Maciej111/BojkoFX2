"""
IBKR Execution Engine (Gateway paper trading)
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Safety gates (ALL three must be clear to send a real order):
  1. IBKR_READONLY = false
  2. ALLOW_LIVE_ORDERS = true
  3. kill_switch_active = False

In any other state the engine logs the intent as DRY and returns a sentinel
order-id of -1.

Bracket order model:
  parent (LIMIT or MARKET)  â†’  attached TP (LMT) + SL (STP)
  TTL on the parent enforced via GTD time-in-force.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from ib_insync import IB, Contract, Forex, LimitOrder, MarketOrder, StopOrder

from ..core.models import ExitReason, OrderIntent, OrderType, Side
from ..core.config import RiskConfig

log = logging.getLogger(__name__)

_PIP: Dict[str, float] = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "USDJPY": 0.01,
    "NAS100USD": 1.0,   # 1 index point per pip
}

# IBKR minimum price variation (tick size) per symbol
# JPY pairs: 0.005, others: 0.00005
_TICK: Dict[str, float] = {
    "USDJPY":   0.005,
    "AUDJPY":   0.005,
    "CADJPY":   0.005,
    "EURJPY":   0.005,
    "GBPJPY":   0.005,
    "CHFJPY":   0.005,
    "NAS100USD": 0.25,  # NAS100 CFD minimum tick
}

# Symbols traded as CFD contracts (not Forex)
_CFD_SYMBOLS = {"NAS100USD"}
_DEFAULT_TICK = 0.00005


def _round_price(price: float, symbol: str) -> float:
    """Round price to IBKR minimum tick size to avoid Warning 110."""
    import math
    tick = _TICK.get(symbol, _DEFAULT_TICK)
    return round(round(price / tick) * tick, 10)


def _pip(symbol: str) -> float:
    return _PIP.get(symbol, 0.0001)


def _make_contract(symbol: str):
    if symbol in _CFD_SYMBOLS:
        return Contract(
            symbol=symbol,
            secType="CFD",
            exchange="SMART",
            currency="USD",
        )
    return Forex(symbol)


# â”€â”€ Order lifecycle record â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _OrderRecord:
    """Tracks the lifecycle of a single trade (parent + tp + sl)."""

    def __init__(
        self,
        intent: OrderIntent,
        parent_id: int,
        tp_id: int,
        sl_id: int,
        create_time: datetime,
    ):
        self.intent = intent
        self.parent_id = parent_id
        self.tp_id = tp_id
        self.sl_id = sl_id
        self.create_time = create_time

        # Filled entry
        self.fill_time: Optional[datetime] = None
        self.fill_price: Optional[float] = None
        self.entry_latency_ms: float = 0.0
        self.entry_slippage_pips: float = 0.0
        self.spread_at_entry: float = 0.0
        self.commissions: float = 0.0

        # Exit
        self.exit_time: Optional[datetime] = None
        self.exit_price: Optional[float] = None
        self.exit_reason: Optional[ExitReason] = None
        self.exit_slippage_pips: float = 0.0

        # Derived
        self.realized_R: Optional[float] = None
        self.pnl: float = 0.0

        # Trailing stop state (programmatic, per-position)
        # trail_cfg: {"ts_r": float, "lock_r": float} or None
        self.trail_cfg: Optional[dict] = None
        self.trail_activated: bool = False
        self.trail_sl: float = 0.0          # current trailing SL price (updated as market moves)
        self.trail_sl_ibkr_id: int = 0      # orderId of the SL leg (to modify)

        # Status timeline (list of (timestamp, status_str))
        self.status_timeline: List[Tuple[datetime, str]] = []

    def add_status(self, status: str):
        self.status_timeline.append((datetime.now(timezone.utc).replace(tzinfo=None), status))

    def compute_R(self) -> Optional[float]:
        if None in (self.fill_price, self.exit_price):
            return None
        sl = self.intent.sl_price
        risk_dist = abs(self.fill_price - sl)
        if risk_dist == 0:
            return None
        if self.intent.side == Side.LONG:
            return (self.exit_price - self.fill_price) / risk_dist
        else:
            return (self.fill_price - self.exit_price) / risk_dist


# â”€â”€ Main engine class â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class IBKRExecutionEngine:
    """
    Execute OrderIntents on IBKR paper account via ib_insync.

    Parameters
    ----------
    ib              : connected IB instance
    risk_config     : RiskConfig dataclass
    readonly        : if True, no orders are sent (IBKR_READONLY gate)
    allow_live_orders: second gate; must be True for real orders
    """

    def __init__(
        self,
        ib: IB,
        risk_config: RiskConfig,
        readonly: bool = True,
        allow_live_orders: bool = False,
        store=None,                 # Optional[SQLiteStateStore]
        trail_config_by_symbol: Optional[Dict[str, dict]] = None,
    ):
        self.ib = ib
        self.risk = risk_config
        self.readonly = readonly
        self.allow_live_orders = allow_live_orders
        self.store = store

        # Per-symbol trailing stop config loaded from config.yaml
        # e.g. {"USDJPY": {"ts_r": 2.0, "lock_r": 0.5}, "CADJPY": {...}}
        self.trail_config_by_symbol: Dict[str, dict] = trail_config_by_symbol or {}

        # Kill switch (can be set externally or auto-triggered)
        self.kill_switch_active: bool = False
        self._peak_equity: float = 0.0
        self._account_equity: float = 0.0

        # Active order records: parent_order_id -> _OrderRecord
        self._records: Dict[int, _OrderRecord] = {}
        # symbol -> set of parent_order_ids
        self._positions_by_symbol: Dict[str, set] = {}
        self._emitted_restore_fills: set = set()

        # Fetch equity on startup
        if ib.isConnected():
            self._refresh_equity()

    # â”€â”€ Safety helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def _live_orders_allowed(self) -> bool:
        return (not self.readonly) and self.allow_live_orders and (not self.kill_switch_active)

    def _is_dry_run(self) -> bool:
        return not self._live_orders_allowed

    def _log_safety_reason(self) -> str:
        if self.kill_switch_active:
            return "KILL_SWITCH_ACTIVE"
        if self.readonly:
            return "IBKR_READONLY=true"
        if not self.allow_live_orders:
            return "ALLOW_LIVE_ORDERS=false"
        return "UNKNOWN"

    # â”€â”€ Account info â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _refresh_equity(self):
        try:
            # IBKR paper accounts report NetLiquidation in "BASE" currency,
            # not "USD".  Collect all NetLiquidation entries and prefer BASE,
            # then USD, then whatever is first.
            nl_values: dict[str, float] = {}
            for av in self.ib.accountValues():
                if av.tag == "NetLiquidation":
                    nl_values[av.currency] = float(av.value)

            ibkr_equity: float = 0.0
            if nl_values:
                ibkr_equity = (
                    nl_values.get("BASE")
                    or nl_values.get("USD")
                    or next(iter(nl_values.values()))
                )

            # equity_override > 0 → use fixed value for sizing (paper accounts
            # often have unrealistic balances that would produce giant orders).
            override = getattr(self.risk, "equity_override", 0.0)
            if override > 0:
                self._account_equity = float(override)
                if self._peak_equity == 0:
                    self._peak_equity = float(override)
                log.info(
                    "Account equity: $%.2f (NetLiquidation currencies seen: %s) "
                    "[SIZING uses equity_override=$%.2f]",
                    ibkr_equity, list(nl_values.keys()), override,
                )
                print(f"[IBKR] Account equity: ${ibkr_equity:,.2f}  "
                      f"[sizing override: ${override:,.2f}]")
            else:
                if ibkr_equity:
                    self._account_equity = ibkr_equity
                    if self._peak_equity == 0:
                        self._peak_equity = ibkr_equity
                log.info("Account equity: $%.2f (NetLiquidation currencies seen: %s)",
                         self._account_equity, list(nl_values.keys()))
                print(f"[IBKR] Account equity: ${self._account_equity:,.2f}")
        except Exception as exc:
            log.warning("Could not fetch account equity: %s", exc)
            self._account_equity = 10_000.0
            self._peak_equity = 10_000.0

    # â”€â”€ Risk checks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def purge_zombie_records(self) -> int:
        """
        Remove _records entries that no longer exist on IBKR.
        Called automatically by _check_risk when the internal count hits the limit,
        and can also be called explicitly (e.g. after reconnect).

        A record is a zombie when:
          - its parent order is gone from ib.trades() (not Pending/Submitted/PreSubmitted)
          - AND there is no open IBKR position for that symbol

        Returns the number of records removed.
        """
        if self._is_dry_run():
            return 0
        try:
            # Build set of active parent order IDs from IBKR
            active_ib_parent_ids: set = set()
            for t in self.ib.trades():
                if t.orderStatus.status not in ("Cancelled", "Filled", "Inactive", "ApiCancelled"):
                    pid = getattr(t.order, "parentId", 0)
                    if pid == 0:
                        active_ib_parent_ids.add(t.order.orderId)

            # Build set of symbols with open IBKR positions
            symbols_with_position: set = set()
            for p in self.ib.positions():
                if abs(p.position) > 0:
                    raw = (getattr(p.contract, "localSymbol", "") or
                           getattr(p.contract, "symbol", ""))
                    symbols_with_position.add(raw.replace(".", "").replace("/", "").upper())

            zombies: list = []
            for pid, rec in list(self._records.items()):
                order_exists = pid in active_ib_parent_ids
                position_exists = rec.intent.symbol in symbols_with_position
                if not order_exists and not position_exists:
                    zombies.append(pid)

            for pid in zombies:
                rec = self._records.pop(pid, None)
                if rec:
                    self._positions_by_symbol.get(rec.intent.symbol, set()).discard(pid)
                    log.warning(
                        "purge_zombie: removed stale record pid=%d %s "
                        "(not found in IBKR orders or positions)",
                        pid, rec.intent.symbol,
                    )
                    print(f"[ZOMBIE_PURGE] Removed stale record: {rec.intent.symbol} pid={pid}")

            if zombies:
                log.info("purge_zombie: removed %d zombie record(s); _records now=%d",
                         len(zombies), len(self._records))
            return len(zombies)
        except Exception as exc:
            log.error("purge_zombie_records error: %s", exc)
            return 0

    def _check_risk(self, symbol: str) -> bool:
        """Return True if a new position may be opened."""
        open_total = len(self._records)
        if open_total >= self.risk.max_open_positions_total:
            # Before hard-blocking: purge records that no longer exist on IBKR.
            # This handles zombie records left after bot restarts or reconnects.
            purged = self.purge_zombie_records()
            open_total = len(self._records)
            if open_total >= self.risk.max_open_positions_total:
                log.warning(
                    "RISK_BLOCK: max_open_positions_total=%d reached "
                    "(after purging %d zombie(s))",
                    self.risk.max_open_positions_total, purged,
                )
                return False
        open_sym = len(self._positions_by_symbol.get(symbol, set()))
        if open_sym >= self.risk.max_open_positions_per_symbol:
            log.warning("RISK_BLOCK: max_open_positions_per_symbol reached for %s", symbol)
            return False
        return True

    # â”€â”€ Position sizing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _calculate_units(self, intent: OrderIntent) -> int:
        """
        Position sizing — dwa tryby kontrolowane przez risk.sizing_mode:

        risk_first (domyślny, rekomendowany):
            units = (equity × risk_fraction) / stop_distance
            Ryzyko per trade jest zawsze stałe jako % equity.
            Backtesty: DD ~4-8% equity, ExpR +12% vs fixed_units.

        fixed_units (legacy):
            Startuje od default_units (5 000), scale-down jeśli
            implied_risk > equity × risk_fraction.
        """
        entry = intent.entry_price
        if not entry or entry <= 0:
            log.error(
                "[SIZING] %s entry_price is zero or None — blocking order "
                "(falling back to account equity would corrupt sizing)",
                intent.symbol,
            )
            return 0
        sl    = intent.sl_price
        stop_dist = abs(entry - sl)
        if stop_dist == 0:
            log.warning("[SIZING] zero stop_dist for %s — skipping", intent.symbol)
            return 0

        max_risk = max(self._account_equity * self.risk.risk_fraction_start, 1.0)
        mode     = getattr(self.risk, "sizing_mode", "risk_first")

        if mode == "risk_first":
            units = int(max_risk / stop_dist)
            units = max(units, 1)
        else:
            # legacy: fixed_units with cap-down
            default_units = getattr(self.risk, "default_units", 5_000)
            implied_risk  = stop_dist * default_units
            if implied_risk > max_risk:
                units = int(max_risk / stop_dist)
                units = max(units, 1)
            else:
                units = default_units

        # Hard cap — prevents oversized orders on large paper/live accounts
        max_units = getattr(self.risk, "max_units_per_trade", 200_000)
        if units > max_units:
            log.warning(
                "[SIZING] %s units=%d capped to max_units_per_trade=%d "
                "(equity=$%.0f, stop=%.5f)",
                intent.symbol, units, max_units,
                self._account_equity, stop_dist,
            )
            units = max_units

        pip       = _pip(intent.symbol)
        stop_pips = stop_dist / pip
        log.info(
            "[SIZING] %s  mode=%s  units=%s  stop=%.1f pips  "
            "risk=$%.2f  equity=$%.2f",
            intent.symbol, mode, f"{units:,}", stop_pips,
            stop_dist * units, self._account_equity,
        )
        return units

    # ── Trailing stop management ──────────────────────────────────────────────

    def _update_trail_sl(
        self,
        record: _OrderRecord,
        current_bid: float,
        current_ask: float,
    ) -> bool:
        """
        Called on every poll cycle for filled positions with trailing stop enabled.

        Logic (mirrors backtests/engine.py update_trail_sl exactly):
          1. Before activation: price reaches entry + ts_r * risk -> activate
             SL locked to entry + lock_r * risk (0 = breakeven)
          2. After activation: SL trails ts_r*risk behind the current price
             LONG: new_sl = price - ts_r*risk  (only moves up)
             SHORT: new_sl = price + ts_r*risk  (only moves down)
          3. If new_sl differs by >= 1 tick -> modifyOrder on IBKR

        Returns True if SL was modified on IBKR.
        """
        cfg = record.trail_cfg
        if cfg is None:
            return False

        ts_r   = float(cfg["ts_r"])
        lock_r = float(cfg.get("lock_r", 0.0))
        intent = record.intent
        entry  = record.fill_price or intent.entry_price or 0.0
        risk   = abs(entry - intent.sl_price)
        if risk <= 0 or entry <= 0:
            return False

        tick  = _TICK.get(intent.symbol, _DEFAULT_TICK)
        # FIX BUG-08: use ASK for LONG (entry was executed on ask) and BID for SHORT.
        # Previously used BID for LONG, creating ~1 spread asymmetry vs fill_price.
        price = current_ask if intent.side == Side.LONG else current_bid

        new_trail_sl = record.trail_sl

        if not record.trail_activated:
            if intent.side == Side.LONG:
                activate_at = entry + ts_r * risk
                if price >= activate_at:
                    record.trail_activated = True
                    new_trail_sl = max(record.trail_sl, entry + lock_r * risk)
                    log.info(
                        "[TS] %s LONG trail ACTIVATED price=%.5f >= %.5f -> SL locked %.5f",
                        intent.symbol, price, activate_at, new_trail_sl,
                    )
                    print(f"[TS] {intent.symbol} LONG ACTIVATED price={price:.5f} -> SL locked {new_trail_sl:.5f}")
            else:
                activate_at = entry - ts_r * risk
                if price <= activate_at:
                    record.trail_activated = True
                    new_trail_sl = min(record.trail_sl, entry - lock_r * risk)
                    log.info(
                        "[TS] %s SHORT trail ACTIVATED price=%.5f <= %.5f -> SL locked %.5f",
                        intent.symbol, price, activate_at, new_trail_sl,
                    )
                    print(f"[TS] {intent.symbol} SHORT ACTIVATED price={price:.5f} -> SL locked {new_trail_sl:.5f}")
        else:
            if intent.side == Side.LONG:
                candidate = price - ts_r * risk
                if candidate > new_trail_sl:
                    new_trail_sl = candidate
            else:
                candidate = price + ts_r * risk
                if candidate < new_trail_sl:
                    new_trail_sl = candidate

        new_trail_sl = _round_price(new_trail_sl, intent.symbol)

        # Only modify if change >= 1 tick (avoid flooding IBKR with micro-updates)
        if abs(new_trail_sl - record.trail_sl) < tick * 0.9:
            return False

        old_sl = record.trail_sl
        record.trail_sl = new_trail_sl

        if record.trail_sl_ibkr_id <= 0:
            log.warning("[TS] %s cannot modify SL — trail_sl_ibkr_id not set", intent.symbol)
            return False

        try:
            trades = self.ib.trades()
            sl_trade = next(
                (t for t in trades if t.order.orderId == record.trail_sl_ibkr_id),
                None,
            )
            if sl_trade is None:
                log.warning(
                    "[TS] %s SL order %d not found in ib.trades() — may already be filled",
                    intent.symbol, record.trail_sl_ibkr_id,
                )
                return False

            sl_trade.order.auxPrice = new_trail_sl
            self.ib.placeOrder(sl_trade.contract, sl_trade.order)
            log.info(
                "[TS] %s SL modified %.5f -> %.5f (activated=%s)",
                intent.symbol, old_sl, new_trail_sl, record.trail_activated,
            )
            print(f"[TS] {intent.symbol} SL moved: {old_sl:.5f} -> {new_trail_sl:.5f} "
                  f"(activated={record.trail_activated})")
            record.add_status(f"TS_SL_moved_{new_trail_sl:.5f}")

            # Persist updated trail state so a restart restores the correct SL
            if self.store is not None:
                try:
                    self.store.save_trail_state(
                        parent_id=record.parent_id,
                        activated=record.trail_activated,
                        sl_price=new_trail_sl,
                        sl_ibkr_id=record.trail_sl_ibkr_id,
                    )
                except Exception as _e:
                    log.warning("[TS] trail_state DB persist failed: %s", _e)

            return True
        except Exception as exc:
            log.error("[TS] %s modifyOrder failed: %s", intent.symbol, exc)
            return False

    # â”€â”€ Main entry point â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def execute_intent(self, intent: OrderIntent) -> Optional[int]:
        """
        Execute an OrderIntent.

        Returns
        -------
        int  : real parent orderId  (or -1 in dry-run)
        None : blocked / error
        """
        # 1) Risk gate
        if not self._check_risk(intent.symbol):
            print(f"[RISK_BLOCK] {intent.symbol}")
            return None

        # 2) Kill-switch gate
        if self.kill_switch_active:
            print(f"[KILL_SWITCH] Order blocked for {intent.symbol}")
            return None

        # 3) Dry-run / safety gate
        if self._is_dry_run():
            reason = self._log_safety_reason()
            print(
                f"[DRY_RUN] {reason} â€” would {intent.side.value} {intent.symbol} "
                f"entry={intent.entry_price}  sl={intent.sl_price}  tp={intent.tp_price}  "
                f"ttl={intent.ttl_bars}h"
            )
            return -1

        # 4) Sizing
        units = self._calculate_units(intent)
        if units <= 0:
            print(f"[ERROR] Zero units for {intent.symbol}")
            return None

        # 4.5) FIX BUG-14: Pre-save intent to DB BEFORE IBKR placement.
        # If bot crashes between bracket placement and the step-7 DB write, process_bar()
        # on restart finds this record via get_order_by_intent_id() and skips re-signalling.
        # Step 7 updates the same row (via ON CONFLICT intent_id DO UPDATE) with the real
        # IBKR parent_id and status=PENDING — no duplicate row is created.
        if self.store is not None:
            try:
                from ..core.state_store import DBOrderRecord, OrderStatus, make_intent_id
                _bos_meta = intent.metadata or {}
                _pre_intent_id = make_intent_id(
                    intent.symbol,
                    intent.side.value,
                    float(_bos_meta.get("bos_level", intent.entry_price or 0)),
                    str(_bos_meta.get("bos_bar_ts", "")),
                )
                self.store.upsert_order(DBOrderRecord(
                    intent_id=_pre_intent_id,
                    symbol=intent.symbol,
                    intent_json={
                        "signal_id": intent.signal_id,
                        "side": intent.side.value,
                        "entry_price": float(intent.entry_price or 0),
                        "sl_price": float(intent.sl_price),
                        "tp_price": float(intent.tp_price),
                        "ttl_bars": intent.ttl_bars,
                        "entry_type": intent.entry_type.value,
                        "metadata": {k: float(v) if hasattr(v, "item") else v
                                     for k, v in _bos_meta.items()},
                    },
                    status=OrderStatus.SENT,
                    parent_id=0,  # not yet placed — updated to real IBKR id at step 7
                ))
                log.debug("[PRE_SAVE] %s intent_id=%s status=SENT parent_id=0",
                          intent.symbol, _pre_intent_id)
            except Exception as _e:
                log.warning("execute_intent: pre-save DB write failed: %s", _e)

        # 5) Place bracket
        try:
            if intent.entry_type == OrderType.LIMIT:
                parent_id, tp_id, sl_id = self._place_limit_bracket(intent, units)
            else:
                parent_id, tp_id, sl_id = self._place_market_bracket(intent, units)
        except Exception as exc:
            log.error("place_order failed for %s: %s", intent.symbol, exc)
            print(f"[ERROR] place_order: {exc}")
            return None

        # 6) Track record
        record = _OrderRecord(
            intent=intent,
            parent_id=parent_id,
            tp_id=tp_id,
            sl_id=sl_id,
            create_time=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        record.add_status("Submitted")

        # ── Trailing stop initialisation ─────────────────────────────────────
        sym_trail_cfg = self.trail_config_by_symbol.get(intent.symbol)
        if sym_trail_cfg and sym_trail_cfg.get("enabled", True):
            record.trail_cfg = {
                "ts_r":   float(sym_trail_cfg.get("ts_r", 1.5)),
                "lock_r": float(sym_trail_cfg.get("lock_r", 0.0)),
            }
            record.trail_sl          = intent.sl_price   # initial SL = original SL
            record.trail_sl_ibkr_id  = sl_id
            record.trail_activated   = False
            log.info(
                "[TS] %s trail config loaded: ts_r=%.1f lock_r=%.1f sl_id=%d",
                intent.symbol, record.trail_cfg["ts_r"], record.trail_cfg["lock_r"], sl_id,
            )
            print(
                f"[TS] {intent.symbol} trailing stop armed: "
                f"ts_r={record.trail_cfg['ts_r']}R lock_r={record.trail_cfg['lock_r']}R"
            )

        self._records[parent_id] = record
        self._positions_by_symbol.setdefault(intent.symbol, set()).add(parent_id)

        # ── Persist trailing stop state to DB so it survives restarts ─────────
        if sym_trail_cfg and sym_trail_cfg.get("enabled", True) and self.store is not None:
            try:
                self.store.save_trail_state(
                    parent_id=parent_id,
                    activated=False,
                    sl_price=intent.sl_price,
                    sl_ibkr_id=sl_id,
                )
            except Exception as _e:
                log.warning("execute_intent: trail_state DB write failed: %s", _e)

        # 7) Persist to DB
        if self.store is not None:
            try:
                from ..core.state_store import (
                    DBOrderRecord, OrderStatus, make_intent_id, _dumps
                )
                bos_meta = intent.metadata or {}
                _intent_id = make_intent_id(
                    intent.symbol,
                    intent.side.value,
                    float(bos_meta.get("bos_level", intent.entry_price or 0)),
                    str(bos_meta.get("bos_bar_ts", "")),
                )
                ibkr_ids = {"parent": parent_id, "tp": tp_id, "sl": sl_id}
                db_rec = DBOrderRecord(
                    intent_id=_intent_id,
                    symbol=intent.symbol,
                    intent_json={
                        "signal_id": intent.signal_id,
                        "side": intent.side.value,
                        "entry_price": float(intent.entry_price or 0),
                        "sl_price": float(intent.sl_price),
                        "tp_price": float(intent.tp_price),
                        "ttl_bars": intent.ttl_bars,
                        "entry_type": intent.entry_type.value,
                        "metadata": {k: float(v) if hasattr(v, "item") else v
                                     for k, v in bos_meta.items()},
                    },
                    status=OrderStatus.PENDING,
                    parent_id=parent_id,
                    ibkr_ids_json=ibkr_ids,
                )
                self.store.upsert_order(db_rec)
                self.store.append_event("ORDER_SENT", {
                    "parent_id": parent_id,
                    "tp_id": tp_id,
                    "sl_id": sl_id,
                    "symbol": intent.symbol,
                    "side": intent.side.value,
                    "entry_price": float(intent.entry_price or 0),
                })
            except Exception as _e:
                log.warning("execute_intent: DB write failed: %s", _e)

        print(f"[ORDER] Placed bracket: parent={parent_id}  tp={tp_id}  sl={sl_id}")
        return parent_id

    # ── Restore state on restart ──────────────────────────────────────────────

    def restore_positions_from_ibkr(
        self, known_symbols: Optional[List[str]] = None
    ) -> Tuple[int, List[dict]]:
        """
        On bot restart, query IBKR for open orders and positions and
        rebuild _records / _positions_by_symbol so that:
          - Risk gate knows we already have open positions (won't double-open)
          - poll_order_events() can detect fills/exits for pre-existing orders

        Returns (count_restored, fill_rows) where fill_rows are dicts ready
        to be logged via TradingLogger.log_exit_row() for each filled position
        so the dashboard shows restored positions immediately.
        """
        if self._is_dry_run():
            log.info("restore_positions: dry-run mode — skipping")
            return 0, []

        restored = 0
        restored_fill_rows: List[dict] = []
        try:
            # ── Step 1: open orders on IBKR ──────────────────────────────────
            trades = self.ib.trades()
            log.info("restore_positions: found %d open trades on IBKR", len(trades))

            # Group by parentId to reconstruct bracket structure
            parent_map: Dict[int, dict] = {}  # parent_id -> {"parent", "tp", "sl"}

            for trade in trades:
                order  = trade.order
                status = trade.orderStatus.status
                if status in ("Cancelled", "Filled", "Inactive"):
                    continue

                oid = order.orderId
                pid = getattr(order, "parentId", 0)

                if pid == 0:
                    parent_map.setdefault(oid, {"parent": None, "tp": None, "sl": None})
                    parent_map[oid]["parent"] = trade
                else:
                    parent_map.setdefault(pid, {"parent": None, "tp": None, "sl": None})
                    if order.orderType in ("LMT",):
                        parent_map[pid]["tp"] = trade
                    elif order.orderType in ("STP",):
                        parent_map[pid]["sl"] = trade
                    else:
                        if parent_map[pid]["tp"] is None:
                            parent_map[pid]["tp"] = trade
                        else:
                            parent_map[pid]["sl"] = trade

            # ── Step 2: open positions (for already-filled parents) ───────────
            positions = {
                p.contract.localSymbol.replace(".", "").upper(): p
                for p in self.ib.positions()
                if abs(p.position) > 0
            }

            # ── Step 3: rebuild _records ──────────────────────────────────────
            for parent_id, bracket in parent_map.items():
                parent_trade = bracket.get("parent")
                tp_trade     = bracket.get("tp")
                sl_trade     = bracket.get("sl")

                # ── Case A: parent still active (pending entry) ───────────────
                if parent_trade is not None:
                    contract    = parent_trade.contract
                    raw_sym     = (getattr(contract, "localSymbol", "") or
                                   getattr(contract, "symbol", ""))
                    symbol      = raw_sym.replace(".", "").replace("/", "").upper()
                    order       = parent_trade.order
                    side        = Side.LONG if order.action == "BUY" else Side.SHORT
                    tp_price    = float(tp_trade.order.lmtPrice) if tp_trade else 0.0
                    sl_price    = float(sl_trade.order.auxPrice) if sl_trade else 0.0
                    entry_price = float(getattr(order, "lmtPrice", None) or
                                        getattr(order, "auxPrice", None) or 0.0)

                # ── Case B: parent already filled — derive from child orders + positions ──
                elif tp_trade is not None or sl_trade is not None:
                    child = tp_trade or sl_trade
                    contract = child.contract
                    raw_sym  = (getattr(contract, "localSymbol", "") or
                                getattr(contract, "symbol", ""))
                    symbol   = raw_sym.replace(".", "").replace("/", "").upper()

                    # TP is a SELL LMT → position is LONG; SL is a SELL STP → LONG
                    child_action = child.order.action  # "SELL" for long position
                    side = Side.SHORT if child_action == "BUY" else Side.LONG

                    tp_price = float(tp_trade.order.lmtPrice) if tp_trade else 0.0
                    sl_price = float(sl_trade.order.auxPrice) if sl_trade else 0.0

                    # entry_price from position avgCost or 0 (will be set below)
                    pos_info = positions.get(symbol)
                    entry_price = float(pos_info.avgCost) if pos_info else 0.0

                    log.info("restore_positions: parent %d already filled — "
                             "reconstructing from child orders for %s", parent_id, symbol)

                else:
                    # No usable data at all — skip
                    continue

                if known_symbols and symbol not in known_symbols:
                    log.debug("restore_positions: skipping %s (not subscribed)", symbol)
                    continue

                tp_id = tp_trade.order.orderId if tp_trade else 0
                sl_id = sl_trade.order.orderId if sl_trade else 0

                intent = OrderIntent(
                    signal_id=f"restored_{parent_id}",
                    timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                    symbol=symbol,
                    side=side,
                    entry_price=entry_price,
                    sl_price=sl_price,
                    tp_price=tp_price,
                    entry_type=OrderType.LIMIT if (
                        parent_trade and parent_trade.order.orderType == "LMT"
                    ) else OrderType.MARKET,
                    ttl_bars=0,
                )

                record = _OrderRecord(
                    intent=intent,
                    parent_id=parent_id,
                    tp_id=tp_id,
                    sl_id=sl_id,
                    create_time=datetime.now(timezone.utc).replace(tzinfo=None),
                )

                pos = positions.get(symbol)
                if pos and abs(pos.position) > 0:
                    record.fill_price = float(pos.avgCost) if pos.avgCost else entry_price
                    record.add_status("Filled/Restored")
                    log.info("restore_positions: %s filled @ %.5f  SL=%.5f  TP=%.5f",
                             symbol, record.fill_price, sl_price, tp_price)
                    if intent.signal_id not in self._emitted_restore_fills:
                        # Emit FILL row so dashboard shows restored position immediately
                        _now = datetime.now(timezone.utc).replace(tzinfo=None)
                        restored_fill_rows.append({
                            "event_type":          "FILL",
                            "timestamp":           _now.isoformat(),
                            "symbol":              symbol,
                            "signal_id":           intent.signal_id,
                            "side":                intent.side.value,
                            "entry_type":          intent.entry_type.value,
                            "entry_price_intent":  intent.entry_price,
                            "sl_price":            sl_price,
                            "tp_price":            tp_price,
                            "ttl_bars":            0,
                            "parentOrderId":       parent_id,
                            "tpOrderId":           tp_id,
                            "slOrderId":           sl_id,
                            "order_create_time":   _now.isoformat(),
                            "fill_time":           _now.isoformat(),
                            "fill_price":          record.fill_price,
                            "status_timeline":     "Filled/Restored",
                            "notes":               "restored_on_bot_restart",
                        })
                        self._emitted_restore_fills.add(intent.signal_id)
                    print(f"[RESTORE] {symbol} — open position @ {record.fill_price:.5f}  "
                          f"SL={sl_price:.5f}  TP={tp_price:.5f}")
                else:
                    record.add_status("Pending/Restored")
                    log.info("restore_positions: %s pending @ %.5f  SL=%.5f  TP=%.5f",
                             symbol, entry_price, sl_price, tp_price)
                    print(f"[RESTORE] {symbol} — pending order @ {entry_price:.5f}  "
                          f"SL={sl_price:.5f}  TP={tp_price:.5f}")

                self._records[parent_id] = record
                self._positions_by_symbol.setdefault(symbol, set()).add(parent_id)

                # ── Restore trailing stop state from DB ───────────────────────
                if self.store is not None:
                    trail_state = self.store.load_trail_state(parent_id)
                    sym_trail_cfg = self.trail_config_by_symbol.get(symbol)
                    if trail_state:
                        if sym_trail_cfg and sym_trail_cfg.get("enabled", True):
                            record.trail_cfg = {
                                "ts_r":   float(sym_trail_cfg.get("ts_r", 1.5)),
                                "lock_r": float(sym_trail_cfg.get("lock_r", 0.0)),
                            }
                            record.trail_activated  = bool(trail_state["activated"])
                            record.trail_sl         = float(trail_state["sl_price"])
                            record.trail_sl_ibkr_id = int(trail_state["sl_ibkr_id"])
                            log.info(
                                "[RESTORE_TS] %s trail state recovered: "
                                "activated=%s sl=%.5f sl_id=%d",
                                symbol, record.trail_activated,
                                record.trail_sl, record.trail_sl_ibkr_id,
                            )
                            print(
                                f"[RESTORE_TS] {symbol} trailing stop restored: "
                                f"activated={record.trail_activated} "
                                f"sl={record.trail_sl:.5f}"
                            )
                    elif sym_trail_cfg and sym_trail_cfg.get("enabled", True):
                        # FIX BUG-16: trail config exists but no DB record — SL will be
                        # at original intent SL, not the activated/moved level. Log warning
                        # so operator knows a protected trade has lost its trail protection.
                        log.warning(
                            "[RESTORE_TS] %s parent_id=%d has trail config but NO trail state in DB. "
                            "SL will revert to original %.5f. If trail was activated, protection is LOST!",
                            symbol, parent_id, record.trail_sl or 0.0,
                        )
                        print(
                            f"[WARN][RESTORE_TS] {symbol} parent_id={parent_id}: "
                            f"trail state missing from DB — SL at original level, trail protection may be lost!"
                        )

                restored += 1

        except Exception as exc:
            log.error("restore_positions_from_ibkr failed: %s", exc, exc_info=True)
            print(f"[WARN] Could not restore positions: {exc}")

        if restored:
            log.info("restore_positions: restored %d bracket(s) from IBKR", restored)
            print(f"[RESTORE] Restored {restored} open bracket(s) from IBKR")
        else:
            log.info("restore_positions: no open brackets found on IBKR")
            print("[RESTORE] No open positions found on IBKR — starting fresh")
        return restored, restored_fill_rows

    # ── Bracket order builders ────────────────────────────────────────────────

    def _place_limit_bracket(
        self, intent: OrderIntent, units: int
    ) -> Tuple[int, int, int]:
        contract = _make_contract(intent.symbol)
        action = "BUY" if intent.side == Side.LONG else "SELL"
        exit_action = "SELL" if intent.side == Side.LONG else "BUY"
        expiry_str = self._expiry_str(intent.ttl_bars)

        entry_px = _round_price(intent.entry_price, intent.symbol)
        tp_px    = _round_price(intent.tp_price,    intent.symbol)
        sl_px    = _round_price(intent.sl_price,    intent.symbol)
        log.debug("Rounded prices %s: entry=%.5f tp=%.5f sl=%.5f",
                  intent.symbol, entry_px, tp_px, sl_px)

        # Parent limit order — transmit=False so IBKR holds it until SL arrives
        parent = LimitOrder(action, units, entry_px)
        parent.tif = "GTD"
        parent.goodTillDate = expiry_str
        parent.transmit = False

        parent_trade = self.ib.placeOrder(contract, parent)
        # Wait until IBKR *server* acknowledges the parent (status=Submitted/PreSubmitted)
        for _ in range(40):
            self.ib.sleep(0.1)
            status = parent_trade.orderStatus.status
            if status in ("Submitted", "PreSubmitted", "Filled"):
                break
        parent_id = parent_trade.order.orderId
        if not parent_id:
            raise RuntimeError(f"Parent order not acknowledged by IBKR (orderId=0)")
        log.debug("Parent order %d status: %s", parent_id, parent_trade.orderStatus.status)

        # Take profit
        tp_order = LimitOrder(exit_action, units, tp_px)
        tp_order.parentId = parent_id
        tp_order.tif = "GTC"
        tp_order.transmit = False
        tp_trade = self.ib.placeOrder(contract, tp_order)
        self.ib.sleep(0.5)
        tp_id = tp_trade.order.orderId

        # Stop loss — transmit=True triggers the whole bracket
        sl_order = StopOrder(exit_action, units, sl_px)
        sl_order.parentId = parent_id
        sl_order.tif = "GTC"
        sl_order.transmit = True
        sl_trade = self.ib.placeOrder(contract, sl_order)
        self.ib.sleep(0.5)
        sl_id = sl_trade.order.orderId

        # FIX BUG-10: if SL was not acknowledged, cancel parent+TP to avoid zombie orders.
        # parent+TP have transmit=False so they are held on IBKR but not yet live.
        if not sl_id:
            log.error(
                "[BRACKET] SL not acknowledged for %s — cancelling parent=%d tp=%d to avoid zombie orders",
                intent.symbol, parent_id, tp_id,
            )
            try:
                self.ib.cancelOrder(parent_trade.order)
                self.ib.cancelOrder(tp_trade.order)
            except Exception as _ce:
                log.error("[BRACKET] Cancel of zombie orders failed: %s", _ce)
            raise RuntimeError(
                f"Bracket placement incomplete for {intent.symbol}: SL order not acknowledged. "
                f"parent={parent_id} tp={tp_id} have been cancelled."
            )

        return parent_id, tp_id, sl_id

    def _place_market_bracket(
        self, intent: OrderIntent, units: int
    ) -> Tuple[int, int, int]:
        contract = _make_contract(intent.symbol)
        action = "BUY" if intent.side == Side.LONG else "SELL"
        exit_action = "SELL" if intent.side == Side.LONG else "BUY"

        tp_px = _round_price(intent.tp_price, intent.symbol)
        sl_px = _round_price(intent.sl_price, intent.symbol)

        parent = MarketOrder(action, units)
        parent.transmit = False

        parent_trade = self.ib.placeOrder(contract, parent)
        # Wait until IBKR *server* acknowledges the parent (status=Submitted/PreSubmitted)
        for _ in range(40):
            self.ib.sleep(0.1)
            status = parent_trade.orderStatus.status
            if status in ("Submitted", "PreSubmitted", "Filled"):
                break
        parent_id = parent_trade.order.orderId
        if not parent_id:
            raise RuntimeError(f"Parent order not acknowledged by IBKR (orderId=0)")
        log.debug("Parent order %d status: %s", parent_id, parent_trade.orderStatus.status)

        tp_order = LimitOrder(exit_action, units, tp_px)
        tp_order.parentId = parent_id
        tp_order.tif = "GTC"
        tp_order.transmit = False
        tp_trade = self.ib.placeOrder(contract, tp_order)
        self.ib.sleep(0.5)
        tp_id = tp_trade.order.orderId

        sl_order = StopOrder(exit_action, units, sl_px)
        sl_order.parentId = parent_id
        sl_order.tif = "GTC"
        sl_order.transmit = True
        sl_trade = self.ib.placeOrder(contract, sl_order)
        self.ib.sleep(0.5)
        sl_id = sl_trade.order.orderId

        # FIX BUG-10: same rollback guard for market bracket
        if not sl_id:
            log.error(
                "[BRACKET] SL not acknowledged for %s (market) — cancelling parent=%d tp=%d",
                intent.symbol, parent_id, tp_id,
            )
            try:
                self.ib.cancelOrder(parent_trade.order)
                self.ib.cancelOrder(tp_trade.order)
            except Exception as _ce:
                log.error("[BRACKET] Cancel of zombie orders failed: %s", _ce)
            raise RuntimeError(
                f"Market bracket placement incomplete for {intent.symbol}: SL order not acknowledged."
            )

        return parent_id, tp_id, sl_id

    @staticmethod
    def _expiry_str(ttl_bars: int) -> str:
        expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=ttl_bars)
        return expiry.strftime("%Y%m%d %H:%M:%S UTC")

    # â”€â”€ Fill / exit polling â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def poll_order_events(self, spread_by_symbol: Optional[Dict[str, float]] = None) -> List[dict]:
        """
        Poll IBKR for order status changes.
        Returns a list of log-row dicts (one per fill / exit event).
        Call from the main loop every N seconds.
        """
        if self._is_dry_run():
            return []

        log_rows: List[dict] = []
        completed_parent_ids: List[int] = []

        try:
            trades = self.ib.trades()
            trade_by_id = {t.order.orderId: t for t in trades}

            for parent_id, record in list(self._records.items()):
                intent = record.intent

                # â”€â”€ Entry fill â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

                parent_trade = trade_by_id.get(parent_id)
                if parent_trade and parent_trade.orderStatus.status == "Filled":
                    if record.fill_time is None:
                        record.fill_time = datetime.now(timezone.utc).replace(tzinfo=None)
                        record.fill_price = parent_trade.orderStatus.avgFillPrice
                        record.entry_latency_ms = (
                            record.fill_time - record.create_time
                        ).total_seconds() * 1000

                        if intent.entry_price:
                            pip = _pip(intent.symbol)
                            record.entry_slippage_pips = (
                                (record.fill_price - intent.entry_price) / pip
                                if intent.side == Side.LONG
                                else (intent.entry_price - record.fill_price) / pip
                            )

                        spread = (spread_by_symbol or {}).get(intent.symbol, 0.0)
                        record.spread_at_entry = spread

                        # Accumulate commissions
                        for fill in parent_trade.fills:
                            record.commissions += abs(fill.commissionReport.commission or 0)

                        record.add_status("Filled")
                        print(
                            f"[FILL] {intent.symbol} {intent.side.value} "
                            f"@ {record.fill_price:.5f}  "
                            f"latency={record.entry_latency_ms:.0f}ms  "
                            f"slip={record.entry_slippage_pips:+.1f}pips"
                        )
                        # ── DB: mark FILLED ───────────────────────────────────
                        if self.store is not None:
                            try:
                                from ..core.state_store import OrderStatus
                                self.store.update_order_status(parent_id, OrderStatus.FILLED)
                                self.store.append_event("ORDER_FILLED", {
                                    "parent_id": parent_id,
                                    "symbol": intent.symbol,
                                    "fill_price": float(record.fill_price),
                                })
                            except Exception as _e:
                                log.warning("DB fill update failed: %s", _e)

                        # -- Emit FILL event to CSV so dashboard shows open position --
                        # Without this row the dashboard only sees ORDER_PLACED and has no
                        # way to know the entry filled; position appears NONE until TP/SL.
                        log_rows.append({
                            "event_type":          "FILL",
                            "timestamp":           record.fill_time.isoformat(),
                            "symbol":              intent.symbol,
                            "signal_id":           intent.signal_id,
                            "side":                intent.side.value,
                            "entry_type":          intent.entry_type.value,
                            "entry_price_intent":  intent.entry_price,
                            "sl_price":            intent.sl_price,
                            "tp_price":            intent.tp_price,
                            "ttl_bars":            intent.ttl_bars,
                            "parentOrderId":       record.parent_id,
                            "tpOrderId":           record.tp_id,
                            "slOrderId":           record.sl_id,
                            "order_create_time":   record.create_time.isoformat(),
                            "fill_time":           record.fill_time.isoformat(),
                            "fill_price":          record.fill_price,
                            "slippage_entry_pips": round(record.entry_slippage_pips, 2),
                            "latency_ms":          round(record.entry_latency_ms, 1),
                            "spread_at_entry":     round(record.spread_at_entry, 6),
                            "status_timeline":     " | ".join(t[1] for t in record.status_timeline),
                        })
                # â”€â”€ Exit: check TP / SL fills â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

                if record.fill_time and record.exit_time is None:
                    tp_trade = trade_by_id.get(record.tp_id)
                    sl_trade = trade_by_id.get(record.sl_id)

                    exit_trade  = None
                    exit_reason = None

                    # FIX BUG-09: check SL before TP — worst-case principle matching backtest.
                    # If both are filled in the same poll cycle, backtest chooses SL (pessimistic).
                    if sl_trade and sl_trade.orderStatus.status == "Filled":
                        exit_trade  = sl_trade
                        # Distinguish: regular SL vs trailing-stop hit
                        exit_reason = ExitReason.TS if record.trail_activated else ExitReason.SL
                    elif tp_trade and tp_trade.orderStatus.status == "Filled":
                        exit_trade  = tp_trade
                        exit_reason = ExitReason.TP

                    if exit_trade:
                        record.exit_time  = datetime.now(timezone.utc).replace(tzinfo=None)
                        record.exit_price = exit_trade.orderStatus.avgFillPrice
                        record.exit_reason = exit_reason

                        # Intended exit price for slippage calculation
                        if exit_reason == ExitReason.TS:
                            intended = record.trail_sl
                        elif exit_reason == ExitReason.TP:
                            intended = intent.tp_price
                        else:
                            intended = intent.sl_price
                        pip = _pip(intent.symbol)
                        record.exit_slippage_pips = abs(record.exit_price - intended) / pip

                        record.realized_R = record.compute_R()

                        if intent.side == Side.LONG:
                            record.pnl = record.exit_price - record.fill_price
                        else:
                            record.pnl = record.fill_price - record.exit_price

                        record.add_status(f"Closed_{exit_reason.value}")
                        trail_info = (
                            f" [TS activated={record.trail_activated}"
                            f" trail_sl={record.trail_sl:.5f}]"
                            if record.trail_cfg else ""
                        )
                        print(
                            f"[EXIT] {intent.symbol} {exit_reason.value} "
                            f"@ {record.exit_price:.5f}  R={record.realized_R:.3f}"
                            f"{trail_info}"
                        )
                        # ── DB: mark EXITED ───────────────────────────────────
                        if self.store is not None:
                            try:
                                from ..core.state_store import OrderStatus
                                self.store.update_order_status(parent_id, OrderStatus.EXITED)
                                evt = (
                                    "EXIT_TP" if exit_reason == ExitReason.TP
                                    else "EXIT_TS" if exit_reason == ExitReason.TS
                                    else "EXIT_SL"
                                )
                                self.store.append_event(evt, {
                                    "parent_id":       parent_id,
                                    "symbol":          intent.symbol,
                                    "exit_price":      float(record.exit_price),
                                    "realized_R":      float(record.realized_R)
                                                       if record.realized_R is not None else None,
                                    "trail_activated": record.trail_activated,
                                })
                            except Exception as _e:
                                log.warning("DB exit update failed: %s", _e)

                        log_rows.append(self._record_to_log_row(record))
                        completed_parent_ids.append(parent_id)

                    else:
                        # No exit yet — update trailing SL if enabled
                        if record.trail_cfg is not None:
                            try:
                                ticker = self.ib.ticker(_make_contract(intent.symbol))
                                bid = ticker.bid if (ticker and ticker.bid
                                                     and ticker.bid > 0) else 0.0
                                ask = ticker.ask if (ticker and ticker.ask
                                                     and ticker.ask > 0) else 0.0
                                if bid > 0 and ask > 0:
                                    self._update_trail_sl(record, bid, ask)
                            except Exception as _te:
                                log.debug("[TS] %s ticker fetch failed: %s",
                                          intent.symbol, _te)

                # â”€â”€ Cancelled / expired â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

                if parent_trade and parent_trade.orderStatus.status in (
                    "Cancelled", "Inactive", "ApiCancelled"
                ):
                    if record.fill_time is None:
                        record.exit_reason = ExitReason.CANCEL
                        record.add_status("Cancelled_no_fill")
                        # ── DB: mark CANCELLED ────────────────────────────────
                        if self.store is not None:
                            try:
                                from ..core.state_store import OrderStatus
                                self.store.update_order_status(parent_id, OrderStatus.CANCELLED)
                                self.store.append_event("ORDER_CANCELLED", {
                                    "parent_id": parent_id, "symbol": intent.symbol,
                                })
                            except Exception as _e:
                                log.warning("DB cancel update failed: %s", _e)
                        log_rows.append(self._record_to_log_row(record))
                        completed_parent_ids.append(parent_id)

                # ── GTD expired / vanished from ib.trades() ───────────────────
                # Order disappeared from IBKR (GTD expired or external cancel)
                # before any fill — remove from _records to avoid permanent RISK_BLOCK.
                elif parent_trade is None and record.fill_time is None:
                    age_hours = (
                        datetime.now(timezone.utc).replace(tzinfo=None) - record.create_time
                    ).total_seconds() / 3600
                    if age_hours > 2:
                        log.warning(
                            "Order %d for %s vanished from IBKR after %.1fh "
                            "(GTD expired?) — removing from _records to unblock RISK gate",
                            parent_id, intent.symbol, age_hours,
                        )
                        print(
                            f"[STALE_ORDER] {intent.symbol} orderId={parent_id} "
                            f"missing from IBKR after {age_hours:.1f}h — auto-cleaning"
                        )
                        record.exit_reason = ExitReason.CANCEL
                        record.add_status("GTD_expired_or_vanished")
                        # ── DB: mark EXPIRED ──────────────────────────────────
                        if self.store is not None:
                            try:
                                from ..core.state_store import OrderStatus
                                self.store.update_order_status(parent_id, OrderStatus.EXPIRED)
                                self.store.append_event("ORDER_EXPIRED", {
                                    "parent_id": parent_id, "symbol": intent.symbol,
                                    "age_hours": round(age_hours, 2),
                                })
                            except Exception as _e:
                                log.warning("DB expired update failed: %s", _e)
                        log_rows.append(self._record_to_log_row(record))
                        completed_parent_ids.append(parent_id)

        except Exception as exc:
            log.error("poll_order_events error: %s", exc)

        # Remove completed records
        for pid in set(completed_parent_ids):
            rec = self._records.pop(pid, None)
            if rec:
                self._positions_by_symbol.get(rec.intent.symbol, set()).discard(pid)

        return log_rows

    # â”€â”€ Kill switch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def check_kill_switch(self):
        """Auto-activate kill switch if drawdown exceeds threshold."""
        if self._account_equity <= 0:
            return
        if self._account_equity > self._peak_equity:
            self._peak_equity = self._account_equity
        dd_pct = (self._peak_equity - self._account_equity) / self._peak_equity * 100
        if dd_pct >= self.risk.kill_switch_dd_pct:
            self.kill_switch_active = True
            print(f"[KILL_SWITCH] AUTO-ACTIVATED â€” DD={dd_pct:.1f}%")

    # â”€â”€ Log-row helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @staticmethod
    def _record_to_log_row(rec: _OrderRecord) -> dict:
        intent = rec.intent
        return {
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "symbol": intent.symbol,
            "signal_id": intent.signal_id,
            "side": intent.side.value,
            "entry_type": intent.entry_type.value,
            "entry_price_intent": intent.entry_price,
            "sl_price": intent.sl_price,
            "tp_price": intent.tp_price,
            "ttl_bars": intent.ttl_bars,
            "parentOrderId": rec.parent_id,
            "tpOrderId": rec.tp_id,
            "slOrderId": rec.sl_id,
            "order_create_time": rec.create_time.isoformat(),
            "fill_time": rec.fill_time.isoformat() if rec.fill_time else "",
            "fill_price": rec.fill_price or "",
            "exit_time": rec.exit_time.isoformat() if rec.exit_time else "",
            "exit_price": rec.exit_price or "",
            "exit_reason": rec.exit_reason.value if rec.exit_reason else "",
            "latency_ms": round(rec.entry_latency_ms, 1),
            "slippage_entry_pips": round(rec.entry_slippage_pips, 2),
            "slippage_exit_pips": round(rec.exit_slippage_pips, 2),
            "realized_R": round(rec.realized_R, 4) if rec.realized_R is not None else "",
            "commissions": round(rec.commissions, 4),
            "spread_at_entry": round(rec.spread_at_entry, 6),
            "status_timeline": " | ".join(f"{t[1]}" for t in rec.status_timeline),
        }

    # â”€â”€ Open positions query â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def get_open_records(self) -> List[_OrderRecord]:
        return list(self._records.values())

