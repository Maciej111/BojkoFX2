"""
VCLSMB backtest runner.

Entry point:  run_vclsmb_backtest(symbol, ltf_df, cfg) → (trades_df, metrics)

Reuses from existing project:
  - scripts.run_backtest_idx.filter_by_date  (date slicing)
  - src.backtest.metrics.compute_metrics     (standard metrics dict)
  - shared.bojkofx_shared.indicators.atr     (via feature_pipeline)
  - shared.bojkofx_shared.indicators.ema     (via feature_pipeline)

Trade simulation:
  - Entry: market open of bar i+1 after MOMENTUM_CONFIRMED on bar i
    LONG  → fill at open_ask[i+1]
    SHORT → fill at open_bid[i+1]
  - Exit checked bar-by-bar:
    SL touched if low_bid (for LONG) or high_bid (for SHORT) crosses SL
    TP touched if high_bid (for LONG) or low_bid (for SHORT) crosses TP
    Same-bar SL/TP: SL wins (conservative)
  - Session filter: entry bar_time.hour must be in [start_hour, end_hour)

Returns:
  trades_df — pd.DataFrame (same schema as trend_following_v1 where applicable)
  metrics   — dict (same keys as run_trend_backtest for comparability)
"""
import sys
from pathlib import Path
from typing import Optional, Tuple
import pandas as pd
import numpy as np

_ROOT = Path(__file__).resolve().parents[3]   # US100/
_SHARED = _ROOT.parent / "shared"
for _p in [str(_ROOT), str(_SHARED)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.backtest.metrics import compute_metrics

from .config import VCLSMBConfig, default_config
from .feature_pipeline import build_features
from .state_machine import MachineContext, State, advance, _reset
from .risk_management import compute_trade_levels
from .signals import Signal


# ── Session filter helper ──────────────────────────────────────────────────────

def _in_session(ts: pd.Timestamp, cfg: VCLSMBConfig) -> bool:
    if not cfg.use_session_filter:
        return True
    h = ts.hour
    start = cfg.session_start_hour_utc
    end   = cfg.session_end_hour_utc
    # Handle overnight windows that cross midnight (e.g. 21 → 02)
    if start < end:
        return start <= h < end
    else:  # wraps midnight
        return h >= start or h < end


# ── Trade simulation helpers ──────────────────────────────────────────────────

def _check_exit(direction: str, row: pd.Series, sl: float, tp: float) -> Optional[str]:
    """Return 'TP', 'SL', or None based on the bar touching levels."""
    if direction == "LONG":
        sl_touched = row["low_bid"]  <= sl
        tp_touched = row["high_bid"] >= tp
    else:  # SHORT
        sl_touched = row["high_bid"] >= sl
        tp_touched = row["low_bid"]  <= tp

    if sl_touched and tp_touched:
        return "SL"   # conservative
    if sl_touched:
        return "SL"
    if tp_touched:
        return "TP"
    return None


def _exit_price(direction: str, reason: str, row: pd.Series, sl: float, tp: float) -> float:
    if reason == "SL":
        return sl
    return tp


# ── Main backtest function ────────────────────────────────────────────────────

def run_vclsmb_backtest(
    symbol: str,
    ltf_df: pd.DataFrame,
    cfg: Optional[VCLSMBConfig] = None,
) -> Tuple[pd.DataFrame, dict]:
    """
    Run VCLSMB strategy backtest on *ltf_df*.

    Parameters
    ----------
    symbol  : str          instrument name (informational)
    ltf_df  : pd.DataFrame LTF bars with bid/ask OHLC, UTC index
    cfg     : VCLSMBConfig (optional; uses default_config() if None)

    Returns
    -------
    (trades_df, metrics)
      trades_df — DataFrame, one row per closed trade
      metrics   — dict compatible with run_trend_backtest metrics
    """
    if cfg is None:
        cfg = default_config()

    # ── Build features (ATR, range, body, etc.) ───────────────────────────────
    df = build_features(ltf_df, cfg)
    bars = df.reset_index()           # integer-indexed for easy i+1 look-ahead
    _ts_col = bars.columns[0]         # former DatetimeIndex column (name varies: 'index', 'datetime', etc.)

    trades = []
    ctx = MachineContext()

    # Active trade tracking
    active: Optional[dict] = None

    n = len(bars)
    for i in range(n):
        row = bars.iloc[i]
        ts  = row[_ts_col]             # timestamp

        # ── Manage open position ──────────────────────────────────────────────
        if active is not None:            # ── Trailing stop update ──────────────────────────────────────────
            if cfg.use_trailing_stop:
                atr_now = row.get("atr", 0.0)
                if atr_now > 0:
                    if active["direction"] == "LONG":
                        # Track best price (highest high seen)
                        active["best_price"] = max(active["best_price"], row["high_bid"])
                        # Break-even: move SL to entry once profit >= breakeven_atr
                        profit_pts = active["best_price"] - active["entry_price"]
                        if profit_pts >= cfg.breakeven_atr_mult * atr_now:
                            active["planned_sl"] = max(active["planned_sl"],
                                                        active["entry_price"])
                        # Trail from best price
                        trail_sl = active["best_price"] - cfg.trailing_atr_multiplier * atr_now
                        if trail_sl > active["planned_sl"]:
                            active["planned_sl"] = trail_sl
                    else:  # SHORT
                        active["best_price"] = min(active["best_price"], row["low_bid"])
                        profit_pts = active["entry_price"] - active["best_price"]
                        if profit_pts >= cfg.breakeven_atr_mult * atr_now:
                            active["planned_sl"] = min(active["planned_sl"],
                                                        active["entry_price"])
                        trail_sl = active["best_price"] + cfg.trailing_atr_multiplier * atr_now
                        if trail_sl < active["planned_sl"]:
                            active["planned_sl"] = trail_sl

            reason = _check_exit(active["direction"], row, active["planned_sl"], active["planned_tp"])
            if reason is not None:
                exit_px = _exit_price(active["direction"], reason, row,
                                      active["planned_sl"], active["planned_tp"])
                active["exit_time"]  = str(ts)
                active["exit_price"] = exit_px
                active["exit_reason"] = reason

                risk = active["risk_distance"]
                if active["direction"] == "LONG":
                    pnl_r = (exit_px - active["entry_price"]) / risk if risk > 0 else 0.0
                else:
                    pnl_r = (active["entry_price"] - exit_px) / risk if risk > 0 else 0.0

                active["R"]   = pnl_r
                active["pnl"] = pnl_r  # raw R — no dollar multiplier needed

                trades.append(active)
                active = None

                # Transition: go to TREND_EXPANSION if pullback entries are still allowed,
                # otherwise reset to IDLE as before.
                if (
                    cfg.enable_pullback_entry
                    and not pd.isna(ctx.breakout_level)
                    and ctx.entries_taken < cfg.max_entries_per_setup
                ):
                    ctx.state = State.TREND_EXPANSION
                    ctx.bars_in_state = 0
                else:
                    _reset(ctx)
                    ctx.state = State.IDLE
            # Don't advance state machine while in position
            continue

        # ── Advance state machine ─────────────────────────────────────────────
        # Volatility regime gate — if regime is suppressed, reset any in-progress
        # setup and skip this bar.  Active positions are NOT affected (managed above).
        if not row.get("vol_regime_ok", True):
            if ctx.state != State.IDLE:
                _reset(ctx)
            continue

        prev_state = ctx.state
        new_state  = advance(ctx, row, i, cfg)

        # ── Entry trigger: MOMENTUM_CONFIRMED on bar i → enter on bar i+1 ─────
        if new_state == State.MOMENTUM_CONFIRMED and prev_state != State.MOMENTUM_CONFIRMED:
            # Need next bar for the fill
            if i + 1 >= n:
                _reset(ctx)
                continue

            # Session filter on the signal bar
            if not _in_session(ts, cfg):
                _reset(ctx)
                ctx.state = State.IDLE
                continue

            levels = compute_trade_levels(ctx, row, cfg)
            if levels is None:
                _reset(ctx)
                ctx.state = State.IDLE
                continue

            # Trend filter: LONG only above EMA, SHORT only below EMA
            if cfg.enable_trend_filter:
                trend_ema = row.get("trend_ema", float("nan"))
                if not pd.isna(trend_ema):
                    close_price = row.get("close_bid", float("nan"))
                    if levels["direction"] == "LONG" and close_price < trend_ema:
                        _reset(ctx)
                        ctx.state = State.IDLE
                        continue
                    if levels["direction"] == "SHORT" and close_price > trend_ema:
                        _reset(ctx)
                        ctx.state = State.IDLE
                        continue

            # Structural liquidity location filter (PDH / PDL)
            # Allow the trade only when the compression range boundary
            # is within liquidity_level_atr_mult × ATR of the relevant daily level:
            #   LONG  → range_low must be within threshold of PDL
            #   SHORT → range_high must be within threshold of PDH
            if cfg.enable_liquidity_location_filter:
                pdh = row.get("previous_day_high", float("nan"))
                pdl = row.get("previous_day_low",  float("nan"))
                atr_now   = row.get("atr", 0.0)
                threshold = atr_now * cfg.liquidity_level_atr_mult
                if not (pd.isna(pdh) or pd.isna(pdl) or threshold <= 0):
                    if levels["direction"] == "SHORT":
                        near_level = abs(ctx.range_high - pdh) <= threshold
                    else:  # LONG
                        near_level = abs(ctx.range_low - pdl) <= threshold
                    if not near_level:
                        _reset(ctx)
                        ctx.state = State.IDLE
                        continue

            next_row = bars.iloc[i + 1]
            next_ts  = next_row[_ts_col]

            if levels["direction"] == "LONG":
                fill_px = next_row.get("open_ask", next_row["open_bid"])
            else:
                fill_px = next_row["open_bid"]

            # Re-compute SL/TP relative to actual fill
            risk = abs(fill_px - levels["planned_sl"])
            if risk <= 0:
                _reset(ctx)
                ctx.state = State.IDLE
                continue

            if levels["direction"] == "LONG":
                sl = fill_px - risk
                tp = fill_px + cfg.risk_reward * risk
            else:
                sl = fill_px + risk
                tp = fill_px - cfg.risk_reward * risk

            entry_type = "pullback" if ctx.entries_taken > 0 else "first"
            ctx.entries_taken += 1

            active = {
                "entry_time":    str(next_ts),
                "exit_time":     None,
                "direction":     levels["direction"],
                "setup_type":    "VCLSMB",
                "entry_price":   fill_px,
                "exit_price":    None,
                "pnl":           0.0,
                "exit_reason":   None,
                "risk_distance": risk,
                "planned_sl":    sl,
                "planned_tp":    tp,
                "R":             0.0,
                "signal_bar_time": str(ts),
                "range_high":   ctx.range_high,
                "range_low":    ctx.range_low,
                "sweep_bar_idx": ctx.sweep_bar_idx,
                "compression_atr": row.get("atr", float("nan")),
                "partial_tp_hit": False,
                "partial_exit_time": None,
                "partial_exit_price": None,
                "best_price":   fill_px,   # for trailing stop tracking
                "entry_type":   entry_type,
            }
            ctx.state = State.IN_POSITION
            ctx.bars_in_state = 0

    # ── Force-close any open position at end of data ──────────────────────────
    if active is not None:
        last_row = bars.iloc[-1]
        last_ts  = last_row[_ts_col]
        exit_px  = last_row["close_bid"]
        risk = active["risk_distance"]
        if active["direction"] == "LONG":
            pnl_r = (exit_px - active["entry_price"]) / risk if risk > 0 else 0.0
        else:
            pnl_r = (active["entry_price"] - exit_px) / risk if risk > 0 else 0.0
        active["exit_time"]   = str(last_ts)
        active["exit_price"]  = exit_px
        active["exit_reason"] = "EOD"
        active["R"]           = pnl_r
        active["pnl"]         = pnl_r
        trades.append(active)

    # ── Build trades DataFrame ────────────────────────────────────────────────
    if not trades:
        trades_df = pd.DataFrame(columns=[
            "entry_time", "exit_time", "direction", "setup_type",
            "entry_price", "exit_price", "pnl", "exit_reason",
            "risk_distance", "planned_sl", "planned_tp", "R",
        ])
    else:
        trades_df = pd.DataFrame(trades)

    # ── Compute metrics (reuse existing metrics module) ───────────────────────
    if len(trades_df) == 0:
        metrics = {
            "trades_count": 0, "expectancy_R": 0.0, "win_rate": 0.0,
            "profit_factor": 0.0, "max_dd_pct": 0.0, "max_losing_streak": 0,
            "missed_rate": 0.0, "avg_bars_to_fill": 0.0, "total_setups": 0,
            "first_entries": 0, "pullback_entries": 0,
        }
    else:
        m = compute_metrics(trades_df, initial_balance=10000)
        pb_count = int((trades_df.get("entry_type", pd.Series(dtype=str)) == "pullback").sum())
        metrics = {
            "trades_count":      m.get("trades_count", len(trades_df)),
            "expectancy_R":      m.get("expectancy_R", trades_df["R"].mean()),
            "win_rate":          m.get("win_rate", 0.0),
            "profit_factor":     m.get("profit_factor", 0.0),
            "max_dd_pct":        m.get("max_dd_percent", 0.0),
            "max_losing_streak": m.get("max_losing_streak", 0),
            "missed_rate":       0.0,
            "avg_bars_to_fill":  0.0,
            "total_setups":      len(trades_df),
            "first_entries":     len(trades_df) - pb_count,
            "pullback_entries":  pb_count,
        }

    return trades_df, metrics
