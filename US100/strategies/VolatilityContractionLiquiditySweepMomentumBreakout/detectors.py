"""
Detectors for VCLSMB.

Each detector is a pure function: (row, cfg) → bool.
They operate on a single bar row (Series) that already has feature columns
computed by feature_pipeline.build_features().

No lookahead: all feature columns were built with shift(1) on rolling windows.
"""
import pandas as pd
from .config import VCLSMBConfig


def is_compression(row: pd.Series, cfg: VCLSMBConfig) -> bool:
    """
    Volatility contraction: current ATR ≤ compression_atr_ratio × rolling-max ATR.

    Requires feature columns: atr, atr_rolling_max
    """
    roll_max = row.get("atr_rolling_max", float("nan"))
    atr      = row.get("atr", float("nan"))
    if pd.isna(roll_max) or pd.isna(atr) or roll_max <= 0:
        return False
    return (atr / roll_max) <= cfg.compression_atr_ratio


def is_liquidity_sweep_bull(row: pd.Series, cfg: VCLSMBConfig) -> bool:
    """
    Bullish sweep: bar wicks below range_low by ≥ sweep_atr_mult × ATR,
    then closes back inside the range (if sweep_close_inside=True).

    A bullish sweep clears sell-side liquidity → expect upside breakout.

    Requires columns: low_bid, high_bid, close_bid, range_low, atr
    """
    range_low = row.get("range_low", float("nan"))
    atr       = row.get("atr", float("nan"))
    if pd.isna(range_low) or pd.isna(atr) or atr <= 0:
        return False

    wick_below = range_low - row["low_bid"]
    if wick_below < cfg.sweep_atr_mult * atr:
        return False

    if cfg.sweep_close_inside:
        return row["close_bid"] >= range_low
    return True


def is_liquidity_sweep_bear(row: pd.Series, cfg: VCLSMBConfig) -> bool:
    """
    Bearish sweep: bar wicks above range_high by ≥ sweep_atr_mult × ATR,
    then closes back inside the range (if sweep_close_inside=True).

    A bearish sweep clears buy-side liquidity → expect downside breakout.

    Requires columns: high_bid, close_bid, range_high, atr
    """
    range_high = row.get("range_high", float("nan"))
    atr        = row.get("atr", float("nan"))
    if pd.isna(range_high) or pd.isna(atr) or atr <= 0:
        return False

    wick_above = row["high_bid"] - range_high
    if wick_above < cfg.sweep_atr_mult * atr:
        return False

    if cfg.sweep_close_inside:
        return row["close_bid"] <= range_high
    return True


def is_momentum_breakout_bull(row: pd.Series, cfg: VCLSMBConfig) -> bool:
    """
    Bullish momentum breakout: close > range_high AND bar body ≥ N×ATR
    AND body/range ≥ threshold.

    Requires columns: close_bid, range_high, bar_body, bar_body_ratio, atr
    """
    range_high = row.get("range_high", float("nan"))
    atr        = row.get("atr", float("nan"))
    if pd.isna(range_high) or pd.isna(atr) or atr <= 0:
        return False

    close_breaks = row["close_bid"] > range_high
    strong_body  = row["bar_body"] >= cfg.momentum_atr_mult * atr
    clean_candle = row["bar_body_ratio"] >= cfg.momentum_body_ratio
    return close_breaks and strong_body and clean_candle


def is_momentum_breakout_bear(row: pd.Series, cfg: VCLSMBConfig) -> bool:
    """
    Bearish momentum breakout: close < range_low AND bar body ≥ N×ATR
    AND body/range ≥ threshold.

    Requires columns: close_bid, range_low, bar_body, bar_body_ratio, atr
    """
    range_low = row.get("range_low", float("nan"))
    atr       = row.get("atr", float("nan"))
    if pd.isna(range_low) or pd.isna(atr) or atr <= 0:
        return False

    close_breaks = row["close_bid"] < range_low
    strong_body  = row["bar_body"] >= cfg.momentum_atr_mult * atr
    clean_candle = row["bar_body_ratio"] >= cfg.momentum_body_ratio
    return close_breaks and strong_body and clean_candle
