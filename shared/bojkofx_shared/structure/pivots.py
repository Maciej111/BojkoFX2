"""
Pivot Detection Module
Wspólny moduł wykrywania pivotów dla różnych timeframe'ów
Z anti-lookahead - pivot jest potwierdzony dopiero po k świecach
"""
import pandas as pd
import numpy as np


def detect_pivots_confirmed(df, lookback=3, confirmation_bars=1):
    """
    Wykrywa swing pivoty z potwierdzeniem (anti-lookahead).

    Pivot High: high[i] jest najwyższe w oknie [i-lookback, i+lookback]
    Pivot Low: low[i] jest najniższe w oknie [i-lookback, i+lookback]

    JEDNAK pivot jest "confirmed" dopiero confirmation_bars świec później.

    Args:
        df: DataFrame z 'high_bid', 'low_bid'
        lookback: okno do sprawdzenia (k)
        confirmation_bars: ile świec później pivot jest potwierdzony

    Returns:
        pivot_highs: Series (bool lub float) - potwierdzony pivot high
        pivot_lows: Series (bool lub float) - potwierdzony pivot low
        pivot_highs_level: Series (float) - poziom pivot high
        pivot_lows_level: Series (float) - poziom pivot low
    """

    n = len(df)

    # Detect raw pivots (najpierw wykrywamy surowy pivot)
    raw_pivot_high = np.zeros(n, dtype=bool)
    raw_pivot_low = np.zeros(n, dtype=bool)

    pivot_high_level = np.full(n, np.nan)
    pivot_low_level = np.full(n, np.nan)

    for i in range(lookback, n - lookback):
        window_high = df['high_bid'].iloc[i-lookback:i+lookback+1]
        window_low = df['low_bid'].iloc[i-lookback:i+lookback+1]

        if df['high_bid'].iloc[i] == window_high.max():
            raw_pivot_high[i] = True
            pivot_high_level[i] = df['high_bid'].iloc[i]

        if df['low_bid'].iloc[i] == window_low.min():
            raw_pivot_low[i] = True
            pivot_low_level[i] = df['low_bid'].iloc[i]

    # Apply confirmation delay (anti-lookahead)
    # Pivot at bar i is confirmed at bar i + confirmation_bars
    confirmed_pivot_high = np.zeros(n, dtype=bool)
    confirmed_pivot_low = np.zeros(n, dtype=bool)

    confirmed_high_level = np.full(n, np.nan)
    confirmed_low_level = np.full(n, np.nan)

    for i in range(n):
        # Check if there was a pivot confirmation_bars ago
        if i >= confirmation_bars:
            if raw_pivot_high[i - confirmation_bars]:
                confirmed_pivot_high[i] = True
                confirmed_high_level[i] = pivot_high_level[i - confirmation_bars]

            if raw_pivot_low[i - confirmation_bars]:
                confirmed_pivot_low[i] = True
                confirmed_low_level[i] = pivot_low_level[i - confirmation_bars]

    return (
        pd.Series(confirmed_pivot_high, index=df.index),
        pd.Series(confirmed_pivot_low, index=df.index),
        pd.Series(confirmed_high_level, index=df.index),
        pd.Series(confirmed_low_level, index=df.index)
    )


def get_last_confirmed_pivot(df, pivot_series, pivot_level_series, current_idx):
    """
    Pobiera ostatni potwierdzony pivot przed current_idx.

    Args:
        df: DataFrame
        pivot_series: Series z bool (czy pivot)
        pivot_level_series: Series z poziomem pivota
        current_idx: obecny indeks

    Returns:
        (pivot_time, pivot_level) lub (None, None)
    """

    # Znajdź wszystkie potwierdzone pivoty przed current_idx
    current_pos = df.index.get_loc(current_idx)

    for i in range(current_pos - 1, -1, -1):
        if pivot_series.iloc[i]:
            return df.index[i], pivot_level_series.iloc[i]

    return None, None


def get_pivot_sequence(df, pivot_highs, pivot_lows, pivot_high_levels, pivot_low_levels,
                       current_idx, count=4):
    """
    Pobiera ostatnie N pivotów (highs i lows) przed current_idx.

    Returns:
        {
            'highs': [(time, level), ...],
            'lows': [(time, level), ...]
        }
    """

    current_pos = df.index.get_loc(current_idx)

    highs = []
    lows = []

    for i in range(current_pos - 1, -1, -1):
        if len(highs) < count and pivot_highs.iloc[i]:
            highs.append((df.index[i], pivot_high_levels.iloc[i]))

        if len(lows) < count and pivot_lows.iloc[i]:
            lows.append((df.index[i], pivot_low_levels.iloc[i]))

        if len(highs) >= count and len(lows) >= count:
            break

    return {
        'highs': highs,
        'lows': lows
    }

