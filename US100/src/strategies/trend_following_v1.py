"""
Trend Following Strategy v1
BOS + Pullback Entry with HTF Bias - SIMPLIFIED VERSION
"""
import pandas as pd
import numpy as np
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.structure.pivots import detect_pivots_confirmed, get_last_confirmed_pivot, get_pivot_sequence
from src.structure.bias import get_htf_bias_at_bar
from src.structure.flags import detect_flag_contraction
from src.backtest.setup_tracker import SetupTracker


def calculate_atr(df, period=14):
    """Calculate ATR."""
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
    """Check if BOS occurred at current bar."""

    current_close = df['close_bid'].iloc[current_idx]

    # Bull BOS: close above last pivot high
    last_ph_time, last_ph_level = get_last_confirmed_pivot(df, pivot_highs, ph_levels, df.index[current_idx])

    if last_ph_level is not None:
        if require_close_break:
            if current_close > last_ph_level:
                return True, 'LONG', last_ph_level
        else:
            if df['high_bid'].iloc[current_idx] > last_ph_level:
                return True, 'LONG', last_ph_level

    # Bear BOS: close below last pivot low
    last_pl_time, last_pl_level = get_last_confirmed_pivot(df, pivot_lows, pl_levels, df.index[current_idx])

    if last_pl_level is not None:
        if require_close_break:
            if current_close < last_pl_level:
                return True, 'SHORT', last_pl_level
        else:
            if df['low_bid'].iloc[current_idx] < last_pl_level:
                return True, 'SHORT', last_pl_level

    return False, None, None


def is_allowed_session(ts, start_hour: int, end_hour: int) -> bool:
    """Return True if the bar timestamp falls within the UTC session window."""
    hour = ts.hour
    return start_hour <= hour <= end_hour


def run_trend_backtest(symbol, ltf_df, htf_df, params_dict, initial_balance=10000):
    """
    Run trend following backtest with runtime parameters.

    Args:
        symbol: Trading symbol
        ltf_df: LTF (H1) bars DataFrame
        htf_df: HTF (H4) bars DataFrame
        params_dict: Dictionary with strategy parameters
        initial_balance: Starting capital

    Returns:
        (trades_df, metrics_dict) - trades DataFrame and metrics dictionary
    """

    # Extract params with defaults
    ltf_lookback = params_dict.get('pivot_lookback_ltf', 3)
    htf_lookback = params_dict.get('pivot_lookback_htf', 5)
    confirmation_bars = params_dict.get('confirmation_bars', 1)
    require_close_break = params_dict.get('require_close_break', True)
    entry_offset_atr = params_dict.get('entry_offset_atr_mult', 0.3)
    pullback_max_bars = params_dict.get('pullback_max_bars', 20)
    sl_anchor = params_dict.get('sl_anchor', 'last_pivot')
    sl_buffer_atr = params_dict.get('sl_buffer_atr_mult', 0.5)
    rr = params_dict.get('risk_reward', 2.0)

    # Session filter params
    use_session_filter = params_dict.get('use_session_filter', False)
    session_start_hour_utc = params_dict.get('session_start_hour_utc', 13)
    session_end_hour_utc = params_dict.get('session_end_hour_utc', 20)

    # BOS momentum filter params
    use_bos_momentum_filter = params_dict.get('use_bos_momentum_filter', False)

    # FLAG_CONTRACTION setup params
    use_flag_setup = params_dict.get('use_flag_contraction_setup', False)
    # Collect all flag-specific keys into one dict passed to detect_flag_contraction()
    flag_params = {
        'flag_impulse_lookback_bars':    params_dict.get('flag_impulse_lookback_bars',    8),
        'flag_contraction_bars':         params_dict.get('flag_contraction_bars',         5),
        'flag_min_impulse_atr_mult':     params_dict.get('flag_min_impulse_atr_mult',     2.5),
        'flag_max_contraction_atr_mult': params_dict.get('flag_max_contraction_atr_mult', 1.2),
        'flag_breakout_buffer_atr_mult': params_dict.get('flag_breakout_buffer_atr_mult', 0.1),
        'flag_sl_buffer_atr_mult':       params_dict.get('flag_sl_buffer_atr_mult',       0.3),
    }
    bos_min_range_atr_mult = params_dict.get('bos_min_range_atr_mult', 1.2)
    bos_min_body_to_range_ratio = params_dict.get('bos_min_body_to_range_ratio', 0.6)

    # Partial TP params (default False = opt-in, preserves existing behaviour)
    use_partial_tp = params_dict.get('use_partial_take_profit', False)
    partial_tp_ratio = params_dict.get('partial_tp_ratio', 0.5)
    partial_tp_rr = params_dict.get('partial_tp_rr', 1.0)
    final_tp_rr = params_dict.get('final_tp_rr', 2.0)
    move_sl_to_be = params_dict.get('move_sl_to_be_after_partial', True)

    # Calculate ATR
    ltf_df = ltf_df.copy()

    # Set timestamp as index if not already
    if 'timestamp' in ltf_df.columns:
        ltf_df.set_index('timestamp', inplace=True)

    htf_df = htf_df.copy()
    if 'timestamp' in htf_df.columns:
        htf_df.set_index('timestamp', inplace=True)

    # VALIDATION: Ensure DatetimeIndex
    assert isinstance(ltf_df.index, pd.DatetimeIndex), f"LTF index must be DatetimeIndex, got {type(ltf_df.index)}"
    assert isinstance(htf_df.index, pd.DatetimeIndex), f"HTF index must be DatetimeIndex, got {type(htf_df.index)}"

    # Sort index
    ltf_df = ltf_df.sort_index()
    htf_df = htf_df.sort_index()

    ltf_df['atr'] = calculate_atr(ltf_df, period=14)

    # Detect pivots on LTF (H1)
    ltf_pivot_highs, ltf_pivot_lows, ltf_ph_levels, ltf_pl_levels = detect_pivots_confirmed(
        ltf_df, lookback=ltf_lookback, confirmation_bars=confirmation_bars
    )

    # Detect pivots on HTF (H4)
    htf_pivot_highs, htf_pivot_lows, htf_ph_levels, htf_pl_levels = detect_pivots_confirmed(
        htf_df, lookback=htf_lookback, confirmation_bars=confirmation_bars
    )

    # Initialize
    tracker = SetupTracker()
    trades = []
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
                partial_fires = (
                    use_partial_tp
                    and not current_position['partial_tp_hit']
                    and current_position['partial_tp_price'] is not None
                    and current_bar['high_bid'] >= current_position['partial_tp_price']
                )
                final_tp_hit = current_bar['high_bid'] >= current_position['tp']

                # Priority order: SL > partial TP > final TP
                if sl_hit:
                    exit_price = current_position['sl']
                    if partial_fires or final_tp_hit:
                        exit_reason = 'SL_intrabar_conflict'
                    elif current_position['partial_tp_hit']:
                        exit_reason = 'SL_after_partial'
                    else:
                        exit_reason = 'SL'
                elif partial_fires:
                    # Record partial TP in position state; do NOT close yet
                    current_position['partial_tp_hit'] = True
                    current_position['partial_r_booked'] = partial_tp_ratio * partial_tp_rr
                    current_position['remaining_size'] = 1.0 - partial_tp_ratio
                    current_position['partial_exit_time'] = current_time
                    current_position['partial_exit_price'] = current_position['partial_tp_price']
                    if move_sl_to_be:
                        current_position['sl'] = current_position['entry']
                    if final_tp_hit:
                        exit_price = current_position['tp']
                        exit_reason = 'TP'
                    else:
                        exit_price = None   # position continues to next bar
                elif final_tp_hit:
                    exit_price = current_position['tp']
                    exit_reason = 'TP'
                else:
                    exit_price = None

                if exit_price is not None:
                    # Use original SL for R calc (sl may have moved to BE)
                    risk_dist = abs(current_position['entry'] - current_position['original_sl'])

                    # Get entry bar for feasibility check
                    entry_bar = ltf_df.loc[current_position['entry_time']]

                    # CLAMP exit price to feasible range (BID for LONG)
                    original_exit_price = exit_price
                    if exit_price < current_bar['low_bid']:
                        exit_price = current_bar['low_bid']
                    elif exit_price > current_bar['high_bid']:
                        exit_price = current_bar['high_bid']

                    # Blended R: partial booked + remaining portion at final exit
                    remaining_realized = exit_price - current_position['entry']
                    remaining_R = remaining_realized / risk_dist if risk_dist > 0 else 0
                    total_R = current_position['partial_r_booked'] + current_position['remaining_size'] * remaining_R
                    realized_dist = total_R * risk_dist

                    # Blended PnL
                    partial_pnl = 0.0
                    if current_position['partial_tp_hit'] and current_position['partial_exit_price'] is not None:
                        partial_pnl = partial_tp_ratio * (
                            current_position['partial_exit_price'] - current_position['entry']
                        ) * 100000
                    remainder_pnl = current_position['remaining_size'] * (
                        exit_price - current_position['entry']
                    ) * 100000
                    exit_pnl = partial_pnl + remainder_pnl

                    # FEASIBILITY CHECKS — LONG: entry on ASK, exit on BID
                    entry_feasible = entry_bar['low_ask'] <= current_position['entry'] <= entry_bar['high_ask']
                    exit_feasible = current_bar['low_bid'] <= exit_price <= current_bar['high_bid']

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
                        'setup_type': current_position.get('setup_type', 'BOS'),
                        'entry_price': current_position['entry'],
                        'exit_price': exit_price,
                        'pnl': exit_pnl,
                        'exit_reason': exit_reason,
                        'risk_distance': risk_dist,
                        'realized_distance': realized_dist,
                        'planned_sl': current_position['original_sl'],
                        'planned_tp': current_position['tp'],
                        'R': total_R,
                        # Partial TP info
                        'partial_tp_hit': current_position['partial_tp_hit'],
                        'partial_exit_time': (
                            pd.Timestamp(current_position['partial_exit_time']).isoformat()
                            if current_position['partial_exit_time'] is not None else None
                        ),
                        'partial_exit_price': current_position['partial_exit_price'],
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
                partial_fires = (
                    use_partial_tp
                    and not current_position['partial_tp_hit']
                    and current_position['partial_tp_price'] is not None
                    and current_bar['low_ask'] <= current_position['partial_tp_price']
                )
                final_tp_hit = current_bar['low_ask'] <= current_position['tp']

                # Priority order: SL > partial TP > final TP
                if sl_hit:
                    exit_price = current_position['sl']
                    if partial_fires or final_tp_hit:
                        exit_reason = 'SL_intrabar_conflict'
                    elif current_position['partial_tp_hit']:
                        exit_reason = 'SL_after_partial'
                    else:
                        exit_reason = 'SL'
                elif partial_fires:
                    current_position['partial_tp_hit'] = True
                    current_position['partial_r_booked'] = partial_tp_ratio * partial_tp_rr
                    current_position['remaining_size'] = 1.0 - partial_tp_ratio
                    current_position['partial_exit_time'] = current_time
                    current_position['partial_exit_price'] = current_position['partial_tp_price']
                    if move_sl_to_be:
                        current_position['sl'] = current_position['entry']
                    if final_tp_hit:
                        exit_price = current_position['tp']
                        exit_reason = 'TP'
                    else:
                        exit_price = None   # position continues to next bar
                elif final_tp_hit:
                    exit_price = current_position['tp']
                    exit_reason = 'TP'
                else:
                    exit_price = None

                if exit_price is not None:
                    # Use original SL for R calc (sl may have moved to BE)
                    risk_dist = abs(current_position['original_sl'] - current_position['entry'])

                    # Get entry bar for feasibility check
                    entry_bar = ltf_df.loc[current_position['entry_time']]

                    # CLAMP exit price to feasible range (ASK for SHORT)
                    original_exit_price = exit_price
                    if exit_price < current_bar['low_ask']:
                        exit_price = current_bar['low_ask']
                    elif exit_price > current_bar['high_ask']:
                        exit_price = current_bar['high_ask']

                    # Blended R: partial booked + remaining portion at final exit
                    remaining_realized = current_position['entry'] - exit_price
                    remaining_R = remaining_realized / risk_dist if risk_dist > 0 else 0
                    total_R = current_position['partial_r_booked'] + current_position['remaining_size'] * remaining_R
                    realized_dist = total_R * risk_dist

                    # Blended PnL
                    partial_pnl = 0.0
                    if current_position['partial_tp_hit'] and current_position['partial_exit_price'] is not None:
                        partial_pnl = partial_tp_ratio * (
                            current_position['entry'] - current_position['partial_exit_price']
                        ) * 100000
                    remainder_pnl = current_position['remaining_size'] * (
                        current_position['entry'] - exit_price
                    ) * 100000
                    exit_pnl = partial_pnl + remainder_pnl

                    # FEASIBILITY CHECKS — SHORT: entry on BID, exit on ASK
                    entry_feasible = entry_bar['low_bid'] <= current_position['entry'] <= entry_bar['high_bid']
                    exit_feasible = current_bar['low_ask'] <= exit_price <= current_bar['high_ask']

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
                        'setup_type': current_position.get('setup_type', 'BOS'),
                        'entry_price': current_position['entry'],
                        'exit_price': exit_price,
                        'pnl': exit_pnl,
                        'exit_reason': exit_reason,
                        'risk_distance': risk_dist,
                        'realized_distance': realized_dist,
                        'planned_sl': current_position['original_sl'],
                        'planned_tp': current_position['tp'],
                        'R': total_R,
                        # Partial TP info
                        'partial_tp_hit': current_position['partial_tp_hit'],
                        'partial_exit_time': (
                            pd.Timestamp(current_position['partial_exit_time']).isoformat()
                            if current_position['partial_exit_time'] is not None else None
                        ),
                        'partial_exit_price': current_position['partial_exit_price'],
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

                # Enter trade
                atr = current_bar['atr']
                entry = setup.entry_price

                # Determine SL:
                #   FLAG_CONTRACTION — SL was precomputed at detection time
                #                      (contraction boundary ± ATR buffer).
                #   BOS              — SL derived from last confirmed opposite pivot.
                if setup.sl_price is not None:
                    sl = setup.sl_price
                    risk = (entry - sl) if setup.direction == 'LONG' else (sl - entry)
                    if risk <= 0:
                        # Degenerate fill (spread or data anomaly): discard safely
                        tracker.clear_active_setup()
                        continue
                else:
                    if setup.direction == 'LONG':
                        if sl_anchor == 'last_pivot':
                            sl_time, sl_level = get_last_confirmed_pivot(
                                ltf_df, ltf_pivot_lows, ltf_pl_levels, current_time)
                        else:  # pre_bos_pivot
                            sl_level = setup.bos_level
                        sl = (sl_level - sl_buffer_atr * atr) if sl_level else (entry - 2 * atr)
                        risk = entry - sl
                    else:  # SHORT
                        if sl_anchor == 'last_pivot':
                            sl_time, sl_level = get_last_confirmed_pivot(
                                ltf_df, ltf_pivot_highs, ltf_ph_levels, current_time)
                        else:
                            sl_level = setup.bos_level
                        sl = (sl_level + sl_buffer_atr * atr) if sl_level else (entry + 2 * atr)
                        risk = sl - entry

                if setup.direction == 'LONG':
                    if use_partial_tp:
                        partial_tp_price = entry + partial_tp_rr * risk
                        tp = entry + final_tp_rr * risk
                    else:
                        partial_tp_price = None
                        tp = entry + (risk * rr)
                else:
                    if use_partial_tp:
                        partial_tp_price = entry - partial_tp_rr * risk
                        tp = entry - final_tp_rr * risk
                    else:
                        partial_tp_price = None
                        tp = entry - (risk * rr)

                current_position = {
                    'direction': setup.direction,
                    'setup_type': setup.setup_type,   # 'BOS' or 'FLAG_CONTRACTION'
                    'entry': entry,
                    'sl': sl,
                    'original_sl': sl,   # preserved for R calc after BE move
                    'tp': tp,
                    'entry_time': current_time,
                    # Partial TP state
                    'partial_tp_hit': False,
                    'partial_tp_price': partial_tp_price,
                    'remaining_size': 1.0,
                    'partial_r_booked': 0.0,
                    'partial_exit_time': None,
                    'partial_exit_price': None,
                }

                tracker.clear_active_setup()

        # Skip if position or setup exists
        if current_position or tracker.has_active_setup():
            continue

        # Get HTF bias (shared by both BOS and FLAG paths)
        htf_bias = get_htf_bias_at_bar(
            htf_df, current_time,
            htf_pivot_highs, htf_pivot_lows, htf_ph_levels, htf_pl_levels,
            pivot_count=4
        )

        if htf_bias == 'NEUTRAL':
            continue

        atr = current_bar['atr']
        # Guard: ATR must be valid for any setup creation
        if pd.isna(atr) or atr <= 0:
            continue

        # Helper: session gate (shared by both paths)
        in_session = (
            not use_session_filter
            or is_allowed_session(current_time, session_start_hour_utc, session_end_hour_utc)
        )

        setup_created = False

        # ==============================================================
        # PATH A: BOS (Break-of-Structure) — runs first, has priority.
        # If this path creates a setup, FLAG_CONTRACTION is skipped.
        # ==============================================================
        bos_detected, bos_direction, bos_level = check_bos(
            ltf_df, i, ltf_pivot_highs, ltf_pivot_lows, ltf_ph_levels, ltf_pl_levels,
            require_close_break
        )

        if bos_detected:
            bos_aligned = (
                (bos_direction == 'LONG' and htf_bias == 'BULL')
                or (bos_direction == 'SHORT' and htf_bias == 'BEAR')
            )
            if bos_aligned and in_session:
                # BOS momentum filter — validates breakout strength
                mom_ok = True
                if use_bos_momentum_filter:
                    impulse_range = current_bar['high_bid'] - current_bar['low_bid']
                    if impulse_range <= 0:
                        mom_ok = False
                    else:
                        body_size = abs(current_bar['close_bid'] - current_bar['open_bid'])
                        body_ratio = body_size / impulse_range
                        mom_ok = (
                            impulse_range >= bos_min_range_atr_mult * atr
                            and body_ratio >= bos_min_body_to_range_ratio
                        )

                if mom_ok:
                    if bos_direction == 'LONG':
                        entry_price = bos_level + entry_offset_atr * atr
                    else:
                        entry_price = bos_level - entry_offset_atr * atr

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
                        ltf_pivot_type='pivot_high' if bos_direction == 'LONG' else 'pivot_low',
                        setup_type='BOS',
                    )
                    setup_created = True

        # ==============================================================
        # PATH B: FLAG_CONTRACTION — only when BOS did NOT fire this bar.
        # Priority rule: BOS > FLAG_CONTRACTION.
        # ==============================================================
        if use_flag_setup and not setup_created and in_session:
            flag_result = detect_flag_contraction(ltf_df, i, atr, flag_params)
            if flag_result is not None:
                flag_dir = flag_result['direction']
                flag_aligned = (
                    (flag_dir == 'LONG' and htf_bias == 'BULL')
                    or (flag_dir == 'SHORT' and htf_bias == 'BEAR')
                )
                if flag_aligned:
                    entry_price = flag_result['entry_price']
                    sl_price    = flag_result['sl_price']
                    risk_dist   = abs(entry_price - sl_price)
                    if risk_dist > 0:
                        expiry_idx  = min(i + pullback_max_bars, len(ltf_df) - 1)
                        expiry_time = ltf_df.index[expiry_idx]
                        # bos_level is repurposed as the reference breakout level
                        ref_level = (
                            flag_result['contraction_high']
                            if flag_dir == 'LONG'
                            else flag_result['contraction_low']
                        )
                        tracker.create_setup(
                            direction=flag_dir,
                            bos_level=ref_level,
                            bos_time=current_time,
                            entry_price=entry_price,
                            expiry_time=expiry_time,
                            expiry_bar_count=pullback_max_bars,
                            htf_bias=htf_bias,
                            ltf_pivot_type='flag_high' if flag_dir == 'LONG' else 'flag_low',
                            setup_type='FLAG_CONTRACTION',
                            sl_price=sl_price,
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

        # Calculate max drawdown
        equity_curve = [initial_balance]
        for pnl in trades_df['pnl']:
            equity_curve.append(equity_curve[-1] + pnl)

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


