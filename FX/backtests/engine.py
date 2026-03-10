"""
backtests/engine.py
Symulator backtestowy: fill logic, portfolio constraints, sizing.
Wejście: list[TradeSetup] per symbol + bary H1 do symulacji fillów/wyjść.

Trailing stop support (2026-03-08):
  trail_cfg = {
      "ts_r":   float,   # R level at which trailing activates (e.g. 1.5)
      "lock_r": float,   # R level to lock in (move SL to entry + lock_r * risk)
                         # if None → lock SL to breakeven (0R) when activated
  }
  When price reaches ts_r * risk beyond entry:
    - SL is moved to entry + lock_r * risk  (or breakeven if lock_r not set)
    - From that point SL trails: never goes back, only moves in direction of trade
  TP remains unchanged.
  Exit reason "TS" (trailing stop) is used when trailing SL is hit.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd

from .signals_bos_pullback import ClosedTrade, TradeSetup


# ── Position sizing ───────────────────────────────────────────────────────────

def calc_units(
    setup: TradeSetup,
    sizing_cfg: dict,
    equity: float,
) -> float:
    """
    Zwraca liczbę units dla danego setup.
    sizing_cfg: {mode: "fixed_units"|"risk_first", units?: float, risk_pct?: float}
    """
    mode = sizing_cfg.get("mode", "fixed_units")
    if mode == "fixed_units":
        return float(sizing_cfg.get("units", 5000))
    elif mode == "risk_first":
        risk_pct = float(sizing_cfg.get("risk_pct", 0.005))
        stop_dist = abs(setup.entry_price - setup.sl_price)
        if stop_dist <= 0:
            return 0.0
        risk_amount = equity * risk_pct
        return risk_amount / stop_dist
    return float(sizing_cfg.get("units", 5000))


# ── Fill simulation per bar ───────────────────────────────────────────────────

def try_fill(setup: TradeSetup,
             bar_open: float, bar_high: float,
             bar_low: float) -> bool:
    """
    Zwraca True jeśli w tym barze następuje fill zlecenia limit.
    LONG:  fill jeśli low <= entry <= high (cena sięgnęła poziomu)
    SHORT: fill jeśli low <= entry <= high
    """
    return bar_low <= setup.entry_price <= bar_high


def try_exit(setup: TradeSetup,
             bar_open: float, bar_high: float, bar_low: float,
             bar_close: float, same_bar_mode: str
             ) -> Optional[Tuple[str, float]]:
    """Standard exit check (no trailing stop)."""
    tp_hit = sl_hit = False
    if setup.side == "LONG":
        tp_hit = bar_high >= setup.tp_price
        sl_hit = bar_low  <= setup.sl_price
    else:
        tp_hit = bar_low  <= setup.tp_price
        sl_hit = bar_high >= setup.sl_price

    if tp_hit and sl_hit:
        if same_bar_mode == "optimistic":
            return ("TP", setup.tp_price)
        return ("SL", setup.sl_price)
    if tp_hit:
        return ("TP", setup.tp_price)
    if sl_hit:
        return ("SL", setup.sl_price)
    return None


def update_trail_sl(
    setup: TradeSetup,
    current_trail_sl: float,
    trail_activated: bool,
    bar_high: float,
    bar_low: float,
    trail_cfg: dict,
) -> Tuple[float, bool]:
    """
    Update trailing SL level for one bar.

    Returns (new_trail_sl, trail_activated).

    Logic:
      - trail activates when price reaches ts_r * risk beyond entry
      - once active, SL moves to max(current_trail_sl, entry + lock_r*risk)
        for LONG, or min(...) for SHORT
      - trail_sl only moves in trade direction, never backwards
    """
    ts_r    = float(trail_cfg.get("ts_r", 1.5))
    lock_r  = trail_cfg.get("lock_r")          # None = breakeven
    risk    = abs(setup.entry_price - setup.sl_price)
    entry   = setup.entry_price

    if setup.side == "LONG":
        activate_price = entry + ts_r * risk
        if not trail_activated:
            if bar_high >= activate_price:
                trail_activated = True
                # Initial lock: move SL to entry + lock_r * risk (or BE)
                lock_level = entry + (float(lock_r) * risk if lock_r is not None else 0.0)
                current_trail_sl = max(current_trail_sl, lock_level)
        else:
            # Trail: SL = bar_high - ts_r * risk (never go below current)
            # Conservative: trail at ts_r R behind the current high
            new_sl = bar_high - ts_r * risk
            current_trail_sl = max(current_trail_sl, new_sl)
    else:  # SHORT
        activate_price = entry - ts_r * risk
        if not trail_activated:
            if bar_low <= activate_price:
                trail_activated = True
                lock_level = entry - (float(lock_r) * risk if lock_r is not None else 0.0)
                current_trail_sl = min(current_trail_sl, lock_level)
        else:
            new_sl = bar_low + ts_r * risk
            current_trail_sl = min(current_trail_sl, new_sl)

    return current_trail_sl, trail_activated


def try_exit_with_trail(
    setup: TradeSetup,
    current_trail_sl: float,
    bar_high: float,
    bar_low: float,
    same_bar_mode: str,
) -> Optional[Tuple[str, float]]:
    """
    Exit check when trailing stop is active.
    Uses current_trail_sl instead of setup.sl_price.
    TP check unchanged.
    Exit reason "TS" for trailing stop hit, "TP" for take profit.
    """
    tp_hit = ts_hit = False
    if setup.side == "LONG":
        tp_hit = bar_high >= setup.tp_price
        ts_hit = bar_low  <= current_trail_sl
    else:
        tp_hit = bar_low  <= setup.tp_price
        ts_hit = bar_high >= current_trail_sl

    if tp_hit and ts_hit:
        if same_bar_mode == "optimistic":
            return ("TP", setup.tp_price)
        return ("TS", current_trail_sl)
    if tp_hit:
        return ("TP", setup.tp_price)
    if ts_hit:
        return ("TS", current_trail_sl)
    return None


# ── Session filter ────────────────────────────────────────────────────────────

def in_session(ts: pd.Timestamp, session_cfg: Optional[dict]) -> bool:
    """Zwraca True jeśli godzina UTC timestampa jest w oknie sesji."""
    if session_cfg is None:
        return True
    start = session_cfg.get("start", 0)
    end   = session_cfg.get("end", 24)
    hour  = ts.hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end   # overnight wrap


# ── Portfolio-level simulator ─────────────────────────────────────────────────

class PortfolioSimulator:
    """
    Symuluje jednoczesne tradowanie na wielu symbolach z ograniczeniami portfolio.

    trail_cfg (optional): enables trailing stop simulation.
      {
        "ts_r":   float,   # R level that activates trailing (e.g. 1.5)
        "lock_r": float,   # R to lock in on activation (e.g. 0.5); None = BE
      }
      If None, standard fixed SL/TP logic is used.
    """

    def __init__(
        self,
        h1_data: Dict[str, pd.DataFrame],
        setups: Dict[str, List[TradeSetup]],
        sizing_cfg: dict,
        session_cfg: Dict[str, dict],
        same_bar_mode: str = "conservative",
        max_positions_total: Optional[int] = 3,
        max_positions_per_symbol: int = 1,
        initial_equity: float = 10_000.0,
        trail_cfg: Optional[dict] = None,
    ):
        self.h1 = h1_data
        self.setups = setups
        self.sizing_cfg = sizing_cfg
        self.session_cfg = session_cfg
        self.same_bar_mode = same_bar_mode
        self.max_total = max_positions_total
        self.max_per_sym = max_positions_per_symbol
        self.equity = initial_equity
        self.trail_cfg = trail_cfg   # None = disabled

    def run(self) -> List[ClosedTrade]:
        """Bar-by-bar simulation with optional trailing stop."""
        sym_arrays: Dict[str, dict] = {}
        for sym, df in self.h1.items():
            idx_list = list(df.index)
            ts_to_i = {ts: i for i, ts in enumerate(idx_list)}
            sym_arrays[sym] = {
                "ts":      idx_list,
                "open":    df["open"].values,
                "high":    df["high"].values,
                "low":     df["low"].values,
                "close":   df["close"].values,
                "ts_to_i": ts_to_i,
                "n":       len(df),
            }

        all_ts_set: set = set()
        for arr in sym_arrays.values():
            all_ts_set.update(arr["ts_to_i"].keys())
        all_ts = sorted(all_ts_set)

        pending: Dict[str, List[TradeSetup]] = {
            sym: sorted(setups, key=lambda s: s.bar_ts)
            for sym, setups in self.setups.items()
        }
        pending_ptr: Dict[str, int] = {sym: 0 for sym in pending}

        # Active: sym -> (setup, fill_bar_i, units, fill_ts, trail_sl, trail_activated)
        active: Dict[str, tuple] = {}
        waiting: Dict[str, list] = {sym: [] for sym in self.h1}
        closed: List[ClosedTrade] = []

        use_trail = self.trail_cfg is not None

        for ts in all_ts:
            # ── Exits ──────────────────────────────────────────────────────
            to_close = []
            for sym, pos in active.items():
                setup, fill_bar_i, units, fill_ts, trail_sl, trail_activated = pos
                arr = sym_arrays[sym]
                i = arr["ts_to_i"].get(ts)
                if i is None:
                    continue
                h = arr["high"][i]
                lo = arr["low"][i]
                o = arr["open"][i]
                c = arr["close"][i]

                if use_trail:
                    # Update trailing SL first
                    new_trail_sl, new_activated = update_trail_sl(
                        setup, trail_sl, trail_activated,
                        h, lo, self.trail_cfg,
                    )
                    active[sym] = (setup, fill_bar_i, units, fill_ts,
                                   new_trail_sl, new_activated)

                    if new_activated:
                        result = try_exit_with_trail(
                            setup, new_trail_sl, h, lo, self.same_bar_mode
                        )
                    else:
                        # Trail not yet active: use original SL
                        result = try_exit(setup, o, h, lo, c, self.same_bar_mode)
                        if result and result[0] == "SL":
                            result = ("SL", setup.sl_price)
                else:
                    result = try_exit(setup, o, h, lo, c, self.same_bar_mode)

                if result:
                    reason, exit_px = result
                    risk = abs(setup.entry_price - setup.sl_price)
                    # Compute realized R
                    if reason == "TP":
                        r_mult = setup.rr
                    elif reason in ("SL", "TS"):
                        if risk > 0:
                            if setup.side == "LONG":
                                r_mult = (exit_px - setup.entry_price) / risk
                            else:
                                r_mult = (setup.entry_price - exit_px) / risk
                        else:
                            r_mult = -1.0
                    else:
                        r_mult = 0.0

                    if setup.side == "LONG":
                        pnl = (exit_px - setup.entry_price) * units
                    else:
                        pnl = (setup.entry_price - exit_px) * units
                    self.equity += pnl

                    closed.append(ClosedTrade(
                        symbol=sym, side=setup.side,
                        entry_ts=fill_ts, entry_price=setup.entry_price,
                        exit_ts=ts, exit_price=exit_px, exit_reason=reason,
                        sl_price=setup.sl_price, tp_price=setup.tp_price,
                        bos_level=setup.bos_level, rr=setup.rr,
                        r_multiple=r_mult, bars_held=i - fill_bar_i,
                        atr_val=setup.atr_val, adx_val=setup.adx_val,
                        atr_pct_val=setup.atr_pct_val,
                        entry_bar_idx=fill_bar_i, exit_bar_idx=i,
                        units=units, pnl_price=pnl,
                    ))
                    to_close.append(sym)
            for sym in to_close:
                del active[sym]

            # ── Try fills ──────────────────────────────────────────────────
            for sym, wlist in waiting.items():
                if sym in active or not wlist:
                    continue
                arr = sym_arrays[sym]
                i = arr["ts_to_i"].get(ts)
                if i is None:
                    continue
                new_waiting = []
                o = arr["open"][i]; h = arr["high"][i]; lo = arr["low"][i]
                for (setup, units, created_ts) in wlist:
                    created_i = arr["ts_to_i"].get(created_ts, 0)
                    if i - created_i > setup.ttl_bars:
                        closed.append(ClosedTrade(
                            symbol=sym, side=setup.side,
                            entry_ts=setup.bar_ts, entry_price=setup.entry_price,
                            exit_ts=ts, exit_price=setup.entry_price,
                            exit_reason="TTL",
                            sl_price=setup.sl_price, tp_price=setup.tp_price,
                            bos_level=setup.bos_level, rr=setup.rr,
                            r_multiple=0.0, bars_held=0,
                            atr_val=setup.atr_val, adx_val=setup.adx_val,
                            atr_pct_val=setup.atr_pct_val,
                            entry_bar_idx=created_i, exit_bar_idx=i,
                            units=units, pnl_price=0.0,
                        ))
                        continue
                    if try_fill(setup, o, h, lo) and sym not in active:
                        n_open = len(active)
                        if (self.max_total is None or n_open < self.max_total) and \
                                len([s for s in active if s == sym]) < self.max_per_sym:
                            # Init trailing state: trail_sl = setup.sl_price, not yet active
                            active[sym] = (setup, i, units, ts,
                                           setup.sl_price, False)
                            continue
                    new_waiting.append((setup, units, created_ts))
                waiting[sym] = new_waiting

            # ── Emit new setups ─────────────────────────────────────────────
            for sym, setup_list in pending.items():
                ptr = pending_ptr[sym]
                while ptr < len(setup_list) and setup_list[ptr].bar_ts <= ts:
                    setup = setup_list[ptr]
                    sess = self.session_cfg.get(sym)
                    if in_session(setup.bar_ts, sess) and sym not in active:
                        units = calc_units(setup, self.sizing_cfg, self.equity)
                        if units > 0:
                            waiting[sym].append((setup, units, setup.bar_ts))
                    ptr += 1
                pending_ptr[sym] = ptr

        # Expire open at end of period
        for sym, pos in active.items():
            setup, fill_bar_i, units, fill_ts, trail_sl, trail_activated = pos
            arr = sym_arrays[sym]
            last_i = arr["n"] - 1
            exit_px = arr["close"][last_i]
            risk = abs(setup.entry_price - setup.sl_price)
            if risk > 0:
                if setup.side == "LONG":
                    r_mult = (exit_px - setup.entry_price) / risk
                else:
                    r_mult = (setup.entry_price - exit_px) / risk
            else:
                r_mult = 0.0
            if setup.side == "LONG":
                pnl = (exit_px - setup.entry_price) * units
            else:
                pnl = (setup.entry_price - exit_px) * units

            closed.append(ClosedTrade(
                symbol=sym, side=setup.side,
                entry_ts=fill_ts, entry_price=setup.entry_price,
                exit_ts=arr["ts"][last_i], exit_price=exit_px,
                exit_reason="TTL",
                sl_price=setup.sl_price, tp_price=setup.tp_price,
                bos_level=setup.bos_level, rr=setup.rr,
                r_multiple=r_mult, bars_held=last_i - fill_bar_i,
                atr_val=setup.atr_val, adx_val=setup.adx_val,
                atr_pct_val=setup.atr_pct_val,
                entry_bar_idx=fill_bar_i, exit_bar_idx=last_i,
                units=units, pnl_price=pnl,
            ))

        return sorted(closed, key=lambda t: t.exit_ts)

