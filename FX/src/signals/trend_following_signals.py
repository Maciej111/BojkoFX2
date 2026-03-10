"""
src/signals/trend_following_signals.py

Single source of truth for BOS + Pullback signal logic.

Used by:
  - src/strategies/trend_following_v1.py  (live trading)
  - backtests/signals_bos_pullback.py    (research backtest)

Both live and backtest must call these functions. Neither should
implement its own BOS detection, pivot computation, SL/entry calculation,
or regime filters.

Public API
----------
precompute_pivots(high, low, lookback)
    O(n) no-lookahead pivot pre-computation (returns 4 lists).

check_bos_signal(close_val, last_ph, last_pl)
    Returns ('LONG', level) | ('SHORT', level) | (None, None).

apply_regime_filters(...)
    Returns True if setup passes all enabled regime filters.

compute_entry_price(bos_level, side, entry_offset_mult, atr_val)
    Entry limit-order level (BOS level ± offset).

compute_sl_at_fill(side, last_pivot_level, sl_buffer_mult, atr_val, entry_price)
    SL calculated AT THE MOMENT OF FILL using pivot at fill time.

compute_tp_price(entry_price, sl_price, rr, side)
    TP = entry ± rr * risk.

compute_adx_series(df, period)
    ADX indicator series from normalized OHLC DataFrame.

compute_atr_series(df, period)
    Wilder-smoothed ATR from normalized OHLC DataFrame.

compute_atr_percentile_series(atr_series, window)
    Rolling ATR percentile (0–100) series.

normalize_ohlc(df, price_type)
    Map bid/ask- suffixed columns to plain high/low/close/open.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# Pivot detection — no-lookahead O(n)
# ─────────────────────────────────────────────────────────────────────────────

def precompute_pivots(
    high: np.ndarray,
    low: np.ndarray,
    lookback: int,
) -> Tuple[list, list, list, list]:
    """
    Pre-computes the last confirmed pivot high/low visible at every bar.

    A pivot at position p is *confirmed* at bar p+lookback (right wing complete),
    so it becomes visible from bar p+lookback+1 onward (no lookahead).

    Returns four lists of length n:
        ph_prices[i]  price of the most recent pivot high confirmed BEFORE bar i
        ph_idxs[i]    bar index of that pivot high (or None)
        pl_prices[i]  price of the most recent pivot low confirmed BEFORE bar i
        pl_idxs[i]    bar index of that pivot low (or None)
    """
    n = len(high)
    ph_prices: list = [None] * n
    ph_idxs:   list = [None] * n
    pl_prices: list = [None] * n
    pl_idxs:   list = [None] * n

    last_ph = last_ph_idx = None
    last_pl = last_pl_idx = None

    for i in range(n):
        # Expose running state BEFORE updating (bar i sees pivots confirmed < i)
        ph_prices[i] = last_ph
        ph_idxs[i]   = last_ph_idx
        pl_prices[i] = last_pl
        pl_idxs[i]   = last_pl_idx

        # Candidate pivot centre: p = i - lookback (confirmed at bar i)
        p = i - lookback
        if p >= lookback:
            lo_s = p - lookback
            hi_e = p + lookback + 1
            if hi_e <= n:
                window_h = high[lo_s:hi_e]
                if high[p] == window_h.max():
                    last_ph     = float(high[p])
                    last_ph_idx = p
                window_l = low[lo_s:hi_e]
                if low[p] == window_l.min():
                    last_pl     = float(low[p])
                    last_pl_idx = p

    return ph_prices, ph_idxs, pl_prices, pl_idxs


# ─────────────────────────────────────────────────────────────────────────────
# BOS detection
# ─────────────────────────────────────────────────────────────────────────────

def check_bos_signal(
    close_val: float,
    last_ph: Optional[float],
    last_pl: Optional[float],
) -> Tuple[Optional[str], Optional[float]]:
    """
    Detects a Break of Structure at the current bar using a close-price break.

    Parameters
    ----------
    close_val : float
        Close price of the current bar.
    last_ph : float or None
        Most recent confirmed pivot high visible at this bar.
    last_pl : float or None
        Most recent confirmed pivot low visible at this bar.

    Returns
    -------
    (side, bos_level) where side = 'LONG' | 'SHORT', or (None, None) if no BOS.

    Rules
    -----
    - LONG BOS:  close > last confirmed pivot high  (bullish breakout)
    - SHORT BOS: close < last confirmed pivot low   (bearish breakout)
    - If both conditions hold simultaneously, LONG takes priority.
    """
    if last_ph is not None and close_val > last_ph:
        return "LONG", last_ph
    if last_pl is not None and close_val < last_pl:
        return "SHORT", last_pl
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Regime filters
# ─────────────────────────────────────────────────────────────────────────────

def apply_regime_filters(
    adx_val: float = 0.0,
    atr_pct_val: float = 50.0,
    use_adx_filter: bool = False,
    adx_threshold: float = 20.0,
    use_atr_percentile_filter: bool = False,
    atr_percentile_min: float = 10.0,
    atr_percentile_max: float = 80.0,
) -> bool:
    """
    Returns True if the setup passes all enabled regime filters.

    Parameters
    ----------
    adx_val : float
        Current ADX value on the chosen timeframe (H4 or D1).
    atr_pct_val : float
        Current ATR percentile (0–100) from the LTF rolling window.
    use_adx_filter : bool
        If True, reject signals where ADX < adx_threshold.
    adx_threshold : float
        Minimum ADX to accept a signal (default 20).
    use_atr_percentile_filter : bool
        If True, reject signals outside [atr_percentile_min, atr_percentile_max].
    atr_percentile_min : float
        Lower ATR percentile bound (default 10).
    atr_percentile_max : float
        Upper ATR percentile bound (default 80).

    Returns
    -------
    bool – True = setup accepted, False = setup rejected.
    """
    if use_adx_filter and adx_val < adx_threshold:
        return False
    if use_atr_percentile_filter and not (atr_percentile_min <= atr_pct_val <= atr_percentile_max):
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Entry / SL / TP price computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_entry_price(
    bos_level: float,
    side: str,
    entry_offset_mult: float,
    atr_val: float,
) -> float:
    """
    Returns the limit-order entry price for a pullback setup.

    LONG:  entry = bos_level + entry_offset_mult * ATR
           (entry slightly above the BOS level — we expect price to pull back
            to the BOS level and the offset prevents immediate over-penetration)
    SHORT: entry = bos_level - entry_offset_mult * ATR
    """
    offset = entry_offset_mult * atr_val
    if side == "LONG":
        return bos_level + offset
    return bos_level - offset


def compute_sl_at_fill(
    side: str,
    last_pivot_level: Optional[float],
    sl_buffer_mult: float,
    atr_val: float,
    entry_price: float,
    fallback_atr_mult: float = 2.0,
) -> float:
    """
    Calculates the stop-loss price AT THE MOMENT OF FILL.

    SL is anchored to the last confirmed opposite pivot at fill time.
    If no pivot is available, a fallback of entry ± fallback_atr_mult * ATR is used.

    LONG SL:  last_pivot_low  - sl_buffer_mult * ATR
    SHORT SL: last_pivot_high + sl_buffer_mult * ATR

    Parameters
    ----------
    side : str
        'LONG' or 'SHORT'.
    last_pivot_level : float or None
        Most recent confirmed pivot on the opposite side (low for LONG, high for SHORT),
        visible at the bar when the trade fills.
    sl_buffer_mult : float
        ATR multiplier for the buffer beyond the pivot.
    atr_val : float
        ATR value at the fill bar.
    entry_price : float
        Actual fill price (used for fallback only).
    fallback_atr_mult : float
        ATR multiplier used when no pivot is available.

    Returns
    -------
    float – stop-loss price.
    """
    buffer = sl_buffer_mult * atr_val
    fallback_dist = fallback_atr_mult * atr_val

    if last_pivot_level is not None:
        if side == "LONG":
            return last_pivot_level - buffer
        return last_pivot_level + buffer

    # Fallback: no pivot available
    if side == "LONG":
        return entry_price - fallback_dist
    return entry_price + fallback_dist


def compute_tp_price(
    entry_price: float,
    sl_price: float,
    rr: float,
    side: str,
) -> float:
    """
    Returns the take-profit price.

    TP = entry ± rr * risk
    where risk = abs(entry - sl).
    """
    risk = abs(entry_price - sl_price)
    if side == "LONG":
        return entry_price + rr * risk
    return entry_price - rr * risk


# ─────────────────────────────────────────────────────────────────────────────
# Indicator helpers (self-contained, no external deps beyond numpy/pandas)
# ─────────────────────────────────────────────────────────────────────────────

def normalize_ohlc(df: pd.DataFrame, price_type: str = "bid") -> pd.DataFrame:
    """
    Normalizes column names for DataFrames that use bid/ask suffixes.

    Maps: high_{price_type} → high, low_{price_type} → low,
          close_{price_type} → close, open_{price_type} → open.

    If columns already named high/low/close/open, returns df unchanged.
    Returns a copy with plain OHLC column names.
    """
    if "high" in df.columns:
        return df  # already normalized
    mapping = {
        f"high_{price_type}":  "high",
        f"low_{price_type}":   "low",
        f"close_{price_type}": "close",
        f"open_{price_type}":  "open",
    }
    existing = {k: v for k, v in mapping.items() if k in df.columns}
    return df.rename(columns=existing)


def compute_atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Wilder's smoothed ATR.
    Expects columns: high, low, close  (use normalize_ohlc first if needed).
    """
    hi = df["high"]
    lo = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        hi - lo,
        (hi - prev_close).abs(),
        (lo - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def compute_adx_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Returns just the ADX series (Wilder smoothed, no DI columns).
    Expects columns: high, low, close  (use normalize_ohlc first if needed).
    """
    hi = df["high"]
    lo = df["low"]
    prev_hi = hi.shift(1)
    prev_lo = lo.shift(1)

    up_move   = hi - prev_hi
    down_move = prev_lo - lo

    plus_dm  = np.where((up_move > down_move) & (up_move > 0),   up_move,   0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_dm_s  = pd.Series(plus_dm,  index=df.index)
    minus_dm_s = pd.Series(minus_dm, index=df.index)

    atr_s = compute_atr_series(df, period)

    alpha    = 1.0 / period
    plus_di  = 100 * plus_dm_s.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_s
    minus_di = 100 * minus_dm_s.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_s

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0)
    return dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()


def compute_atr_percentile_series(
    atr_series: pd.Series,
    window: int = 100,
) -> pd.Series:
    """
    Rolling ATR percentile: for each bar, the percentile of the current ATR
    value within the last `window` bars (0–100).
    """
    def _pct(arr: np.ndarray) -> float:
        if len(arr) < 2:
            return 50.0
        cur = arr[-1]
        return float(np.sum(arr[:-1] < cur) / (len(arr) - 1) * 100)

    return atr_series.rolling(window, min_periods=max(2, window // 4)).apply(
        _pct, raw=True
    )
