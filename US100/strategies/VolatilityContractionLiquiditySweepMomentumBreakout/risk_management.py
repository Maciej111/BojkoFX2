"""
Risk management for VCLSMB.

Computes entry, stop-loss, and take-profit prices given:
  - the momentum confirmation bar
  - the state machine context (direction, sweep extreme, range)
  - the current ATR value

SL anchoring modes (cfg.sl_anchor):
  "range_extreme" — SL placed at the opposite range edge + buffer
  "sweep_wick"    — SL placed at the sweep wick extreme + buffer

All prices are on the BID side (consistent with how trend_following_v1 anchors SL).
Entry is computed as:
  LONG:  ask price of the breakout bar close   (open_ask of the next bar would be
         the actual fill — strategy.py uses open_ask of bar i+1)
  SHORT: bid price of the breakout bar close

Take-profit = entry ± risk_reward × risk_distance.
"""
import pandas as pd
from .config import VCLSMBConfig
from .state_machine import MachineContext


def compute_trade_levels(
    ctx: MachineContext,
    momentum_row: pd.Series,
    cfg: VCLSMBConfig,
) -> dict:
    """
    Return a dict with:
        direction, entry_price, planned_sl, planned_tp, risk_distance

    Parameters
    ----------
    ctx          : MachineContext (direction, range_high/low, sweep_low/high set)
    momentum_row : pd.Series — the momentum confirmation bar (with ATR)
    cfg          : VCLSMBConfig

    Returns dict or None if levels cannot be computed (NaN guards).
    """
    atr = momentum_row.get("atr", float("nan"))
    if pd.isna(atr) or atr <= 0:
        return None

    if ctx.direction == "LONG":
        # Entry: market order next bar open (ask side); use close_ask as proxy
        entry = momentum_row.get("close_ask", momentum_row["close_bid"])

        if cfg.sl_anchor == "sweep_wick":
            sl_base = ctx.sweep_low
        else:  # "range_extreme"
            sl_base = ctx.range_low

        if pd.isna(sl_base):
            return None

        sl = sl_base - cfg.sl_buffer_atr_mult * atr
        risk = entry - sl
        if risk <= 0:
            return None
        tp = entry + cfg.risk_reward * risk

    elif ctx.direction == "SHORT":
        # Entry: BID side
        entry = momentum_row["close_bid"]

        if cfg.sl_anchor == "sweep_wick":
            sl_base = ctx.sweep_high
        else:
            sl_base = ctx.range_high

        if pd.isna(sl_base):
            return None

        sl = sl_base + cfg.sl_buffer_atr_mult * atr
        risk = sl - entry
        if risk <= 0:
            return None
        tp = entry - cfg.risk_reward * risk

    else:
        return None

    return {
        "direction":     ctx.direction,
        "entry_price":   entry,
        "planned_sl":    sl,
        "planned_tp":    tp,
        "risk_distance": risk,
    }
