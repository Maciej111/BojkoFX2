"""
Trend Following Strategy v1
BOS + Pullback Entry with HTF Bias

Signal generation delegates to src.signals.trend_following_signals (shared
with the backtest pipeline) to guarantee identical behaviour in live and
research code.

Regime filters (ADX, ATR-percentile) are applied via the same
apply_regime_filters() function used by backtests/signals_bos_pullback.py.

SL is computed AT THE MOMENT OF FILL using compute_sl_at_fill() — this
is the canonical rule for both live and backtest (Task 5 / audit #3).
"""
import bisect
import pandas as pd
import numpy as np
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.structure.pivots import detect_pivots_confirmed, get_last_confirmed_pivot, get_pivot_sequence
from src.structure.bias import get_htf_bias_at_bar
from src.backtest.setup_tracker import SetupTracker

# ── Shared signal primitives ──────────────────────────────────────────────────
from src.signals.trend_following_signals import (
    precompute_pivots,
    check_bos_signal,
    apply_regime_filters,
    compute_entry_price,
    compute_sl_at_fill,
    compute_tp_price,
    normalize_ohlc,
    compute_adx_series,
    compute_atr_series,
    compute_atr_percentile_series,
)


def calculate_atr(df, period=14):
    """Calculate ATR (legacy wrapper kept for backward compat)."""
    high = df['high_bid']
    low = df['low_bid']
    close = df['close_bid']

    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    return atr


def check_bos(df, current_idx, pivot_highs, pivot_lows, ph_levels, pl_levels, require_close_break):
    """
    DEPRECATED — FIX BUG-06: This wrapper uses get_last_confirmed_pivot() which is based on
    detect_pivots_confirmed() (lookahead 1–2 bars). It is NOT used in the main backtest loop
    (which directly uses ltf_ph_pre[i] / ltf_pl_pre[i] from precompute_pivots).

    If you see this warning, someone is calling the legacy wrapper — switch to:
        from src.signals.trend_following_signals import check_bos_signal
        bos_side, bos_level = check_bos_signal(close, ph_pre[i], pl_pre[i])
    """
    import warnings
    warnings.warn(
        "check_bos() is a deprecated lookahead wrapper. "
        "Use check_bos_signal() with precompute_pivots() no-lookahead series instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    current_close = df['close_bid'].iloc[current_idx]

    # Resolve last pivot levels from the pre-computed series
    last_ph_time, last_ph_level = get_last_confirmed_pivot(
        df, pivot_highs, ph_levels, df.index[current_idx]
    )
    last_pl_time, last_pl_level = get_last_confirmed_pivot(
        df, pivot_lows, pl_levels, df.index[current_idx]
    )

    if not require_close_break:
        # Intrabar break — use high/low directly (not via shared function)
        if last_ph_level is not None and df['high_bid'].iloc[current_idx] > last_ph_level:
            return True, 'LONG', last_ph_level
        if last_pl_level is not None and df['low_bid'].iloc[current_idx] < last_pl_level:
            return True, 'SHORT', last_pl_level
        return False, None, None

    side, bos_level = check_bos_signal(current_close, last_ph_level, last_pl_level)
    if side is not None:
        return True, side, bos_level
    return False, None, None


def run_trend_backtest(symbol, ltf_df, htf_df, params_dict, initial_balance=10000):
    """
    Run trend following backtest with runtime parameters.

    Args:
        symbol:         Trading symbol
        ltf_df:         LTF (H1) bars DataFrame (columns: high_bid/low_bid/close_bid/...)
        htf_df:         HTF (H4) bars DataFrame  (same column convention)
        params_dict:    Strategy parameters dict — see src.config.strategy_params.StrategyParams
        initial_balance: Starting capital

    Regime filter keys (optional, default = no filtering):
        use_adx_filter          (bool)  – enable ADX gate
        adx_threshold           (float) – minimum ADX to accept signal (default 20.0)
        adx_timeframe           (str)   – "H4" | "D1" (default "H4")
        adx_period              (int)   – ADX period (default 14)
        use_atr_percentile_filter (bool) – enable ATR percentile gate
        atr_percentile_min      (float) – lower bound (default 10.0)
        atr_percentile_max      (float) – upper bound (default 80.0)
        atr_percentile_window   (int)   – rolling window (default 100)

    Returns:
        (trades_df, metrics_dict)
    """

    # ── Extract params ────────────────────────────────────────────────────────
    ltf_lookback        = params_dict.get('pivot_lookback_ltf', 3)
    htf_lookback        = params_dict.get('pivot_lookback_htf', 5)
    confirmation_bars   = params_dict.get('confirmation_bars', 1)
    require_close_break = params_dict.get('require_close_break', True)
    entry_offset_atr    = params_dict.get('entry_offset_atr_mult', 0.3)
    pullback_max_bars   = params_dict.get('pullback_max_bars', 20)
    sl_anchor           = params_dict.get('sl_anchor', 'last_pivot')
    sl_buffer_atr       = params_dict.get('sl_buffer_atr_mult', 0.1)
    rr                  = params_dict.get('risk_reward', 2.0)
    atr_period          = params_dict.get('atr_period', 14)

    # Regime filter params
    use_adx_filter            = bool(params_dict.get('use_adx_filter', False))
    adx_threshold             = float(params_dict.get('adx_threshold', 20.0))
    adx_period                = int(params_dict.get('adx_period', 14))
    use_atr_percentile_filter = bool(params_dict.get('use_atr_percentile_filter', False))
    atr_percentile_min        = float(params_dict.get('atr_percentile_min', 10.0))
    atr_percentile_max        = float(params_dict.get('atr_percentile_max', 80.0))
    atr_percentile_window     = int(params_dict.get('atr_percentile_window', 100))

    # ── Prepare DataFrames ────────────────────────────────────────────────────
    ltf_df = ltf_df.copy()
    if 'timestamp' in ltf_df.columns:
        ltf_df.set_index('timestamp', inplace=True)

    htf_df = htf_df.copy()
    if 'timestamp' in htf_df.columns:
        htf_df.set_index('timestamp', inplace=True)

    assert isinstance(ltf_df.index, pd.DatetimeIndex), \
        f"LTF index must be DatetimeIndex, got {type(ltf_df.index)}"
    assert isinstance(htf_df.index, pd.DatetimeIndex), \
        f"HTF index must be DatetimeIndex, got {type(htf_df.index)}"

    ltf_df = ltf_df.sort_index()
    htf_df = htf_df.sort_index()

    ltf_df['atr'] = calculate_atr(ltf_df, period=atr_period)

    # ── Regime filter pre-computation ─────────────────────────────────────────
    # ATR percentile on LTF (used for ATR percentile filter)
    if use_atr_percentile_filter:
        ltf_df['atr_pct'] = compute_atr_percentile_series(
            ltf_df['atr'], window=atr_percentile_window
        )
    else:
        ltf_df['atr_pct'] = 50.0   # neutral default, filter not applied

    # HTF ADX series (no-lookahead: forward-fill to H1 timestamps)
    htf_adx_at_h1: pd.Series = pd.Series(dtype=float)
    if use_adx_filter:
        htf_norm = normalize_ohlc(htf_df, price_type='bid')
        htf_adx_raw = compute_adx_series(htf_norm, period=adx_period)
        # No-lookahead reindex: for each H1 bar, use the last closed H4 bar's ADX
        # Forward-fill aligns HTF ADX to the H1 timeline without lookahead
        htf_adx_at_h1 = htf_adx_raw.reindex(
            ltf_df.index, method='ffill'
        )
        # Shift by 1 H4 period to ensure the most recent bar is closed
        # (conservative: use the ADX that was confirmed at the previous H4 close)
        htf_adx_shifted = htf_adx_raw.shift(1).reindex(
            ltf_df.index, method='ffill'
        )
        htf_adx_at_h1 = htf_adx_shifted.fillna(0.0)

    # Build a lookup of HTF ADX by H1 timestamp for O(log n) access
    _htf_adx_dict: dict = {}
    _htf_adx_sorted_keys: list = []
    if use_adx_filter and len(htf_adx_at_h1) > 0:
        _htf_adx_dict = htf_adx_at_h1.to_dict()
        _htf_adx_sorted_keys = sorted(_htf_adx_dict.keys())

    # ── Pivot detection ───────────────────────────────────────────────────────
    # Detect pivots on LTF (H1)
    # FIX BUG-04/BUG-11: confirmation_bars=ltf_lookback eliminates lookahead.
    # Raw pivot at bar p uses window [p-lb, p+lb]. With conf=lb it is confirmed
    # at bar p+lb exactly when the right wing is complete — zero future bars used.
    ltf_pivot_highs, ltf_pivot_lows, ltf_ph_levels, ltf_pl_levels = detect_pivots_confirmed(
        ltf_df, lookback=ltf_lookback, confirmation_bars=ltf_lookback
    )

    # LTF pivots as numpy arrays for use by shared check_bos_signal via precompute_pivots
    ltf_high_arr = ltf_df['high_bid'].values
    ltf_low_arr  = ltf_df['low_bid'].values
    ltf_ph_pre, _, ltf_pl_pre, _ = precompute_pivots(
        ltf_high_arr, ltf_low_arr, ltf_lookback
    )

    # Detect pivots on HTF (H4) for HTF bias calculation
    # FIX BUG-04: confirmation_bars=htf_lookback — same no-lookahead logic as above.
    htf_pivot_highs, htf_pivot_lows, htf_ph_levels, htf_pl_levels = detect_pivots_confirmed(
        htf_df, lookback=htf_lookback, confirmation_bars=htf_lookback
    )

    # ── Main backtest loop ────────────────────────────────────────────────────
    tracker      = SetupTracker()
    trades       = []
    current_position = None

    # Main loop through LTF bars
    for i in range(len(ltf_df)):
        current_time = ltf_df.index[i]
        current_bar = ltf_df.iloc[i]

        # Update position if exists
        if current_position:
            # Check SL/TP
            if current_position['direction'] == 'LONG':
                # LONG exits on BID side
                sl_hit = current_bar['low_bid'] <= current_position['sl']
                tp_hit = current_bar['high_bid'] >= current_position['tp']

                # WORST-CASE: if both hit, choose SL
                if sl_hit and tp_hit:
                    exit_price = current_position['sl']
                    exit_reason = 'SL_intrabar_conflict'
                    exit_pnl = (exit_price - current_position['entry']) * 100000
                elif sl_hit:
                    exit_price = current_position['sl']
                    exit_reason = 'SL'
                    exit_pnl = (exit_price - current_position['entry']) * 100000
                elif tp_hit:
                    exit_price = current_position['tp']
                    exit_reason = 'TP'
                    exit_pnl = (exit_price - current_position['entry']) * 100000
                else:
                    exit_price = None

                if exit_price is not None:
                    # Calculate extended fields
                    risk_dist = abs(current_position['entry'] - current_position['sl'])

                    # Get entry bar for feasibility check
                    entry_bar = ltf_df.loc[current_position['entry_time']]

                    # CLAMP exit price to feasible range (BID for LONG)
                    # This handles pivot-based SL/TP that may be outside bar range
                    original_exit_price = exit_price
                    if exit_price < current_bar['low_bid']:
                        exit_price = current_bar['low_bid']  # Clamp to low
                    elif exit_price > current_bar['high_bid']:
                        exit_price = current_bar['high_bid']  # Clamp to high

                    # FIX BUG-13: warn when clamping fires — hides model price violations
                    if exit_price != original_exit_price:
                        import logging as _logging
                        _logging.getLogger(__name__).warning(
                            "[CLAMP_LONG] exit_price clamped %.5f → %.5f at %s "
                            "(bar BID range [%.5f, %.5f])",
                            original_exit_price, exit_price, current_time,
                            current_bar['low_bid'], current_bar['high_bid'],
                        )
                    realized_dist = exit_price - current_position['entry']
                    R_calc = realized_dist / risk_dist if risk_dist > 0 else 0
                    exit_pnl = (exit_price - current_position['entry']) * 100000

                    # FEASIBILITY CHECKS
                    # LONG: entry on ASK, exit on BID
                    entry_feasible = entry_bar['low_ask'] <= current_position['entry'] <= entry_bar['high_ask']
                    exit_feasible = current_bar['low_bid'] <= exit_price <= current_bar['high_bid']

                    # After clamping, exit MUST be feasible
                    if not exit_feasible:
                        raise ValueError(
                            f"LONG exit STILL infeasible after clamping!\n"
                            f"  Exit time: {current_time}\n"
                            f"  Original exit: {original_exit_price:.5f}\n"
                            f"  Clamped exit: {exit_price:.5f}\n"
                            f"  Bar BID range: [{current_bar['low_bid']:.5f}, {current_bar['high_bid']:.5f}]"
                        )

                    trades.append({
                        'entry_time': pd.Timestamp(current_position['entry_time']).isoformat(),
                        'exit_time': pd.Timestamp(current_time).isoformat(),
                        'direction': 'LONG',
                        'entry_price': current_position['entry'],
                        'exit_price': exit_price,
                        'pnl': exit_pnl,
                        'exit_reason': exit_reason,
                        'risk_distance': risk_dist,
                        'realized_distance': realized_dist,
                        'planned_sl': current_position['sl'],
                        'planned_tp': current_position['tp'],
                        'R': R_calc,
                        # Feasibility columns
                        'entry_bar_time': pd.Timestamp(current_position['entry_time']).isoformat(),
                        'exit_bar_time': pd.Timestamp(current_time).isoformat(),
                        'entry_bar_low': entry_bar['low_ask'],
                        'entry_bar_high': entry_bar['high_ask'],
                        'exit_bar_low': current_bar['low_bid'],
                        'exit_bar_high': current_bar['high_bid'],
                        'entry_feasible': entry_feasible,
                        'exit_feasible': exit_feasible,
                        'violated_side': 'none' if (entry_feasible and exit_feasible) else ('ask' if not entry_feasible else 'bid')
                    })
                    current_position = None
                    continue

            else:  # SHORT
                # SHORT exits on ASK side (NOT BID!)
                sl_hit = current_bar['high_ask'] >= current_position['sl']
                tp_hit = current_bar['low_ask'] <= current_position['tp']

                # WORST-CASE: if both hit, choose SL
                if sl_hit and tp_hit:
                    exit_price = current_position['sl']
                    exit_reason = 'SL_intrabar_conflict'
                    exit_pnl = (current_position['entry'] - exit_price) * 100000
                elif sl_hit:
                    exit_price = current_position['sl']
                    exit_reason = 'SL'
                    exit_pnl = (current_position['entry'] - exit_price) * 100000
                elif tp_hit:
                    exit_price = current_position['tp']
                    exit_reason = 'TP'
                    exit_pnl = (current_position['entry'] - exit_price) * 100000
                else:
                    exit_price = None

                if exit_price is not None:
                    # Calculate extended fields
                    risk_dist = abs(current_position['sl'] - current_position['entry'])

                    # Get entry bar for feasibility check
                    entry_bar = ltf_df.loc[current_position['entry_time']]

                    # CLAMP exit price to feasible range (ASK for SHORT)
                    # This handles pivot-based SL/TP that may be outside bar range
                    original_exit_price = exit_price
                    if exit_price < current_bar['low_ask']:
                        exit_price = current_bar['low_ask']  # Clamp to low
                    elif exit_price > current_bar['high_ask']:
                        exit_price = current_bar['high_ask']  # Clamp to high

                    # FIX BUG-13: warn when clamping fires — hides model price violations
                    if exit_price != original_exit_price:
                        import logging as _logging
                        _logging.getLogger(__name__).warning(
                            "[CLAMP_SHORT] exit_price clamped %.5f → %.5f at %s "
                            "(bar ASK range [%.5f, %.5f])",
                            original_exit_price, exit_price, current_time,
                            current_bar['low_ask'], current_bar['high_ask'],
                        )

                    # Recalculate with clamped price
                    realized_dist = current_position['entry'] - exit_price
                    R_calc = realized_dist / risk_dist if risk_dist > 0 else 0
                    exit_pnl = (current_position['entry'] - exit_price) * 100000

                    # FEASIBILITY CHECKS
                    # SHORT: entry on BID, exit on ASK
                    entry_feasible = entry_bar['low_bid'] <= current_position['entry'] <= entry_bar['high_bid']
                    exit_feasible = current_bar['low_ask'] <= exit_price <= current_bar['high_ask']

                    # After clamping, exit MUST be feasible
                    if not exit_feasible:
                        raise ValueError(
                            f"SHORT exit STILL infeasible after clamping!\n"
                            f"  Exit time: {current_time}\n"
                            f"  Original exit: {original_exit_price:.5f}\n"
                            f"  Clamped exit: {exit_price:.5f}\n"
                            f"  Bar ASK range: [{current_bar['low_ask']:.5f}, {current_bar['high_ask']:.5f}]"
                        )

                    trades.append({
                        'entry_time': pd.Timestamp(current_position['entry_time']).isoformat(),
                        'exit_time': pd.Timestamp(current_time).isoformat(),
                        'direction': 'SHORT',
                        'entry_price': current_position['entry'],
                        'exit_price': exit_price,
                        'pnl': exit_pnl,
                        'exit_reason': exit_reason,
                        'risk_distance': risk_dist,
                        'realized_distance': realized_dist,
                        'planned_sl': current_position['sl'],
                        'planned_tp': current_position['tp'],
                        'R': R_calc,
                        # Feasibility columns
                        'entry_bar_time': pd.Timestamp(current_position['entry_time']).isoformat(),
                        'exit_bar_time': pd.Timestamp(current_time).isoformat(),
                        'entry_bar_low': entry_bar['low_bid'],
                        'entry_bar_high': entry_bar['high_bid'],
                        'exit_bar_low': current_bar['low_ask'],
                        'exit_bar_high': current_bar['high_ask'],
                        'entry_feasible': entry_feasible,
                        'exit_feasible': exit_feasible,
                        'violated_side': 'none' if (entry_feasible and exit_feasible) else ('bid' if not entry_feasible else 'ask')
                    })
                    current_position = None
                    continue

        # Check setup fill if active
        if tracker.has_active_setup() and not current_position:
            setup = tracker.get_active_setup()
            if tracker.check_fill(current_bar, current_time):
                bos_bar_idx = ltf_df.index.get_loc(setup.bos_time)
                setup.bars_to_fill = i - bos_bar_idx

                # ── SL at fill time (shared canonical rule) ───────────────────
                atr   = current_bar['atr']
                entry = setup.entry_price

                # FIX BUG-11: use no-lookahead precomputed pivot visible at fill bar i.
                # ltf_pl_pre[i] / ltf_ph_pre[i] from precompute_pivots are zero-lookahead
                # by construction (pivot at p confirmed at p+lookback, visible from p+lookback+1).
                # Replaces get_last_confirmed_pivot(detect_pivots_confirmed) which had
                # 1-2 bar lookahead from the raw pivot window i+lookback.
                if setup.direction == 'LONG':
                    sl_pivot_level = ltf_pl_pre[i]   # last confirmed PL visible at fill bar
                else:
                    sl_pivot_level = ltf_ph_pre[i]   # last confirmed PH visible at fill bar

                sl = compute_sl_at_fill(
                    side=setup.direction,
                    last_pivot_level=sl_pivot_level,
                    sl_buffer_mult=sl_buffer_atr,
                    atr_val=atr,
                    entry_price=entry,
                )
                tp = compute_tp_price(entry, sl, rr, setup.direction)

                current_position = {
                    'direction': setup.direction,
                    'entry': entry,
                    'sl': sl,
                    'tp': tp,
                    'entry_time': current_time
                }

                tracker.clear_active_setup()

        # Skip if position or setup exists
        if current_position or tracker.has_active_setup():
            continue

        # Get HTF bias
        htf_bias = get_htf_bias_at_bar(
            htf_df, current_time,
            htf_pivot_highs, htf_pivot_lows, htf_ph_levels, htf_pl_levels,
            pivot_count=4
        )

        if htf_bias == 'NEUTRAL':
            continue

        # Check for BOS using the shared signal function
        # Use precomputed no-lookahead pivot arrays for consistency with backtests
        last_ph = ltf_ph_pre[i]
        last_pl = ltf_pl_pre[i]

        bos_side, bos_level = check_bos_signal(
            current_bar['close_bid'], last_ph, last_pl
        )
        bos_detected = bos_side is not None
        bos_direction = bos_side

        if not bos_detected:
            continue

        # BOS must align with HTF bias
        if (bos_direction == 'LONG' and htf_bias != 'BULL') or \
           (bos_direction == 'SHORT' and htf_bias != 'BEAR'):
            continue

        # ── Regime filters (via shared apply_regime_filters) ─────────────────
        # Resolve current ADX value on the filter timeframe (H4)
        adx_val_now = 0.0
        if use_adx_filter and _htf_adx_dict:
            adx_val_now = _htf_adx_dict.get(current_time, 0.0)
            if adx_val_now == 0.0 and _htf_adx_sorted_keys:
                pos = bisect.bisect_right(_htf_adx_sorted_keys, current_time) - 1
                if pos >= 0:
                    adx_val_now = _htf_adx_dict[_htf_adx_sorted_keys[pos]]

        atr_pct_now = float(ltf_df['atr_pct'].iloc[i]) if 'atr_pct' in ltf_df.columns else 50.0
        if np.isnan(atr_pct_now):
            atr_pct_now = 50.0

        if not apply_regime_filters(
            adx_val=adx_val_now,
            atr_pct_val=atr_pct_now,
            use_adx_filter=use_adx_filter,
            adx_threshold=adx_threshold,
            use_atr_percentile_filter=use_atr_percentile_filter,
            atr_percentile_min=atr_percentile_min,
            atr_percentile_max=atr_percentile_max,
        ):
            continue

        # ── Create pullback setup ─────────────────────────────────────────────
        atr = current_bar['atr']

        # Entry price via shared function
        entry_price = compute_entry_price(bos_level, bos_direction, entry_offset_atr, atr)

        expiry_idx = min(i + pullback_max_bars, len(ltf_df) - 1)
        expiry_time = ltf_df.index[expiry_idx]

        tracker.create_setup(
            direction=bos_direction,
            bos_level=bos_level,
            bos_time=current_time,
            entry_price=entry_price,
            expiry_time=expiry_time,
            expiry_bar_count=pullback_max_bars,
            htf_bias=htf_bias,
            ltf_pivot_type='pivot_high' if bos_direction == 'LONG' else 'pivot_low'
        )

    # Get setup stats
    setup_stats = tracker.get_stats()

    # Create trades DataFrame
    trades_df = pd.DataFrame(trades)

    # Calculate metrics
    if len(trades_df) == 0:
        metrics = {
            'trades_count': 0,
            'expectancy_R': 0.0,
            'win_rate': 0.0,
            'profit_factor': 0.0,
            'max_dd_pct': 0.0,
            'max_losing_streak': 0,
            'missed_rate': setup_stats.get('missed_rate', 0.0),
            'avg_bars_to_fill': setup_stats.get('avg_bars_to_fill', 0.0),
            'total_setups': setup_stats.get('total_setups', 0)
        }
    else:
        # R column already calculated correctly in trades
        # No need to recalculate

        wins = trades_df[trades_df['pnl'] > 0]
        losses = trades_df[trades_df['pnl'] <= 0]

        win_rate = len(wins) / len(trades_df) * 100 if len(trades_df) > 0 else 0
        expectancy_R = trades_df['R'].mean()

        total_wins = wins['pnl'].sum() if len(wins) > 0 else 0
        total_losses = abs(losses['pnl'].sum()) if len(losses) > 0 else 1
        profit_factor = total_wins / total_losses if total_losses > 0 else 0

        # FIX BUG-12: DD computed from R-scaled compound equity curve.
        # Old curve used pnl built on hardcoded 100_000 units — wrong for risk_first sizing
        # where each trade risks current_equity × risk_fraction (compounding).
        # New: equity[t+1] = equity[t] × (1 + R[t] × risk_fraction), matching live model.
        _risk_fraction = float(params_dict.get('risk_pct', 0.0025))
        equity_curve = [initial_balance]
        _eq = float(initial_balance)
        for r_val in trades_df['R']:
            _eq = _eq * (1.0 + r_val * _risk_fraction)
            equity_curve.append(_eq)

        peak = equity_curve[0]
        max_dd = 0
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak * 100
            if dd > max_dd:
                max_dd = dd

        # Max losing streak
        streak = 0
        max_streak = 0
        for pnl in trades_df['pnl']:
            if pnl <= 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0

        metrics = {
            'trades_count': len(trades_df),
            'expectancy_R': expectancy_R,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'max_dd_pct': max_dd,
            'max_losing_streak': max_streak,
            'missed_rate': setup_stats.get('missed_rate', 0.0),
            'avg_bars_to_fill': setup_stats.get('avg_bars_to_fill', 0.0),
            'total_setups': setup_stats.get('total_setups', 0)
        }

    return trades_df, metrics


def run_trend_following_backtest(ltf_df, htf_df, config, initial_balance=10000):
    """
    Main backtest loop for trend following strategy.
    Wrapper for backward compatibility - uses config dict.
    """

    # Build params dict from config
    params_dict = {
        'pivot_lookback_ltf': config['trend_strategy'].get('pivot_lookback_ltf', 3),
        'pivot_lookback_htf': config['trend_strategy'].get('pivot_lookback_htf', 5),
        'confirmation_bars': config['trend_strategy'].get('confirmation_bars', 1),
        'require_close_break': config['trend_strategy'].get('require_close_break', True),
        'entry_offset_atr_mult': config['trend_strategy'].get('entry_offset_atr_mult', 0.3),
        'pullback_max_bars': config['trend_strategy'].get('pullback_max_bars', 20),
        'sl_anchor': config['trend_strategy'].get('sl_anchor', 'last_pivot'),
        'sl_buffer_atr_mult': config['trend_strategy'].get('sl_buffer_atr_mult', 0.5),
        'risk_reward': config['trend_strategy'].get('risk_reward', 2.0)
    }

    print(f"Running Trend Following Backtest...")
    print(f"  LTF bars: {len(ltf_df)}")
    print(f"  HTF bars: {len(htf_df)}")
    print("Detecting LTF pivots...")
    print("Detecting HTF pivots...")
    print("Running backtest loop...")

    # Call the new function
    trades_df, metrics = run_trend_backtest('EURUSD', ltf_df, htf_df, params_dict, initial_balance)

    print(f"Backtest complete. Trades: {len(trades_df)}")

    # Build setup_stats dict for backward compatibility
    setup_stats = {
        'total_setups': metrics.get('total_setups', 0),
        'filled_setups': metrics.get('trades_count', 0),
        'missed_setups': int(metrics.get('total_setups', 0) * metrics.get('missed_rate', 0.0)),
        'missed_rate': metrics.get('missed_rate', 0.0),
        'avg_bars_to_fill': metrics.get('avg_bars_to_fill', 0.0)
    }

    return trades_df, setup_stats


