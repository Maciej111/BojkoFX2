"""
Feature pipeline for VCLSMB.

Computes all derived columns needed for the strategy on the LTF DataFrame.
Reuses shared indicators: calculate_atr (Wilder), calculate_ema.

Output columns added to df (in-place copy returned):
  atr                  — Wilder ATR(atr_period)
  atr_rolling_max      — rolling max of ATR over compression_lookback bars
  range_high           — rolling max of high_bid over range_window bars (shifted 1)
  range_low            — rolling min of low_bid over range_window bars (shifted 1)
  bar_body             — abs(close_bid - open_bid)
  bar_range            — high_bid - low_bid
  bar_body_ratio       — bar_body / bar_range (0 if range==0)
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Ensure US100 root is on sys.path so src.indicators shims are importable
_ROOT = Path(__file__).resolve().parents[3]   # US100/
_SHARED = _ROOT.parent / "shared"
for _p in [str(_ROOT), str(_SHARED)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Use the existing src shim — avoids duplicating path resolution logic
try:
    from src.indicators.atr import calculate_atr  # noqa: E402
except ImportError:
    from bojkofx_shared.indicators.atr import calculate_atr  # noqa: E402

try:
    from src.indicators.ema import calculate_ema  # type: ignore  # noqa: E402
except ImportError:
    from bojkofx_shared.indicators.ema import calculate_ema  # noqa: E402

from .config import VCLSMBConfig


def build_features(df: pd.DataFrame, cfg: VCLSMBConfig) -> pd.DataFrame:
    """
    Return a copy of *df* with all strategy feature columns appended.

    Parameters
    ----------
    df : pd.DataFrame
        LTF bars with bid/ask OHLC columns, UTC-sorted index.
    cfg : VCLSMBConfig
        Strategy parameters.

    Returns
    -------
    pd.DataFrame  (new copy — original not mutated)
    """
    df = df.copy()

    # ── ATR (Wilder) ──────────────────────────────────────────────────────────
    df["atr"] = calculate_atr(df, period=cfg.atr_period)

    # ── ATR rolling max — measures compression ────────────────────────────────
    df["atr_rolling_max"] = (
        df["atr"].rolling(cfg.compression_lookback, min_periods=cfg.compression_lookback).max()
    )

    # ── Consolidation range (no-lookahead: shift(1) so bar N uses bars 0..N-1) ─
    df["range_high"] = (
        df["high_bid"].shift(1)
        .rolling(cfg.range_window, min_periods=cfg.range_window).max()
    )
    df["range_low"] = (
        df["low_bid"].shift(1)
        .rolling(cfg.range_window, min_periods=cfg.range_window).min()
    )

    # ── Bar body / range ──────────────────────────────────────────────────────
    df["bar_body"]  = (df["close_bid"] - df["open_bid"]).abs()
    df["bar_range"] = df["high_bid"] - df["low_bid"]
    df["bar_body_ratio"] = np.where(
        df["bar_range"] > 0, df["bar_body"] / df["bar_range"], 0.0
    )
    # ── Trend EMA (optional, only when filter is enabled) ────────────────────
    if cfg.enable_trend_filter:
        df["trend_ema"] = calculate_ema(df["close_bid"], period=cfg.trend_ema_period)

    # ── Volatility regime filter (optional) ──────────────────────────────────
    # Computes a boolean column vol_regime_ok:
    #   True  → current 1h ATR is above its Nth percentile → trading allowed
    #   False → low-volatility regime             → skip setup generation
    if cfg.enable_volatility_filter:
        try:
            from src.indicators.volatility_regime import compute_volatility_regime
        except ImportError:
            from bojkofx_shared.indicators.volatility_regime import compute_volatility_regime  # type: ignore # noqa: E501
        df["vol_regime_ok"] = compute_volatility_regime(
            df,
            htf_freq=cfg.volatility_htf,
            atr_period=cfg.volatility_atr_period,
            window_days=cfg.volatility_window_days,
            percentile_threshold=cfg.volatility_percentile_threshold,
        )
    else:
        df["vol_regime_ok"] = True

    # ── Previous-day high / low (structural liquidity levels) ─────────────────
    # Resample LTF bars to daily, shift(1) to get *previous* day (no lookahead),
    # then forward-fill back to the LTF index so every 5m bar carries the
    # levels from the most recently completed trading day.
    if cfg.enable_liquidity_location_filter:
        daily = df.resample("1D", closed="left", label="left").agg(
            {"high_bid": "max", "low_bid": "min"}
        )
        daily_shifted = daily.shift(1)  # previous day — no lookahead
        combined_idx = df.index.union(daily_shifted.index)
        df["previous_day_high"] = (
            daily_shifted["high_bid"].reindex(combined_idx).ffill().reindex(df.index)
        )
        df["previous_day_low"] = (
            daily_shifted["low_bid"].reindex(combined_idx).ffill().reindex(df.index)
        )
    else:
        df["previous_day_high"] = float("nan")
        df["previous_day_low"]  = float("nan")

    return df
