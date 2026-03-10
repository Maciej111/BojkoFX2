"""
EMA (Exponential Moving Average) indicator.
"""
import pandas as pd
import numpy as np


def calculate_ema(series, period):
    """
    Calculate EMA for a pandas Series.

    Args:
        series: pandas Series (e.g., close prices)
        period: EMA period (e.g., 200)

    Returns:
        pandas Series with EMA values
    """
    return series.ewm(span=period, adjust=False).mean()


def calculate_ema_from_df(df, column='close_bid', period=200):
    """
    Calculate EMA from DataFrame.

    Args:
        df: DataFrame with OHLC data
        column: Column name to calculate EMA on
        period: EMA period

    Returns:
        pandas Series with EMA values, indexed same as df
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in DataFrame")

    return calculate_ema(df[column], period)

