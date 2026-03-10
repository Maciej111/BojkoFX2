"""
Flag contraction pattern detection.

Detects trend continuation setups based on three conditions:
  1) Impulse move      — a strong directional price move over N bars
  2) Volatility contraction — tight consolidation following the impulse
  3) Breakout close    — close beyond the contraction boundary in impulse direction

Detection is fully ATR-based and deterministic.  No geometric trendlines,
no pivot sequences, no complex pattern recognition.

Detection windows (all relative to current bar index ``i``, no lookahead):
  impulse window    : df.iloc[i - contraction_bars - impulse_lookback_bars
                               : i - contraction_bars]
  contraction window: df.iloc[i - contraction_bars : i]
  breakout bar      : df.iloc[i]   (only its close_bid is evaluated)
"""

from typing import Optional

import pandas as pd


def detect_flag_contraction(
    df: pd.DataFrame,
    i: int,
    atr: float,
    params: dict,
) -> Optional[dict]:
    """
    Detect a FLAG_CONTRACTION setup at bar index ``i``.

    Parameters
    ----------
    df : DataFrame
        LTF bars with bid OHLC columns and an 'atr' column already computed.
        Index must be DatetimeIndex (UTC, timezone-naive or UTC-aware).
    i : int
        Current bar index (0-based, integer position).
    atr : float
        ATR value at bar ``i``  (df['atr'].iloc[i]).
    params : dict
        Strategy parameters:
          flag_impulse_lookback_bars   (int,   default 8)
          flag_contraction_bars        (int,   default 5)
          flag_min_impulse_atr_mult    (float, default 2.5)
          flag_max_contraction_atr_mult(float, default 1.2)
          flag_breakout_buffer_atr_mult(float, default 0.1)
          flag_sl_buffer_atr_mult      (float, default 0.3)

    Returns
    -------
    dict  with keys:
        direction        : 'LONG' or 'SHORT'
        contraction_high : float   (max high in contraction window)
        contraction_low  : float   (min low  in contraction window)
        entry_price      : float   (limit entry beyond breakout level)
        sl_price         : float   (ATR-buffered stop beyond opposite contraction edge)
    or None if no valid pattern is found.

    Priority rule: LONG is evaluated first; in the degenerate case where both
    conditions hold simultaneously (impossible in real data), LONG is returned.
    """
    impulse_lookback = params.get('flag_impulse_lookback_bars', 8)
    contraction_bars = params.get('flag_contraction_bars', 5)
    min_impulse_mult = params.get('flag_min_impulse_atr_mult', 2.5)
    max_contraction_mult = params.get('flag_max_contraction_atr_mult', 1.2)
    breakout_buffer = params.get('flag_breakout_buffer_atr_mult', 0.1)
    sl_buffer = params.get('flag_sl_buffer_atr_mult', 0.3)

    # Need enough history for both windows
    if i < contraction_bars + impulse_lookback:
        return None

    if atr is None or pd.isna(atr) or atr <= 0:
        return None

    # ------------------------------------------------------------------
    # Contraction window: bars [i - contraction_bars, i)
    # ------------------------------------------------------------------
    c_start = i - contraction_bars
    contraction_slice = df.iloc[c_start:i]

    c_high = contraction_slice['high_bid'].max()
    c_low  = contraction_slice['low_bid'].min()
    c_range = c_high - c_low

    mean_atr_c = contraction_slice['atr'].mean()
    if pd.isna(mean_atr_c) or mean_atr_c <= 0:
        return None

    # Reject if consolidation range is too wide (not a flag)
    if c_range > max_contraction_mult * mean_atr_c:
        return None

    # ------------------------------------------------------------------
    # Impulse window: bars [i - contraction_bars - impulse_lookback,
    #                        i - contraction_bars)
    # ------------------------------------------------------------------
    imp_start = i - contraction_bars - impulse_lookback
    imp_end   = i - contraction_bars           # exclusive

    impulse_slice = df.iloc[imp_start:imp_end]
    imp_open  = impulse_slice['open_bid'].iloc[0]
    imp_close = impulse_slice['close_bid'].iloc[-1]

    current_close = df['close_bid'].iloc[i]

    # ------------------------------------------------------------------
    # LONG: upward impulse  +  breakout close above contraction high
    # ------------------------------------------------------------------
    impulse_up = imp_close - imp_open
    if impulse_up >= min_impulse_mult * atr and current_close > c_high:
        entry_price = c_high + breakout_buffer * atr
        sl_price    = c_low  - sl_buffer * atr
        if entry_price > sl_price:      # degenerate-guard: risk must be positive
            return {
                'direction':        'LONG',
                'contraction_high': c_high,
                'contraction_low':  c_low,
                'entry_price':      entry_price,
                'sl_price':         sl_price,
            }

    # ------------------------------------------------------------------
    # SHORT: downward impulse  +  breakout close below contraction low
    # ------------------------------------------------------------------
    impulse_down = imp_open - imp_close
    if impulse_down >= min_impulse_mult * atr and current_close < c_low:
        entry_price = c_low  - breakout_buffer * atr
        sl_price    = c_high + sl_buffer * atr
        if sl_price > entry_price:      # degenerate-guard
            return {
                'direction':        'SHORT',
                'contraction_high': c_high,
                'contraction_low':  c_low,
                'entry_price':      entry_price,
                'sl_price':         sl_price,
            }

    return None
