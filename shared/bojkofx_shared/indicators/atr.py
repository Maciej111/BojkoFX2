import pandas as pd
import numpy as np

def calculate_atr(df, period=14, high_col='high_bid', low_col='low_bid', close_col='close_bid'):
    """
    Calculate ATR using specified columns (default to Bid).
    df: DataFrame with high, low, close columns
    """
    high = df[high_col]
    low = df[low_col]
    close = df[close_col]

    # TR calculation
    # TR = max(high-low, abs(high-prev_close), abs(low-prev_close))
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR = Wilder's Smoothing
    atr = tr.ewm(alpha=1/period, adjust=False).mean()

    return atr

