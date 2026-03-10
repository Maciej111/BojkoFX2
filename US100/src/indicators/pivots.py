"""
Pivot detection and Break of Structure (BOS) logic.
"""
import pandas as pd
import numpy as np


def detect_pivots(df, lookback=3):
    """
    Detect swing highs and swing lows (pivots).

    A pivot high at index i exists if:
    - high[i] is the highest in window [i-lookback, i+lookback]

    A pivot low at index i exists if:
    - low[i] is the lowest in window [i-lookback, i+lookback]

    Args:
        df: DataFrame with 'high_bid' and 'low_bid' columns
        lookback: Number of bars on each side to check

    Returns:
        tuple: (pivot_highs, pivot_lows) - pandas Series with NaN where no pivot
    """
    highs = df['high_bid'].values
    lows = df['low_bid'].values

    pivot_highs = pd.Series(index=df.index, dtype=float)
    pivot_lows = pd.Series(index=df.index, dtype=float)

    for i in range(lookback, len(df) - lookback):
        # Check pivot high
        window_highs = highs[i-lookback:i+lookback+1]
        if highs[i] == max(window_highs):
            pivot_highs.iloc[i] = highs[i]

        # Check pivot low
        window_lows = lows[i-lookback:i+lookback+1]
        if lows[i] == min(window_lows):
            pivot_lows.iloc[i] = lows[i]

    return pivot_highs, pivot_lows


def check_break_of_structure(df, pivot_highs, pivot_lows, impulse_idx, base_start_idx):
    """
    Check if impulse candle breaks structure (BOS).

    For DEMAND (bullish impulse):
    - Must break above the last pivot high before base

    For SUPPLY (bearish impulse):
    - Must break below the last pivot low before base

    Args:
        df: DataFrame with OHLC data
        pivot_highs: Series with pivot high prices
        pivot_lows: Series with pivot low prices
        impulse_idx: Index of impulse candle
        base_start_idx: Index where base starts

    Returns:
        tuple: (demand_bos, supply_bos) - booleans
    """
    impulse_high = df.iloc[impulse_idx]['high_bid']
    impulse_low = df.iloc[impulse_idx]['low_bid']
    impulse_close = df.iloc[impulse_idx]['close_bid']
    impulse_open = df.iloc[impulse_idx]['open_bid']

    # Find last pivot high before base
    last_pivot_high = None
    for idx in range(base_start_idx - 1, -1, -1):
        if not pd.isna(pivot_highs.iloc[idx]):
            last_pivot_high = pivot_highs.iloc[idx]
            break

    # Find last pivot low before base
    last_pivot_low = None
    for idx in range(base_start_idx - 1, -1, -1):
        if not pd.isna(pivot_lows.iloc[idx]):
            last_pivot_low = pivot_lows.iloc[idx]
            break

    # Check DEMAND BOS (bullish impulse breaks above last pivot high)
    demand_bos = False
    if last_pivot_high is not None and impulse_close > impulse_open:
        # Bullish candle - check if high breaks above pivot high
        if impulse_high > last_pivot_high:
            demand_bos = True

    # Check SUPPLY BOS (bearish impulse breaks below last pivot low)
    supply_bos = False
    if last_pivot_low is not None and impulse_close < impulse_open:
        # Bearish candle - check if low breaks below pivot low
        if impulse_low < last_pivot_low:
            supply_bos = True

    return demand_bos, supply_bos

