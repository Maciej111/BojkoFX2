"""
State machine for VCLSMB.

States:
  IDLE                — waiting for compression
  COMPRESSION         — ATR contraction detected; building range
  SWEEP_DETECTED      — liquidity sweep fired; waiting for momentum
  MOMENTUM_CONFIRMED  — momentum breakout bar confirmed; signal ready
  IN_POSITION         — trade is open
  TREND_EXPANSION     — watching for pullback to breakout level (continuation entry)

Transitions (per bar):
  IDLE            → COMPRESSION        : is_compression()
  COMPRESSION     → SWEEP_DETECTED     : is_liquidity_sweep_bull/bear()
  COMPRESSION     → IDLE               : timeout or compression lost
  SWEEP_DETECTED  → MOMENTUM_CONFIRMED : is_momentum_breakout_bull/bear()
  SWEEP_DETECTED  → IDLE               : timeout or opposing sweep
  MOMENTUM_CONFIRMED → IN_POSITION     : entry bar processed (next bar)  [strategy.py]
  IN_POSITION     → TREND_EXPANSION    : trade closed + pullback enabled  [strategy.py]
  IN_POSITION     → IDLE               : trade closed, pullback disabled   [strategy.py]
  TREND_EXPANSION → MOMENTUM_CONFIRMED : pullback touches breakout zone
  TREND_EXPANSION → IDLE               : timeout / max_entries reached / new compression
"""
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

from .config import VCLSMBConfig
from .detectors import (
    is_compression,
    is_liquidity_sweep_bull, is_liquidity_sweep_bear,
    is_momentum_breakout_bull, is_momentum_breakout_bear,
)


class State(Enum):
    IDLE               = auto()
    COMPRESSION        = auto()
    SWEEP_DETECTED     = auto()
    MOMENTUM_CONFIRMED = auto()
    IN_POSITION        = auto()
    TREND_EXPANSION    = auto()  # continuation: waiting for pullback to breakout level


@dataclass
class MachineContext:
    """Mutable state carried across bars."""
    state: State = State.IDLE
    bars_in_state: int = 0
    direction: Optional[str] = None        # "LONG" | "SHORT" set at SWEEP_DETECTED
    range_high: float = float("nan")       # snapshot at COMPRESSION entry
    range_low:  float = float("nan")       # snapshot at COMPRESSION entry
    sweep_bar_idx: Optional[int] = None    # LTF index of sweep bar
    sweep_low:  float = float("nan")       # wick extreme of bull sweep
    sweep_high: float = float("nan")       # wick extreme of bear sweep
    momentum_bar_idx: Optional[int] = None # LTF index when momentum confirmed
    # Pullback continuation tracking
    breakout_level: float = float("nan")   # range_high (LONG) or range_low (SHORT) at BOS
    entries_taken: int = 0                 # number of entries opened for this setup


def _reset(ctx: MachineContext) -> None:
    ctx.state            = State.IDLE
    ctx.bars_in_state    = 0
    ctx.direction        = None
    ctx.range_high       = float("nan")
    ctx.range_low        = float("nan")
    ctx.sweep_bar_idx    = None
    ctx.sweep_low        = float("nan")
    ctx.sweep_high       = float("nan")
    ctx.momentum_bar_idx = None
    ctx.breakout_level   = float("nan")
    ctx.entries_taken    = 0


def advance(ctx: MachineContext, row: pd.Series, bar_idx: int,
            cfg: VCLSMBConfig) -> State:
    """
    Advance the state machine by one bar.

    Parameters
    ----------
    ctx      : MachineContext  (mutated in place)
    row      : pd.Series       single bar with feature columns
    bar_idx  : int             0-based integer position in the LTF DataFrame
    cfg      : VCLSMBConfig

    Returns
    -------
    State  — the new state after processing this bar
    """
    ctx.bars_in_state += 1

    # ── IN_POSITION: managed externally by strategy.py, skip transitions ─────
    if ctx.state == State.IN_POSITION:
        return ctx.state

    # ── MOMENTUM_CONFIRMED → IN_POSITION: entry happens on the *next* bar ────
    # strategy.py sets IN_POSITION after placing the trade; here we just return.
    if ctx.state == State.MOMENTUM_CONFIRMED:
        # Caller is responsible for transitioning to IN_POSITION
        return ctx.state

    # ── IDLE → COMPRESSION ───────────────────────────────────────────────────
    if ctx.state == State.IDLE:
        if is_compression(row, cfg):
            ctx.state = State.COMPRESSION
            ctx.bars_in_state = 0
            # Snapshot range at compression start
            ctx.range_high = row.get("range_high", float("nan"))
            ctx.range_low  = row.get("range_low",  float("nan"))
        return ctx.state

    # ── COMPRESSION ──────────────────────────────────────────────────────────
    if ctx.state == State.COMPRESSION:
        # Timeout
        if ctx.bars_in_state > cfg.max_bars_in_state:
            _reset(ctx)
            return ctx.state

        # Update range (keep tightest) — no-lookahead because range_high/low use shift(1)
        rh = row.get("range_high", float("nan"))
        rl = row.get("range_low",  float("nan"))
        if not pd.isna(rh):
            ctx.range_high = rh
        if not pd.isna(rl):
            ctx.range_low = rl

        # Check for sweep FIRST — sweep bar is by definition an expansion bar
        # (higher ATR), so we must check before the "compression lost" guard.
        # Defensive guard: only detect sweep if range is fully defined (not NaN).
        range_defined = (not pd.isna(ctx.range_high)) and (not pd.isna(ctx.range_low))
        if range_defined and is_liquidity_sweep_bull(row, cfg):
            ctx.state         = State.SWEEP_DETECTED
            ctx.direction     = "LONG"
            ctx.sweep_bar_idx = bar_idx
            ctx.sweep_low     = row["low_bid"]
            ctx.bars_in_state = 0
        elif range_defined and is_liquidity_sweep_bear(row, cfg):
            ctx.state         = State.SWEEP_DETECTED
            ctx.direction     = "SHORT"
            ctx.sweep_bar_idx = bar_idx
            ctx.sweep_high    = row["high_bid"]
            ctx.bars_in_state = 0
        elif not is_compression(row, cfg):
            # Compression lost and no sweep → back to IDLE
            _reset(ctx)

        return ctx.state

    # ── SWEEP_DETECTED ────────────────────────────────────────────────────────
    if ctx.state == State.SWEEP_DETECTED:
        if ctx.bars_in_state > cfg.max_bars_in_state:
            _reset(ctx)
            return ctx.state

        if ctx.direction == "LONG":
            # Invalidated by bearish sweep
            if is_liquidity_sweep_bear(row, cfg):
                _reset(ctx)
                return ctx.state
            if is_momentum_breakout_bull(row, cfg):
                ctx.state            = State.MOMENTUM_CONFIRMED
                ctx.momentum_bar_idx = bar_idx
                ctx.bars_in_state    = 0
                ctx.breakout_level   = ctx.range_high  # BOS level for LONG

        elif ctx.direction == "SHORT":
            # Invalidated by bullish sweep
            if is_liquidity_sweep_bull(row, cfg):
                _reset(ctx)
                return ctx.state
            if is_momentum_breakout_bear(row, cfg):
                ctx.state            = State.MOMENTUM_CONFIRMED
                ctx.momentum_bar_idx = bar_idx
                ctx.bars_in_state    = 0
                ctx.breakout_level   = ctx.range_low   # BOS level for SHORT

        return ctx.state

    # ── TREND_EXPANSION: watching for pullback to breakout level ──────────────
    if ctx.state == State.TREND_EXPANSION:
        # Timeout
        if ctx.bars_in_state > cfg.max_bars_in_state:
            _reset(ctx)
            return ctx.state

        # Max entries reached
        if ctx.entries_taken >= cfg.max_entries_per_setup:
            _reset(ctx)
            return ctx.state

        # New compression starting → let a fresh setup begin from IDLE
        if is_compression(row, cfg):
            _reset(ctx)
            return ctx.state

        # Pullback detection
        atr = row.get("atr", float("nan"))
        if not pd.isna(atr) and atr > 0 and not pd.isna(ctx.breakout_level):
            threshold = cfg.pullback_atr_mult * atr
            if ctx.direction == "LONG":
                if row["low_bid"] <= ctx.breakout_level + threshold:
                    ctx.state            = State.MOMENTUM_CONFIRMED
                    ctx.momentum_bar_idx = bar_idx
                    ctx.bars_in_state    = 0
            elif ctx.direction == "SHORT":
                if row["high_bid"] >= ctx.breakout_level - threshold:
                    ctx.state            = State.MOMENTUM_CONFIRMED
                    ctx.momentum_bar_idx = bar_idx
                    ctx.bars_in_state    = 0

        return ctx.state

    return ctx.state
