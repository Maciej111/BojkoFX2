"""
backtests/indicators.py
ATR, ADX, rolling ATR-percentile — czyste numpy/pandas, bez zależności produkcyjnych.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ── ATR ───────────────────────────────────────────────────────────────────────

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    True Range → Wilder's smoothed ATR.
    Wymaga kolumn: high, low, close.
    """
    hi = df["high"]
    lo = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        hi - lo,
        (hi - prev_close).abs(),
        (lo - prev_close).abs(),
    ], axis=1).max(axis=1)
    # Wilder smoothing (EWM z alpha=1/period)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


# ── ADX ───────────────────────────────────────────────────────────────────────

def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Return DataFrame with columns: adx, plus_di, minus_di.
    Wymaga kolumn: high, low, close.
    Działa na dowolnym TF (H1/H4/D1) — kolumny muszą być poprawnie znormalizowane.
    """
    hi = df["high"]
    lo = df["low"]
    prev_hi = hi.shift(1)
    prev_lo = lo.shift(1)

    up_move   = hi - prev_hi
    down_move = prev_lo - lo

    plus_dm  = np.where((up_move > down_move) & (up_move > 0), up_move,   0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_dm_s  = pd.Series(plus_dm,  index=df.index)
    minus_dm_s = pd.Series(minus_dm, index=df.index)

    atr_s = atr(df, period)

    # Wilder smoothing
    alpha = 1.0 / period
    plus_di  = 100 * plus_dm_s.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_s
    minus_di = 100 * minus_dm_s.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_s

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0)
    adx_s = dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    return pd.DataFrame({"adx": adx_s, "plus_di": plus_di, "minus_di": minus_di},
                        index=df.index)


def compute_adx(df_ohlc: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Convenience helper: zwraca tylko serię ADX (bez DI).
    Przyjmuje DataFrame z kolumnami high/low/close (dowolny TF).
    """
    return adx(df_ohlc, period)["adx"]


# ── Rolling ATR percentile ────────────────────────────────────────────────────

def atr_percentile(atr_series: pd.Series, window: int = 100) -> pd.Series:
    """
    Dla każdego baru: percentyl bieżącego ATR w oknie ostatnich `window` barów.
    Zwraca serię wartości 0–100.
    """
    def _pct(arr: np.ndarray) -> float:
        if len(arr) < 2:
            return 50.0
        cur = arr[-1]
        return float(np.sum(arr[:-1] < cur) / (len(arr) - 1) * 100)

    return atr_series.rolling(window, min_periods=max(2, window // 4)).apply(
        _pct, raw=True
    )


# ── ADX slope ─────────────────────────────────────────────────────────────────

def adx_slope(adx_series: pd.Series, lag: int = 3) -> pd.Series:
    """True jeśli ADX(t) > ADX(t-lag)."""
    return adx_series > adx_series.shift(lag)


def adx_slope_sma(adx_series: pd.Series, sma_period: int = 5) -> pd.Series:
    """
    Slope via SMA: True jeśli ADX(t) > SMA(ADX, sma_period) w chwili t.
    Alternatywna definicja 'rising ADX' — mniej szumowa niż lag.
    """
    return adx_series > adx_series.rolling(sma_period, min_periods=1).mean()


# ── Adaptive RR helpers ───────────────────────────────────────────────────────

def rr_from_adx(adx_val: float, mode: str) -> float:
    """Zwraca RR na podstawie wartości ADX i nazwy trybu."""
    if mode == "adx_map_v1":
        if adx_val >= 35:
            return 3.5
        elif adx_val >= 25:
            return 3.0
        elif adx_val >= 20:
            return 2.5
        return 2.0   # ADX < 20 → nie handlujemy (gate powinien odfiltrować)
    elif mode == "adx_map_v2":
        if adx_val >= 35:
            return 4.0
        elif adx_val >= 25:
            return 3.0
        elif adx_val >= 20:
            return 2.0
        return 2.0
    return 3.0   # fallback


def rr_from_atr_pct(atr_pct_val: float) -> float:
    """Zwraca RR na podstawie percentyla ATR."""
    if atr_pct_val >= 80:
        return 2.5   # high vol → mniejszy TP (częstsze exity)
    elif atr_pct_val >= 20:
        return 3.0   # mid vol
    return 2.0       # low vol


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    True Range → Wilder's smoothed ATR.
    Wymaga kolumn: high, low, close.
    """
    hi = df["high"]
    lo = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        hi - lo,
        (hi - prev_close).abs(),
        (lo - prev_close).abs(),
    ], axis=1).max(axis=1)
    # Wilder smoothing (EWM z alpha=1/period)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


# ── ADX ───────────────────────────────────────────────────────────────────────

def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Return DataFrame with columns: adx, plus_di, minus_di.
    Wymaga kolumn: high, low, close.
    """
    hi = df["high"]
    lo = df["low"]
    prev_hi = hi.shift(1)
    prev_lo = lo.shift(1)

    up_move   = hi - prev_hi
    down_move = prev_lo - lo

    plus_dm  = np.where((up_move > down_move) & (up_move > 0), up_move,   0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_dm_s  = pd.Series(plus_dm,  index=df.index)
    minus_dm_s = pd.Series(minus_dm, index=df.index)

    atr_s = atr(df, period)

    # Wilder smoothing
    alpha = 1.0 / period
    plus_di  = 100 * plus_dm_s.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_s
    minus_di = 100 * minus_dm_s.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_s

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0)
    adx_s = dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    return pd.DataFrame({"adx": adx_s, "plus_di": plus_di, "minus_di": minus_di},
                        index=df.index)


# ── Rolling ATR percentile ────────────────────────────────────────────────────

def atr_percentile(atr_series: pd.Series, window: int = 100) -> pd.Series:
    """
    Dla każdego baru: percentyl bieżącego ATR w oknie ostatnich `window` barów.
    Zwraca serię wartości 0–100.
    """
    def _pct(arr: np.ndarray) -> float:
        if len(arr) < 2:
            return 50.0
        cur = arr[-1]
        return float(np.sum(arr[:-1] < cur) / (len(arr) - 1) * 100)

    return atr_series.rolling(window, min_periods=max(2, window // 4)).apply(
        _pct, raw=True
    )


# ── ADX slope ─────────────────────────────────────────────────────────────────

def adx_slope(adx_series: pd.Series, lag: int = 3) -> pd.Series:
    """True jeśli ADX(t) > ADX(t-lag)."""
    return adx_series > adx_series.shift(lag)


# ── Adaptive RR helpers ───────────────────────────────────────────────────────

def rr_from_adx(adx_val: float, mode: str) -> float:
    """Zwraca RR na podstawie wartości ADX i nazwy trybu."""
    if mode == "adx_map_v1":
        if adx_val >= 35:
            return 3.5
        elif adx_val >= 25:
            return 3.0
        elif adx_val >= 20:
            return 2.5
        return 2.0   # ADX < 20 → nie handlujemy (gate powinien odfiltrować)
    elif mode == "adx_map_v2":
        if adx_val >= 35:
            return 4.0
        elif adx_val >= 25:
            return 3.0
        elif adx_val >= 20:
            return 2.0
        return 2.0
    return 3.0   # fallback


def rr_from_atr_pct(atr_pct_val: float) -> float:
    """Zwraca RR na podstawie percentyla ATR."""
    if atr_pct_val >= 80:
        return 2.5   # high vol → mniejszy TP (częstsze exity)
    elif atr_pct_val >= 20:
        return 3.0   # mid vol
    return 2.0       # low vol

